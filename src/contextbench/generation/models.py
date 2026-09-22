"""Provider-neutral models for answer-generation experiments."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contextbench.evaluation.models import DEFAULT_TOKEN_BUDGETS, BenchmarkSystem


class PricingMetadata(BaseModel):
    """Explicit USD prices used to calculate benchmark economics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_usd_per_million: float = Field(ge=0)
    cached_input_usd_per_million: float = Field(default=0, ge=0)
    output_usd_per_million: float = Field(ge=0)


class AnswerModelConfig(BaseModel):
    """Provider, prompt, and price settings shared across answer experiments."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1)
    max_output_tokens: int = Field(default=256, ge=1)
    reasoning_effort: str | None = None
    # ``None`` means the setting is not sent at all, so the provider default
    # applies. Many reasoning models reject an explicit temperature, so an
    # unset value cannot be modelled as a numeric default.
    temperature: float | None = Field(default=None, ge=0)
    seed: int | None = None
    pricing: PricingMetadata
    prompt_version: Literal["answer-json-v1"] = "answer-json-v1"


class GenerationConfig(AnswerModelConfig):
    """Model and retrieval-cell settings shared by every comparison arm."""

    systems: tuple[BenchmarkSystem, ...] = tuple(BenchmarkSystem)
    budgets: tuple[int, ...] = DEFAULT_TOKEN_BUDGETS
    citation_entailment_judge: bool = False

    @model_validator(mode="after")
    def selections_are_canonical(self) -> "GenerationConfig":
        if not self.systems or len(self.systems) != len(set(self.systems)):
            raise ValueError("systems must be non-empty and unique")
        if not self.budgets or any(value < 1 for value in self.budgets):
            raise ValueError("budgets must contain positive values")
        if self.budgets != tuple(sorted(set(self.budgets))):
            raise ValueError("budgets must be sorted and unique")
        return self


class AnswerRequest(BaseModel):
    """One provider request with an already-rendered, arm-invariant prompt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str
    system: str
    token_budget: int | None = Field(default=None, ge=1)
    prompt: str
    evidence_ids: tuple[str, ...]


class ProviderAnswer(BaseModel):
    """Normalized response and provider-reported usage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    model_id: str
    response_id: str | None = None
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    provider_usage: dict[str, Any] = Field(default_factory=dict)
    # Provider-reported completion state. ``None`` means the provider reports
    # no status, which cannot be read as a failure.
    status: str | None = None
    incomplete_reason: str | None = None

    @model_validator(mode="after")
    def cached_tokens_are_part_of_input(self) -> "ProviderAnswer":
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens cannot exceed input_tokens")
        return self

    @property
    def provider_valid(self) -> bool:
        """Whether the provider itself reports a completed response.

        A truncated response still returns text, so without this check a
        cut-off answer is scored as a wrong answer rather than as a failure.
        """
        return self.status is None or self.status == "completed"


class GenerationEvaluationRecord(BaseModel):
    """Answer quality, citation, usage, latency, and cost for one cell."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    retrieval_run_id: str
    question_id: str
    system: BenchmarkSystem
    token_budget: int = Field(ge=1)
    answerable: bool
    gold_answer: str
    raw_response: str
    parsed_answer: str
    citations: tuple[str, ...]
    # False when the provider did not complete the response or when the
    # response did not satisfy the strict JSON answer contract.
    response_valid: bool
    provider_status: str | None = None
    provider_incomplete_reason: str | None = None
    accuracy: float = Field(ge=0, le=1)
    token_f1: float = Field(ge=0, le=1)
    anls: float = Field(ge=0, le=1)
    citation_validity: float = Field(ge=0, le=1)
    # Historical name retained for artifact compatibility. This measures
    # citation alignment with registered gold pages, not semantic entailment.
    citation_support: float | None = Field(default=None, ge=0, le=1)
    citation_entailment: float | None = Field(default=None, ge=0, le=1)
    citation_entailment_judge_valid: bool | None = None
    citation_entailment_judge_reason: str | None = None
    citation_entailment_judge_raw_response: str | None = None
    citation_present: bool
    insufficient_evidence_correct: bool
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(ge=0)
    calls: int = Field(default=1, ge=1)
    latency_ms: float = Field(ge=0)
    judge_input_tokens: int = Field(default=0, ge=0)
    judge_cached_input_tokens: int = Field(default=0, ge=0)
    judge_output_tokens: int = Field(default=0, ge=0)
    judge_reasoning_tokens: int = Field(default=0, ge=0)
    judge_latency_ms: float = Field(default=0, ge=0)
    judge_response_id: str | None = None
    model_id: str
    response_id: str | None = None
    provider_usage: dict[str, Any]
    cost_usd: float = Field(ge=0)


class GenerationSummaryRow(BaseModel):
    """Aggregate answer metrics for one system and budget."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    system: BenchmarkSystem
    token_budget: int
    question_count: int
    # Share of cells whose response was both provider-completed and parseable.
    # Without it an arm truncated at 40% reads exactly like one that answered
    # badly.
    response_valid_rate: float
    mean_accuracy: float
    mean_token_f1: float
    mean_anls: float
    mean_citation_validity: float
    # Historical field name: mean registered-gold-page alignment.
    mean_citation_support: float | None
    mean_citation_entailment: float | None = None
    citation_present_rate: float
    insufficient_evidence_accuracy: float | None
    mean_input_tokens: float
    mean_output_tokens: float
    mean_latency_ms: float
    dollars_per_query: float
    dollars_per_correct: float | None


class GenerationBenchmarkSummary(BaseModel):
    """Machine-readable answer-generation comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    retrieval_run_id: str
    rows: tuple[GenerationSummaryRow, ...]
