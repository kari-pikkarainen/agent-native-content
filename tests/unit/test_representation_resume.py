"""Checkpointed, resumable representation runs.

Every provider here is an in-memory fake; no test makes a network call.
"""

import fcntl
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_evaluation import _corpus
from test_ir import FixtureTokenCounter
from test_representation import JudgedRepresentationProvider, _config

from contextbench.evaluation import EvaluationCorpus
from contextbench.representation import (
    RepresentationCondition,
    RepresentationError,
    representation_call_ceiling,
    run_gold_representation_benchmark,
)
from contextbench.representation.checkpoint import (
    CELLS_FILE,
    HEADER_FILE,
    LOCK_FILE,
    SERVED_MODEL_FILE,
    checkpoint_path,
)

RUN_ID = "representation-resume"
CONDITIONS = (
    RepresentationCondition.QUESTION_ONLY,
    RepresentationCondition.RAW,
    RepresentationCondition.IR,
)
QUESTION_IDS = ("question-1", "question-2", "question-3")
# 3 questions x 3 conditions.
CELL_COUNT = 9
# Fields that describe one call rather than the experiment: they legitimately
# differ between any two runs, interrupted or not.
PER_CALL_RECORD_FIELDS = {
    "latency_ms",
    "answer_latency_ms",
    "judge_latency_ms",
    "response_id",
}
TIMING_SUMMARY_FIELDS = {
    "enrichment_prepare_ms",
    "amortized_enrichment_ms_per_question",
}
TIMING_ROW_FIELDS = {
    "mean_latency_ms",
    "mean_answer_latency_ms",
    "mean_judge_latency_ms",
}
RUN_SPECIFIC_MANIFEST_FIELDS = {
    "enrichment_prepare_ms",
    "enrichment_document_ms",
    "resumed",
    "checkpoint_cells_loaded",
    "checkpoint_partial_lines_discarded",
}


class ProviderDown(RuntimeError):
    """What the fake provider raises once it is told to fail."""


class FlakyProvider(JudgedRepresentationProvider):
    """Judged fixture provider that raises from a given call onward.

    ``served_model`` replaces the provider-reported model ID from call
    ``served_from_call`` onward; ``judge_model`` replaces it on judge calls.
    """

    def __init__(
        self,
        *,
        fail_from_call: int | None = None,
        served_model: str | None = None,
        served_from_call: int = 1,
        judge_model: str | None = None,
    ) -> None:
        super().__init__()
        self.fail_from_call = fail_from_call
        self.served_model = served_model
        self.served_from_call = served_from_call
        self.judge_model = judge_model
        self.attempts = 0

    def generate(self, request, *, config):
        self.attempts += 1
        if self.fail_from_call is not None and self.attempts >= self.fail_from_call:
            raise ProviderDown("connection reset by local server")
        response = super().generate(request, config=config)
        if self.judge_model is not None and ":" in request.system:
            return response.model_copy(update={"model_id": self.judge_model})
        if self.served_model is not None and self.attempts >= self.served_from_call:
            return response.model_copy(update={"model_id": self.served_model})
        return response


def _multi_corpus(tmp_path: Path) -> EvaluationCorpus:
    base = _corpus(tmp_path)
    question = base.questions[0]
    return EvaluationCorpus(
        questions=tuple(
            question.model_copy(update={"id": question_id})
            for question_id in QUESTION_IDS
        ),
        documents=base.documents,
        source_documents=base.source_documents,
    )


def _resume_config(**overrides):
    return _config(
        **{
            "conditions": CONDITIONS,
            "answer_equivalence_judge": True,
            "citation_entailment_judge": True,
            **overrides,
        }
    )


