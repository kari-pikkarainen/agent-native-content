"""Schemas for controlled content-unit × selection-policy experiments."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contextbench.evaluation.models import DEFAULT_TOKEN_BUDGETS
from contextbench.retrieval import RetrievalConfig


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
    # set is unchanged until the ablation is asked for. Each value sets
    # ``RetrievalConfig.heading_search_context`` for the index that cell
    # retrieves from, which applies to the structural and IR units. The fixed
    # unit does not read the field -- its windows concatenate every node,
    # heading nodes included -- so its rows are constant across this factor and
    # an unchanged fixed row is not evidence about heading context.
    heading_contexts: tuple[bool, ...] = (True,)
    seed: int = 20260919
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    faceting: FactorialFacetConfig = Field(default_factory=FactorialFacetConfig)

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
