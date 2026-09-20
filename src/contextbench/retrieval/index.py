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
        self._vectors = self.embedder.embed(
            [chunk.retrieval_text for chunk in self.chunks]
        )

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
        token_budget: int | None = None,
        document_ids: set[str] | None = None,
    ) -> tuple[RankedEvidence, ...]:
        """Run sparse, dense, RRF, and reranking stages."""
        candidates = self.retrieve_candidates(
            query,
            limit=limit,
            token_budget=token_budget,
            document_ids=document_ids,
        )
        return self.rerank(query, candidates)

    def retrieve_candidates(
        self,
        query: str,
        *,
        limit: int | None = None,
        token_budget: int | None = None,
        document_ids: set[str] | None = None,
    ) -> tuple[RankedEvidence, ...]:
        """Run sparse, dense, and RRF stages without the cross-encoder."""
        if token_budget is not None and token_budget < 0:
            raise ValueError("token_budget must not be negative")
        minimum_candidate_limit = limit or self.config.candidate_limit
        search_limit = (
            self.config.max_candidate_limit
            if token_budget is not None
            else minimum_candidate_limit
        )
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
            search_limit,
            allowed_indices=allowed_indices,
        )
        dense_hits = self._dense_search(
            query,
            search_limit,
            allowed_indices=allowed_indices,
        )
        if token_budget is not None:
            candidate_token_target = round(
                token_budget * self.config.candidate_token_multiplier
            )
            sparse_hits = self._trim_hits(
                sparse_hits,
                minimum_count=minimum_candidate_limit,
                token_target=candidate_token_target,
            )
            dense_hits = self._trim_hits(
                dense_hits,
                minimum_count=minimum_candidate_limit,
                token_target=candidate_token_target,
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
        candidate_indices = self._unique_by_search_text(candidate_indices)
        rerank_limit = self.config.rerank_limit
        if token_budget is not None:
            rerank_token_target = round(
                token_budget * self.config.rerank_token_multiplier
            )
            candidate_indices = self._trim_indices(
                candidate_indices,
                minimum_count=rerank_limit,
                token_target=rerank_token_target,
                maximum_count=self.config.max_rerank_limit,
            )
        else:
            candidate_indices = candidate_indices[:rerank_limit]
        return tuple(
            RankedEvidence(
                rank=rank,
                chunk=self.chunks[index],
                scores=RetrievalScores(
                    dense=dense_scores.get(index, 0.0),
                    sparse=sparse_scores.get(index, 0.0),
                    fused=fused[index],
                    reranked=fused[index],
                ),
            )
            for rank, index in enumerate(candidate_indices, 1)
        )

    def rerank(
        self,
        query: str,
        candidates: Sequence[RankedEvidence],
    ) -> tuple[RankedEvidence, ...]:
        """Apply the configured reranker once to an existing candidate pool."""
        scores = self.reranker.score(
            query,
            [candidate.chunk for candidate in candidates],
        )
        ranked = sorted(
            zip(candidates, scores, strict=True),
            key=lambda pair: (
                -pair[1],
                -pair[0].scores.fused,
                pair[0].chunk.id,
            ),
        )
        return tuple(
            candidate.model_copy(
                update={
                    "rank": rank,
                    "scores": candidate.scores.model_copy(
                        update={"reranked": score}
                    ),
                }
            )
            for rank, (candidate, score) in enumerate(ranked, 1)
        )

    def pack(
        self,
        query: str,
        *,
        token_budget: int,
        retrieval_token_budget: int | None = None,
        limit: int | None = None,
        document_ids: set[str] | None = None,
    ) -> ContextPacket:
        """Pack ranked evidence without exceeding the requested budget."""
        ranked = self.retrieve(
            query,
            limit=limit,
            token_budget=(
                retrieval_token_budget
                if retrieval_token_budget is not None
                else token_budget
            ),
            document_ids=document_ids,
        )
        return self.pack_ranked(query, ranked, token_budget=token_budget)

    def pack_ranked(
        self,
        query: str,
        ranked: Sequence[RankedEvidence],
        *,
        token_budget: int,
    ) -> ContextPacket:
        """Pack an existing ranking without repeating retrieval or reranking."""
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

    def _trim_hits(
        self,
        hits: Sequence[tuple[int, float]],
        *,
        minimum_count: int,
        token_target: int,
    ) -> list[tuple[int, float]]:
        selected: list[tuple[int, float]] = []
        token_count = 0
        for hit in hits:
            selected.append(hit)
            token_count += self.chunks[hit[0]].token_count
            if len(selected) >= minimum_count and token_count >= token_target:
                break
        return selected

    def _unique_by_search_text(self, indices: Sequence[int]) -> list[int]:
        seen: set[str] = set()
        selected: list[int] = []
        for index in indices:
            normalized = " ".join(self.chunks[index].retrieval_text.casefold().split())
            if normalized in seen:
                continue
            seen.add(normalized)
            selected.append(index)
        return selected

    def _trim_indices(
        self,
        indices: Sequence[int],
        *,
        minimum_count: int,
        token_target: int,
        maximum_count: int,
    ) -> list[int]:
        selected: list[int] = []
        token_count = 0
        for index in indices[:maximum_count]:
            selected.append(index)
            token_count += self.chunks[index].token_count
            if len(selected) >= minimum_count and token_count >= token_target:
                break
        return selected


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