def _run(
    root: Path,
    provider,
    *,
    run_id: str | None = RUN_ID,
    config=None,
    git_commit: str = "c" * 40,
    subset_sha256: str = "1" * 64,
    subset_path: str | None = "/subsets/fixture.json",
    clock_day: int = 20,
    git_dirty: bool = False,
):
    return run_gold_representation_benchmark(
        _multi_corpus(root),
        config=config or _resume_config(),
        provider=provider,
        artifacts_root=root / "artifacts",
        dataset="fixture",
        dataset_version="v1",
        dataset_revision="revision-1",
        subset_name="fixture-three",
        subset_sha256=subset_sha256,
        subset_path=subset_path,
        run_id=run_id,
        tokenizer=FixtureTokenCounter(),
        git_commit=git_commit,
        git_dirty=git_dirty,
        clock=lambda: datetime(2026, 9, clock_day, tzinfo=UTC),
    )


def _checkpoint(root: Path, run_id: str = RUN_ID) -> Path:
    return checkpoint_path(root / "artifacts" / "representation-runs", run_id)


def _cell_lines(root: Path, run_id: str = RUN_ID) -> list[bytes]:
    return (_checkpoint(root, run_id) / CELLS_FILE).read_bytes().splitlines(
        keepends=True
    )


def _interrupt(root: Path, *, fail_from_call: int = 8, **kwargs) -> str:
    """Run until the provider fails; return the abort message."""
    with pytest.raises(RepresentationError) as caught:
        _run(root, FlakyProvider(fail_from_call=fail_from_call), **kwargs)
    return str(caught.value)


def _cell_of(request) -> tuple[str, str]:
    return request.question_id, request.system.split(":", 1)[0]


def _records(run_path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (run_path / "representation.jsonl").read_text().splitlines()
    ]


def _without(value: dict, fields: set[str]) -> dict:
    return {key: item for key, item in value.items() if key not in fields}


def test_interrupted_then_resumed_run_publishes_the_uninterrupted_result(
    tmp_path: Path,
) -> None:
    baseline = _run(tmp_path / "uninterrupted", FlakyProvider())
    interrupted_root = tmp_path / "interrupted"

    # Calls 1-7 complete the first cells; call 8 fails mid-cell, after the
    # cell's answer call, so that cell's paid answer is not kept.
    message = _interrupt(interrupted_root, fail_from_call=8)
    assert "connection reset by local server" in message
    assert f"--run-id {RUN_ID} to resume" in message
    assert not (interrupted_root / "artifacts/representation-runs" / RUN_ID).exists()
    completed_lines = _cell_lines(interrupted_root)
    completed = [
        (entry["question_id"], entry["condition"])
        for entry in map(json.loads, completed_lines)
    ]
    assert 0 < len(completed) < CELL_COUNT
    assert f"{len(completed)} of {CELL_COUNT} cells are checkpointed" in message

    resumed_provider = FlakyProvider()
    resumed = _run(interrupted_root, resumed_provider)

    # Only unfinished cells were called, in the original planned order.
    called_cells = list(dict.fromkeys(map(_cell_of, resumed_provider.requests)))
    planned = [
        (question_id, condition.value)
        for question_id in QUESTION_IDS
        for condition in CONDITIONS
    ]
    assert called_cells == [cell for cell in planned if cell not in completed]
    assert not _checkpoint(interrupted_root).exists()

    assert (resumed.path / "contexts.jsonl").read_bytes() == (
        baseline.path / "contexts.jsonl"
    ).read_bytes()
    assert [
        _without(record, PER_CALL_RECORD_FIELDS) for record in _records(resumed.path)
    ] == [
        _without(record, PER_CALL_RECORD_FIELDS)
        for record in _records(baseline.path)
    ]

    def stable_summary(run_path: Path) -> dict:
        summary = json.loads((run_path / "summary.json").read_text())
        summary["rows"] = [
            _without(row, TIMING_ROW_FIELDS) for row in summary["rows"]
        ]
        return _without(summary, TIMING_SUMMARY_FIELDS)

    assert stable_summary(resumed.path) == stable_summary(baseline.path)
    resumed_manifest = json.loads((resumed.path / "manifest.json").read_text())
    baseline_manifest = json.loads((baseline.path / "manifest.json").read_text())
    assert _without(resumed_manifest, RUN_SPECIFIC_MANIFEST_FIELDS) == _without(
        baseline_manifest, RUN_SPECIFIC_MANIFEST_FIELDS
    )
    assert baseline_manifest["resumed"] is False
    assert baseline_manifest["checkpoint_cells_loaded"] == 0
    assert resumed_manifest["resumed"] is True
    assert resumed_manifest["checkpoint_cells_loaded"] == len(completed)
    assert resumed_manifest["checkpoint_partial_lines_discarded"] == 0
    assert {path.name for path in resumed.path.iterdir()} == {
        path.name for path in baseline.path.iterdir()
    }


