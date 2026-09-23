"""Shared sparse+dense retrieval, RRF fusion, and derived index artifacts."""

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from itertools import groupby
from pathlib import Path

import numpy as np
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
from contextbench.retrieval.rendering import (
    DEFAULT_BUDGET_ACCOUNTING,
    DEFAULT_EVIDENCE_RENDER_VERSION,
    BudgetAccounting,
    EvidenceBudget,
    EvidenceRenderVersion,
    verified_count,
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
        reuse_pair_scores: bool = False,
    ) -> None:
        self.chunks = tuple(chunks)
        self.config = config
        # Off by default, and it must stay that way until someone measures the
        # ranking change. See ``_scored_pairs``: reusing a score across batches
        # is not result-neutral, because this cross-encoder is not bitwise
        # invariant to batch composition.
        self.reuse_pair_scores = reuse_pair_scores
        self.embedder = embedder or embedding_model_from_config(config)
        self.reranker = reranker or reranker_from_config(config)
        self.tokenizer = tokenizer or TiktokenTokenCounter(config.tokenizer_name)
        self.sparse = BM25Index(
            self.chunks,
            k1=config.sparse_k1,
            b=config.sparse_b,
        )
        self._vectors = np.asarray(
            self.embedder.embed([chunk.retrieval_text for chunk in self.chunks]),
            dtype=np.float64,
        )
        self._document_indices = _document_indices(self.chunks)
        self._retrieval_cache: dict[tuple[object, ...], tuple[RankedEvidence, ...]] = {}
        self._rerank_cache: dict[tuple[object, ...], tuple[RankedEvidence, ...]] = {}
        self._pair_score_cache: dict[tuple[str, str], float] = {}

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
        return cls.from_chunks(
            chunks,
            config=my_config,
            embedder=embedder,
            reranker=reranker,
            tokenizer=counter,
            artifacts_root=artifacts_root,
            documents=documents,
            arm=arm,
        )

    @classmethod
    def from_chunks(
        cls,
        chunks: Sequence[RetrievalChunk],
        *,
        config: RetrievalConfig,
        documents: Sequence[IRDocument],
        arm: RetrievalArm,
        artifacts_root: Path | None = None,
        embedder: EmbeddingModel | None = None,
        reranker: Reranker | None = None,
        tokenizer: TokenCounter | None = None,
    ) -> "HybridIndex":
        """Load a verified derived index when present, otherwise build it."""
        counter = tokenizer or TiktokenTokenCounter(config.tokenizer_name)
        dense_model = embedder or embedding_model_from_config(config)
        ranking_model = reranker or reranker_from_config(config)
        if artifacts_root is not None:
            key = _index_key(
                documents,
                arm=arm,
                config=config,
                chunks=chunks,
                embedding_model=dense_model.name,
                embedding_version=dense_model.version,
                embedding_revision=dense_model.revision,
                reranker_model=ranking_model.name,
                reranker_version=ranking_model.version,
                reranker_revision=ranking_model.revision,
                tokenizer=counter.name,
                tokenizer_version=counter.version,
            )
            artifact_path = artifacts_root / "indexes" / key / "index.json"
            if artifact_path.is_file():
                return cls.load(
                    artifact_path,
                    config=config,
                    chunks=chunks,
                    embedder=dense_model,
                    reranker=ranking_model,
                    tokenizer=counter,
                )
        index = cls(
            chunks,
            config=config,
            embedder=dense_model,
            reranker=ranking_model,
            tokenizer=counter,
        )
        if artifacts_root is not None:
            index.save(artifacts_root, documents=documents, arm=arm)
        return index

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        config: RetrievalConfig,
        chunks: Sequence[RetrievalChunk],
        embedder: EmbeddingModel,
        reranker: Reranker,
        tokenizer: TokenCounter,
    ) -> "HybridIndex":
        """Load and validate a deterministic index artifact without re-embedding."""
        value = json.loads(path.read_text(encoding="utf-8"))
        expected_metadata = {
            "embedding_model": embedder.name,
            "embedding_version": embedder.version,
            "embedding_revision": embedder.revision,
            "reranker_model": reranker.name,
            "reranker_version": reranker.version,
            "reranker_revision": reranker.revision,
            "tokenizer": tokenizer.name,
            "tokenizer_version": tokenizer.version,
        }
        for field_name, expected in expected_metadata.items():
            if value.get(field_name) != expected:
                raise ValueError(
                    f"index artifact {field_name} does not match configured value"
                )
        if RetrievalConfig.model_validate(value.get("config")) != config:
            raise ValueError("index artifact retrieval config does not match")
        loaded_chunks = tuple(
            RetrievalChunk.model_validate(chunk) for chunk in value.get("chunks", ())
        )
        if loaded_chunks != tuple(chunks):
            raise ValueError("index artifact chunks do not match derived chunks")
        vectors = value.get("vectors")
        if not isinstance(vectors, list) or len(vectors) != len(loaded_chunks):
            raise ValueError("index artifact vectors do not match derived chunks")
        if vectors:
            dimensions = len(vectors[0])
            if dimensions == 0 or any(
                not isinstance(vector, list) or len(vector) != dimensions
                for vector in vectors
            ):
                raise ValueError("index artifact vectors have inconsistent dimensions")

        index = cls.__new__(cls)
        index.chunks = loaded_chunks
        index.config = config
        index.embedder = embedder
        index.reranker = reranker
        index.tokenizer = tokenizer
        index.sparse = BM25Index(
            loaded_chunks,
            k1=config.sparse_k1,
            b=config.sparse_b,
        )
        index._vectors = np.asarray(vectors, dtype=np.float64)
        index._document_indices = _document_indices(loaded_chunks)
        index._retrieval_cache = {}
        index._rerank_cache = {}
        index._pair_score_cache = {}
        index.reuse_pair_scores = False
        return index

    def retrieve(
        self,
        query: str,
        *,
        limit: int | None = None,
        token_budget: int | None = None,
        document_ids: set[str] | None = None,
        maximum_rerank_limit: int | None = None,
    ) -> tuple[RankedEvidence, ...]:
        """Run sparse, dense, RRF, and reranking stages."""
        cache_key = _query_cache_key(
            query,
            limit=limit,
            token_budget=token_budget,
            document_ids=document_ids,
            maximum_rerank_limit=maximum_rerank_limit,
        )
        cached = self._retrieval_cache.get(cache_key)
        if cached is not None:
            return cached
        candidates = self.retrieve_candidates(
            query,
            limit=limit,
            token_budget=token_budget,
            document_ids=document_ids,
            maximum_rerank_limit=maximum_rerank_limit,
        )
        ranked = self.rerank(query, candidates)
        self._retrieval_cache[cache_key] = ranked
        return ranked

    def retrieve_candidates(
        self,
        query: str,
        *,
        limit: int | None = None,
        token_budget: int | None = None,
        document_ids: set[str] | None = None,
        maximum_rerank_limit: int | None = None,
    ) -> tuple[RankedEvidence, ...]:
        """Run sparse, dense, and RRF stages without the cross-encoder."""
        if token_budget is not None and token_budget < 0:
            raise ValueError("token_budget must not be negative")
        if maximum_rerank_limit is not None and maximum_rerank_limit < 1:
            raise ValueError("maximum_rerank_limit must be positive")
        minimum_candidate_limit = limit or self.config.candidate_limit
        search_limit = (
            self.config.max_candidate_limit
            if token_budget is not None
            else minimum_candidate_limit
        )
        allowed_indices = self._allowed_indices(document_ids)
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
                maximum_count=min(
                    self.config.max_rerank_limit,
                    maximum_rerank_limit or self.config.max_rerank_limit,
                ),
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

    def _scored_pairs(
        self,
        pairs: Sequence[tuple[str, RetrievalChunk]],
    ) -> list[float]:
        """Score (query, chunk) pairs, optionally reusing in-process results.

        Task 7 of the improvement plan asks for a cross-encoder cache keyed on
        (query, node). This implements it, and it is **off by default**,
        because it cannot satisfy the same task's requirement that rankings
        stay byte-identical.

        The obstruction is measurable, not theoretical.
        ``cross-encoder/ms-marco-MiniLM-L-6-v2`` at its pinned revision is not
        bitwise invariant to batch composition: the same pair scored alone and
        scored inside a 200-pair batch differed for 2 of 10 sampled pairs, by
        about 1e-6, because a batch is padded to its own longest sequence. A
        cache changes batch composition by construction -- it removes the hits
        from the batch -- so the survivors are scored under different padding
        and come back marginally different. On a six-query, five-budget grid
        over two cached documents that moved 6 of 30 packets: a 1e-6 score
        change is enough to flip a near-tie and reorder a packet.

        No score cache can avoid this. Even an all-or-nothing cache returns
        scores computed under the first batch's padding, not this one's. The
        only result-neutral cache is one keyed on the exact batch, which is
        what ``_rerank_cache`` already is.

        So this is a latency/ranking trade, not a free win, and it is exposed
        as one. ``chunk.id`` is a sound key -- it covers arm, document, ordinal
        and text, and an index's chunks are fixed at construction -- but that
        was never the difficulty.
        """
        if not self.reuse_pair_scores:
            score_pairs = getattr(self.reranker, "score_pairs", None)
            if score_pairs is None:
                computed: list[float] = []
                for query, group in groupby(pairs, key=lambda pair: pair[0]):
                    computed.extend(
                        self.reranker.score(query, [chunk for _q, chunk in group])
                    )
            else:
                computed = list(score_pairs(pairs))
            if len(computed) != len(pairs):
                raise ValueError(
                    "reranker score count does not match query-candidate pairs"
                )
            return computed
        scores: list[float | None] = []
        missing: list[tuple[str, RetrievalChunk]] = []
        missing_positions: list[int] = []
        for position, (query, chunk) in enumerate(pairs):
            cached = self._pair_score_cache.get((query, chunk.id))
            scores.append(cached)
            if cached is None:
                missing.append((query, chunk))
                missing_positions.append(position)
        if missing:
            score_pairs = getattr(self.reranker, "score_pairs", None)
            if score_pairs is None:
                # ``score`` takes one query for the whole batch, so group by
                # query rather than assuming the batch shares one.
                computed = []
                for query, group in groupby(missing, key=lambda pair: pair[0]):
                    chunks = [chunk for _query, chunk in group]
                    computed.extend(self.reranker.score(query, chunks))
            else:
                computed = list(score_pairs(missing))
            if len(computed) != len(missing):
                raise ValueError(
                    "reranker score count does not match query-candidate pairs"
                )
            for position, (query, chunk), score in zip(
                missing_positions, missing, computed, strict=True
            ):
                scores[position] = score
                self._pair_score_cache[(query, chunk.id)] = score
        if any(score is None for score in scores):
            raise ValueError("reranker left a query-candidate pair unscored")
        return [score for score in scores if score is not None]

    def rerank(
        self,
        query: str,
        candidates: Sequence[RankedEvidence],
    ) -> tuple[RankedEvidence, ...]:
        """Apply the configured reranker once to an existing candidate pool."""
        cache_key = _rerank_cache_key(query, candidates)
        cached = self._rerank_cache.get(cache_key)
        if cached is not None:
            return cached
        scores = self._scored_pairs(
            [(query, candidate.chunk) for candidate in candidates]
        )
        ranked = sorted(
            zip(candidates, scores, strict=True),
            key=lambda pair: (
                -pair[1],
                -pair[0].scores.fused,
                pair[0].chunk.id,
            ),
        )
        result = tuple(
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
        self._rerank_cache[cache_key] = result
        return result

    def rerank_many(
        self,
        requests: Sequence[tuple[str, Sequence[RankedEvidence]]],
    ) -> tuple[tuple[RankedEvidence, ...], ...]:
        """Rerank independent candidate pools in one model invocation."""
        pairs = [
            (query, candidate.chunk)
            for query, candidates in requests
            for candidate in candidates
        ]
        if getattr(self.reranker, "score_pairs", None) is None:
            return tuple(
                self.rerank(query, candidates) for query, candidates in requests
            )
        scores = iter(self._scored_pairs(pairs))
        results = []
        for _query, candidates in requests:
            ranking = sorted(
                ((candidate, next(scores)) for candidate in candidates),
                key=lambda pair: (
                    -pair[1],
                    -pair[0].scores.fused,
                    pair[0].chunk.id,
                ),
            )
            results.append(
                tuple(
                    candidate.model_copy(
                        update={
                            "rank": rank,
                            "scores": candidate.scores.model_copy(
                                update={"reranked": score}
                            ),
                        }
                    )
                    for rank, (candidate, score) in enumerate(ranking, 1)
                )
            )
        return tuple(results)

    def pack(
        self,
        query: str,
        *,
        token_budget: int,
        retrieval_token_budget: int | None = None,
        limit: int | None = None,
        document_ids: set[str] | None = None,
        budget_accounting: BudgetAccounting = DEFAULT_BUDGET_ACCOUNTING,
        evidence_render_version: EvidenceRenderVersion = (
            DEFAULT_EVIDENCE_RENDER_VERSION
        ),
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
        return self.pack_ranked(
            query,
            ranked,
            token_budget=token_budget,
            budget_accounting=budget_accounting,
            evidence_render_version=evidence_render_version,
        )

    def pack_ranked(
        self,
        query: str,
        ranked: Sequence[RankedEvidence],
        *,
        token_budget: int,
        budget_accounting: BudgetAccounting = DEFAULT_BUDGET_ACCOUNTING,
        evidence_render_version: EvidenceRenderVersion = (
            DEFAULT_EVIDENCE_RENDER_VERSION
        ),
    ) -> ContextPacket:
        """Pack an existing ranking without repeating retrieval or reranking."""
        return pack_evidence(
            query,
            ranked,
            token_budget=token_budget,
            tokenizer=self.tokenizer,
            budget_accounting=budget_accounting,
            evidence_render_version=evidence_render_version,
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
            embedding_revision=self.embedder.revision,
            reranker_model=self.reranker.name,
            reranker_version=self.reranker.version,
            reranker_revision=self.reranker.revision,
            tokenizer=self.tokenizer.name,
            tokenizer_version=self.tokenizer.version,
        )
        output_dir = artifacts_root / "indexes" / key
        output_dir.mkdir(parents=True, exist_ok=True)
        value = {
            "arm": arm.value,
            "config": self.config.model_dump(mode="json"),
            "chunks": [chunk.model_dump(mode="json") for chunk in self.chunks],
            "vectors": self._vectors.tolist(),
            "sparse_parameters": {
                "k1": self.config.sparse_k1,
                "b": self.config.sparse_b,
            },
            "embedding_model": self.embedder.name,
            "embedding_version": self.embedder.version,
            "embedding_revision": self.embedder.revision,
            "reranker_model": self.reranker.name,
            "reranker_version": self.reranker.version,
            "reranker_revision": self.reranker.revision,
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
        query_vector = np.asarray(self.embedder.embed([query])[0], dtype=np.float64)
        indices = (
            np.arange(len(self.chunks), dtype=np.int64)
            if allowed_indices is None
            else np.asarray(sorted(allowed_indices), dtype=np.int64)
        )
        if not len(indices):
            return []
        similarities = self._vectors[indices] @ query_vector
        scores: list[tuple[float, int]] = []
        for similarity, index in zip(similarities, indices, strict=True):
            score = float(similarity)
            if score <= 0.0:
                # A chunk with no positive similarity to the query is not a
                # dense hit. Appending it anyway gave it a rank, and so
                # reciprocal-rank-fusion credit, ordered by chunk id -- a hash,
                # not relevance. This is the sparse guard in
                # ``BM25Index.search`` applied to the dense channel, and the
                # two channels must keep the same semantics: a channel holding
                # no evidence returns nothing rather than hash-ordered filler.
                #
                # Stored vectors are L2-normalized, so ``score`` is a cosine
                # and ``<= 0.0`` means at or beyond orthogonal: no shared
                # direction left to rank on. The test is ``<= 0.0`` rather
                # than ``== 0.0`` deliberately, because a negative cosine is
                # weaker evidence than none at all, not stronger.
                #
                # Under the production embedder this branch is unreachable --
                # every stored chunk pair and every measured query-chunk pair
                # is strictly positive -- so it fires only under the offline
                # ``hash-256-v1`` model, whose sign-bit vectors leave most
                # chunks at exactly 0.0 against a short query. When both
                # channels refuse, ``retrieve`` returns no candidates and
                # ``pack`` yields an empty packet; that is the intended
                # outcome, not a failure. See ``docs/specs/retrieval.md``.
                continue
            scores.append((score, int(index)))
        scores.sort(key=lambda pair: (-pair[0], self.chunks[pair[1]].id))
        return [(index, score) for score, index in scores[:limit]]

    def _allowed_indices(self, document_ids: set[str] | None) -> set[int] | None:
        if document_ids is None:
            return None
        return {
            index
            for document_id in document_ids
            for index in self._document_indices.get(document_id, ())
        }

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
    budget_accounting: BudgetAccounting = DEFAULT_BUDGET_ACCOUNTING,
    evidence_render_version: EvidenceRenderVersion = DEFAULT_EVIDENCE_RENDER_VERSION,
) -> ContextPacket:
    """Deduplicate by source and pack in reranked order.

    The budget is checked against the rendered evidence block by default --
    tags, IDs, joiners and content -- and against content alone only when
    ``budget_accounting="content"``, which reproduces the accounting used
    before the rendered block was counted. A candidate that does not fit is
    skipped and packing continues, so a later smaller item can still use the
    space, exactly as before.
    """
    items = []
    used_sources: set[tuple[str, ...]] = set()
    total = 0
    budget = EvidenceBudget(
        token_budget, tokenizer, budget_accounting, evidence_render_version
    )
    for evidence in ranked:
        chunk = evidence.chunk
        source_key = (chunk.document_id, *chunk.source_item_ids)
        if source_key in used_sources:
            continue
        token_count = tokenizer.count(chunk.text)
        evidence_id = "evidence_" + hashlib.sha256(chunk.id.encode()).hexdigest()
        costs = budget.item_costs(evidence_id, chunk.text)
        if not budget.fits(costs):
            continue
        budget.add(costs)
        used_sources.add(source_key)
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
        rendered_token_count=_checked_rendered_count(
            [(item["evidence_id"], item["content"]) for item in items],
            tokenizer=tokenizer,
            token_budget=token_budget,
            budget_accounting=budget_accounting,
            evidence_render_version=evidence_render_version,
        ),
        budget_accounting=budget_accounting,
        evidence_render_version=evidence_render_version,
    )


def _checked_rendered_count(
    items: Sequence[tuple[str, str]],
    *,
    tokenizer: TokenCounter,
    token_budget: int,
    budget_accounting: BudgetAccounting,
    evidence_render_version: EvidenceRenderVersion,
) -> int:
    """Count the finished rendered block and refuse it if it overruns.

    Recorded in both modes, so a content-accounted packet still reports what
    its prompt would have cost. Under rendered accounting the incremental sum
    in ``EvidenceBudget`` is exact for the project tokenizer; this verifies the
    finished block anyway, so a tokenizer that breaks that assumption fails
    loudly instead of emitting a packet over budget.
    """
    rendered = verified_count(
        items, tokenizer, "rendered_evidence", evidence_render_version
    )
    if budget_accounting == "rendered_evidence" and rendered > token_budget:
        raise ValueError(
            f"rendered evidence block is {rendered} tokens, over the "
            f"{token_budget}-token budget; incremental accounting disagreed "
            "with the finished block"
        )
    return rendered


def _document_indices(
    chunks: Sequence[RetrievalChunk],
) -> dict[str, tuple[int, ...]]:
    mutable: dict[str, list[int]] = {}
    for index, chunk in enumerate(chunks):
        mutable.setdefault(chunk.document_id, []).append(index)
    return {document_id: tuple(indices) for document_id, indices in mutable.items()}


def _query_cache_key(
    query: str,
    *,
    limit: int | None,
    token_budget: int | None,
    document_ids: set[str] | None,
    maximum_rerank_limit: int | None,
) -> tuple[object, ...]:
    return (
        query,
        limit,
        token_budget,
        tuple(sorted(document_ids)) if document_ids is not None else None,
        maximum_rerank_limit,
    )


def _rerank_cache_key(
    query: str,
    candidates: Sequence[RankedEvidence],
) -> tuple[object, ...]:
    return (
        query,
        tuple(
            (
                candidate.chunk.id,
                candidate.scores.dense,
                candidate.scores.sparse,
                candidate.scores.fused,
            )
            for candidate in candidates
        ),
    )


def embedding_model_from_config(
    config: RetrievalConfig,
    *,
    revision: str | None = None,
) -> EmbeddingModel:
    """Construct the configured dense model lazily at a pinned revision.

    ``revision`` is the model-weight commit for hub-backed models and is
    required for them; the offline hash model has no hub identity and ignores
    it. The pin stays out of ``RetrievalConfig`` on purpose: the config is part
    of the index key, so putting it there would rekey the offline fixtures too.
    """
    if config.embedding_model.startswith("hash-"):
        return HashEmbeddingModel(config.embedding_dimensions)
    return SentenceTransformerEmbeddingModel(
        config.embedding_model,
        revision=revision,
    )


def reranker_from_config(
    config: RetrievalConfig,
    *,
    revision: str | None = None,
) -> Reranker:
    """Construct the configured reranker lazily at a pinned revision."""
    if config.reranker_model == "lexical-overlap-v1":
        return LexicalOverlapReranker()
    return SentenceTransformerCrossEncoderReranker(
        config.reranker_model,
        revision=revision,
    )


def _config_hash(config: RetrievalConfig) -> str:
    serialized = json.dumps(
        config.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


_CHUNK_DIGEST_DOMAIN = b"contextbench-index-chunks-v1"


def _chunks_digest(chunks: Sequence[RetrievalChunk]) -> str:
    """Digest the complete state of every chunk, in order, in one pass.

    The index key used to carry ``[chunk.id for chunk in chunks]``, which is
    identity and order but not content. A compiler node chunk's id is
    ``compiler-node-v3\\0document\\0node\\0text`` and deliberately omits
    ``heading_path``, so any change that moves heading paths without permuting
    ordinals produced an identical key over different content. Measured across
    the 0.10.0 IR ordinal repair, 119 of 1,034 node chunks on one document kept
    their id while their heading path moved; that release only rekeyed because
    ordinals permuted the list as well, which was luck.

    ``RetrievalChunk`` is frozen with ``extra="forbid"``, so
    ``model_dump(mode="json")`` is its entire state: ``text`` and
    ``search_text`` (hence ``retrieval_text``, what the indexes and reranker
    actually read), ``heading_path``, both provenance tuples, the page range
    and ``token_count``. Digesting that closes the gap for every field at once
    rather than for the one that happened to bite.

    Streaming rather than embedding the dumps in the key payload: at corpus
    scale this runs over tens of thousands of chunks whose text is up to a
    full window each, so materializing them into one JSON string would build
    hundreds of megabytes to hash once. This holds a single chunk at a time and
    puts one hex string in the payload.

    Order-sensitive, deliberately. The key it replaces already was, and order
    is load-bearing downstream: ``HybridIndex.load`` compares chunk tuples
    positionally, ``_document_indices`` slices by position, and BM25 and the
    ``chunk.id`` tie-breaks depend on it. An order-insensitive digest would
    claim an index is reusable that ``load`` then rejects -- a loud abort in
    place of a cheap miss.
    """
    hasher = hashlib.sha256()
    hasher.update(_CHUNK_DIGEST_DOMAIN)
    hasher.update(b"\0")
    for chunk in chunks:
        serialized = json.dumps(
            chunk.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        hasher.update(serialized.encode())
        # ``json.dumps`` escapes control characters, so a NUL byte cannot
        # appear inside ``serialized`` and frames the entries unambiguously.
        hasher.update(b"\0")
    return hasher.hexdigest()


def _index_key(
    documents: Sequence[IRDocument],
    *,
    arm: RetrievalArm,
    config: RetrievalConfig,
    chunks: Sequence[RetrievalChunk],
    embedding_model: str,
    embedding_version: str,
    embedding_revision: str | None,
    reranker_model: str,
    reranker_version: str,
    reranker_revision: str | None,
    tokenizer: str,
    tokenizer_version: str,
) -> str:
    payload = {
        "arm": arm.value,
        "config": config.model_dump(mode="json"),
        "documents": [document.id for document in documents],
        # The chunk ids are not listed alongside this. ``id`` is a field of the
        # dump the digest covers, so a separate list would be redundant, and
        # leaving it in would invite a later reader to treat the id list as the
        # thing that makes the key content-sensitive when it is not.
        "chunks_digest": _chunks_digest(chunks),
        "embedding_model": embedding_model,
        "embedding_version": embedding_version,
        "embedding_revision": embedding_revision,
        "reranker_model": reranker_model,
        "reranker_version": reranker_version,
        "reranker_revision": reranker_revision,
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
