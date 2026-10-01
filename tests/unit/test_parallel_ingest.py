"""Parallel pre-ingestion: same artifacts, same failures, no double parsing."""

import json
import multiprocessing
import os
import stat
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.utils import strip_ansi
from parallel_fixtures import (
    FixtureSource,
    FixtureSourceCache,
    RacingParser,
    RecordingParser,
    SlowParser,
    ingest_then_die_before_publish,
    write_pdf,
)
from typer.testing import CliRunner

import agent_native_content.evaluation.factorial_xl as factorial_xl
import agent_native_content.evaluation.xl_docbench as retrieval_xl
import agent_native_content.ingest.cache as cache_module
import agent_native_content.representation.xl_docbench as representation_xl
from agent_native_content.cli import app
from agent_native_content.ingest import IngestionCache, IngestionError
from agent_native_content.ingest.parallel import (
    ParallelIngestionError,
    warm_ingestion_cache,
)

IDS = ("doc_a", "doc_b", "doc_c", "doc_d")


def _pdfs(directory: Path, contents: dict[str, list[str]]) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    return {
        document_id: write_pdf(directory / f"{document_id}.pdf", lines)
        for document_id, lines in contents.items()
    }


def _default_pdfs(tmp_path: Path) -> dict[str, Path]:
    return _pdfs(
        tmp_path / "pdfs",
        {
            document_id: [f"{document_id} line {n}" for n in range(3)]
            for document_id in IDS
        },
    )


def _entries(root: Path) -> dict[str, dict[str, bytes]]:
    """Every cache entry, keyed by its path relative to the cache root."""
    entries = {}
    for metadata in sorted(root.glob("*/*/*/metadata.json")):
        entry = metadata.parent
        entries[str(entry.relative_to(root))] = {
            path.name: path.read_bytes() for path in sorted(entry.iterdir())
        }
    return entries


def _without_timestamp(metadata: bytes) -> dict:
    value = json.loads(metadata)
    value.pop("created_at")
    return value


def _sources(ids=IDS) -> list[FixtureSource]:
    return [
        FixtureSource(id=document_id, url=f"https://x/{document_id}")
        for document_id in ids
    ]


def _sequential(cache: IngestionCache, paths: dict[str, Path], ids=IDS) -> None:
    for document_id in ids:
        cache.ingest(paths[document_id])


# --- the pre-step itself ---------------------------------------------------


def test_one_worker_does_nothing(tmp_path: Path) -> None:
    paths = _default_pdfs(tmp_path)
    parser = RecordingParser(tmp_path / "log")
    source_cache = FixtureSourceCache(paths)

    summary = warm_ingestion_cache(
        _sources(),
        source_cache=source_cache,
        ingestion_cache=IngestionCache(tmp_path / "cache", parser),
        workers=1,
    )

    assert summary.parsed == ()
    assert source_cache.fetched == []
    assert parser.parses() == []
    assert not (tmp_path / "cache").exists()


def test_parallel_artifacts_are_byte_identical_to_sequential(tmp_path: Path) -> None:
    paths = _default_pdfs(tmp_path)
    sequential_root = tmp_path / "sequential"
    _sequential(
        IngestionCache(sequential_root, RecordingParser(tmp_path / "l1")), paths
    )
    expected = _entries(sequential_root)
    assert len(expected) == len(IDS)

    for workers in (2, 4):
        root = tmp_path / f"parallel-{workers}"
        parser = RecordingParser(tmp_path / f"l{workers}")
        summary = warm_ingestion_cache(
            _sources(),
            source_cache=FixtureSourceCache(paths),
            ingestion_cache=IngestionCache(root, parser),
            workers=workers,
        )
        actual = _entries(root)

        assert summary.parsed == IDS
        # Same entries at the same keys, and nothing else in them.
        assert actual.keys() == expected.keys()
        for key, files in expected.items():
            assert (
                actual[key].keys() == files.keys() == {"document.json", "metadata.json"}
            )
            assert actual[key]["document.json"] == files["document.json"]
            # metadata.json carries the parse time; every other byte agrees.
            assert _without_timestamp(actual[key]["metadata.json"]) == (
                _without_timestamp(files["metadata.json"])
            )
        # Parsed in worker processes, not here.
        assert {pid for _name, pid in parser.parses()}.isdisjoint({os.getpid()})


