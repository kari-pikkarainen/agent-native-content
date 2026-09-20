"""Shared retrieval primitives for benchmark Arms A and B."""

from contextbench.retrieval.chunking import fixed_chunks, structural_chunks
from contextbench.retrieval.embeddings import (
    HashEmbeddingModel,
    SentenceTransformerEmbeddingModel,
)
from contextbench.retrieval.index import HybridIndex, pack_evidence
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
    "pack_evidence",
    "structural_chunks",
]
