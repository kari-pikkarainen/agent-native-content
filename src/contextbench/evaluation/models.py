"""Schemas for evidence-only retrieval benchmark artifacts."""

import math
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contextbench.compiler import CompilerConfig
from contextbench.retrieval import RetrievalConfig

DEFAULT_TOKEN_BUDGETS = (2048, 4096, 8192, 16384)


class BenchmarkSystem(StrEnum):
    FIXED = "fixed"
    STRUCTURAL = "structural"
    LONG_CONTEXT = "long_context"
    COMPILER = "compiler"


class RetrievalBenchmarkConfig(BaseModel):
    """Fully explicit configuration for one A/B/C/D benchmark run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    budgets: tuple[int, ...] = DEFAULT_TOKEN_BUDGETS
    systems: tuple[BenchmarkSystem, ...] = tuple(BenchmarkSystem)
    seed: int = 20260919
    compiler_stage_audit: bool = False
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    compiler: CompilerConfig = Field(default_factory=CompilerConfig)

    @model_validator(mode="after")
    def configuration_is_fair_and_canonical(self) -> "RetrievalBenchmarkConfig":
        if not self.budgets or any(budget < 1 for budget in self.budgets):
            raise ValueError("budgets must contain positive values")
        if self.budgets != tuple(sorted(set(self.budgets))):
            raise ValueError("budgets must be sorted and unique")
        if not self.systems or len(self.systems) != len(set(self.systems)):
            raise ValueError("systems must be non-empty and unique")
        if self.compiler.retrieval != self.retrieval:
            raise ValueError("compiler and baseline retrieval configs must match")
        if self.compiler_stage_audit and BenchmarkSystem.COMPILER not in self.systems:
            raise ValueError("compiler_stage_audit requires the compiler system")
        return self


class CandidateStageMetrics(BaseModel):
    """Evidence coverage within one bounded candidate pool."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_count: int = Field(ge=0)
    candidate_tokens: int = Field(ge=0)
    selected_pages: dict[str, tuple[int, ...]]
    matched_pages: dict[str, tuple[int, ...]]
    evidence_page_recall: float = Field(ge=0, le=1)
    full_evidence_coverage: bool


class CompilerStageAuditRecord(BaseModel):
    """Candidate recall through each compiler boundary for one budget."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str
    token_budget: int = Field(ge=1)
    gold_pages: dict[str, tuple[int, ...]]
    raw_node_retrieval: CandidateStageMetrics
    faceted_node_retrieval: CandidateStageMetrics
    structural_retrieval: CandidateStageMetrics
    compiler_structural_union: CandidateStageMetrics
    structural_expansion: CandidateStageMetrics
    deduplication: CandidateStageMetrics
    packing: CandidateStageMetrics


class RetrievalEvaluationRecord(BaseModel):
    """Evidence metrics for one question/system/token-budget cell."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str
    answerable: bool
    document_ids: tuple[str, ...]
    system: BenchmarkSystem
    token_budget: int = Field(ge=1)
    # Packed content tokens. The historical name is kept so published
    # ``retrieval.jsonl`` files stay readable; see ``rendered_evidence_tokens``.
    token_count: int = Field(ge=0)
    # Tokens of the rendered evidence block the answer prompt would carry:
    # tags, IDs, joiners and content (``retrieval/rendering.py``). Recorded
    # under both accountings, so a content-accounted run still states what its
    # prompt cost. ``None`` on records written before the field existed.
    rendered_evidence_tokens: int | None = Field(default=None, ge=0)
    # Which of the two ``token_budget`` was enforced against. ``None`` on
    # records that predate the field, all of which were content-accounted.
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
    # Whether the normalised gold answer occurs inside a single packed item's
    # content. ``None`` means not applicable -- an unanswerable question, or a
    # gold answer that is empty or boolean -- and is never a hit or a miss.
    # See ``evidence.gold_answer_present`` for the definition and its blind
    # spots, chief among them computed answers that no context can contain.
    gold_answer_present: bool | None = None
    verification_rule: str | None = None