def test_checkpoint_lines_are_complete_records_before_the_failure(
    tmp_path: Path,
) -> None:
    _interrupt(tmp_path, fail_from_call=8)
    lines = _cell_lines(tmp_path)
    assert all(line.endswith(b"\n") for line in lines)
    header = json.loads((_checkpoint(tmp_path) / HEADER_FILE).read_text())
    assert header["run_id"] == RUN_ID
    assert header["cells"][0] == ["question-1", "question_only"]
    assert len(header["cells"]) == CELL_COUNT
    assert header["subset_path"] == "/subsets/fixture.json"
    assert header["provider_timeout_seconds"] == 600.0
    assert set(header["prompt_hashes"]) == {
        "prompt_sha256",
        "answer_equivalence_prompt_sha256",
        "citation_entailment_prompt_sha256",
    }


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"config": _resume_config(max_output_tokens=512)}, "config.max_output_tokens"),
        ({"config": _resume_config(temperature=0.0)}, "config.temperature"),
        ({"config": _resume_config(seed=7)}, "config.seed"),
        (
            {"config": _resume_config(provider_timeout_seconds=2400)},
            "provider_timeout_seconds",
        ),
        ({"git_commit": "e" * 40}, "git_commit"),
        ({"subset_sha256": "2" * 64}, "subset_sha256"),
        ({"subset_path": "/subsets/other.json"}, "subset_path"),
    ],
)
def test_resume_refuses_any_changed_input(
    tmp_path: Path, change: dict, field: str
) -> None:
    _interrupt(tmp_path)
    before = (_checkpoint(tmp_path) / CELLS_FILE).read_bytes()
    provider = FlakyProvider()

    with pytest.raises(RepresentationError, match="does not match") as caught:
        _run(tmp_path, provider, **change)

    assert field in str(caught.value)
    # Only names are reported, never the recorded or new values.
    assert "e" * 40 not in str(caught.value)
    assert "2" * 64 not in str(caught.value)
    assert "other.json" not in str(caught.value)
    assert provider.attempts == 0
    assert (_checkpoint(tmp_path) / CELLS_FILE).read_bytes() == before


def test_resume_refuses_a_changed_prompt_template(
    tmp_path: Path, monkeypatch
) -> None:
    _interrupt(tmp_path)
    monkeypatch.setattr(
        "contextbench.representation.runner.ANSWER_PROMPT_INSTRUCTIONS",
        "A different answer prompt.",
    )
    provider = FlakyProvider()
    with pytest.raises(RepresentationError, match="prompt_hashes.prompt_sha256"):
        _run(tmp_path, provider)
    assert provider.attempts == 0


def test_resume_refuses_a_cell_whose_prompt_renders_differently(
    tmp_path: Path,
) -> None:
    _interrupt(tmp_path)
    cells = _checkpoint(tmp_path) / CELLS_FILE
    lines = _cell_lines(tmp_path)
    entry = json.loads(lines[0])
    entry["prompt_sha256"] = "0" * 64
    cells.write_bytes(json.dumps(entry).encode() + b"\n" + b"".join(lines[1:]))
    with pytest.raises(RepresentationError, match="line 1 .*no longer renders"):
        _run(tmp_path, FlakyProvider())


