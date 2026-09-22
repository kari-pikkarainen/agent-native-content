"""Models shared by retrieval arms and their context outputs."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RetrievalArm(StrEnum):
    """Benchmark retrieval chunking strategies."""

    FIXED = "fixed"
    STRUCTURAL = "structural"
    LONG_CONTEXT = "long_context"
    COMPILER = "compiler"


class RetrievalConfig(BaseModel):
    """Explicit configuration shared by Arms A and B."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fixed_chunk_tokens: int = Field(default=512, ge=1)
    fixed_overlap_tokens: int = Field(default=64, ge=0)
    structural_chunk_tokens: int = Field(default=512, ge=1)
    # Heading search context, one field per heading-bearing content unit.
    #
    # Both default on, which is exactly what the single ``heading_search_context``
    # field they replace did, so every default run is unchanged. They were split
    # because the development factorial measured the factor to be *asymmetric*:
    # heading context costs the compiler's IR-node unit page recall at every
    # budget while helping structural chunks at the smaller budgets. One field
    # made the useful configuration -- structural on, IR nodes off --
    # unreachable. Splitting makes it reachable; it does not choose it. Neither
    # default moves here.
    #
    # Neither position changes emitted chunk text or token counts on either
    # unit: both only fill ``search_text``, which is what the indexes read and
    # what a model never sees. The fixed unit reads neither field -- its windows
    # already include heading nodes incidentally -- so it is constant across
    # both. See ``docs/specs/retrieval.md``.

    # Read by ``retrieval/chunking.structural_chunks``. Off reproduces the
    # pre-fix structural behaviour exactly, leaving ``search_text`` as ``None``
    # on every structural chunk, which is what keeps the ablation measurable.
    structural_heading_search_context: bool = True
    # Read by ``compiler/candidates.node_chunks``. Off leaves ``search_text``
    # as ``None`` on every IR-node candidate; ``chunk.id`` is derived from node
    # text alone, so neither position permutes candidate ids.
    compiler_node_heading_search_context: bool = True
    sparse_k1: float = Field(default=1.5, gt=0)
    sparse_b: float = Field(default=0.75, ge=0, le=1)
    rrf_k: int = Field(default=60, ge=1)
    candidate_limit: int = Field(default=40, ge=1)
    rerank_limit: int = Field(default=20, ge=1)
    candidate_token_multiplier: float = Field(default=3.0, ge=1)
    rerank_token_multiplier: float = Field(default=2.0, ge=1)
    max_candidate_limit: int = Field(default=500, ge=1)
    max_rerank_limit: int = Field(default=250, ge=1)
    embedding_model: str = "hash-256-v1"
    embedding_dimensions: int = Field(default=256, ge=8)
    reranker_model: str = "lexical-overlap-v1"
    tokenizer_name: str = "o200k_base"

    @model_validator(mode="after")
    def overlap_is_smaller_than_chunk(self) -> "RetrievalConfig":
        if self.fixed_overlap_tokens >= self.fixed_chunk_tokens:
            raise ValueError("fixed_overlap_tokens must be smaller than chunk size")
        if self.max_candidate_limit < self.candidate_limit:
            raise ValueError("max_candidate_limit must be at least candidate_limit")
        if self.max_rerank_limit < self.rerank_limit:
            raise ValueError("max_rerank_limit must be at least rerank_limit")
        if self.max_rerank_limit > self.max_candidate_limit * 2:
            raise ValueError(
                "max_rerank_limit cannot exceed the fused candidate capacity"
            )
        return self


class RetrievalChunk(BaseModel):
    """One source-traceable text unit submitted to the shared indexes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    arm: RetrievalArm
    document_id: str
    text: str
    search_text: str | None = None
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
        if self.search_text is not None and not self.search_text.strip():
            raise ValueError("search_text must be non-empty when provided")
        if not self.source_node_ids:
            raise ValueError("retrieval chunks require source nodes")
        if not self.source_item_ids:
            raise ValueError("retrieval chunks require source items")
        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("page_start and page_end must be both set or both null")
        if self.page_start is not None and self.page_start > self.page_end:
            raise ValueError("page_start must not exceed page_end")
        return self

    @property
    def retrieval_text(self) -> str:
        """Return contextual text used for search without changing emitted text."""
        return self.search_text or self.text


class RetrievalScores(BaseModel):
    """Scores from each shared retrieval stage.

    Only ``reranked`` is comparable across candidate classes. It always holds a
    cross-encoder score for this candidate against the query, optionally shrunk
    by an explicit structural penalty, so it is the one field any cross-class
    ordering may key on.

    ``dense``, ``sparse`` and ``fused`` are provenance: they record how a
    candidate reached the pool, and their units depend on which path it took.
    ``fused`` is an RRF sum for anything retrieved -- over sparse and dense for
    a single query, over rankings for a faceted one -- and a lexical overlap
    ratio for a keyed table join, which was never retrieved at all. Comparing
    those numbers to each other is meaningless; they may break ties only inside
    one class, and are published so a run can be audited.
    """

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
