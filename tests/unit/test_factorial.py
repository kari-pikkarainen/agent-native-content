"""Controlled content-unit × selection-policy experiment tests."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_compiler import compiler_source
from test_ir import FixtureTokenCounter, ingest_metadata

from contextbench.datasets.base import BenchmarkQuestion, EvidenceItem, GoldEvidence
from contextbench.evaluation import (
    ContentUnit,
    EvaluationCorpus,
    EvaluationError,
    FactorialConfig,
    FactorialFacetConfig,
    SelectionPolicy,
    run_factorial_benchmark,
)
from contextbench.evaluation import factorial as factorial_runner
from contextbench.evaluation.factorial import _pack_factorial_context
from contextbench.experiments import manifest
from contextbench.ir import project_document
from contextbench.retrieval import (
    HashEmbeddingModel,
    LexicalOverlapReranker,
    RankedEvidence,
    RetrievalArm,
    RetrievalChunk,
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
        id="factorial-question",
        question="Which target increased and which baseline changed?",
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


def _config() -> FactorialConfig:
    retrieval = RetrievalConfig(
        fixed_chunk_tokens=12,
        fixed_overlap_tokens=3,
        structural_chunk_tokens=24,
        candidate_limit=10,
        rerank_limit=5,
    )
    return FactorialConfig(
        budgets=(12, 24),
        retrieval=retrieval,
        faceting=FactorialFacetConfig(retrieval=retrieval),
    )


def test_factorial_runner_crosses_every_unit_and_policy(tmp_path: Path) -> None:
    config = _config()
    result = run_factorial_benchmark(
        _corpus(tmp_path),
        config=config,
        artifacts_root=tmp_path / "artifacts",
        dataset="fixture",
        dataset_version="v1",
        dataset_revision="revision-1",
        subset_name="fixture-one",
        subset_sha256="1" * 64,
        run_id="factorial-fixture",
        tokenizer=FixtureTokenCounter(),
        embedder=HashEmbeddingModel(),
        reranker=LexicalOverlapReranker(),
        git_commit="a" * 40,
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 21, tzinfo=UTC),
    )

    expected_cells = {
        (unit, policy, budget)
        for unit in ContentUnit
        for policy in SelectionPolicy
        for budget in config.budgets
    }
    assert {
        (record.content_unit, record.selection_policy, record.token_budget)
        for record in result.records
    } == expected_cells
    assert len(result.records) == 12
    assert all(record.token_count <= record.token_budget for record in result.records)
    assert len(result.summary.rows) == 12
    assert result.path.parent.name == "factorial-runs"
    assert {path.name for path in result.path.iterdir()} == {
        "contexts.jsonl",
        "manifest.json",
        "report.md",
        "retrieval.jsonl",
        "summary.json",
    }

    manifest = json.loads((result.path / "manifest.json").read_text())
    assert manifest["git_commit"] == "a" * 40
    assert manifest["git_dirty"] is False
    assert manifest["systems"] == [
        f"{unit.value}:{policy.value}"
        for unit in ContentUnit
        for policy in SelectionPolicy
    ]
    report = (result.path / "report.md").read_text()
    assert "Policy effect within each content unit" in report
    assert "IR effect under each selection policy" in report
    assert "No structural expansion" in report


def test_factorial_config_requires_identical_retrieval_configuration() -> None:
    with pytest.raises(ValueError, match="shared retrieval configs must match"):
        FactorialConfig(
            retrieval=RetrievalConfig(candidate_limit=10),
            faceting=FactorialFacetConfig(
                retrieval=RetrievalConfig(candidate_limit=11)
            ),
        )


def test_factorial_policies_share_provenance_deduplication() -> None:
    def ranked(chunk_id: str, rank: int) -> RankedEvidence:
        return RankedEvidence(
            rank=rank,
            chunk=RetrievalChunk(
                id=chunk_id,
                arm=RetrievalArm.FIXED,
                document_id="doc",
                text=f"target evidence {chunk_id}",
                token_count=3,
                source_node_ids=("node",),
                source_item_ids=("item",),
            ),
            scores=RetrievalScores(reranked=1 / rank),
        )

    evidence = (ranked("first", 1), ranked("overlap", 2))
    counter = FixtureTokenCounter()
    packets = [
        _pack_factorial_context(
            "target evidence",
            evidence,
            unit=ContentUnit.FIXED,
            policy=policy,
            token_budget=20,
            tokenizer=counter,
        )
        for policy in SelectionPolicy
    ]

    assert all(len(packet.items) == 1 for packet in packets)
    assert all(packet.items[0].source_item_ids == ("item",) for packet in packets)


def test_factorial_dirty_worktree_is_refused_before_any_artifact_is_written(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(manifest, "current_git_commit", lambda: "d" * 40)
    monkeypatch.setattr(manifest, "current_git_dirty", lambda: True)
    artifacts_root = tmp_path / "artifacts"

    with pytest.raises(EvaluationError, match="modified worktree"):
        run_factorial_benchmark(
            _corpus(tmp_path),
            config=_config(),
            artifacts_root=artifacts_root,
            dataset="fixture",
            dataset_version="v1",
            dataset_revision="revision-1",
            subset_name="fixture-one",
            subset_sha256="1" * 64,
            run_id="factorial-dirty",
            tokenizer=FixtureTokenCounter(),
            embedder=HashEmbeddingModel(),
            reranker=LexicalOverlapReranker(),
            git_commit=None,
            allow_dirty=False,
            clock=lambda: datetime(2026, 9, 21, tzinfo=UTC),
        )

    assert not artifacts_root.exists()


def test_factorial_dirty_worktree_is_refused_before_any_model_is_constructed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The gate must fire before an embedder or reranker can load weights."""
    monkeypatch.setattr(manifest, "current_git_commit", lambda: "d" * 40)
    monkeypatch.setattr(manifest, "current_git_dirty", lambda: True)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "model construction must not run before the worktree gate"
        )

    monkeypatch.setattr(factorial_runner, "embedding_model_from_config", forbidden)
    monkeypatch.setattr(factorial_runner, "reranker_from_config", forbidden)
    artifacts_root = tmp_path / "artifacts"

    with pytest.raises(EvaluationError, match="modified worktree"):
        run_factorial_benchmark(
            _corpus(tmp_path),
            config=_config(),
            artifacts_root=artifacts_root,
            dataset="fixture",
            dataset_version="v1",
            dataset_revision="revision-1",
            subset_name="fixture-one",
            subset_sha256="1" * 64,
            run_id="factorial-dirty-no-models",
            tokenizer=FixtureTokenCounter(),
            git_commit=None,
            allow_dirty=False,
            clock=lambda: datetime(2026, 9, 21, tzinfo=UTC),
        )

    assert not artifacts_root.exists()
