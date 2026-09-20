"""Models for gold-evidence representation experiments."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contextbench.agentdoc import (
    AgentEnrichmentConfig,
    AgentFeatureKind,
)
from contextbench.generation import AnswerModelConfig


class RepresentationCondition(StrEnum):
    """Representations compared without retrieval."""

    RAW = "raw"
    IR = "ir"
    ENRICHED = "enriched"


class RepresentationExperimentConfig(AnswerModelConfig):
    """Shared model settings and selected representation conditions."""

    conditions: tuple[RepresentationCondition, ...] = tuple(RepresentationCondition)
    enrichment: AgentEnrichmentConfig = Field(default_factory=AgentEnrichmentConfig)
    inline_feature_kinds: tuple[AgentFeatureKind, ...] = (
        AgentFeatureKind.OUTLINE,
        AgentFeatureKind.SECTION_SUMMARY,
        AgentFeatureKind.KEY_FACT,
        AgentFeatureKind.DEFINITION,
        AgentFeatureKind.ENTITY,
        AgentFeatureKind.RELATIONSHIP,
        AgentFeatureKind.TABLE_SCHEMA,
    )
    max_inline_features: int = Field(default=128, ge=1)
    tokenizer_name: str = "o200k_base"

    @model_validator(mode="after")
    def conditions_are_unique(self) -> "RepresentationExperimentConfig":
        if not self.conditions or len(self.conditions) != len(set(self.conditions)):
            raise ValueError("conditions must be non-empty and unique")
        if len(self.inline_feature_kinds) != len(set(self.inline_feature_kinds)):
            raise ValueError("inline_feature_kinds must be unique")
        return self


class RepresentationEvaluationRecord(BaseModel):
    """Quality and economics for one question/representation cell."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str
    condition: RepresentationCondition
    answerable: bool
    gold_answer: str
    gold_pages: dict[str, tuple[int, ...]]
    source_node_count: int = Field(ge=0)
    feature_count: int = Field(ge=0)
    representation_tokens: int = Field(ge=0)
    raw_response: str
    parsed_answer: str
    citations: tuple[str, ...]
    response_valid: bool
    accuracy: float = Field(ge=0, le=1)
    token_f1: float = Field(ge=0, le=1)
    anls: float = Field(ge=0, le=1)
    citation_validity: float = Field(ge=0, le=1)
    citation_support: float = Field(ge=0, le=1)
    citation_present: bool
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(ge=0)
    calls: int = Field(default=1, ge=1)
    latency_ms: float = Field(ge=0)
    model_id: str
    response_id: str | None = None
    provider_usage: dict[str, Any]
    cost_usd: float = Field(ge=0)


class RepresentationSummaryRow(BaseModel):
    """Aggregate metrics for one representation condition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    condition: RepresentationCondition
    question_count: int
    mean_accuracy: float
    mean_token_f1: float
    mean_anls: float
    mean_citation_validity: float
    mean_citation_support: float
    citation_present_rate: float
    mean_representation_tokens: float
    mean_input_tokens: float
    mean_output_tokens: float
    mean_latency_ms: float
    dollars_per_query: float
    dollars_per_correct: float | None


class RepresentationBenchmarkSummary(BaseModel):
    """Machine-readable RAW/IR/ENRICHED comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    evaluated_question_ids: tuple[str, ...]
    skipped_question_ids: tuple[str, ...]
    enrichment_prepare_ms: float = Field(ge=0)
    amortized_enrichment_ms_per_question: float = Field(ge=0)
    rows: tuple[RepresentationSummaryRow, ...]
