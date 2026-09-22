"""Controlled content-unit × selection-policy experiment tests."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_compiler import compiler_source
from test_ir import FixtureTokenCounter, ingest_metadata, source_document

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
    assert config.heading_contexts == (True,)
    assert manifest["systems"] == [
        f"{unit.value}:{policy.value}:heading-on"
        for unit in ContentUnit
        for policy in SelectionPolicy
    ]
    assert all(record.heading_context is True for record in result.records)
    report = (result.path / "report.md").read_text()
    assert "Policy effect within each content unit" in report
    assert "IR effect under each selection policy" in report
    assert "No structural expansion" in report


def _heading_vocabulary_corpus(tmp_path: Path) -> EvaluationCorpus:
    """A corpus whose only query term exists in a heading and nowhere else.

    ``Methods`` is a level-1 heading of the shared IR fixture; the only node
    under it is the code node ``print('measured')``, whose body does not
    contain the term. Whether a unit can answer this question is therefore
    exactly whether heading text reaches what it indexes.
    """
    source = source_document()
    counter = FixtureTokenCounter()
    document = project_document(
        source,
        ingest_metadata(tmp_path),
        tokenizer=counter,
    )
    question = BenchmarkQuestion(
        id="heading-question",
        question="Methods",
        document_ids=("dataset-doc-1",),
        gold_answer="measured",
        answer_format="short_text",
        verification_rule="exact",
        gold_evidence=(
            GoldEvidence(
                document_id="dataset-doc-1",
                pages=(2,),
                page_numbering="pdf_index",
                items=(EvidenceItem(quote="print('measured')"),),
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


def _ablation_config() -> FactorialConfig:
    return _config().model_copy(update={"heading_contexts": (True, False)})


def _run(
    corpus: EvaluationCorpus,
    config: FactorialConfig,
    tmp_path: Path,
    run_id: str,
):
    return run_factorial_benchmark(
        corpus,
        config=config,
        artifacts_root=tmp_path / f"artifacts-{run_id}",
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
        git_dirty=False,
        clock=lambda: datetime(2026, 9, 21, tzinfo=UTC),
    )


def _comparable(record) -> dict[str, object]:
    """Everything a cell measured, minus its identity and wall-clock timing."""
    return record.model_dump(
        exclude={"heading_context", "retrieval_latency_ms"},
        mode="json",
    )


def test_heading_context_is_a_crossed_factor(tmp_path: Path) -> None:
    """Both positions must produce their own cells, each recording its value."""
    config = _ablation_config()
    result = _run(
        _heading_vocabulary_corpus(tmp_path),
        config,
        tmp_path,
        "factorial-heading-ablation",
    )

    expected_cells = {
        (unit, policy, heading_context, budget)
        for unit in ContentUnit
        for policy in SelectionPolicy
        for heading_context in (True, False)
        for budget in config.budgets
    }
    assert {
        (
            record.content_unit,
            record.selection_policy,
            record.heading_context,
            record.token_budget,
        )
        for record in result.records
    } == expected_cells
    # Twice the twelve cells of the single-valued default.
    assert len(result.records) == 24
    assert len(result.summary.rows) == 24
    assert {row.heading_context for row in result.summary.rows} == {True, False}

    manifest_value = json.loads((result.path / "manifest.json").read_text())
    assert manifest_value["systems"] == [
        f"{unit.value}:{policy.value}:{label}"
        for unit in ContentUnit
        for policy in SelectionPolicy
        for label in ("heading-on", "heading-off")
    ]
    contexts = [
        json.loads(line)
        for line in (result.path / "contexts.jsonl").read_text().splitlines()
    ]
    assert {context["heading_context"] for context in contexts} == {True, False}
    assert {
        context["context"]["metadata"]["heading_context"] for context in contexts
    } == {"heading-on", "heading-off"}
    report = (result.path / "report.md").read_text()
    assert "## Heading-context factor" in report
    # The fixed unit's constancy is stated where the ablation is reported.
    assert "its windows already concatenate heading nodes" in report


def test_heading_context_moves_the_structural_and_ir_units_only(
    tmp_path: Path,
) -> None:
    """The factor must reach both heading-bearing units, and only those.

    This is the point of making it a factor: the compiler's node candidates
    have always carried heading context, so an ablation that toggled it on the
    structural unit alone could not tell "IR nodes beat structural chunks"
    apart from "IR nodes carry heading context". Here both units lose the
    heading trail together, and both lose the answer with it.

    The fixed unit is constant across the factor by construction -- it does not
    read the field, and its windows concatenate every node, heading nodes
    included -- so its unchanged rows are not evidence about heading context.
    """
    config = _ablation_config()
    result = _run(
        _heading_vocabulary_corpus(tmp_path),
        config,
        tmp_path,
        "factorial-heading-effect",
    )

    def record(unit: ContentUnit, heading_context: bool):
        return next(
            item
            for item in result.records
            if item.content_unit == unit
            and item.selection_policy == SelectionPolicy.RANKED
            and item.heading_context == heading_context
            and item.token_budget == max(config.budgets)
        )

    for unit in (ContentUnit.STRUCTURAL, ContentUnit.IR):
        assert _comparable(record(unit, True)) != _comparable(record(unit, False))
        # Not merely a different evidence id: the answer itself is lost.
        assert record(unit, True).evidence_quote_recall == 1.0
        assert record(unit, False).evidence_quote_recall == 0.0

    assert _comparable(record(ContentUnit.FIXED, True)) == _comparable(
        record(ContentUnit.FIXED, False)
    )
    assert record(ContentUnit.FIXED, True).evidence_quote_recall == 1.0


def test_heading_context_keeps_ir_chunk_ids_identical_across_positions(
    tmp_path: Path,
) -> None:
    """The factor must move what is indexed, never the candidate ids.

    ``chunk.id`` is a deterministic tie-break sort key in the indexes and in
    the coverage objective. While the IR node id payload embedded the indexed
    string, toggling this factor permuted every IR id, so an IR heading-on/off
    delta carried an id-permutation effect that the structural unit -- whose
    id payload omits ``search_text`` -- does not have. That made the factor
    arm-asymmetric in exactly the comparison it exists to enable.

    Ids are now derived from content alone on both heading-bearing units, so
    both positions of every unit agree on ids while still disagreeing on
    ``search_text``. Cache isolation is unaffected: each position still gets
    its own ``RetrievalConfig`` and its own derived-index key.
    """
    config = _ablation_config()
    corpus = _heading_vocabulary_corpus(tmp_path)
    documents = tuple(corpus.documents.values())
    indexes = factorial_runner._build_factorial_indexes(
        documents,
        sources_by_ir_id={
            document.id: corpus.source_documents[document_id]
            for document_id, document in corpus.documents.items()
        },
        config=config,
        artifacts_root=tmp_path / "id-identity-artifacts",
        tokenizer=FixtureTokenCounter(),
        embedder=HashEmbeddingModel(),
        reranker=LexicalOverlapReranker(),
    )

    for unit in ContentUnit:
        on = indexes[(unit, SelectionPolicy.RANKED, True)].chunks
        off = indexes[(unit, SelectionPolicy.RANKED, False)].chunks
        assert [chunk.id for chunk in on] == [chunk.id for chunk in off]
        assert [chunk.text for chunk in on] == [chunk.text for chunk in off]

    for unit in (ContentUnit.STRUCTURAL, ContentUnit.IR):
        on = indexes[(unit, SelectionPolicy.RANKED, True)].chunks
        off = indexes[(unit, SelectionPolicy.RANKED, False)].chunks
        # The factor is not inert: the indexed string still differs.
        assert all(chunk.search_text is None for chunk in off)
        assert any(chunk.search_text not in (None, chunk.text) for chunk in on)

    # The fixed unit does not read the factor at all.
    fixed_on = indexes[(ContentUnit.FIXED, SelectionPolicy.RANKED, True)].chunks
    fixed_off = indexes[(ContentUnit.FIXED, SelectionPolicy.RANKED, False)].chunks
    assert fixed_on == fixed_off


def test_default_heading_contexts_leave_the_cell_set_unchanged(
    tmp_path: Path,
) -> None:
    """The default single value must reproduce the pre-factor run exactly.

    Every metric of every cell is compared, not just the cell count, so the
    added factor cannot move a result while it stays single-valued.
    """
    config = _config()
    assert config.heading_contexts == (True,)
    corpus = _heading_vocabulary_corpus(tmp_path)

    default = _run(corpus, config, tmp_path, "factorial-default")
    crossed = _run(corpus, _ablation_config(), tmp_path, "factorial-crossed")

    assert len(default.records) == 12
    assert {record.heading_context for record in default.records} == {True}
    assert [_comparable(record) for record in default.records] == [
        _comparable(record) for record in crossed.records if record.heading_context
    ]


@pytest.mark.parametrize("heading_contexts", [(), (True, True)])
def test_factorial_config_rejects_empty_or_duplicated_heading_contexts(
    heading_contexts: tuple[bool, ...],
) -> None:
    with pytest.raises(ValueError, match="heading_contexts must be non-empty"):
        FactorialConfig(heading_contexts=heading_contexts)


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
            heading_context=True,
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