def test_an_unterminated_last_line_is_discarded_and_its_cell_rerun(
    tmp_path: Path,
) -> None:
    _interrupt(tmp_path)
    cells = _checkpoint(tmp_path) / CELLS_FILE
    lines = _cell_lines(tmp_path)
    # A crash after writing a whole record but before its newline: the line
    # parses, but it was never committed, so it must not be trusted.
    last = json.loads(lines[-1])
    cells.write_bytes(b"".join(lines[:-1]) + lines[-1].rstrip(b"\n"))

    # Resume once more and fail at once: the fragment is cut from the file.
    with pytest.raises(RepresentationError, match="to resume"):
        _run(tmp_path, FlakyProvider(fail_from_call=1))
    assert cells.read_bytes() == b"".join(lines[:-1])

    cells.write_bytes(b"".join(lines[:-1]) + b'{"cell_index": 4, "quest')
    provider = FlakyProvider()
    result = _run(tmp_path, provider)
    manifest = json.loads((result.path / "manifest.json").read_text())
    assert manifest["checkpoint_cells_loaded"] == len(lines) - 1
    assert manifest["checkpoint_partial_lines_discarded"] == 1
    called = list(dict.fromkeys(map(_cell_of, provider.requests)))
    assert called[0] == (last["question_id"], last["condition"])
    assert len(result.records) == CELL_COUNT


@pytest.mark.parametrize(
    ("corrupt", "reason"),
    [
        (lambda lines: [lines[0], lines[0], *lines[1:]], "line 2 repeats cell 0"),
        (lambda lines: [b"not json\n", *lines[1:]], "line 1 is not valid JSON"),
        (lambda lines: [b"\n", *lines], "line 1 is not valid JSON"),
        (
            lambda lines: [
                _edit(lines[0], question_id="question-foreign"),
                *lines[1:],
            ],
            "line 1 names a cell outside this run",
        ),
        (
            lambda lines: [_edit(lines[0], cell_index=CELL_COUNT), *lines[1:]],
            "line 1 names a cell outside this run",
        ),
        (
            lambda lines: [_edit(lines[0], cell_index=True), *lines[1:]],
            "line 1 names a cell outside this run",
        ),
        (
            lambda lines: [
                _edit_record(lines[0], question_id="question-2"),
                *lines[1:],
            ],
            "line 1 holds a record for another cell",
        ),
        (
            lambda lines: [_edit_record(lines[0], accuracy=2.0), *lines[1:]],
            "line 1 holds a record that does not validate",
        ),
        (
            lambda lines: [_edit(lines[0], extra=1), *lines[1:]],
            "line 1 is not a checkpointed cell",
        ),
    ],
)
def test_resume_refuses_a_corrupt_committed_checkpoint(
    tmp_path: Path, corrupt, reason: str
) -> None:
    _interrupt(tmp_path)
    cells = _checkpoint(tmp_path) / CELLS_FILE
    cells.write_bytes(b"".join(corrupt(_cell_lines(tmp_path))))
    provider = FlakyProvider()
    with pytest.raises(RepresentationError, match=reason):
        _run(tmp_path, provider)
    assert provider.attempts == 0


def _edit(line: bytes, **changes) -> bytes:
    return json.dumps({**json.loads(line), **changes}).encode() + b"\n"


def _edit_record(line: bytes, **changes) -> bytes:
    entry = json.loads(line)
    entry["record"].update(changes)
    return json.dumps(entry).encode() + b"\n"


def test_resume_requires_an_explicit_run_id(tmp_path: Path) -> None:
    message = _interrupt(tmp_path, run_id=None)
    runs_dir = tmp_path / "artifacts" / "representation-runs"
    (partial,) = runs_dir.iterdir()
    auto_id = partial.name.removeprefix(".partial-")
    assert auto_id.startswith("representation-20260920T000000Z-")
    assert f"--run-id {auto_id} to resume" in message

    # The same auto-generated ID is refused without --run-id, before any call.
    provider = FlakyProvider()
    with pytest.raises(RepresentationError, match="explicitly with --run-id"):
        _run(tmp_path, provider, run_id=None)
    assert provider.attempts == 0

    result = _run(tmp_path, FlakyProvider(), run_id=auto_id)
    manifest = json.loads((result.path / "manifest.json").read_text())
    assert manifest["resumed"] is True
    # The resumed run keeps the time the run was first started.
    assert manifest["created_at"] == "2026-09-20T00:00:00+00:00"


