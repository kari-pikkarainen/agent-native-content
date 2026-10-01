"""Configuration and internal models for deterministic context compilation."""

import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from docling_core.types.doc import DoclingDocument
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_native_content.ir.models import IRDocument
from agent_native_content.retrieval.models import (
    RankedEvidence,
    RetrievalChunk,
    RetrievalConfig,
    RetrievalScores,
)
from agent_native_content.retrieval.rendering import (
    DEFAULT_BUDGET_ACCOUNTING,
    DEFAULT_EVIDENCE_RENDER_VERSION,
    BudgetAccounting,
    EvidenceRenderVersion,
)

# Not a release number and not tied to the package version. It tracks one
# thing: whether compiled packet contents can differ for a reason a config diff
# would not reveal -- a change in selection, expansion, or packing behavior at
# an identical ``compiler_config`` hash. It is emitted into packet metadata, so
# archived packets from either side of such a change stay distinguishable by
# their own metadata alone. Bump it whenever that is true; leave it alone for
# refactors, comments, and anything a config already records.
#
# An IR-level change can trip this criterion without being a compiler change at
# all: 0.10.0 is a repair to ``ir/project.py`` ordinals, which moves heading
# paths for the nodes whose position changed and rebuilds every page-neighbor
# window. The compiler's own chunk ids are derived from node id and text, so
# they do not move and cannot signal it. The criterion is still the right one
# to bump on -- packet contents can differ -- but it does not describe the
# change; the fixed arm moves too and this constant says nothing about that.
#
# There is no companion IR projection version, and there should not be. The
# 0.10.0 commit message says one "is proposed there and not implemented"; that
# is wrong, nothing was proposed here, and the correction is this paragraph.
# A hand-maintained projection constant would be redundant against
# ``resolve_git_state``, which pins the commit and refuses a dirty worktree, so
# the recorded SHA already pins ``ir/project.py`` byte for byte. Worse, it
# would be unchecked: a projection change with a forgotten bump asserts a
# sameness nobody verified, which is a weaker guarantee than the SHA it
# duplicates.
#
# The real gap is the derived-index key. ``_index_key`` hashes chunk *ids*,
# and a compiler node chunk's id covers document, node id and text but not
# ``heading_path`` or ``search_text``. Measured on the first cached document
# across the 0.10.0 change, 119 of 1,034 node chunks kept their id while their
# heading path moved. The ``xldev24`` rerun was not served stale vectors
# because ordinals also permuted the id list and the key is an ordered list, so
# the key moved anyway; that is luck, not a guarantee. It is not silent, which
# is the part that matters: ``HybridIndex.load`` compares full ``RetrievalChunk``
# models, so a key collision with different content raises rather than serving
# the wrong vectors. (Rekeying on chunk content has since landed in its own
# commit, 9db9c5d.)
#
# The Phase 1 freeze -- sibling expansion switched on by default -- did not
# bump this, deliberately. A default change moves packets, but ``compiler_config``
# is hashed from the full ``CompilerConfig`` and emitted into every packet's
# metadata, so packets from either side of the freeze already differ in their
# own metadata. That is "anything a config already records", which the first
# paragraph says to leave alone. Bumping would spend the one signal reserved
# for changes a config cannot reveal on a change it does.
#
# Rendered-evidence budget accounting did not bump it either, for the same
# reason and one more. It is ``budget_accounting``, a field of this config, so
# every compiler packet's ``compiler_config`` hash already separates the two
# accountings; and adding the field changes that hash for *every*
# configuration, so no post-change packet can share a hash with a pre-change
# one. The fixed, structural and long-context arms carry no compiler hash, which
# is why every packet now states its own ``budget_accounting``.
#
# Evidence aliases (``evidence_render_version``) did not bump it, on exactly
# the same grounds: a config field, hashed into every compiler packet, whose
# addition changes the hash of every configuration; and every packet states
# its own render version for the arms that carry no compiler hash.
#
# Retrieval-unit merging and the candidate token-mass floor did not bump it
# either. Both are config fields (``node_merge_*``,
# ``expanded_candidate_token_mass_multiple``), and adding them changed every
# configuration's hash. The code paths they add -- merged-unit expansion, the
# node-overlap dedupe rule, the floored pool cut -- are unreachable unless a
# field turns them on: expansion and dedupe branch only on multi-node compiler
# evidence, which only merging produces, and the cut is ``[:500]`` verbatim at
# ``None``. Measured at 7a9726b against this change with defaults, 90
# corpus packets (all 30 ``xldev24`` and ``xlholdout6c`` questions at
# 2K/8K/16K) matched item for item; only their ``compiler_config`` hash
# differed.
COMPILER_VERSION = "0.10.0"

# ``priority_tier`` states a candidate's class and nothing else. It must never
# depend on what an expansion happened to produce for one query, because
# ``compiler/pack.py`` treats it as a hard gate: coverage packing considers only
# the lowest tier that still fits, so a candidate one tier up cannot be selected
# at all while anything below it fits the remaining budget.
#
# Tier 0 holds everything that can carry the answer -- direct retrieval,
# siblings, list neighbors, table fragments, and keyed table joins. Inside the
# tier they compete on coverage and score, never by class.
PRIMARY_EVIDENCE_TIER = 0
# Tier 1 holds bounded fixed-window context added only to spend budget that
# primary evidence left over. It must never gate primary evidence out.
FALLBACK_CONTEXT_TIER = 1


