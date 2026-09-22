"""Tests for the command-line entry point."""

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from contextbench import __version__
from contextbench.cli import app
from contextbench.evaluation import BenchmarkSystem

runner = CliRunner()
FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "context-compilation benchmark" in result.stdout


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_dataset_inspect_prints_normalized_question() -> None:
    result = runner.invoke(
        app,
        [
            "dataset",
            "inspect",
            "xl-docbench",
            "adubench_single_fixture_002",
            "--data-dir",
            str(FIXTURES / "xl_docbench"),
            "--no-verify-release",
        ],
    )

    assert result.exit_code == 0
    value = json.loads(result.stdout)
    assert value == {
        "answerable": True,
        "gold_answer": "alpha",
        "gold_evidence_pages": {"doc_fixture_001": [3]},
        "question": "What is alpha?",
        "question_id": "adubench_single_fixture_002",
        "source_document_ids": ["doc_fixture_001"],
    }


def test_dataset_list_preserves_subset_order() -> None:
    result = runner.invoke(
        app,
        [
            "dataset",
            "list",
            "xl-docbench",
            "--data-dir",
            str(FIXTURES / "xl_docbench"),
            "--subset-file",
            str(FIXTURES / "xl_fixture_subset.json"),
            "--no-verify-release",
        ],
    )

    assert result.exit_code == 0
    question_ids = [
        json.loads(line)["question_id"] for line in result.stdout.splitlines()
    ]
    assert question_ids == [
        "adubench_single_fixture_002",
        "adubench_cross_fixture_001",
    ]