def test_a_document_is_never_parsed_twice(tmp_path: Path) -> None:
    paths = _default_pdfs(tmp_path)
    # doc_d has doc_a's exact bytes: one cache entry, so one parse.
    paths["doc_d"].write_bytes(paths["doc_a"].read_bytes())
    parser = RecordingParser(tmp_path / "log")
    cache = IngestionCache(tmp_path / "cache", parser)
    # doc_b is already cached before the pool starts.
    cache.ingest(paths["doc_b"])
    assert parser.parses() == [("doc_b.pdf", os.getpid())]

    summary = warm_ingestion_cache(
        _sources(),
        source_cache=FixtureSourceCache(paths),
        ingestion_cache=cache,
        workers=4,
    )

    parsed_names = [name for name, _pid in parser.parses()]
    assert sorted(parsed_names) == ["doc_a.pdf", "doc_b.pdf", "doc_c.pdf"]
    assert summary.parsed == ("doc_a", "doc_c")
    assert summary.already_cached == ("doc_b",)
    assert summary.duplicate_content == ("doc_d",)

    # A second pass schedules nothing at all.
    again = warm_ingestion_cache(
        _sources(),
        source_cache=FixtureSourceCache(paths),
        ingestion_cache=cache,
        workers=4,
    )
    assert again.parsed == ()
    assert len(parser.parses()) == 3


def test_every_failure_is_reported_after_the_others_finish(tmp_path: Path) -> None:
    paths = _default_pdfs(tmp_path)
    write_pdf(paths["doc_b"], ["FAIL"])
    parser = RecordingParser(tmp_path / "log")
    root = tmp_path / "cache"

    with pytest.raises(ParallelIngestionError) as raised:
        warm_ingestion_cache(
            _sources(),
            source_cache=FixtureSourceCache(paths, fail=frozenset({"doc_d"})),
            ingestion_cache=IngestionCache(root, parser),
            workers=3,
        )

    failures = raised.value.failures
    assert list(failures) == ["doc_b", "doc_d"]  # caller's order
    assert failures["doc_b"].startswith("ingest:")
    assert "fixture parse failure" in failures["doc_b"]
    assert failures["doc_d"].startswith("source:")
    assert "doc_b" in str(raised.value) and "doc_d" in str(raised.value)
    # The other documents still finished and are cached.
    assert len(_entries(root)) == 2
    assert sorted(name for name, _pid in parser.parses()) == [
        "doc_a.pdf",
        "doc_b.pdf",
        "doc_c.pdf",
    ]


def test_a_killed_worker_is_reported_not_ignored(tmp_path: Path) -> None:
    paths = _default_pdfs(tmp_path)
    write_pdf(paths["doc_c"], ["CRASH"])

    with pytest.raises(ParallelIngestionError) as raised:
        warm_ingestion_cache(
            _sources(),
            source_cache=FixtureSourceCache(paths),
            ingestion_cache=IngestionCache(
                tmp_path / "cache", RecordingParser(tmp_path / "log")
            ),
            workers=2,
        )

    assert "doc_c" in raised.value.failures


def test_the_scheduling_key_is_the_entry_ingest_uses(tmp_path: Path) -> None:
    paths = _default_pdfs(tmp_path)
    cache = IngestionCache(tmp_path / "cache", RecordingParser(tmp_path / "log"))
    entry = cache.entry_dir(paths["doc_a"])
    assert not cache.has_entry(entry)

    result = cache.ingest(paths["doc_a"])

    assert entry == result.artifact_dir
    assert cache.has_entry(entry)
    # Keyed by parser config too: another config is another entry.
    other = IngestionCache(tmp_path / "cache", _OtherConfigParser(tmp_path / "log"))
    assert other.entry_dir(paths["doc_a"]) != entry
    # ``ingest`` never leaves a half-entry (see the crash test below), so one
    # can only come from outside damage. It is still refused, not re-parsed
    # over: the pre-step counts it present and ``ingest`` then fails loudly.
    (entry / "metadata.json").unlink()
    assert cache.has_entry(entry)
    with pytest.raises(IngestionError, match="incomplete ingestion cache entry"):
        cache.ingest(paths["doc_a"])


