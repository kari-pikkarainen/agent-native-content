"""Shared sparse+dense retrieval, RRF fusion, and derived index artifacts."""

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from docling_core.types.doc import DoclingDocument

from contextbench.ir.models import IRDocument
from contextbench.ir.tokenizer import TiktokenTokenCounter, TokenCounter
from contextbench.retrieval.chunking import fixed_chunks, structural_chunks
from contextbench.retrieval.embeddings import (
    EmbeddingModel,
    HashEmbeddingModel,
    SentenceTransformerEmbeddingModel,
)
from contextbench.retrieval.models import (
    ContextPacket,
    RankedEvidence,
    RetrievalArm,
    RetrievalChunk,
    RetrievalConfig,
    RetrievalScores,
)
from contextbench.retrieval.rerank import (
    LexicalOverlapReranker,
    Reranker,
    SentenceTransformerCrossEncoderReranker,
)
from contextbench.retrieval.sparse import BM25Index


class HybridIndex:
    """A shared BM25/dense index with deterministic hybrid ranking."""

    def __init__(
        self,
        chunks: Sequence[RetrievalChunk],
        *,
        config: RetrievalConfig,
        embedder: EmbeddingModel | None = None,
        reranker: Reranker | None = None,
        tokenizer: TokenCounter | None = None,
    ) -> None:
        self.chunks = tuple(chunks)
        self.config = config
        self.embedder = embedder or embedding_model_from_config(config)
        self.reranker = reranker or reranker_from_config(config)
        self.tokenizer = tokenizer or TiktokenTokenCounter(config.tokenizer_name)
        self.sparse = BM25Index(
            self.chunks,
            k1=config.sparse_k1,
            b=config.sparse_b,
        )
        self._vectors = self.embedder.embed([chunk.text for chunk in self.chunks])

    @classmethod
    def build(
        cls,
        documents: Sequence[IRDocument],
        *,
        arm: RetrievalArm,
        config: RetrievalConfig | None = None,
        source_documents: Mapping[str, DoclingDocument] | None = None,
        tokenizer: TokenCounter | None = None,
        embedder: EmbeddingModel | None = None,
        reranker: Reranker | None = None,
        artifacts_root: Path | None = None,
    ) -> "HybridIndex":
        my_config = config or RetrievalConfig()
        counter = tokenizer or TiktokenTokenCounter(my_config.tokenizer_name)
        chunks: list[RetrievalChunk] = []
        for document in documents:
            if arm == RetrievalArm.FIXED:
                chunks.extend(
                    fixed_chunks(document, config=my_config, tokenizer=counter)
                )
            else:
                if source_documents is None or document.id not in source_documents:
                    raise ValueError(
                        "structural retrieval requires the source DoclingDocument "
                        f"for {document.id}"
                    )
                chunks.extend(
                    structural_chunks(
                        document,
                        source_documents[document.id],
                        config=my_config,
                        tokenizer=counter,
                    )
                )
        index = cls(
            chunks,
            config=my_config,
            embedder=embedder,
            reranker=reranker,
            tokenizer=counter,
        )
        if artifacts_root is not None:
            index.save(artifacts_root, documents=documents, arm=arm)
        return index

    def retrieve(
        self,
        query: str,
        *,
        limit: int | None = None,
        document_ids: set[str] | None = None,
    ) -> tuple[RankedEvidence, ...]:
        """Run sparse, dense, RRF, and reranking stages."""
        candidate_limit = limit or self.config.candidate_limit
        allowed_indices = (
            {
                index
                for index, chunk in enumerate(self.chunks)
                if chunk.document_id in document_ids
            }
            if document_ids is not None
            else None
        )
        sparse_hits = self.sparse.search(
            query,
            candidate_limit,
            allowed_indices=allowed_indices,
        )
        dense_hits = self._dense_search(
            query,
            candidate_limit,
            allowed_indices=allowed_indices,
        )
        sparse_ranks = {
            index: rank for rank, (index, _score) in enumerate(sparse_hits, 1)
        }
        dense_ranks = {
            index: rank for rank, (index, _score) in enumerate(dense_hits, 1)
        }
        sparse_scores = dict(sparse_hits)
        dense_scores = dict(dense_hits)
        candidate_indices = sorted(
            set(sparse_ranks) | set(dense_ranks),
            key=lambda index: self.chunks[index].id,
        )
        fused = {
            index: (
                1 / (self.config.rrf_k + sparse_ranks[index])
                if index in sparse_ranks
                else 0
            )
            + (
                1 / (self.config.rrf_k + dense_ranks[index])
                if index in dense_ranks
                else 0
            )
            for index in candidate_indices
        }
        candidate_indices.sort(key=lambda index: (-fused[index], self.chunks[index].id))
        candidate_indices = candidate_indices[: self.config.rerank_limit]
        rerank_scores = self.reranker.score(
            query,
            [self.chunks[index] for index in candidate_indices],
        )
        ranked = sorted(
            zip(candidate_indices, rerank_scores, strict=True),
            key=lambda pair: (-pair[1], -fused[pair[0]], self.chunks[pair[0]].id),
        )
        return tuple(
            RankedEvidence(
                rank=rank,
                chunk=self.chunks[index],
                scores=RetrievalScores(
                    dense=dense_scores.get(index, 0.0),
                    sparse=sparse_scores.get(index, 0.0),
                    fused=fused[index],
                    reranked=score,
                ),
            )
            for rank, (index, score) in enumerate(ranked, 1)
        )

    def pack(
        self,
        query: str,
        *,
        token_budget: int,
        limit: int | None = None,
        document_ids: set[str] | None = None,
    ) -> ContextPacket:
        """Pack ranked evidence without exceeding the requested budget."""
        ranked = self.retrieve(
            query,
            limit=limit,
            document_ids=document_ids,
        )
        return pack_evidence(
            query,
            ranked,
            token_budget=token_budget,
            tokenizer=self.tokenizer,
            metadata={
                "arm": self.chunks[0].arm.value if self.chunks else "unknown",
                "embedding_model": self.embedder.name,
                "reranker_model": self.reranker.name,
                "retrieval_config": _config_hash(self.config),
            },
        )

    def save(
        self,
        artifacts_root: Path,
        *,
        documents: Sequence[IRDocument],
        arm: RetrievalArm,
    ) -> Path:
        """Persist the derived index under a deterministic content/config hash."""
        key = _index_key(
            documents,
            arm=arm,
            config=self.config,
            chunks=self.chunks,
            embedding_model=self.embedder.name,
            embedding_version=self.embedder.version,
            reranker_model=self.reranker.name,
            reranker_version=self.reranker.version,
            tokenizer=self.tokenizer.name,
            tokenizer_version=self.tokenizer.version,
        )
        output_dir = artifacts_root / "indexes" / key
        output_dir.mkdir(parents=True, exist_ok=True)
        value = {
            "arm": arm.value,
            "config": self.config.model_dump(mode="json"),
            "chunks": [chunk.model_dump(mode="json") for chunk in self.chunks],
            "vectors": self._vectors,
            "sparse_parameters": {
                "k1": self.config.sparse_k1,
                "b": self.config.sparse_b,
            },
            "embedding_model": self.embedder.name,
            "embedding_version": self.embedder.version,
            "reranker_model": self.reranker.name,
            "reranker_version": self.reranker.version,
            "tokenizer": self.tokenizer.name,
            "tokenizer_version": self.tokenizer.version,
        }
        _atomic_json(output_dir / "index.json", value)
        return output_dir

    def _dense_search(
        self,
        query: str,
        limit: int,
        *,
        allowed_indices: set[int] | None = None,
    ) -> list[tuple[int, float]]:
        query_vector = self.embedder.embed([query])[0]
        scores = [
            (_cosine(query_vector, vector), index)
            for index, vector in enumerate(self._vectors)
            if allowed_indices is None or index in allowed_indices
        ]
        scores.sort(key=lambda pair: (-pair[0], self.chunks[pair[1]].id))
        return [(index, score) for score, index in scores[:limit]]


