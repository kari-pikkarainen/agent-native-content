"""Evidence-only benchmark runner and artifact acceptance tests."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_compiler import compiler_source
from test_ir import FixtureTokenCounter, ingest_metadata

from contextbench.compiler import CompilerConfig
from contextbench.datasets.base import BenchmarkQuestion, GoldEvidence
from contextbench.evaluation import (
    BenchmarkSystem,
    EvaluationCorpus,
    EvaluationError,
    RetrievalBenchmarkConfig,
    run_retrieval_benchmark,
)
from contextbench.ir import project_document
from contextbench.retrieval import (
    HashEmbeddingModel,
    HybridIndex,
    LexicalOverlapReranker,
    RetrievalConfig,
)


def _corpus(tmp_path: Path) -> EvaluationCorpus:
    source = compiler_source()
    counter = FixtureTokenCounter()
    document = project_document(
        source,
        ingest_metadata(tmp_path),
        tokenizer=counter,
    )
    question = BenchmarkQuestion(
        id="question-1",
        question="Which target increased?",
        document_ids=("dataset-doc-1",),
        gold_answer="revenue",
        answer_format="short_text",
        verification_rule="exact",
        gold_evidence=(
            GoldEvidence(
                document_id="dataset-doc-1",
                pages=(1,),
                page_numbering="pdf_index",
            ),
        ),
        answerable=True,
        task_type="single_doc",
    )
    return EvaluationCorpus(
        questions=(question,),
        documents={"dataset-doc-1": document},
        source_documents={"dataset-doc-1": source},
    )


def _config() -> RetrievalBenchmarkConfig:
    retrieval = RetrievalConfig(
        fixed_chunk_tokens=12,
        fixed_overlap_tokens=3,
        structural_chunk_tokens=24,
        candidate_limit=10,
        rerank_limit=5,
    )
    return RetrievalBenchmarkConfig(
        budgets=(12, 24),
        retrieval=retrieval,
        compiler=CompilerConfig(retrieval=retrieval),
    )


def _run(tmp_path: Path, *, run_id: str):
    return run_retrieval_benchmark(
        _corpus(tmp_path),
        config=_config(),
        artifacts_root=tmp_path / "artifacts",
        dataset="fixture",
        dataset_version="v1",
        dataset_revision="revision-1",
        subset_name="fixture-one",
        subset_sha256="1" * 64,
        run_id=run_id,
        tokenizer=FixtureTokenCounter(),
        embedder=HashEmbeddingModel(),
        reranker=LexicalOverlapReranker(),
        git_commit="a" * 40,
        clock=lambda: datetime(2026, 9, 19, tzinfo=UTC),
    )


def test_runner_writes_complete_immutable_evidence_artifacts(tmp_path: Path) -> None:
    result = _run(tmp_path, run_id="fixture-run")

    assert len(result.records) == 6
    assert {record.system for record in result.records} == set(BenchmarkSystem)
    assert all(record.token_count <= record.token_budget for record in result.records)
    assert all(
        record.gold_pages == {"dataset-doc-1": (1,)} for record in result.records
    )
    assert all(record.retrieval_latency_ms >= 0 for record in result.records)
    assert len(result.summary.rows) == 6

    expected_files = {
        "contexts.jsonl",
        "manifest.json",
        "report.md",
        "retrieval.jsonl",
        "summary.json",
    }
    assert {path.name for path in result.path.iterdir()} == expected_files
    manifest = json.loads((result.path / "manifest.json").read_text())
    assert manifest["git_commit"] == "a" * 40
    assert manifest["dataset_revision"] == "revision-1"
    assert manifest["question_ids"] == ["question-1"]
    assert manifest["token_budgets"] == [12, 24]
    assert manifest["embedding_model"] == "hash-256-v1"
    report = (result.path / "report.md").read_text()
    assert "No answer-generation model was used" in report
    assert "Evidence-only decision gate" in report


def test_repeated_fixture_runs_reproduce_selection_and_refuse_overwrite(
    tmp_path: Path,
) -> None:
    first = _run(tmp_path, run_id="first")
    second = _run(tmp_path, run_id="second")

    def deterministic_fields(result):
        return [
            record.model_dump(exclude={"retrieval_latency_ms"})
            for record in result.records
        ]

    assert deterministic_fields(first) == deterministic_fields(second)
    original_manifest = (first.path / "manifest.json").read_bytes()
    with pytest.raises(EvaluationError, match="completed run already exists"):
        _run(tmp_path, run_id="first")
    assert (first.path / "manifest.json").read_bytes() == original_manifest


def test_invalid_run_id_is_rejected_before_artifacts_are_written(
    tmp_path: Path,
) -> None:
    with pytest.raises(EvaluationError, match="unsafe path"):
        _run(tmp_path, run_id="../escape")

    assert not (tmp_path / "escape").exists()


def test_runner_retrieves_once_per_question_and_system(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = HybridIndex.retrieve

    def counted_retrieve(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(HybridIndex, "retrieve", counted_retrieve)

    _run(tmp_path, run_id="single-retrieval")

    assert calls == len(BenchmarkSystem)