class _OtherConfigParser(RecordingParser):
    @property
    def config(self) -> dict:
        return {"fixture": False}


# --- an entry is published whole or not at all ------------------------------


def _staging_dirs(root: Path) -> list[Path]:
    return sorted(root.glob("*/*/.partial-*"))


def test_a_kill_between_the_two_writes_leaves_no_entry(tmp_path: Path) -> None:
    paths = _default_pdfs(tmp_path)
    root = tmp_path / "cache"
    parser = RecordingParser(tmp_path / "log")
    cache = IngestionCache(root, parser)
    entry = cache.entry_dir(paths["doc_a"])

    child = multiprocessing.get_context("spawn").Process(
        target=ingest_then_die_before_publish,
        args=(str(root), str(tmp_path / "log"), str(paths["doc_a"])),
    )
    child.start()
    child.join(60)

    assert child.exitcode == 9
    # The kill came after document.json was written...
    (staged,) = _staging_dirs(root)
    assert (staged / "document.json").is_file()
    assert not (staged / "metadata.json").exists()
    # ...and none of it is an entry: nothing to refuse, so a rerun re-parses.
    assert not entry.exists()
    assert not cache.has_entry(entry)
    rerun = cache.ingest(paths["doc_a"])
    assert rerun.reused is False
    assert rerun.artifact_dir == entry
    assert [name for name, _pid in parser.parses()] == ["doc_a.pdf", "doc_a.pdf"]
    # The staging directory is never mistaken for an entry.
    assert len(staged.name) != 64 and staged.name.startswith(".partial-")


def test_a_failed_write_cleans_up_and_leaves_no_entry(
    tmp_path: Path, monkeypatch
) -> None:
    paths = _default_pdfs(tmp_path)
    root = tmp_path / "cache"
    cache = IngestionCache(root, RecordingParser(tmp_path / "log"))

    def fail(_path, _value):
        raise OSError("disk full")

    monkeypatch.setattr(cache_module, "_write_json_atomic", fail)
    with pytest.raises(OSError, match="disk full"):
        cache.ingest(paths["doc_a"])

    assert not cache.has_entry(cache.entry_dir(paths["doc_a"]))
    assert _staging_dirs(root) == []


def test_a_concurrent_writer_that_publishes_first_wins(tmp_path: Path) -> None:
    paths = _default_pdfs(tmp_path)
    root = tmp_path / "cache"
    cache = IngestionCache(root, RacingParser(tmp_path / "log", root))

    result = cache.ingest(paths["doc_a"])

    # The competitor's entry was complete when our rename lost; we verified
    # and returned it, and discarded our own staged copy.
    assert result.reused is True
    on_disk = json.loads((result.artifact_dir / "metadata.json").read_bytes())
    assert result.metadata.model_dump(mode="json") == on_disk
    assert _staging_dirs(root) == []
    assert len(_entries(root)) == 1


