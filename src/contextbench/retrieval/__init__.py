"""Shared retrieval primitives for benchmark Arms A and B."""

from contextbench.retrieval.chunking import fixed_chunks, structural_chunks
from contextbench.retrieval.embeddings import (
    HashEmbeddingModel,
    SentenceTransformerEmbeddingModel,
)
from contextbench.retrieval.index import (
    HybridIndex,
    embedding_model_from_config,
    pack_evidence,
    reranker_from_config,
)
from contextbench.retrieval.long_context import long_context_chunks, rank_long_context
from contextbench.retrieval.models import (
    ContextItem,
    ContextPacket,
    RankedEvidence,
    RetrievalArm,
    RetrievalChunk,
    RetrievalConfig,
    RetrievalScores,
)
from contextbench.retrieval.rerank import (
    LexicalOverlapReranker,
    SentenceTransformerCrossEncoderReranker,
)

__all__ = [
    "ContextItem",
    "ContextPacket",
    "HashEmbeddingModel",
    "HybridIndex",
    "LexicalOverlapReranker",
    "RankedEvidence",
    "RetrievalArm",
    "RetrievalChunk",
    "RetrievalConfig",
    "RetrievalScores",
    "SentenceTransformerCrossEncoderReranker",
    "SentenceTransformerEmbeddingModel",
    "fixed_chunks",
    "embedding_model_from_config",
    "long_context_chunks",
    "pack_evidence",
    "rank_long_context",
    "reranker_from_config",
    "structural_chunks",
]
