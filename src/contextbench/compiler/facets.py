"""Deterministic lexical query faceting and rank fusion."""

import re
from collections.abc import Sequence

from contextbench.compiler.models import CompilerConfig
from contextbench.retrieval.index import HybridIndex
from contextbench.retrieval.models import RankedEvidence

_CLAUSE_BOUNDARY = re.compile(
    r"\s*(?:[,;]|\b(?:and|versus|vs\.?|while|whereas)\b)\s*",
    flags=re.IGNORECASE,
)
_LEADING_SCAFFOLD = re.compile(
    r"^(?:(?:across|using|within|from|in|according to|based on)\s+|"
    r"(?:which|what|where|when|how|does|do|is|are)\s+)",
    flags=re.IGNORECASE,
)
_TERM = re.compile(r"[\w][\w.-]*", flags=re.UNICODE)


def query_facets(
    query: str,
    *,
    limit: int,
    min_terms: int,
) -> tuple[str, ...]:
    """Extract bounded, source-order lexical clauses from a complex query."""
    normalized = " ".join(query.split())
    candidates = _CLAUSE_BOUNDARY.split(normalized)
    facets = []
    seen = {normalized.casefold().rstrip("?.!")}
    for candidate in candidates:
        facet = _LEADING_SCAFFOLD.sub("", candidate).strip(" .?!,:;-")
        key = facet.casefold()
        if len(_TERM.findall(facet)) < min_terms or key in seen:
            continue
        seen.add(key)
        facets.append(facet)
        if len(facets) == limit:
            break
    return tuple(facets)


def retrieve_faceted(
    index: HybridIndex,
    query: str,
    ranked: Sequence[RankedEvidence],
    *,
    token_budget: int,
    document_ids: set[str],
    config: CompilerConfig,
) -> tuple[RankedEvidence, ...]:
    """Fuse cheap facet candidates, then rerank the bounded pool once."""
    if not ranked:
        return ()
    if not config.query_faceting_enabled:
        return index.rerank(query, ranked)
    facets = query_facets(
        query,
        limit=config.query_facet_limit,
        min_terms=config.query_facet_min_terms,
    )
    if not facets:
        return index.rerank(query, ranked)

    candidate_rankings = [tuple(ranked)]
    candidate_rankings.extend(
        index.retrieve_candidates(
            facet,
            token_budget=token_budget,
            document_ids=document_ids,
            maximum_rerank_limit=config.node_rerank_candidate_limit,
        )
        for facet in facets
    )
    if config.query_facet_rerank_strategy == "batched":
        rankings = index.rerank_many(
            tuple(zip((query, *facets), candidate_rankings, strict=True))
        )
    else:
        rankings = tuple(candidate_rankings)
    by_id: dict[str, RankedEvidence] = {}
    fused: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    for ranking_index, ranking in enumerate(rankings):
        weight = config.query_facet_full_weight if ranking_index == 0 else 1.0
        for evidence in ranking:
            chunk_id = evidence.chunk.id
            by_id.setdefault(chunk_id, evidence)
            fused[chunk_id] = fused.get(chunk_id, 0.0) + weight / (
                config.retrieval.rrf_k + evidence.rank
            )
            best_rank[chunk_id] = min(
                best_rank.get(chunk_id, evidence.rank),
                evidence.rank,
            )

    ordered = sorted(
        by_id,
        key=lambda chunk_id: (-fused[chunk_id], best_rank[chunk_id], chunk_id),
    )[: len(ranked)]
    fused_candidates = tuple(
        by_id[chunk_id].model_copy(
            update={
                "rank": rank,
                "scores": by_id[chunk_id].scores.model_copy(
                    update={
                        "fused": fused[chunk_id],
                        "reranked": fused[chunk_id],
                    }
                ),
            }
        )
        for rank, chunk_id in enumerate(ordered, 1)
    )
    if config.query_facet_rerank_strategy == "batched":
        return fused_candidates
    return index.rerank(query, fused_candidates)
