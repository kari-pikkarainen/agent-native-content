"""Public deterministic context compiler API."""

import hashlib
import json
from collections.abc import Sequence

from contextbench.compiler.candidates import node_chunks
from contextbench.compiler.dedupe import deduplicate_candidates
from contextbench.compiler.expand import expand_candidates
from contextbench.compiler.facets import query_facets, retrieve_faceted
from contextbench.compiler.models import (
    COMPILER_VERSION,
    CompilerCandidate,
    CompilerConfig,
    CompilerQueryCache,
    CompilerTrace,
    DocumentScope,
)
from contextbench.compiler.pack import pack_candidates
from contextbench.ir.models import IRDocument
from contextbench.ir.tokenizer import TiktokenTokenCounter, TokenCounter
from contextbench.retrieval.embeddings import EmbeddingModel
from contextbench.retrieval.index import HybridIndex
from contextbench.retrieval.models import ContextPacket, RankedEvidence, RetrievalArm
from contextbench.retrieval.rerank import Reranker


def compile_context(
    query: str,
    document_scope: DocumentScope | Sequence[IRDocument],
    token_budget: int,
    config: CompilerConfig | None = None,
    *,
    tokenizer: TokenCounter | None = None,
    embedder: EmbeddingModel | None = None,
    reranker: Reranker | None = None,
    hybrid_index: HybridIndex | None = None,
    retrieval_token_budget: int | None = None,
    ranked_evidence: Sequence[RankedEvidence] | None = None,
    structural_evidence: Sequence[RankedEvidence] | None = None,
    query_cache: CompilerQueryCache | None = None,
) -> ContextPacket:
    """Compile query-specific evidence without an LLM or budget overflow."""
    packet, _trace = compile_context_with_trace(
        query,
        document_scope,
        token_budget,
        config,
        tokenizer=tokenizer,
        embedder=embedder,
        reranker=reranker,
        hybrid_index=hybrid_index,
        retrieval_token_budget=retrieval_token_budget,
        ranked_evidence=ranked_evidence,
        structural_evidence=structural_evidence,
        query_cache=query_cache,
    )
    return packet


def compile_context_with_trace(
    query: str,
    document_scope: DocumentScope | Sequence[IRDocument],
    token_budget: int,
    config: CompilerConfig | None = None,
    *,
    tokenizer: TokenCounter | None = None,
    embedder: EmbeddingModel | None = None,
    reranker: Reranker | None = None,
    hybrid_index: HybridIndex | None = None,
    retrieval_token_budget: int | None = None,
    ranked_evidence: Sequence[RankedEvidence] | None = None,
    structural_evidence: Sequence[RankedEvidence] | None = None,
    query_cache: CompilerQueryCache | None = None,
) -> tuple[ContextPacket, CompilerTrace]:
    """Compile context and expose immutable candidate stages for diagnostics."""
    if not query.strip():
        raise ValueError("query must not be empty")
    if token_budget < 0:
        raise ValueError("token_budget must not be negative")
    my_config = config or CompilerConfig()
    scope = (
        document_scope
        if isinstance(document_scope, DocumentScope)
        else DocumentScope.from_documents(document_scope)
    )
    document_ids = [document.id for document in scope.documents]
    if len(document_ids) != len(set(document_ids)):
        raise ValueError("document_scope contains duplicate document IDs")

    counter = tokenizer or TiktokenTokenCounter(my_config.retrieval.tokenizer_name)
    if hybrid_index is not None and hybrid_index.config != my_config.retrieval:
        raise ValueError("hybrid_index configuration differs from compiler config")
    index = hybrid_index
    if index is None:
        chunks = node_chunks(scope.documents, tokenizer=counter)
        index = HybridIndex(
            chunks,
            config=my_config.retrieval,
            tokenizer=counter,
            embedder=embedder,
            reranker=reranker,
        )
    if ranked_evidence is None:
        ranked = index.retrieve(
            query,
            token_budget=(
                retrieval_token_budget
                if retrieval_token_budget is not None
                else token_budget
            ),
            document_ids=set(document_ids),
        )
        ranked = retrieve_faceted(
            index,
            query,
            ranked,
            token_budget=(
                retrieval_token_budget
                if retrieval_token_budget is not None
                else token_budget
            ),
            document_ids=set(document_ids),
            config=my_config,
        )
    else:
        ranked = tuple(ranked_evidence)
        unexpected_documents = {
            evidence.chunk.document_id for evidence in ranked
        }.difference(document_ids)
        if unexpected_documents:
            raise ValueError(
                "ranked_evidence contains documents outside document_scope: "
                f"{sorted(unexpected_documents)}"
            )
    structural_ranked = _structural_evidence(
        query,
        scope,
        token_budget=(
            retrieval_token_budget
            if retrieval_token_budget is not None
            else token_budget
        ),
        config=my_config,
        tokenizer=counter,
        node_index=index,
        supplied=structural_evidence,
    )
    if query_cache is not None:
        query_cache.begin_compilation()
    expanded = expand_candidates(
        query,
        ranked,
        scope.documents,
        source_documents=scope.source_documents,
        token_budget=token_budget,
        config=my_config,
        tokenizer=counter,
        reranker=index.reranker,
        query_cache=query_cache,
    )
    fused = _fuse_structural_candidates(expanded, structural_ranked)
    unique = deduplicate_candidates(fused, scope.documents)[
        : my_config.max_expanded_candidates
    ]
    packet = pack_candidates(
        query,
        unique,
        token_budget=token_budget,
        tokenizer=counter,
        metadata={
            "arm": "compiler",
            "compiler_version": COMPILER_VERSION,
            "compiler_config": _config_hash(my_config),
            "embedding_model": index.embedder.name,
            "reranker_model": index.reranker.name,
            "tokenizer": counter.name,
        },
        coverage_facets=(
            query_facets(
                query,
                limit=my_config.query_facet_limit,
                min_terms=my_config.query_facet_min_terms,
                include_references=my_config.query_reference_facets_enabled,
                reference_limit=my_config.query_reference_facet_limit,
            )[: my_config.facet_coverage_limit]
            if my_config.facet_coverage_packing_enabled
            else ()
        ),
    )
    return packet, CompilerTrace(
        ranked_evidence=tuple(ranked),
        expanded_candidates=tuple(expanded),
        fused_candidates=tuple(fused),
        deduplicated_candidates=tuple(unique),
    )


