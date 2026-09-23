"""Schemas for controlled content-unit × selection-policy experiments."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contextbench.compiler.models import NodeMergePolicy
from contextbench.evaluation.models import DEFAULT_TOKEN_BUDGETS
from contextbench.retrieval import RetrievalConfig
from contextbench.retrieval.rendering import (
    DEFAULT_BUDGET_ACCOUNTING,
    DEFAULT_EVIDENCE_RENDER_VERSION,
    BudgetAccounting,
    EvidenceRenderVersion,
)


class ContentUnit(StrEnum):
    """Source-derived unit submitted to the otherwise shared retrieval stack."""

    FIXED = "fixed"
    STRUCTURAL = "structural"
    IR = "ir"


class SelectionPolicy(StrEnum):
    """Query and packing policy crossed with every content unit."""

    RANKED = "ranked"
    FACETED_COVERAGE = "faceted_coverage"


class FactorialFacetConfig(BaseModel):
    """Only the enhanced policy parameters used in the factorial control."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    query_faceting_enabled: bool = True
    query_facet_limit: int = Field(default=3, ge=1)
    query_facet_min_terms: int = Field(default=3, ge=1)
    query_facet_full_weight: float = Field(default=2.0, gt=0)
    query_facet_rerank_strategy: Literal["batched", "single_pass"] = "batched"
    query_facet_rerank_candidate_limit: int = Field(default=250, ge=1)
    query_facet_rerank_token_target: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def candidate_limit_is_valid(self) -> "FactorialFacetConfig":
        if self.query_facet_rerank_candidate_limit < self.retrieval.rerank_limit:
            raise ValueError(
                "query_facet_rerank_candidate_limit must be at least rerank_limit"
            )
        if self.query_facet_rerank_candidate_limit > self.retrieval.max_rerank_limit:
            raise ValueError(
                "query_facet_rerank_candidate_limit cannot exceed max_rerank_limit"
            )
        return self