class RetrievalAnswerPresenceRow(BaseModel):
    """Gold-answer presence for one system, budget and verification rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    system: BenchmarkSystem
    token_budget: int = Field(ge=1)
    verification_rule: str
    applicable_question_count: int = Field(ge=1)
    present_count: int = Field(ge=0)
    present_rate: float = Field(ge=0, le=1)


class RetrievalSummaryRow(BaseModel):
    """Aggregate metrics for one system and budget."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    system: BenchmarkSystem
    token_budget: int
    question_count: int
    mean_evidence_page_recall: float
    full_evidence_coverage_rate: float
    mean_evidence_quote_recall: float
    full_quote_coverage_rate: float
    mean_context_tokens: float
    median_context_tokens: float
    median_tokens_to_full_evidence: float | None
    mean_redundancy: float
    mean_retrieval_latency_ms: float
    # Every ``answerable_*`` field below is over questions that are BOTH
    # marked answerable AND carry at least one annotated gold page, as decided
    # by ``reports._is_answerable_with_pages``. The name is narrower than the
    # eligibility it now reports: a question with no annotated gold page is
    # excluded even when its answerable flag is true, because its vacuous
    # recall of 1.0 is identical in every arm. The Markdown column was renamed
    # to "Answerable gold-page n" to say so; these JSON keys keep their
    # historical names so published ``summary.json`` files stay readable by
    # existing consumers, which is why the meaning is documented here instead.
    answerable_question_count: int = Field(default=0, ge=0)
    quoted_question_count: int = Field(default=0, ge=0)
    answerable_mean_evidence_page_recall: float | None = None
    answerable_full_evidence_coverage_rate: float | None = None
    answerable_mean_content_verified_page_recall: float | None = None
    answerable_full_content_verified_coverage_rate: float | None = None
    quoted_mean_evidence_quote_recall: float | None = None
    quoted_full_quote_coverage_rate: float | None = None
    # Mean tokens of the rendered evidence block, and gold-answer presence
    # over answerable questions with a gold answer. All defaulted, so
    # summaries written before these fields existed still validate.
    mean_rendered_evidence_tokens: float | None = None
    answer_present_question_count: int = Field(default=0, ge=0)
    answer_present_rate: float | None = None


class RetrievalPairedInterval(BaseModel):
    """Document-clustered paired uncertainty for one treatment contrast."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    treatment: BenchmarkSystem
    baseline: BenchmarkSystem
    token_budget: int = Field(ge=1)
    metric: str
    eligible_question_count: int = Field(ge=1)
    source_cluster_count: int = Field(ge=1)
    mean_delta: float
    ci95_low: float
    ci95_high: float
    bootstrap_resamples: int = Field(ge=1)


# Prespecified in ``docs/plans/2026-09-21-improvement-plan.md`` and restated as
# A2 of ``docs/research-log/prereg-adaptive-packing.md``. It is a module
# constant and deliberately not an argument to ``summarize``: a margin a caller
# can pass per run is a margin that can be chosen after seeing the result,
# which is the one thing "prespecified" forbids. Changing it means editing this
# line in a reviewable commit, and every run pins its commit, so the value that
# judged any published artifact is recoverable. Each emitted record also
# carries the margin it was judged against, so an artifact is self-describing
# even if this constant later moves.
NON_INFERIORITY_MARGIN = -0.03


def _minimum_units_for_margin(margin: float) -> int:
    """Smallest population in which one unit is worth no more than the margin.

    A delta over ``n`` units moves by at least ``1 / n`` when a single unit
    flips outright. If ``1 / n`` exceeds the margin, the comparison is finer
    than the instrument making it: the interval is being tested against a
    threshold that one question, or one resampled cluster, can cross on its
    own. That is the plan's "large enough to reach that bound", derived from
    the margin rather than imported from a convention.
    """
    return math.ceil(1 / abs(margin))


class RetrievalNonInferiorityCheck(BaseModel):
    """Verdict on one paired page-recall interval against the fixed margin.

    ``margin_satisfied`` is the mechanical fact: the interval's lower bound is
    strictly above the margin. ``confirmatory`` is whether the population can
    support reading that fact as a non-inferiority result at all. They are
    independent, and ``status`` spells out the combination in words so a
    reader of either artifact cannot take a screening pass for a confirmation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    treatment: BenchmarkSystem
    baseline: BenchmarkSystem
    token_budget: int = Field(ge=1)
    metric: str
    margin: float
    mean_delta: float
    ci95_low: float
    eligible_question_count: int = Field(ge=1)
    source_cluster_count: int = Field(ge=1)
    minimum_confirmatory_questions: int = Field(ge=1)
    minimum_confirmatory_clusters: int = Field(ge=1)
    margin_satisfied: bool
    confirmatory: bool
    status: Literal[
        "confirmatory pass",
        "confirmatory fail",
        "screening pass",
        "screening fail",
    ]


class RetrievalBenchmarkSummary(BaseModel):
    """Machine-readable comparison summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    rows: tuple[RetrievalSummaryRow, ...]
    paired_intervals: tuple[RetrievalPairedInterval, ...] = ()
    # Defaulted so every published ``summary.json`` written before this check
    # existed still validates unchanged.
    non_inferiority: tuple[RetrievalNonInferiorityCheck, ...] = ()
    # How the gold-quote comparison was performed. Defaulted to the original
    # policy so a summary written before this field validates and reads
    # truthfully: the field was introduced with v2, so its absence means v1.
    quote_match_policy: str = "literal-casefold-v1"
    # Gold-answer presence broken down by the dataset's verification rule, so a
    # rule the metric cannot serve well -- a computed number -- is visible
    # rather than averaged away.
    answer_present_by_rule: tuple[RetrievalAnswerPresenceRow, ...] = ()
