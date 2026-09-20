"""Configuration and internal models for deterministic context compilation."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from docling_core.types.doc import DoclingDocument
from pydantic import BaseModel, ConfigDict, Field

from contextbench.ir.models import IRDocument
from contextbench.retrieval.models import (
    RetrievalChunk,
    RetrievalConfig,
    RetrievalScores,
)

COMPILER_VERSION = "0.2.1"


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
    preserve_tables: bool = True
    table_chunk_tokens: int = Field(default=512, ge=1)
    max_expanded_candidates: int = Field(default=500, ge=1)


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
    allow_shared_source: bool = False