def test_resumed_run_keeps_the_original_start_time(tmp_path: Path) -> None:
    _interrupt(tmp_path, clock_day=20)
    result = _run(tmp_path, FlakyProvider(), clock_day=21)
    manifest = json.loads((result.path / "manifest.json").read_text())
    assert manifest["created_at"] == "2026-09-20T00:00:00+00:00"


def test_a_published_run_is_never_resumed(tmp_path: Path) -> None:
    _run(tmp_path, FlakyProvider())
    provider = FlakyProvider()
    with pytest.raises(RepresentationError, match="completed run already exists"):
        _run(tmp_path, provider)
    assert provider.attempts == 0


def test_a_locked_checkpoint_is_refused(tmp_path: Path) -> None:
    _interrupt(tmp_path)
    descriptor = os.open(_checkpoint(tmp_path) / LOCK_FILE, os.O_RDWR)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        provider = FlakyProvider()
        with pytest.raises(RepresentationError, match="in use by another process"):
            _run(tmp_path, provider)
        assert provider.attempts == 0
    finally:
        os.close(descriptor)
    assert _run(tmp_path, FlakyProvider()).records


def test_resuming_never_calls_more_than_the_planned_ceiling(tmp_path: Path) -> None:
    ceiling = representation_call_ceiling(len(QUESTION_IDS), _resume_config())
    first = FlakyProvider(fail_from_call=8)
    with pytest.raises(RepresentationError):
        _run(tmp_path, first)
    loaded = len(_cell_lines(tmp_path))
    second = FlakyProvider()
    result = _run(tmp_path, second)
    # Completed cells are never called again: the resumed process makes at
    # most the calls of the cells it still had to run.
    assert len(second.requests) == sum(
        record.calls for record in result.records[loaded:]
    )
    assert sum(record.calls for record in result.records) <= ceiling
    # The run failed in planned order, so the loaded cells are a prefix.
    # Across both processes only the interrupted cell's successful calls
    # (at most answer plus one judge) are made twice.
    first_successful = first.attempts - 1
    repeated = first_successful - sum(
        record.calls for record in result.records[:loaded]
    )
    assert 0 < repeated <= 2
    assert first_successful + len(second.requests) == (
        sum(record.calls for record in result.records) + repeated
    )


def test_resume_refuses_a_different_served_model_before_writing(
    tmp_path: Path,
) -> None:
    _interrupt(tmp_path)
    partial = _checkpoint(tmp_path)
    cells_before = (partial / CELLS_FILE).read_bytes()
    pinned = json.loads((partial / SERVED_MODEL_FILE).read_text())
    assert pinned == {"served_model_id": "fixture-model"}

    # The local server restarted between nights with another model loaded.
    swapped = FlakyProvider(served_model="gemma-other-quant")
    with pytest.raises(RepresentationError) as caught:
        _run(tmp_path, swapped)
    assert "'gemma-other-quant'" in str(caught.value)
    assert "'fixture-model'" in str(caught.value)
    assert "rerun the same command to resume" in str(caught.value)
    assert (partial / CELLS_FILE).read_bytes() == cells_before
    assert json.loads((partial / SERVED_MODEL_FILE).read_text()) == pinned

    result = _run(tmp_path, FlakyProvider())
    manifest = json.loads((result.path / "manifest.json").read_text())
    assert manifest["served_model_ids"] == ["fixture-model"]