class FactorialConfig(BaseModel):
    """Complete controlled-factor configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    budgets: tuple[int, ...] = DEFAULT_TOKEN_BUDGETS
    content_units: tuple[ContentUnit, ...] = tuple(ContentUnit)
    selection_policies: tuple[SelectionPolicy, ...] = tuple(SelectionPolicy)
    # Crossed with the other two factors. Single-valued by default so the cell
    # set is unchanged until the ablation is asked for. Each value sets *both*
    # ``RetrievalConfig.structural_heading_search_context`` and
    # ``RetrievalConfig.compiler_node_heading_search_context`` to that value for
    # the index the cell retrieves from, which is what makes this factor
    # arm-symmetric: the structural and IR units move together, so the
    # IR-versus-structural contrast is never confounded by one arm changing and
    # the other not. Those two fields are separate on ``RetrievalConfig`` so a
    # benchmark run can set them independently; this factor deliberately does
    # not. The fixed unit reads neither field -- its windows concatenate every
    # node, heading nodes included -- so its rows are constant across this
    # factor and an unchanged fixed row is not evidence about heading context.
    heading_contexts: tuple[bool, ...] = (True,)
    seed: int = 20260919
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    faceting: FactorialFacetConfig = Field(default_factory=FactorialFacetConfig)
    # The same accounting the benchmark runner applies to every arm; every
    # factorial cell packs through ``pack_candidates``, so one value covers all.
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
    # Retrieval-unit merging for the IR content unit, with the meaning and
    # defaults of the ``CompilerConfig`` fields of the same names. Off by
    # default. It changes only the IR unit's chunks; the fixed and structural
    # units read none of these.
    node_merge_enabled: bool = False
    node_merge_min_tokens: int = Field(default=64, ge=1)
    node_merge_target_tokens: int = Field(default=128, ge=1)
    node_merge_max_tokens: int = Field(default=256, ge=1)
    node_merge_max_page_span: int = Field(default=1, ge=1)

    @property
    def node_merge_policy(self) -> NodeMergePolicy | None:
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
    def configuration_is_complete_and_fair(self) -> "FactorialConfig":
        if not self.budgets or any(budget < 1 for budget in self.budgets):
            raise ValueError("budgets must contain positive values")
        if self.budgets != tuple(sorted(set(self.budgets))):
            raise ValueError("budgets must be sorted and unique")
        if not self.content_units or len(self.content_units) != len(
            set(self.content_units)
        ):
            raise ValueError("content_units must be non-empty and unique")
        if not self.selection_policies or len(self.selection_policies) != len(
            set(self.selection_policies)
        ):
            raise ValueError("selection_policies must be non-empty and unique")
        if not self.heading_contexts or len(self.heading_contexts) != len(
            set(self.heading_contexts)
        ):
            raise ValueError("heading_contexts must be non-empty and unique")
        if self.faceting.retrieval != self.retrieval:
            raise ValueError("faceting and shared retrieval configs must match")
        if not (
            self.node_merge_min_tokens
            <= self.node_merge_target_tokens
            <= self.node_merge_max_tokens
        ):
            raise ValueError(
                "node merge bounds must satisfy min <= target <= max tokens"
            )
        return self


class FactorialEvaluationRecord(BaseModel):
    """Evidence metrics for one question × unit × policy × heading × budget cell."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str
    content_unit: ContentUnit
    selection_policy: SelectionPolicy
    # Constant across this factor for ``ContentUnit.FIXED``, which does not
    # read it; see ``FactorialConfig.heading_contexts``.
    heading_context: bool
    token_budget: int = Field(ge=1)
    token_count: int = Field(ge=0)
    # Same meaning as on ``RetrievalEvaluationRecord``; see there.
    rendered_evidence_tokens: int | None = Field(default=None, ge=0)
    budget_accounting: Literal["rendered_evidence", "content"] | None = None
    # How the evidence block was rendered, which the rendered count priced.
    # ``None`` on records that predate the field: those were v1.
    evidence_render_version: (
        Literal["evidence-render-v1", "evidence-render-v2"] | None
    ) = None
    selected_evidence_ids: tuple[str, ...]
    selected_pages: dict[str, tuple[int, ...]]
    gold_pages: dict[str, tuple[int, ...]]
    matched_pages: dict[str, tuple[int, ...]]
    evidence_page_recall: float = Field(ge=0, le=1)
    full_evidence_coverage: bool
    content_verified_selected_pages: dict[str, tuple[int, ...]]
    content_verified_matched_pages: dict[str, tuple[int, ...]]
    content_verified_page_recall: float = Field(ge=0, le=1)
    full_content_verified_coverage: bool
    gold_quote_count: int = Field(ge=0)
    matched_quote_count: int = Field(ge=0)
    evidence_quote_recall: float = Field(ge=0, le=1)
    full_quote_coverage: bool
    tokens_to_full_evidence: int | None = Field(default=None, ge=0)
    redundancy: float = Field(ge=0, le=1)
    retrieval_latency_ms: float = Field(ge=0)
    # Same meaning as on ``RetrievalEvaluationRecord``. Recorded per cell; the
    # factorial report does not aggregate it.
    gold_answer_present: bool | None = None
    verification_rule: str | None = None


class FactorialSummaryRow(BaseModel):
    """Aggregate metrics for one unit, policy and heading cell at one budget."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content_unit: ContentUnit
    selection_policy: SelectionPolicy
    heading_context: bool
    token_budget: int
    question_count: int
    mean_evidence_page_recall: float
    full_evidence_coverage_rate: float
    mean_content_verified_page_recall: float
    full_content_verified_coverage_rate: float
    mean_evidence_quote_recall: float
    full_quote_coverage_rate: float
    mean_context_tokens: float
    median_context_tokens: float
    median_tokens_to_full_evidence: float | None
    mean_redundancy: float
    mean_retrieval_latency_ms: float


class FactorialSummary(BaseModel):
    """Machine-readable controlled-factor comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    rows: tuple[FactorialSummaryRow, ...]