def test_dataset_error_is_reported_without_traceback(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "dataset",
            "inspect",
            "xl-docbench",
            "missing",
            "--data-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 1
    assert "release file not found" in result.output
    assert "Traceback" not in result.output


def test_eval_retrieval_runs_all_default_budgets_and_prints_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    captured = {}

    def fake_run_xl_retrieval(**kwargs):
        captured.update(kwargs)
        path = tmp_path / "artifacts" / "runs" / "run-1"
        return SimpleNamespace(
            path=path,
            manifest=SimpleNamespace(run_id="run-1"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.xl_docbench.run_xl_retrieval",
        fake_run_xl_retrieval,
    )

    result = runner.invoke(
        app,
        [
            "eval-retrieval",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "run-1",
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output["run_id"] == "run-1"
    assert output["report"].endswith("run-1/report.md")
    config = captured["config"]
    assert config.budgets == (2048, 4096, 8192, 16384)
    assert set(config.systems) == set(BenchmarkSystem)
    assert config.retrieval.embedding_model == "BAAI/bge-small-en-v1.5"
    assert config.retrieval.reranker_model == ("cross-encoder/ms-marco-MiniLM-L-6-v2")
    assert config.compiler.keyed_table_join_enabled
    assert captured["retrieval_corpus_subset_file"] is None


def test_eval_retrieval_accepts_fixed_retrieval_corpus(
    tmp_path: Path, monkeypatch
) -> None:
    captured = {}

    def fake_run_xl_retrieval(**kwargs):
        captured.update(kwargs)
        path = tmp_path / "artifacts" / "runs" / "run-fixed-corpus"
        return SimpleNamespace(
            path=path,
            manifest=SimpleNamespace(run_id="run-fixed-corpus"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.xl_docbench.run_xl_retrieval",
        fake_run_xl_retrieval,
    )
    corpus = tmp_path / "parent.json"

    result = runner.invoke(
        app,
        [
            "eval-retrieval",
            "--retrieval-corpus-subset-file",
            str(corpus),
            "--run-id",
            "run-fixed-corpus",
        ],
    )

    assert result.exit_code == 0
    assert captured["retrieval_corpus_subset_file"] == corpus


def test_eval_retrieval_disables_keyed_table_joins(
    tmp_path: Path, monkeypatch
) -> None:
    captured = {}

    def fake_run_xl_retrieval(**kwargs):
        captured.update(kwargs)
        path = tmp_path / "artifacts" / "runs" / "run-joins"
        return SimpleNamespace(
            path=path,
            manifest=SimpleNamespace(run_id="run-joins"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.xl_docbench.run_xl_retrieval",
        fake_run_xl_retrieval,
    )

    result = runner.invoke(
        app,
        [
            "eval-retrieval",
            "--no-compiler-keyed-table-joins",
            "--run-id",
            "run-joins",
        ],
    )

    assert result.exit_code == 0
    assert not captured["config"].compiler.keyed_table_join_enabled


def test_eval_factorial_defaults_to_small_fixed_corpus(
    tmp_path: Path, monkeypatch
) -> None:
    captured = {}

    def fake_run_xl_factorial(**kwargs):
        captured.update(kwargs)
        path = tmp_path / "artifacts" / "factorial-runs" / "factorial-1"
        return SimpleNamespace(
            path=path,
            manifest=SimpleNamespace(run_id="factorial-1"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.factorial_xl.run_xl_factorial",
        fake_run_xl_factorial,
    )

    result = runner.invoke(
        app,
        [
            "eval-factorial",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "factorial-1",
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output["run_id"] == "factorial-1"
    assert captured["subset_file"].name == "xldev2-tables.json"
    assert captured["retrieval_corpus_subset_file"].name == "xldev24.json"
    config = captured["config"]
    assert config.budgets == (2048, 4096, 8192, 16384)
    assert set(config.content_units) == {"fixed", "structural", "ir"}
    assert set(config.selection_policies) == {"ranked", "faceted_coverage"}


def test_eval_factorial_crosses_both_heading_context_positions(
    tmp_path: Path, monkeypatch
) -> None:
    """The ablation the factor exists for has to be reachable from the command.

    ``FactorialConfig.heading_contexts`` is crossed with the content units and
    the selection policies, but the command built the config without it, so a
    two-position run could be made only from Python. Omitting the flag must
    still produce exactly the single-valued default, because that is what keeps
    an unasked-for run identical to the runs made before the flag existed.
    """
    captured: dict[str, dict] = {}

    def fake_run_xl_factorial(**kwargs):
        captured[kwargs["run_id"]] = kwargs
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "factorial-runs" / kwargs["run_id"],
            manifest=SimpleNamespace(run_id=kwargs["run_id"]),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.factorial_xl.run_xl_factorial",
        fake_run_xl_factorial,
    )

    crossed = runner.invoke(
        app,
        [
            "eval-factorial",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "crossed",
            "--heading-context",
            "on",
            "--heading-context",
            "off",
        ],
    )
    default = runner.invoke(
        app,
        [
            "eval-factorial",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "default",
        ],
    )

    assert crossed.exit_code == 0, crossed.output
    assert default.exit_code == 0, default.output
    assert captured["crossed"]["config"].heading_contexts == (True, False)
    assert captured["default"]["config"].heading_contexts == (True,)


def test_eval_factorial_refuses_an_unusable_heading_context(
    tmp_path: Path, monkeypatch
) -> None:
    """A rejected factor must say what is wrong before any index is built.

    Non-empty and unique are ``FactorialConfig``'s own rules, so a repeated
    position has to surface that validator's message rather than a traceback or
    a silently deduplicated run; an unspellable position is caught by the CLI,
    which owns the on/off vocabulary.
    """
    calls: list[str] = []

    def fake_run_xl_factorial(**kwargs):
        calls.append("factorial")
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "factorial-runs" / "run-1",
            manifest=SimpleNamespace(run_id="run-1"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.factorial_xl.run_xl_factorial",
        fake_run_xl_factorial,
    )

    repeated = runner.invoke(
        app,
        ["eval-factorial", "--heading-context", "on", "--heading-context", "on"],
    )
    empty = runner.invoke(app, ["eval-factorial", "--heading-context", ""])

    assert repeated.exit_code == 1
    assert "heading_contexts must be non-empty and unique" in repeated.output
    assert empty.exit_code == 1
    assert "--heading-context takes 'on' or 'off'" in empty.output
    assert calls == []


def test_eval_commands_forward_pinned_model_revisions(
    tmp_path: Path, monkeypatch
) -> None:
    """The pin lives in CLI configuration, so it has to reach the runner.

    Both model defaults name a moving Hugging Face branch. If the revision
    stopped being forwarded, a run would resolve whatever the branch points at
    while the recorded configuration still looked pinned.
    """
    captured: dict[str, dict] = {}

    def fake_run_xl_retrieval(**kwargs):
        captured["retrieval"] = kwargs
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "runs" / "run-1",
            manifest=SimpleNamespace(run_id="run-1"),
        )

    def fake_run_xl_factorial(**kwargs):
        captured["factorial"] = kwargs
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "factorial-runs" / "run-2",
            manifest=SimpleNamespace(run_id="run-2"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.xl_docbench.run_xl_retrieval",
        fake_run_xl_retrieval,
    )
    monkeypatch.setattr(
        "contextbench.evaluation.factorial_xl.run_xl_factorial",
        fake_run_xl_factorial,
    )

    retrieval_result = runner.invoke(
        app,
        [
            "eval-retrieval",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "run-1",
        ],
    )
    factorial_result = runner.invoke(
        app,
        [
            "eval-factorial",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "run-2",
            "--embedding-revision",
            "a" * 40,
        ],
    )

    assert retrieval_result.exit_code == 0, retrieval_result.output
    assert factorial_result.exit_code == 0, factorial_result.output
    assert captured["retrieval"]["embedding_revision"] == (
        "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    )
    assert captured["retrieval"]["reranker_revision"] == (
        "233902d25c440f23af6f7d6e94d2946bac0bee0a"
    )
    assert captured["factorial"]["embedding_revision"] == "a" * 40
    assert captured["factorial"]["reranker_revision"] == (
        "233902d25c440f23af6f7d6e94d2946bac0bee0a"
    )


def test_eval_commands_refuse_a_new_model_id_on_the_default_revision(
    tmp_path: Path, monkeypatch
) -> None:
    """A default revision pins the default weights and nothing else.

    Each default revision is the commit its own default model ID resolved to.
    Left in place beside a different model ID it would record a hash that never
    belonged to those weights, so the CLI must refuse before the run rather
    than leave the mismatch for the hub to notice.
    """
    calls: list[str] = []

    def fake_run_xl_retrieval(**kwargs):
        calls.append("retrieval")
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "runs" / "run-1",
            manifest=SimpleNamespace(run_id="run-1"),
        )

    def fake_run_xl_factorial(**kwargs):
        calls.append("factorial")
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "factorial-runs" / "run-2",
            manifest=SimpleNamespace(run_id="run-2"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.xl_docbench.run_xl_retrieval",
        fake_run_xl_retrieval,
    )
    monkeypatch.setattr(
        "contextbench.evaluation.factorial_xl.run_xl_factorial",
        fake_run_xl_factorial,
    )

    embedding = runner.invoke(
        app,
        ["eval-retrieval", "--embedding-model", "other/embedding-v2"],
    )
    reranker = runner.invoke(
        app,
        ["eval-factorial", "--reranker-model", "other/reranker-v2"],
    )

    assert embedding.exit_code == 1
    assert "--embedding-revision" in embedding.output
    assert "other/embedding-v2" in embedding.output
    assert reranker.exit_code == 1
    assert "--reranker-revision" in reranker.output
    assert "other/reranker-v2" in reranker.output
    assert calls == []

    paired = runner.invoke(
        app,
        [
            "eval-retrieval",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "run-1",
            "--embedding-model",
            "other/embedding-v2",
            "--embedding-revision",
            "c" * 40,
        ],
    )

    assert paired.exit_code == 0, paired.output
    assert calls == ["retrieval"]


def test_eval_commands_accept_offline_models_without_a_revision(
    tmp_path: Path, monkeypatch
) -> None:
    """The offline models have no commit to name, so none may be demanded.

    ``hash-256-v1`` and ``lexical-overlap-v1`` are computed locally and have no
    Hugging Face repository, so the revision is never used. Refusing them while
    the default revision is in place asked the user for the commit of a model
    that has none, which is advice that cannot be followed.
    """
    captured: dict[str, dict] = {}

    def fake_run_xl_retrieval(**kwargs):
        captured["retrieval"] = kwargs
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "runs" / "run-1",
            manifest=SimpleNamespace(run_id="run-1"),
        )

    def fake_run_xl_factorial(**kwargs):
        captured["factorial"] = kwargs
        return SimpleNamespace(
            path=tmp_path / "artifacts" / "factorial-runs" / "run-2",
            manifest=SimpleNamespace(run_id="run-2"),
        )

    monkeypatch.setattr(
        "contextbench.evaluation.xl_docbench.run_xl_retrieval",
        fake_run_xl_retrieval,
    )
    monkeypatch.setattr(
        "contextbench.evaluation.factorial_xl.run_xl_factorial",
        fake_run_xl_factorial,
    )

    offline_embedding = runner.invoke(
        app,
        [
            "eval-retrieval",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "run-1",
            "--embedding-model",
            "hash-256-v1",
        ],
    )
    offline_reranker = runner.invoke(
        app,
        [
            "eval-factorial",
            "--artifacts-root",
            str(tmp_path / "artifacts"),
            "--run-id",
            "run-2",
            "--reranker-model",
            "lexical-overlap-v1",
        ],
    )

    assert offline_embedding.exit_code == 0, offline_embedding.output
    assert offline_reranker.exit_code == 0, offline_reranker.output
    assert captured["retrieval"]["config"].retrieval.embedding_model == "hash-256-v1"
    assert (
        captured["factorial"]["config"].retrieval.reranker_model
        == "lexical-overlap-v1"
    )

    # The guard still refuses a hub model ID paired with a revision that pins
    # a different model.
    hub_mismatch = runner.invoke(
        app,
        ["eval-retrieval", "--embedding-model", "other/embedding-v2"],
    )

    assert hub_mismatch.exit_code == 1
    assert "--embedding-revision" in hub_mismatch.output
