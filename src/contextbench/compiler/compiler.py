"""Public deterministic context compiler API."""

import hashlib
import json
from collections.abc import Sequence

from contextbench.compiler.candidates import node_chunks
from contextbench.compiler.corpus import CompilerCorpusIndex
from contextbench.compiler.dedupe import deduplicate_candidates
from contextbench.compiler.expand import expand_candidates
from contextbench.compiler.facets import query_facets, retrieve_faceted
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
from contextbench.retrieval.models import ContextPacket, RankedEvidence
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
    query_cache: CompilerQueryCache | None = None,
    corpus_index: CompilerCorpusIndex | None = None,
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
        query_cache=query_cache,
        corpus_index=corpus_index,
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
    query_cache: CompilerQueryCache | None = None,
    corpus_index: CompilerCorpusIndex | None = None,
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
    if (
        corpus_index is not None
        and corpus_index.retrieval_config != my_config.retrieval
    ):
        raise ValueError("corpus_index configuration differs from compiler config")
    if corpus_index is not None:
        missing_documents = set(document_ids).difference(corpus_index.documents_by_id)
        if missing_documents:
            raise ValueError(
                "corpus_index is missing document_scope IDs: "
                f"{sorted(missing_documents)}"
            )
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
        ranked = index.retrieve_candidates(
            query,
            token_budget=(
                retrieval_token_budget
                if retrieval_token_budget is not None
                else token_budget
            ),
            document_ids=set(document_ids),
            maximum_rerank_limit=my_config.node_rerank_candidate_limit,
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
        corpus_index=corpus_index,
    )
    unique = deduplicate_candidates(expanded, scope.documents)[
        : my_config.max_expanded_candidates
    ]
    active_operators = []
    if my_config.query_faceting_enabled and query_facets(
        query,
        limit=my_config.query_facet_limit,
        min_terms=my_config.query_facet_min_terms,
    ):
        active_operators.append("query_faceting")
    packet = pack_candidates(
        query,
        unique,
        token_budget=token_budget,
        tokenizer=counter,
        strategy=my_config.packing_strategy,
        metadata={
            "arm": "compiler",
            "compiler_version": COMPILER_VERSION,
            "compiler_config": _config_hash(my_config),
            "embedding_model": index.embedder.name,
            "reranker_model": index.reranker.name,
            "tokenizer": counter.name,
            "packing_strategy": my_config.packing_strategy,
            "active_operators": ",".join(active_operators),
        },
    )
    return packet, CompilerTrace(
        ranked_evidence=tuple(ranked),
        expanded_candidates=tuple(expanded),
        deduplicated_candidates=tuple(unique),
    )


def _config_hash(config: CompilerConfig) -> str:
    value = json.dumps(
        config.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode()).hexdigest()
