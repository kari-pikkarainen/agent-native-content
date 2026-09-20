"""Tests for deterministic compiler query faceting."""

from contextbench.compiler.facets import query_facets, retrieve_faceted
from contextbench.compiler.models import CompilerConfig
from contextbench.retrieval import RetrievalArm, RetrievalChunk
from contextbench.retrieval.models import (
    RankedEvidence,
    RetrievalConfig,
    RetrievalScores,
)


def test_query_facets_extract_bounded_meaningful_clauses() -> None:
    query = (
        "Using the doubling CO2 forcing and the mean TCR ratio, which emulator "
        "has the lowest normalized warming?"
    )

    assert query_facets(query, limit=3, min_terms=3) == (
        "the doubling CO2 forcing",
        "the mean TCR ratio",
        "emulator has the lowest normalized warming",
    )


def test_faceted_retrieval_promotes_evidence_from_separate_clauses() -> None:
    def evidence(chunk_id: str, text: str) -> RankedEvidence:
        return RankedEvidence(
            rank=1,
            chunk=RetrievalChunk(
                id=chunk_id,
                arm=RetrievalArm.COMPILER,
                document_id="doc",
                text=text,
                token_count=len(text.split()),
                source_node_ids=(f"node-{chunk_id}",),
                source_item_ids=(f"item-{chunk_id}",),
            ),
            scores=RetrievalScores(reranked=1),
        )

    full = evidence("full", "general comparison")
    forcing = evidence("forcing", "doubling CO2 forcing")
    warming = evidence("warming", "lowest normalized warming emulator")

    class StubIndex:
        def retrieve(self, query: str, **_kwargs):
            return (forcing,) if "forcing" in query else (warming,)

    retrieval = RetrievalConfig(
        candidate_limit=1,
        rerank_limit=1,
        max_candidate_limit=1,
        max_rerank_limit=1,
    )
    config = CompilerConfig(
        retrieval=retrieval,
        query_faceting_enabled=True,
        query_facet_limit=3,
        query_facet_min_terms=3,
        query_facet_full_weight=0.1,
    )
    query = (
        "Using doubling CO2 forcing, which emulator has lowest normalized warming?"
    )

    faceted = retrieve_faceted(
        StubIndex(),  # type: ignore[arg-type]
        query,
        (full,),
        token_budget=10,
        document_ids={"doc"},
        config=config,
    )

    assert [item.chunk.id for item in faceted] == ["forcing"]
    assert len(faceted) == 1
    assert [evidence.rank for evidence in faceted] == list(
        range(1, len(faceted) + 1)
    )