def _structural_evidence(
    query: str,
    scope: DocumentScope,
    *,
    token_budget: int,
    config: CompilerConfig,
    tokenizer: TokenCounter,
    node_index: HybridIndex,
    supplied: Sequence[RankedEvidence] | None,
) -> tuple[RankedEvidence, ...]:
    if not config.structural_fusion_enabled:
        if supplied is not None:
            raise ValueError(
                "structural_evidence requires structural_fusion_enabled"
            )
        return ()
    document_ids = {document.id for document in scope.documents}
    if supplied is not None:
        ranked = tuple(supplied)
    else:
        missing_sources = document_ids.difference(scope.source_documents)
        if missing_sources:
            raise ValueError(
                "structural fusion requires source documents for every IR document"
            )
        structural_index = HybridIndex.build(
            scope.documents,
            arm=RetrievalArm.STRUCTURAL,
            config=config.retrieval,
            source_documents=scope.source_documents,
            tokenizer=tokenizer,
            embedder=node_index.embedder,
            reranker=node_index.reranker,
        )
        ranked = structural_index.retrieve(
            query,
            token_budget=token_budget,
            document_ids=document_ids,
        )
        ranked = retrieve_faceted(
            structural_index,
            query,
            ranked,
            token_budget=token_budget,
            document_ids=document_ids,
            config=config,
        )
    unexpected_documents = {
        evidence.chunk.document_id for evidence in ranked
    }.difference(document_ids)
    if unexpected_documents:
        raise ValueError(
            "structural_evidence contains documents outside document_scope: "
            f"{sorted(unexpected_documents)}"
        )
    return ranked


def _fuse_structural_candidates(
    expanded: Sequence[CompilerCandidate],
    structural: Sequence[RankedEvidence],
) -> tuple[CompilerCandidate, ...]:
    """Interleave bounded node and structural rankings before deduplication."""
    if not structural:
        return tuple(expanded)
    core = [candidate for candidate in expanded if candidate.priority_tier == 0]
    backfill = [candidate for candidate in expanded if candidate.priority_tier > 0]
    structural_candidates = [
        CompilerCandidate(
            chunk=evidence.chunk.model_copy(update={"arm": RetrievalArm.COMPILER}),
            scores=evidence.scores,
            origin_rank=evidence.rank,
            expansion_order=len(expanded) + offset,
        )
        for offset, evidence in enumerate(structural)
    ]
    fused = []
    for index in range(max(len(core), len(structural_candidates))):
        if index < len(core):
            fused.append(core[index])
        if index < len(structural_candidates):
            fused.append(structural_candidates[index])
    fused.extend(backfill)
    return tuple(fused)


def _config_hash(config: CompilerConfig) -> str:
    value = json.dumps(
        config.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode()).hexdigest()