def test_published_entries_keep_their_bytes_fields_and_permissions(
    tmp_path: Path,
) -> None:
    paths = _default_pdfs(tmp_path)
    root = tmp_path / "cache"
    result = IngestionCache(root, RecordingParser(tmp_path / "log")).ingest(
        paths["doc_a"]
    )

    # document.json is exactly what the old in-place path wrote.
    reference = tmp_path / "reference.json"
    result.document.save_as_json(
        reference, indent=2, ensure_ascii=False, sort_keys=True
    )
    assert result.document_path.read_bytes() == reference.read_bytes()
    # Nothing in the metadata points into the staging directory.
    metadata = json.loads(result.metadata_path.read_bytes())
    assert metadata["document_file"] == "document.json"
    assert metadata["source_path"] == str(paths["doc_a"].resolve())
    assert ".partial-" not in json.dumps(metadata)
    # The entry directory has the mode a plain ``mkdir`` gives, as before.
    probe = result.artifact_dir.parent / "probe"
    probe.mkdir()
    assert stat.S_IMODE(result.artifact_dir.stat().st_mode) == stat.S_IMODE(
        probe.stat().st_mode
    )


# --- interruption ---------------------------------------------------------


def test_an_interrupt_cancels_the_queued_documents(tmp_path: Path) -> None:
    count = 20
    paths = _pdfs(
        tmp_path / "pdfs", {f"doc_{n:02d}": [f"doc {n}"] for n in range(count)}
    )
    sources = [FixtureSource(id=key, url=f"https://x/{key}") for key in paths]
    parser = SlowParser(tmp_path / "log", delay=0.2)

    def interrupt_on_first_parse(message: str) -> None:
        if message.endswith(": parsed"):
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        warm_ingestion_cache(
            sources,
            source_cache=FixtureSourceCache(paths),
            ingestion_cache=IngestionCache(tmp_path / "cache", parser),
            workers=2,
            progress=interrupt_on_first_parse,
        )
    # Let anything still running, or wrongly still queued, finish: all twenty
    # would take 2 s on two workers.
    time.sleep(3)

    parsed = len(parser.parses())
    # One finished, two running, the three already in the executor's call
    # queue (max_workers + 1, not recallable), and at most one or two more the
    # manager thread moves in as results land before the cancel: measured 6
    # or 7. Everything behind them is cancelled; without cancellation all
    # twenty run.
    assert parsed <= 8
    assert parsed < count


def test_workers_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        warm_ingestion_cache(
            [],
            source_cache=FixtureSourceCache({}),
            ingestion_cache=IngestionCache(tmp_path, RecordingParser(tmp_path)),
            workers=0,
        )


# --- the entry points -------------------------------------------------------


ENTRY_POINTS = {
    "retrieval": (retrieval_xl, "run_xl_retrieval", "run_retrieval_benchmark"),
    "factorial": (factorial_xl, "run_xl_factorial", "run_factorial_benchmark"),
    "representation": (
        representation_xl,
        "run_xl_gold_representation",
        "run_gold_representation_benchmark",
    ),
}


def _harness(monkeypatch, tmp_path: Path, name: str, paths: dict[str, Path]):
    module, _entry, runner_name = ENTRY_POINTS[name]
    events: list = []
    parser = RecordingParser(tmp_path / "log", events)
    source_cache = FixtureSourceCache(paths, events=events)
    question = SimpleNamespace(
        id="q1",
        document_ids=IDS,
        gold_evidence_pages={document_id: (1,) for document_id in IDS},
    )
    sources = {
        document_id: source for document_id, source in zip(IDS, _sources(), strict=True)
    }
    dataset = SimpleNamespace(
        iter_subset=lambda _subset: iter([question]),
        get_document=sources.__getitem__,
    )
    captured: dict = {}

    def project(document, metadata, *, source_uri, tokenizer):
        events.append(("project", metadata.source_name))
        return document

    def run(corpus, **kwargs):
        captured["corpus"] = corpus
        return "RUN"

    monkeypatch.setattr(module, "download_release", lambda _dir: None)
    monkeypatch.setattr(module, "XLDocBenchDataset", lambda _dir: dataset)
    monkeypatch.setattr(
        module, "load_subset", lambda _path: SimpleNamespace(name="fixture")
    )
    monkeypatch.setattr(module, "SourceDocumentCache", lambda _dir: source_cache)
    monkeypatch.setattr(module, "DoclingParser", lambda artifacts_path=None: parser)
    monkeypatch.setattr(module, "project_document", project)
    monkeypatch.setattr(module, "TiktokenTokenCounter", lambda _name: object())
    monkeypatch.setattr(module, runner_name, run)
    return events, parser, captured


