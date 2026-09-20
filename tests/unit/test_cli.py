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
