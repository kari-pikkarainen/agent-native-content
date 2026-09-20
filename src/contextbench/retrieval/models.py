"""Models shared by retrieval arms and their context outputs."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RetrievalArm(StrEnum):
    """Benchmark retrieval chunking strategies."""

    FIXED = "fixed"
    STRUCTURAL = "structural"
    COMPILER = "compiler"


class RetrievalConfig(BaseModel):
    """Explicit configuration shared by Arms A and B."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fixed_chunk_tokens: int = Field(default=512, ge=1)
    fixed_overlap_tokens: int = Field(default=64, ge=0)
    structural_chunk_tokens: int = Field(default=512, ge=1)
    sparse_k1: float = Field(default=1.5, gt=0)
    sparse_b: float = Field(default=0.75, ge=0, le=1)
    rrf_k: int = Field(default=60, ge=1)
    candidate_limit: int = Field(default=40, ge=1)
    rerank_limit: int = Field(default=20, ge=1)
    embedding_model: str = "hash-256-v1"
    embedding_dimensions: int = Field(default=256, ge=8)
    reranker_model: str = "lexical-overlap-v1"
    tokenizer_name: str = "o200k_base"

    @model_validator(mode="after")
    def overlap_is_smaller_than_chunk(self) -> "RetrievalConfig":
        if self.fixed_overlap_tokens >= self.fixed_chunk_tokens:
            raise ValueError("fixed_overlap_tokens must be smaller than chunk size")
        return self


class RetrievalChunk(BaseModel):
    """One source-traceable text unit submitted to the shared indexes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    arm: RetrievalArm
    document_id: str
    text: str
    token_count: int = Field(ge=0)
    heading_path: tuple[str, ...] = ()
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    source_node_ids: tuple[str, ...]
    source_item_ids: tuple[str, ...]

    @model_validator(mode="after")
    def has_traceable_content(self) -> "RetrievalChunk":
        if not self.text.strip():
            raise ValueError("retrieval chunks must contain text")
        if not self.source_node_ids:
            raise ValueError("retrieval chunks require source nodes")
        if not self.source_item_ids:
            raise ValueError("retrieval chunks require source items")
        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("page_start and page_end must be both set or both null")
        if self.page_start is not None and self.page_start > self.page_end:
            raise ValueError("page_start must not exceed page_end")
        return self


class RetrievalScores(BaseModel):
    """Scores from each shared retrieval stage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dense: float = 0.0
    sparse: float = 0.0
    fused: float = 0.0
    reranked: float = 0.0


class RankedEvidence(BaseModel):
    """A ranked chunk and all scores needed for analysis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rank: int = Field(ge=1)
    chunk: RetrievalChunk
    scores: RetrievalScores


class ContextItem(BaseModel):
    """A packed evidence item with citation-ready provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str
    document_id: str
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    heading_path: tuple[str, ...] = ()
    content: str
    token_count: int = Field(ge=0)
    source_node_ids: tuple[str, ...]
    source_item_ids: tuple[str, ...]
    scores: RetrievalScores


class ContextPacket(BaseModel):
    """Deterministic token-budgeted output for one retrieval query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str
    token_budget: int = Field(ge=0)
    token_count: int = Field(ge=0)
    items: tuple[ContextItem, ...]
    metadata: dict[str, str]

    @model_validator(mode="after")
    def budget_and_count_are_consistent(self) -> "ContextPacket":
        expected = sum(item.token_count for item in self.items)
        if expected != self.token_count:
            raise ValueError("token_count must equal the sum of item token counts")
        if self.token_count > self.token_budget:
            raise ValueError("context packet exceeds token budget")
        return self
