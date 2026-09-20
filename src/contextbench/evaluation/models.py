"""Schemas for evidence-only retrieval benchmark artifacts."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contextbench.compiler import CompilerConfig
from contextbench.retrieval import RetrievalConfig

DEFAULT_TOKEN_BUDGETS = (2048, 4096, 8192, 16384)


class BenchmarkSystem(StrEnum):
    FIXED = "fixed"
    STRUCTURAL = "structural"
    COMPILER = "compiler"


class RetrievalBenchmarkConfig(BaseModel):
    """Fully explicit, shared configuration for one A/B/D benchmark run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    budgets: tuple[int, ...] = DEFAULT_TOKEN_BUDGETS
    systems: tuple[BenchmarkSystem, ...] = tuple(BenchmarkSystem)
    seed: int = 20260919
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
        return self


class RetrievalEvaluationRecord(BaseModel):
    """Evidence metrics for one question/system/token-budget cell."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str
    system: BenchmarkSystem
    token_budget: int = Field(ge=1)
    token_count: int = Field(ge=0)
    selected_evidence_ids: tuple[str, ...]
    selected_pages: dict[str, tuple[int, ...]]
    gold_pages: dict[str, tuple[int, ...]]
    matched_pages: dict[str, tuple[int, ...]]
    evidence_page_recall: float = Field(ge=0, le=1)
    full_evidence_coverage: bool
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
    mean_context_tokens: float
    median_context_tokens: float
    median_tokens_to_full_evidence: float | None
    mean_redundancy: float
    mean_retrieval_latency_ms: float


class RetrievalBenchmarkSummary(BaseModel):
    """Machine-readable comparison summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    rows: tuple[RetrievalSummaryRow, ...]
