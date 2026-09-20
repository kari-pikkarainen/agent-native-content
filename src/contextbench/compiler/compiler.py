"""Public deterministic context compiler API."""

import hashlib
import json
from collections.abc import Sequence

from contextbench.compiler.candidates import node_chunks
from contextbench.compiler.dedupe import deduplicate_candidates
from contextbench.compiler.expand import expand_candidates
from contextbench.compiler.models import (
    COMPILER_VERSION,
    CompilerConfig,
    DocumentScope,
)
from contextbench.compiler.pack import pack_candidates
from contextbench.ir.models import IRDocument
from contextbench.ir.tokenizer import TiktokenTokenCounter, TokenCounter
from contextbench.retrieval.embeddings import EmbeddingModel
from contextbench.retrieval.index import HybridIndex
from contextbench.retrieval.models import ContextPacket
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
) -> ContextPacket:
    """Compile query-specific evidence without an LLM or budget overflow."""
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
    ranked = index.retrieve(
        query,
        token_budget=(
            retrieval_token_budget
            if retrieval_token_budget is not None
            else token_budget
        ),
        document_ids=set(document_ids),
    )
    expanded = expand_candidates(
        query,
        ranked,
        scope.documents,
        source_documents=scope.source_documents,
        token_budget=token_budget,
        config=my_config,
        tokenizer=counter,
        reranker=index.reranker,
    )
    unique = deduplicate_candidates(expanded, scope.documents)
    return pack_candidates(
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


def _config_hash(config: CompilerConfig) -> str:
    value = json.dumps(
        config.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode()).hexdigest()