def pack_evidence(
    query: str,
    ranked: Sequence[RankedEvidence],
    *,
    token_budget: int,
    tokenizer: TokenCounter,
    metadata: dict[str, str],
) -> ContextPacket:
    """Deduplicate by source and pack in reranked order."""
    items = []
    used_sources: set[tuple[str, ...]] = set()
    total = 0
    for evidence in ranked:
        chunk = evidence.chunk
        source_key = (chunk.document_id, *chunk.source_item_ids)
        if source_key in used_sources:
            continue
        token_count = tokenizer.count(chunk.text)
        if total + token_count > token_budget:
            continue
        used_sources.add(source_key)
        evidence_id = "evidence_" + hashlib.sha256(chunk.id.encode()).hexdigest()
        items.append(
            {
                "evidence_id": evidence_id,
                "document_id": chunk.document_id,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "heading_path": chunk.heading_path,
                "content": chunk.text,
                "token_count": token_count,
                "source_node_ids": chunk.source_node_ids,
                "source_item_ids": chunk.source_item_ids,
                "scores": evidence.scores,
            }
        )
        total += token_count
    from contextbench.retrieval.models import ContextItem

    return ContextPacket(
        query=query,
        token_budget=token_budget,
        token_count=total,
        items=tuple(ContextItem.model_validate(item) for item in items),
        metadata=metadata,
    )


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def embedding_model_from_config(config: RetrievalConfig) -> EmbeddingModel:
    """Construct the configured dense model lazily."""
    if config.embedding_model.startswith("hash-"):
        return HashEmbeddingModel(config.embedding_dimensions)
    return SentenceTransformerEmbeddingModel(config.embedding_model)


def reranker_from_config(config: RetrievalConfig) -> Reranker:
    """Construct the configured reranker lazily."""
    if config.reranker_model == "lexical-overlap-v1":
        return LexicalOverlapReranker()
    return SentenceTransformerCrossEncoderReranker(config.reranker_model)


def _config_hash(config: RetrievalConfig) -> str:
    serialized = json.dumps(
        config.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def _index_key(
    documents: Sequence[IRDocument],
    *,
    arm: RetrievalArm,
    config: RetrievalConfig,
    chunks: Sequence[RetrievalChunk],
    embedding_model: str,
    embedding_version: str,
    reranker_model: str,
    reranker_version: str,
    tokenizer: str,
    tokenizer_version: str,
) -> str:
    payload = {
        "arm": arm.value,
        "config": config.model_dump(mode="json"),
        "documents": [document.id for document in documents],
        "chunks": [chunk.id for chunk in chunks],
        "embedding_model": embedding_model,
        "embedding_version": embedding_version,
        "reranker_model": reranker_model,
        "reranker_version": reranker_version,
        "tokenizer": tokenizer,
        "tokenizer_version": tokenizer_version,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    descriptor, raw_temp_path = tempfile.mkstemp(
        prefix="index-", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temp_path = Path(raw_temp_path)
    try:
        temp_path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
