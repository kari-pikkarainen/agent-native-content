"""Tests for the command-line entry point."""

import json
from pathlib import Path

from typer.testing import CliRunner

from contextbench import __version__
from contextbench.cli import app

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