def _call(name: str, tmp_path: Path, workers: int):
    module, entry, _runner = ENTRY_POINTS[name]
    subset = tmp_path / "subset.json"
    subset.write_text("{}")
    kwargs = dict(
        data_dir=tmp_path / "data",
        subset_file=subset,
        source_cache_dir=tmp_path / "sources",
        ingest_cache_dir=tmp_path / "cache",
        artifacts_root=tmp_path / "artifacts",
        parse_workers=workers,
    )
    if name == "retrieval":
        kwargs["config"] = SimpleNamespace(
            retrieval=SimpleNamespace(tokenizer_name="t"), systems=()
        )
    elif name == "factorial":
        kwargs["config"] = SimpleNamespace(
            retrieval=SimpleNamespace(tokenizer_name="t")
        )
        kwargs["retrieval_corpus_subset_file"] = subset
    else:
        kwargs["config"] = SimpleNamespace(tokenizer_name="t", conditions=())
        kwargs["provider"] = object()
    return getattr(module, entry)(**kwargs)


@pytest.mark.parametrize("name", list(ENTRY_POINTS))
def test_one_worker_keeps_the_sequential_loop_exactly(
    monkeypatch, tmp_path: Path, name: str
) -> None:
    paths = _default_pdfs(tmp_path)
    events, parser, captured = _harness(monkeypatch, tmp_path, name, paths)
    called = []
    module = ENTRY_POINTS[name][0]
    monkeypatch.setattr(
        module, "warm_ingestion_cache", lambda *a, **k: called.append(1)
    )

    assert _call(name, tmp_path, workers=1) == "RUN"

    assert called == []
    # Fetch, parse, project, one document at a time, in document order, all in
    # this process -- the loop as it was.
    assert events == [
        event
        for document_id in IDS
        for event in (
            ("fetch", document_id),
            ("parse", f"{document_id}.pdf"),
            ("project", f"{document_id}.pdf"),
        )
    ]
    assert {pid for _name, pid in parser.parses()} == {os.getpid()}
    assert list(captured["corpus"].documents) == list(IDS)


@pytest.mark.parametrize("name", list(ENTRY_POINTS))
def test_many_workers_parse_first_then_the_loop_reuses_the_cache(
    monkeypatch, tmp_path: Path, name: str
) -> None:
    paths = _default_pdfs(tmp_path)
    events, parser, captured = _harness(monkeypatch, tmp_path, name, paths)

    assert _call(name, tmp_path, workers=3) == "RUN"

    # Every parse happened once, in a worker; the loop parsed nothing.
    parses = parser.parses()
    assert sorted(name for name, _pid in parses) == [f"{d}.pdf" for d in IDS]
    assert os.getpid() not in {pid for _name, pid in parses}
    assert [event for event in events if event[0] == "parse"] == []
    # Pre-step fetches every source, then the unchanged loop runs in order.
    assert events == [("fetch", d) for d in IDS] + [
        event
        for document_id in IDS
        for event in (("fetch", document_id), ("project", f"{document_id}.pdf"))
    ]
    assert list(captured["corpus"].documents) == list(IDS)


@pytest.mark.parametrize("workers", [0, -2])
@pytest.mark.parametrize("name", list(ENTRY_POINTS))
def test_a_non_positive_worker_count_is_refused_before_anything_runs(
    monkeypatch, tmp_path: Path, name: str, workers: int
) -> None:
    """Not silently sequential: the runners only branch on ``> 1`` below."""
    paths = _default_pdfs(tmp_path)
    events, parser, captured = _harness(monkeypatch, tmp_path, name, paths)
    downloads: list = []
    monkeypatch.setattr(ENTRY_POINTS[name][0], "download_release", downloads.append)

    with pytest.raises(ValueError, match=f"at least 1, got {workers}"):
        _call(name, tmp_path, workers=workers)

    assert downloads == []
    assert events == []
    assert parser.parses() == []
    assert captured == {}
    assert not (tmp_path / "cache").exists()
    assert not (tmp_path / "artifacts").exists()


