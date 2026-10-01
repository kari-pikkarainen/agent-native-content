"""Tests for deterministic compiler query faceting."""

from agent_native_content.compiler.facets import query_facets, retrieve_faceted
from agent_native_content.compiler.models import CompilerConfig
from agent_native_content.retrieval import RetrievalArm, RetrievalChunk
from agent_native_content.retrieval.models import (
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
        batch_calls = 0

        def retrieve_candidates(self, query: str, **_kwargs):
            return (forcing,) if "forcing" in query else (warming,)

        def rerank(self, _query: str, candidates):
            return tuple(
                candidate.model_copy(update={"rank": rank})
                for rank, candidate in enumerate(candidates, 1)
            )

        def rerank_many(self, requests):
            self.batch_calls += 1
            return tuple(
                tuple(
                    candidate.model_copy(update={"rank": rank})
                    for rank, candidate in enumerate(candidates, 1)
                )
                for _query, candidates in requests
            )

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

    index = StubIndex()
    faceted = retrieve_faceted(
        index,  # type: ignore[arg-type]
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
    assert index.batch_calls == 1