def test_a_served_model_change_mid_run_is_refused(tmp_path: Path) -> None:
    # Calls 1-5 complete two cells; from call 6 the server reports another model.
    provider = FlakyProvider(served_model="swapped-model", served_from_call=6)
    with pytest.raises(RepresentationError, match="'swapped-model'"):
        _run(tmp_path, provider)
    lines = _cell_lines(tmp_path)
    assert len(lines) == 2
    assert all(
        json.loads(line)["record"]["model_id"] == "fixture-model" for line in lines
    )


def test_answer_and_judge_from_different_served_models_are_refused(
    tmp_path: Path,
) -> None:
    provider = FlakyProvider(judge_model="judge-model")
    with pytest.raises(RepresentationError, match="different served models"):
        _run(tmp_path, provider)
    assert _cell_lines(tmp_path) == []
    assert not (_checkpoint(tmp_path) / SERVED_MODEL_FILE).exists()


def test_records_keep_every_calls_served_model(tmp_path: Path) -> None:
    result = _run(tmp_path, FlakyProvider())
    by_cell = {(r.question_id, r.condition): r for r in result.records}
    raw = by_cell[("question-1", RepresentationCondition.RAW)]
    assert raw.model_id == "fixture-model"
    assert raw.answer_judge_model_id == "fixture-model"
    assert raw.citation_judge_model_id == "fixture-model"
    question_only = by_cell[("question-1", RepresentationCondition.QUESTION_ONLY)]
    # No citation judge call is made for a cell without evidence.
    assert question_only.citation_judge_model_id is None
    manifest = json.loads((result.path / "manifest.json").read_text())
    assert manifest["served_model_ids"] == ["fixture-model"]


def test_resume_refuses_loaded_cells_from_another_served_model(
    tmp_path: Path,
) -> None:
    _interrupt(tmp_path)
    cells = _checkpoint(tmp_path) / CELLS_FILE
    lines = _cell_lines(tmp_path)
    cells.write_bytes(
        _edit_record(lines[0], answer_judge_model_id="other") + b"".join(lines[1:])
    )
    with pytest.raises(RepresentationError, match="different served models"):
        _run(tmp_path, FlakyProvider())
    cells.write_bytes(
        _edit_record(lines[0], model_id="other", answer_judge_model_id="other")
        + b"".join(lines[1:])
    )
    with pytest.raises(RepresentationError, match="cell 0 was answered by another"):
        _run(tmp_path, FlakyProvider())


def test_resume_refuses_cells_without_a_pinned_served_model(
    tmp_path: Path,
) -> None:
    _interrupt(tmp_path)
    (_checkpoint(tmp_path) / SERVED_MODEL_FILE).unlink()
    provider = FlakyProvider()
    with pytest.raises(RepresentationError, match="no pinned served model"):
        _run(tmp_path, provider)
    assert provider.attempts == 0


def test_a_dirty_run_is_never_resumed(tmp_path: Path) -> None:
    message = _interrupt(tmp_path, git_dirty=True)
    assert "cannot be resumed" in message
    assert "--run-id" not in message
    provider = FlakyProvider()
    with pytest.raises(RepresentationError, match="modified worktree"):
        _run(tmp_path, provider, git_dirty=True)
    assert provider.attempts == 0


def test_a_run_published_by_a_racing_process_is_not_run_again(
    tmp_path: Path, monkeypatch
) -> None:
    from contextbench.representation import runner

    real_open = runner.RepresentationCheckpoint.open
    final_path = tmp_path / "artifacts" / "representation-runs" / RUN_ID

    def open_after_a_race(*args, **kwargs):
        # Another process published the run after this one's first check.
        checkpoint = real_open(*args, **kwargs)
        final_path.mkdir(parents=True)
        (final_path / "manifest.json").write_text("{}")
        return checkpoint

    monkeypatch.setattr(runner.RepresentationCheckpoint, "open", open_after_a_race)
    provider = FlakyProvider()
    with pytest.raises(RepresentationError, match="completed run already exists"):
        _run(tmp_path, provider)
    assert provider.attempts == 0
    # The empty checkpoint this process created is not left behind.
    assert not _checkpoint(tmp_path).exists()