@pytest.mark.parametrize("name", list(ENTRY_POINTS))
def test_a_failed_document_stops_the_run_before_it_starts(
    monkeypatch, tmp_path: Path, name: str
) -> None:
    paths = _default_pdfs(tmp_path)
    write_pdf(paths["doc_c"], ["FAIL"])
    events, _parser, captured = _harness(monkeypatch, tmp_path, name, paths)

    with pytest.raises(ParallelIngestionError) as raised:
        _call(name, tmp_path, workers=3)

    assert list(raised.value.failures) == ["doc_c"]
    assert "corpus" not in captured
    assert not any(event[0] == "project" for event in events)


# --- the CLI ---------------------------------------------------------------


CLI_TARGETS = {
    "eval-retrieval": "agent_native_content.evaluation.xl_docbench.run_xl_retrieval",
    "eval-factorial": "agent_native_content.evaluation.factorial_xl.run_xl_factorial",
    "eval-representation": (
        "agent_native_content.representation.run_xl_gold_representation"
    ),
}


def _cli_workers(monkeypatch, tmp_path: Path, command: str, options: list[str]):
    result, captured = _invoke_cli(monkeypatch, tmp_path, command, options)
    assert result.exit_code == 0, result.output
    return captured["parse_workers"]


def _invoke_cli(monkeypatch, tmp_path: Path, command: str, options: list[str]):
    """Run one command with its run target stubbed: no dataset, no network."""
    captured: dict = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            path=tmp_path / "run",
            manifest=SimpleNamespace(run_id="run"),
            summary=SimpleNamespace(run_id="run"),
        )

    monkeypatch.setattr(CLI_TARGETS[command], fake)
    required: list[str] = []
    if command == "eval-representation":
        _stub_representation_preflight(monkeypatch)
        required = [
            "--model",
            "fixture-model",
            "--input-usd-per-million",
            "0",
            "--cached-input-usd-per-million",
            "0",
            "--output-usd-per-million",
            "0",
            "--max-calls",
            "1",
        ]
    result = CliRunner().invoke(
        app,
        [command, *required, *options, "--run-id", "run"],
        color=False,
    )
    return result, captured


def _stub_representation_preflight(monkeypatch) -> None:
    question = SimpleNamespace(gold_evidence=())
    monkeypatch.setattr("agent_native_content.cli.download_release", lambda _dir: None)
    monkeypatch.setattr(
        "agent_native_content.cli.XLDocBenchDataset",
        lambda _dir: SimpleNamespace(iter_subset=lambda _subset: iter([question])),
    )
    monkeypatch.setattr("agent_native_content.cli.load_subset", lambda _path: object())
    monkeypatch.setattr(
        "agent_native_content.generation.OpenAIAnswerProvider",
        lambda **_kwargs: object(),
    )


@pytest.mark.parametrize("command", list(CLI_TARGETS))
def test_parse_workers_reaches_every_ingesting_command(
    monkeypatch, tmp_path: Path, command: str
) -> None:
    assert _cli_workers(monkeypatch, tmp_path, command, []) == 1
    assert _cli_workers(monkeypatch, tmp_path, command, ["--parse-workers", "4"]) == 4


@pytest.mark.parametrize("command", list(CLI_TARGETS))
def test_parse_workers_rejects_zero(monkeypatch, tmp_path: Path, command: str) -> None:
    # Every other required option is supplied and the run target is stubbed,
    # so the only thing that can stop this command is the option's bound.
    result, captured = _invoke_cli(
        monkeypatch, tmp_path, command, ["--parse-workers", "0"]
    )

    assert result.exit_code == 2, result.output
    output = strip_ansi(result.output)
    assert "--parse-workers" in output
    assert "0 is not in the range x>=1" in output
    assert captured == {}
