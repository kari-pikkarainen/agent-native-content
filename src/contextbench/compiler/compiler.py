"""Public deterministic context compiler API."""

import hashlib
import json
from collections.abc import Sequence

from contextbench.compiler.anchors import anchor_node_evidence
from contextbench.compiler.candidates import node_chunks
from contextbench.compiler.dedupe import deduplicate_candidates
from contextbench.compiler.expand import expand_candidates
from contextbench.compiler.facets import retrieve_faceted
from contextbench.compiler.models import (
    COMPILER_VERSION,
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
    structural_anchor_evidence: Sequence[RankedEvidence] | None = None,
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
        structural_anchor_evidence=structural_anchor_evidence,
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
    structural_anchor_evidence: Sequence[RankedEvidence] | None = None,
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
    if my_config.structural_anchor_enabled:
        if ranked_evidence is not None:
            raise ValueError(
                "ranked_evidence cannot be supplied in structural-anchor mode"
            )
        structural_ranked = (
            tuple(structural_anchor_evidence)
            if structural_anchor_evidence is not None
            else _retrieve_structural_anchors(
                query,
                scope,
                token_budget=(
                    retrieval_token_budget
                    if retrieval_token_budget is not None
                    else token_budget
                ),
                config=my_config,
                tokenizer=counter,
                embedder=index.embedder,
                reranker=index.reranker,
            )
        )
        _validate_ranked_scope(
            structural_ranked,
            document_ids,
            name="structural_anchor_evidence",
        )
        ranked = anchor_node_evidence(
            structural_ranked,
            scope.documents,
            tokenizer=counter,
            limit=my_config.structural_anchor_candidate_limit,
        )
    elif structural_anchor_evidence is not None:
        raise ValueError(
            "structural_anchor_evidence requires structural_anchor_enabled"
        )
    elif ranked_evidence is None:
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
        _validate_ranked_scope(ranked, document_ids, name="ranked_evidence")
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
    unique = deduplicate_candidates(expanded, scope.documents)[
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
    )
    return packet, CompilerTrace(
        ranked_evidence=tuple(ranked),
        expanded_candidates=tuple(expanded),
        deduplicated_candidates=tuple(unique),
    )


def _retrieve_structural_anchors(
    query: str,
    scope: DocumentScope,
    *,
    token_budget: int,
    config: CompilerConfig,
    tokenizer: TokenCounter,
    embedder: EmbeddingModel,
    reranker: Reranker,
) -> tuple[RankedEvidence, ...]:
    document_ids = {document.id for document in scope.documents}
    missing_sources = document_ids.difference(scope.source_documents)
    if missing_sources:
        raise ValueError(
            "structural-anchor mode requires source documents for every IR document"
        )
    index = HybridIndex.build(
        scope.documents,
        arm=RetrievalArm.STRUCTURAL,
        config=config.retrieval,
        source_documents=scope.source_documents,
        tokenizer=tokenizer,
        embedder=embedder,
        reranker=reranker,
    )
    return index.retrieve(
        query,
        token_budget=token_budget,
        document_ids=document_ids,
    )


def _validate_ranked_scope(
    ranked: Sequence[RankedEvidence],
    document_ids: Sequence[str],
    *,
    name: str,
) -> None:
    unexpected_documents = {
        evidence.chunk.document_id for evidence in ranked
    }.difference(document_ids)
    if unexpected_documents:
        raise ValueError(
            f"{name} contains documents outside document_scope: "
            f"{sorted(unexpected_documents)}"
        )


def _config_hash(config: CompilerConfig) -> str:
    value = json.dumps(
        config.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode()).hexdigest()
