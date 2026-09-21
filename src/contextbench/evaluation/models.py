"""Schemas for evidence-only retrieval benchmark artifacts."""

from enum import StrEnum

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
    answerable_question_count: int = Field(default=0, ge=0)
    quoted_question_count: int = Field(default=0, ge=0)
    answerable_mean_evidence_page_recall: float | None = None
    answerable_full_evidence_coverage_rate: float | None = None
    answerable_mean_content_verified_page_recall: float | None = None
    answerable_full_content_verified_coverage_rate: float | None = None
    quoted_mean_evidence_quote_recall: float | None = None
    quoted_full_quote_coverage_rate: float | None = None


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


class RetrievalBenchmarkSummary(BaseModel):
    """Machine-readable comparison summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    rows: tuple[RetrievalSummaryRow, ...]
    paired_intervals: tuple[RetrievalPairedInterval, ...] = ()
