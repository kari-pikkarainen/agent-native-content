"""Configuration and internal models for deterministic context compilation."""

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from docling_core.types.doc import DoclingDocument
from pydantic import BaseModel, ConfigDict, Field, model_validator

from contextbench.ir.models import IRDocument
from contextbench.retrieval.models import (
    RankedEvidence,
    RetrievalChunk,
    RetrievalConfig,
    RetrievalScores,
)

COMPILER_VERSION = "0.5.0"


class CompilerConfig(BaseModel):
    """All configurable decisions in compiler v0."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    include_heading_context: bool = True
    include_previous_sibling: bool = False
    include_next_sibling: bool = False
    sibling_neighbor_limit: int = Field(default=1, ge=0)
    sibling_score_penalty: float = Field(default=0.85, gt=0, le=1)
    group_adjacent_list_items: bool = True
    list_neighbor_limit: int = Field(default=1, ge=0)
    list_score_penalty: float = Field(default=0.9, gt=0, le=1)
    query_faceting_enabled: bool = True
    query_facet_limit: int = Field(default=3, ge=1)
    query_facet_min_terms: int = Field(default=3, ge=1)
    query_facet_full_weight: float = Field(default=2.0, gt=0)
    query_facet_rerank_strategy: Literal["batched", "single_pass"] = "batched"
    node_rerank_candidate_limit: int = Field(default=250, ge=1)
    query_facet_rerank_candidate_limit: int = Field(default=96, ge=1)
    page_neighbor_radius: int = Field(default=3, ge=0)
    page_neighbor_min_budget: int = Field(default=16384, ge=1)
    page_neighbor_origin_limit: int = Field(default=20, ge=1)
    page_neighbor_prerank_limit: int = Field(default=64, ge=1)
    page_neighbor_candidate_limit: int = Field(default=64, ge=1)
    page_neighbor_score_penalty: float = Field(default=0.8, gt=0, le=1)
    preserve_tables: bool = True
    table_chunk_tokens: int = Field(default=512, ge=1)
    keyed_table_join_enabled: bool = True
    keyed_table_join_candidate_limit: int = Field(default=16, ge=1)
    keyed_table_join_empty_marker: str = Field(default="[blank]", min_length=1)
    max_expanded_candidates: int = Field(default=500, ge=1)

    @model_validator(mode="after")
    def candidate_limit_can_satisfy_minimum(self) -> "CompilerConfig":
        if self.node_rerank_candidate_limit < self.retrieval.rerank_limit:
            raise ValueError(
                "node_rerank_candidate_limit must be at least rerank_limit"
            )
        if self.query_facet_rerank_candidate_limit < self.retrieval.rerank_limit:
            raise ValueError(
                "query_facet_rerank_candidate_limit must be at least rerank_limit"
            )
        return self


@dataclass(frozen=True)
class DocumentScope:
    """IR documents plus optional authoritative Docling artifacts."""

    documents: tuple[IRDocument, ...]
    source_documents: Mapping[str, DoclingDocument] = field(default_factory=dict)

    @classmethod
    def from_documents(
        cls,
        documents: Sequence[IRDocument],
        *,
        source_documents: Mapping[str, DoclingDocument] | None = None,
    ) -> "DocumentScope":
        return cls(tuple(documents), source_documents or {})


class CompilerCandidate(BaseModel):
    """One retrieved or structurally expanded item before final packing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk: RetrievalChunk
    scores: RetrievalScores
    origin_rank: int = Field(ge=1)
    expansion_order: int = Field(ge=0)
    priority_tier: int = Field(default=0, ge=0)
    allow_shared_source: bool = False


@dataclass(frozen=True)
class CompilerTrace:
    """Candidate snapshots at the compiler's loss-bearing boundaries."""

    ranked_evidence: tuple[RankedEvidence, ...]
    expanded_candidates: tuple[CompilerCandidate, ...]
    deduplicated_candidates: tuple[CompilerCandidate, ...]


@dataclass
class CompilerQueryCache:
    """Query-scoped derived expansion state shared across token budgets."""

    _page_neighbor_key: str | None = None
    _page_neighbors: tuple[CompilerCandidate, ...] = ()
    page_neighbor_prepare_ms: float = 0.0
    page_neighbors_used: bool = False
    page_neighbor_cache_hit: bool = False
    _keyed_join_key: str | None = None
    _keyed_joins: tuple[CompilerCandidate, ...] = ()
    keyed_join_prepare_ms: float = 0.0
    keyed_joins_used: bool = False
    keyed_join_cache_hit: bool = False

    def begin_compilation(self) -> None:
        """Reset per-compilation observations without clearing cached state."""
        self.page_neighbors_used = False
        self.page_neighbor_cache_hit = False
        self.keyed_joins_used = False
        self.keyed_join_cache_hit = False

    def page_neighbors(
        self,
        key: str,
        factory: Callable[[], tuple[CompilerCandidate, ...]],
    ) -> tuple[CompilerCandidate, ...]:
        """Return one validated page-neighbor ranking for this query."""
        self.page_neighbors_used = True
        if self._page_neighbor_key is None:
            started = time.perf_counter_ns()
            self._page_neighbors = factory()
            self.page_neighbor_prepare_ms = (
                time.perf_counter_ns() - started
            ) / 1_000_000
            self._page_neighbor_key = key
            return self._page_neighbors
        if self._page_neighbor_key != key:
            raise ValueError("CompilerQueryCache cannot be reused for another query")
        self.page_neighbor_cache_hit = True
        return self._page_neighbors

    def keyed_joins(
        self,
        key: str,
        factory: Callable[[], tuple[CompilerCandidate, ...]],
    ) -> tuple[CompilerCandidate, ...]:
        """Return one query-scoped keyed-table join ranking."""
        self.keyed_joins_used = True
        if self._keyed_join_key is None:
            started = time.perf_counter_ns()
            self._keyed_joins = factory()
            self.keyed_join_prepare_ms = (time.perf_counter_ns() - started) / 1_000_000
            self._keyed_join_key = key
            return self._keyed_joins
        if self._keyed_join_key != key:
            raise ValueError("CompilerQueryCache cannot be reused for another query")
        self.keyed_join_cache_hit = True
        return self._keyed_joins
