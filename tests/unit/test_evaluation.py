"""Evidence-only benchmark runner and artifact acceptance tests."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_compiler import compiler_source
from test_ir import FixtureTokenCounter, ingest_metadata

import contextbench.compiler.expand as compiler_expand
from contextbench.compiler import CompilerConfig
from contextbench.datasets.base import BenchmarkQuestion, EvidenceItem, GoldEvidence
from contextbench.evaluation import (
    BenchmarkSystem,
    EvaluationCorpus,
    EvaluationError,
    RetrievalBenchmarkConfig,
    RetrievalBenchmarkSummary,
    run_retrieval_benchmark,
)
from contextbench.evaluation.evidence import evaluate_context
from contextbench.evaluation.models import RetrievalSummaryRow
from contextbench.evaluation.reports import markdown_report, summarize
from contextbench.experiments import manifest
from contextbench.ir import project_document
from contextbench.retrieval import (
    ContextItem,
    ContextPacket,
    HashEmbeddingModel,
    HybridIndex,
    LexicalOverlapReranker,
    RetrievalConfig,
    RetrievalScores,
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
                items=(EvidenceItem(quote="Target revenue increased."),),
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


def _run(
    tmp_path: Path,
    *,
    run_id: str,
    config: RetrievalBenchmarkConfig | None = None,
):
    return run_retrieval_benchmark(
        _corpus(tmp_path),
        config=config or _config(),
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

    assert len(result.records) == 8
    assert {record.system for record in result.records} == set(BenchmarkSystem)
    assert all(record.token_count <= record.token_budget for record in result.records)
    assert all(
        record.gold_pages == {"dataset-doc-1": (1,)} for record in result.records
    )
    assert all(record.retrieval_latency_ms >= 0 for record in result.records)
    assert all(record.gold_quote_count == 1 for record in result.records)
    assert all(record.matched_quote_count <= 1 for record in result.records)
    assert all(record.answerable for record in result.records)
    assert all(
        record.document_ids == ("dataset-doc-1",) for record in result.records
    )
    assert all(
        0 <= record.content_verified_page_recall <= 1
        for record in result.records
    )
    assert len(result.summary.rows) == 8
    assert len(result.summary.paired_intervals) == 12
    assert all(
        interval.ci95_low == interval.mean_delta == interval.ci95_high
        for interval in result.summary.paired_intervals
    )

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
    assert manifest["retrieval_corpus_name"] == "fixture-one"
    assert manifest["retrieval_corpus_sha256"] == "1" * 64
    assert manifest["retrieval_corpus_question_ids"] == ["question-1"]
    assert manifest["token_budgets"] == [12, 24]
    assert manifest["embedding_model"] == "hash-256-v1"
    report = (result.path / "report.md").read_text()
    assert "No answer-generation model was used" in report
    assert "Evidence-only decision gate" in report
    assert "Audited metrics" in report
    assert "Paired source-cluster bootstrap" in report


def test_content_verified_pages_do_not_credit_partial_source_nodes(
    tmp_path: Path,
) -> None:
    corpus = _corpus(tmp_path)
    document = corpus.documents["dataset-doc-1"]
    node = next(
        node
        for node in document.nodes
        if any(box.page_no == 1 for box in node.bounding_boxes)
    )
    item = ContextItem(
        evidence_id="partial-node",
        document_id=document.id,
        page_start=node.page_start,
        page_end=node.page_end,
        content="deliberately incomplete fragment",
        token_count=3,
        source_node_ids=(node.id,),
        source_item_ids=node.source_item_ids,
        scores=RetrievalScores(),
    )
    packet = ContextPacket(
        query="target",
        token_budget=10,
        token_count=3,
        items=(item,),
        metadata={},
    )

    metrics = evaluate_context(corpus.questions[0], packet, corpus.documents)

    assert metrics["evidence_page_recall"] == 1.0
    assert metrics["content_verified_page_recall"] == 0.0
    assert metrics["content_verified_selected_pages"] == {"dataset-doc-1": ()}


def test_answerable_and_quoted_summaries_exclude_vacuous_questions(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path, run_id="audit-summary")
    answerable = result.records[0].model_copy(
        update={
            "evidence_page_recall": 0.0,
            "content_verified_page_recall": 0.0,
            "evidence_quote_recall": 0.0,
        }
    )
    unanswerable = result.records[0].model_copy(
        update={
            "question_id": "unanswerable",
            "answerable": False,
            "gold_pages": {},
            "matched_pages": {},
            "evidence_page_recall": 1.0,
            "full_evidence_coverage": True,
            "content_verified_matched_pages": {},
            "content_verified_page_recall": 1.0,
            "full_content_verified_coverage": True,
            "gold_quote_count": 0,
            "matched_quote_count": 0,
            "evidence_quote_recall": 1.0,
            "full_quote_coverage": True,
        }
    )

    row = summarize("audit", (answerable, unanswerable)).rows[0]

    assert row.mean_evidence_page_recall == 0.5
    assert row.answerable_question_count == 1
    assert row.answerable_mean_evidence_page_recall == 0.0
    assert row.quoted_question_count == 1
    assert row.quoted_mean_evidence_quote_recall == 0.0


def test_report_breaks_baseline_coverage_ties_with_recall() -> None:
    def row(system: BenchmarkSystem, recall: float) -> RetrievalSummaryRow:
        return RetrievalSummaryRow(
            system=system,
            token_budget=2048,
            question_count=2,
            mean_evidence_page_recall=recall,
            full_evidence_coverage_rate=0.0,
            mean_evidence_quote_recall=0.0,
            full_quote_coverage_rate=0.0,
            mean_context_tokens=2048.0,
            median_context_tokens=2048.0,
            median_tokens_to_full_evidence=None,
            mean_redundancy=0.0,
            mean_retrieval_latency_ms=1.0,
        )

    summary = RetrievalBenchmarkSummary(
        run_id="baseline-tie",
        rows=(
            row(BenchmarkSystem.FIXED, 0.5),
            row(BenchmarkSystem.STRUCTURAL, 0.7),
            row(BenchmarkSystem.COMPILER, 0.6),
        ),
    )

    assert "-0.100 recall" in markdown_report(summary)


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


def test_runner_rejects_questions_outside_declared_retrieval_corpus(
    tmp_path: Path,
) -> None:
    with pytest.raises(EvaluationError, match="included in the retrieval corpus"):
        run_retrieval_benchmark(
            _corpus(tmp_path),
            config=_config(),
            artifacts_root=tmp_path / "artifacts",
            dataset="fixture",
            dataset_version="v1",
            dataset_revision="revision-1",
            subset_name="fixture-one",
            subset_sha256="1" * 64,
            retrieval_corpus_name="different",
            retrieval_corpus_sha256="2" * 64,
            retrieval_corpus_question_ids=("other-question",),
            run_id="invalid-corpus",
            tokenizer=FixtureTokenCounter(),
            embedder=HashEmbeddingModel(),
            reranker=LexicalOverlapReranker(),
            git_commit="a" * 40,
            clock=lambda: datetime(2026, 9, 19, tzinfo=UTC),
        )


def test_runner_reranks_once_per_question_and_system(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retrieve_calls = 0
    candidate_calls = 0
    rerank_calls = 0
    original_retrieve = HybridIndex.retrieve
    original_candidates = HybridIndex.retrieve_candidates
    original_rerank = HybridIndex.rerank

    def counted_retrieve(self, *args, **kwargs):
        nonlocal retrieve_calls
        retrieve_calls += 1
        return original_retrieve(self, *args, **kwargs)

    def counted_candidates(self, *args, **kwargs):
        nonlocal candidate_calls
        candidate_calls += 1
        return original_candidates(self, *args, **kwargs)

    def counted_rerank(self, *args, **kwargs):
        nonlocal rerank_calls
        rerank_calls += 1
        return original_rerank(self, *args, **kwargs)

    monkeypatch.setattr(HybridIndex, "retrieve", counted_retrieve)
    monkeypatch.setattr(HybridIndex, "retrieve_candidates", counted_candidates)
    monkeypatch.setattr(HybridIndex, "rerank", counted_rerank)

    _run(tmp_path, run_id="single-retrieval")

    assert retrieve_calls == 2
    assert candidate_calls == 3
    assert rerank_calls == 3


def test_runner_reuses_compiler_page_ranking_across_budgets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    original = compiler_expand._page_neighbor_candidates

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(compiler_expand, "_page_neighbor_candidates", counted)
    retrieval = RetrievalConfig(
        fixed_chunk_tokens=12,
        fixed_overlap_tokens=3,
        structural_chunk_tokens=24,
        candidate_limit=10,
        rerank_limit=1,
        max_candidate_limit=10,
        max_rerank_limit=1,
    )
    config = RetrievalBenchmarkConfig(
        budgets=(50, 100),
        systems=(BenchmarkSystem.COMPILER,),
        retrieval=retrieval,
        compiler=CompilerConfig(
            retrieval=retrieval,
            page_neighbor_radius=1,
            page_neighbor_min_budget=50,
            page_neighbor_origin_limit=1,
            page_neighbor_candidate_limit=10,
        ),
    )

    result = _run(tmp_path, run_id="cached-page-ranking", config=config)

    assert calls == 1
    assert len(result.records) == 2


def test_runner_writes_opt_in_compiler_stage_audit(tmp_path: Path) -> None:
    base = _config()
    config = base.model_copy(
        update={
            "systems": (BenchmarkSystem.COMPILER,),
            "compiler_stage_audit": True,
        }
    )

    result = _run(tmp_path, run_id="stage-audit", config=config)

    assert len(result.stage_audits) == len(config.budgets)
    assert (result.path / "compiler-stages.jsonl").is_file()
    assert {path.name for path in result.path.iterdir()} == {
        "compiler-stages.jsonl",
        "contexts.jsonl",
        "manifest.json",
        "report.md",
        "retrieval.jsonl",
        "summary.json",
    }
    for record in result.stage_audits:
        assert record.raw_node_retrieval.candidate_count > 0
        assert record.faceted_node_retrieval.candidate_count > 0
        assert record.structural_retrieval.candidate_count > 0
        assert record.compiler_structural_union.evidence_page_recall >= (
            record.faceted_node_retrieval.evidence_page_recall
        )
        assert record.compiler_structural_union.evidence_page_recall >= (
            record.structural_retrieval.evidence_page_recall
        )
        assert record.packing.candidate_tokens <= record.token_budget


def test_stage_audit_requires_compiler_system() -> None:
    with pytest.raises(ValueError, match="requires the compiler system"):
        RetrievalBenchmarkConfig(
            systems=(BenchmarkSystem.STRUCTURAL,),
            compiler_stage_audit=True,
        )


def _run_from_worktree(
    tmp_path: Path,
    *,
    run_id: str,
    allow_dirty: bool,
):
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
        git_commit=None,
        allow_dirty=allow_dirty,
        clock=lambda: datetime(2026, 9, 21, tzinfo=UTC),
    )


def test_dirty_worktree_is_refused_before_any_artifact_is_written(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(manifest, "current_git_commit", lambda: "d" * 40)
    monkeypatch.setattr(manifest, "current_git_dirty", lambda: True)
    artifacts_root = tmp_path / "artifacts"

    with pytest.raises(EvaluationError, match="modified worktree"):
        _run_from_worktree(tmp_path, run_id="dirty-run", allow_dirty=False)

    assert not artifacts_root.exists()


def test_allow_dirty_stamps_the_manifest_instead_of_hiding_the_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(manifest, "current_git_commit", lambda: "d" * 40)
    monkeypatch.setattr(manifest, "current_git_dirty", lambda: True)

    result = _run_from_worktree(tmp_path, run_id="dirty-run", allow_dirty=True)

    written = json.loads((result.path / "manifest.json").read_text())
    assert written["git_commit"] == "d" * 40
    assert written["git_dirty"] is True