class NodeMergePolicy(BaseModel):
    """Bounds for joining source-adjacent tiny IR nodes into one unit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_tokens: int = Field(ge=1)
    target_tokens: int = Field(ge=1)
    max_tokens: int = Field(ge=1)
    max_page_span: int = Field(ge=1)

    @model_validator(mode="after")
    def bounds_are_ordered(self) -> "NodeMergePolicy":
        if not self.min_tokens <= self.target_tokens <= self.max_tokens:
            raise ValueError("merge bounds must satisfy min <= target <= max")
        return self


class CompilerConfig(BaseModel):
    """All configurable decisions in compiler v0."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    include_heading_context: bool = True
    heading_context_depth: int | None = Field(default=None, ge=1)
    # Frozen on for Phase 1. Measured under quote policy v2 in
    # ``xldev24-v2-sibON-nbON-08acd28``: sibling expansion carries the quote
    # recall gain (0.185/0.278/0.347 -> 0.199/0.319/0.361 at 2K/4K/8K) while
    # page neighbours, left on, keep the -3pp non-inferiority margin at 8/8.
    include_previous_sibling: bool = True
    include_next_sibling: bool = True
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
    query_facet_rerank_candidate_limit: int = Field(default=250, ge=1)
    query_facet_rerank_token_target: int | None = Field(default=None, ge=1)
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
    # ``coverage`` stays the default until the preregistered rule in
    # ``docs/research-log/prereg-adaptive-packing.md`` says otherwise.
    # ``ranked`` and ``coverage`` are ablation controls and must stay.
    packing_strategy: Literal["ranked", "coverage", "adaptive"] = "coverage"
    max_expanded_candidates: int = Field(default=500, ge=1)
    # What ``token_budget`` is checked against, for every arm: the rendered
    # evidence block (tags, IDs, joiners and content, ``retrieval/rendering.py``)
    # or, reachable for the re-baseline, content alone. It lives here, not in
    # ``RetrievalConfig``, because ``RetrievalConfig`` keys every derived index
    # and this changes packing only; the benchmark runner reads it for the
    # fixed, structural and long-context arms too, so all arms share one value.
    budget_accounting: BudgetAccounting = DEFAULT_BUDGET_ACCOUNTING
    # How evidence is rendered, and therefore what the rendered budget prices:
    # ``evidence-render-v2`` (positional aliases, the default for new runs) or
    # ``evidence-render-v1`` (full evidence IDs, as every earlier run used). Read
    # by every arm, like ``budget_accounting``, and recorded in the manifest;
    # generation reads it back from the retrieval manifest, so what a model is
    # shown is what the budget priced.
    evidence_render_version: EvidenceRenderVersion = (
        DEFAULT_EVIDENCE_RENDER_VERSION
    )
    # Retrieval-unit merging (``compiler/candidates.py``, ``merge_node_units``).
    # Off by default: with it off, node candidates are exactly one IR node each,
    # as every earlier run used. When on, runs of source-adjacent prose nodes
    # under one ``heading_path`` whose nodes are each under ``min`` tokens are
    # joined into one unit that grows to ``target`` and never past ``max``,
    # covering at most ``max_page_span`` pages. None of the values is tuned;
    # 64 and 256 are the owner's initial bounds and 128 sits between them.
    # These live here and not in ``RetrievalConfig`` because they change only
    # the compiler's unit; the merged chunks rekey the compiler index through
    # its content digest, and the other arms' indexes are untouched.
    node_merge_enabled: bool = False
    node_merge_min_tokens: int = Field(default=64, ge=1)
    node_merge_target_tokens: int = Field(default=128, ge=1)
    node_merge_max_tokens: int = Field(default=256, ge=1)
    node_merge_max_page_span: int = Field(default=1, ge=1)
    # Token-mass floor under ``max_expanded_candidates``. ``None`` keeps the
    # count cap alone, as before. A number ``m`` stops the count cap from
    # truncating the deduplicated pool until the pool's rendered cost (content
    # plus per-item framing) reaches ``m`` times the token budget, so a pool of
    # tiny candidates cannot run out before the budget is spent. It never
    # removes a candidate the count cap would have kept.
    expanded_candidate_token_mass_multiple: float | None = Field(
        default=None,
        gt=0,
    )

    @property
    def node_merge_policy(self) -> "NodeMergePolicy | None":
        """The merge bounds when merging is on, else ``None``."""
        if not self.node_merge_enabled:
            return None
        return NodeMergePolicy(
            min_tokens=self.node_merge_min_tokens,
            target_tokens=self.node_merge_target_tokens,
            max_tokens=self.node_merge_max_tokens,
            max_page_span=self.node_merge_max_page_span,
        )

    @model_validator(mode="after")
    def node_merge_bounds_are_ordered(self) -> "CompilerConfig":
        if not (
            self.node_merge_min_tokens
            <= self.node_merge_target_tokens
            <= self.node_merge_max_tokens
        ):
            raise ValueError(
                "node merge bounds must satisfy min <= target <= max tokens"
            )
        return self

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
    # One of the tier constants above; see their comment for the gate it drives.
    priority_tier: int = Field(default=PRIMARY_EVIDENCE_TIER, ge=0)
    allow_shared_source: bool = False
    operator: Literal[
        "retrieval",
        "sibling",
        "list_neighbor",
        "table_fragment",
        "keyed_join",
        "page_neighbor",
    ] = "retrieval"


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
