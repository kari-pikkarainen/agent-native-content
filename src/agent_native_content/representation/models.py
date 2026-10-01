"""Models for gold-evidence representation experiments."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_native_content.agentdoc import (
    AgentEnrichmentConfig,
    AgentFeatureKind,
)
from agent_native_content.generation import AnswerModelConfig

# How a representation prompt labels what it shows. v1 and v2 are the two
# schemes of ``retrieval/rendering.py``; v3 exists only here, because only the
# representation experiment renders IR node IDs and feature references.
#
# * ``evidence-render-v1``: full ``evidence_`` + 64-hex evidence IDs, full
#   ``node_`` + 64-hex node IDs in the ``source_node`` attribute, and the last
#   12 hex digits of each feature ID as an indexed feature's ``ref``. Every
#   representation run before these schemes existed.
# * ``evidence-render-v2``: v1 with evidence aliases ``E1``, ``E2``, ... in
#   place of evidence IDs. Node IDs and feature refs stay hex.
# * ``evidence-render-v3``, the default: v2 plus short node references ``N1``,
#   ``N2``, ... in place of node IDs and short feature references ``F1``,
#   ``F2``, ... in place of the feature-ID suffix. A v3 prompt shows no hex
#   identifier at all.
RepresentationRenderVersion = Literal[
    "evidence-render-v1", "evidence-render-v2", "evidence-render-v3"
]
REPRESENTATION_RENDER_V1: RepresentationRenderVersion = "evidence-render-v1"
REPRESENTATION_RENDER_V2: RepresentationRenderVersion = "evidence-render-v2"
REPRESENTATION_RENDER_V3: RepresentationRenderVersion = "evidence-render-v3"
DEFAULT_REPRESENTATION_RENDER_VERSION: RepresentationRenderVersion = (
    REPRESENTATION_RENDER_V3
)


class RepresentationError(RuntimeError):
    """Raised when a representation experiment cannot run reproducibly."""


class RepresentationCondition(StrEnum):
    """Representations compared without retrieval."""

    QUESTION_ONLY = "question_only"
    RAW = "raw"
    IR = "ir"
    ENRICHED = "enriched"
    INDEXED = "indexed"


# ``question_only`` is an opt-in control: adding it to the enum must not
# silently change the default run's conditions and provider-call count for
# callers that relied on "all conditions" meaning the four encodings. This does
# not keep ``config_sha256`` stable: the judge fields added beside it appear in
# the config dump, so config hashes are not comparable across that change.
DEFAULT_REPRESENTATION_CONDITIONS: tuple[RepresentationCondition, ...] = (
    RepresentationCondition.RAW,
    RepresentationCondition.IR,
    RepresentationCondition.ENRICHED,
    RepresentationCondition.INDEXED,
)


class RepresentationExperimentConfig(AnswerModelConfig):
    """Shared model settings and selected representation conditions."""

    conditions: tuple[RepresentationCondition, ...] = DEFAULT_REPRESENTATION_CONDITIONS
    enrichment: AgentEnrichmentConfig = Field(default_factory=AgentEnrichmentConfig)
    inline_feature_kinds: tuple[AgentFeatureKind, ...] = (
        AgentFeatureKind.OUTLINE,
        AgentFeatureKind.SECTION_SUMMARY,
        AgentFeatureKind.KEY_FACT,
        AgentFeatureKind.DEFINITION,
        AgentFeatureKind.ENTITY,
        AgentFeatureKind.RELATIONSHIP,
        AgentFeatureKind.TABLE_SCHEMA,
        AgentFeatureKind.QUANTITY,
    )
    max_inline_features: int = Field(default=128, ge=1)
    indexed_max_features: int = Field(default=32, ge=1)
    indexed_feature_token_budget: int = Field(default=2048, ge=1)
    answer_equivalence_judge: bool = False
    citation_entailment_judge: bool = False
    tokenizer_name: str = "o200k_base"
    # How every evidence-bearing condition labels evidence items, IR nodes and
    # indexed features (``RepresentationRenderVersion`` above). Aliases and
    # node references are assigned once per question in gold-evidence order,
    # so raw, ir, enriched and indexed show the *same* label for the same item
    # and differ only in encoding. Cited aliases are mapped back to full
    # evidence IDs before any citation is scored or recorded.
    #
    # A 12B local model could not copy 64-hex IDs, and looped on them, so
    # citation metrics measured ID copying; the hex node IDs also cost only
    # the structured conditions tokens. Manifests written before this field
    # existed have no such key in their config; they were all v1.
    evidence_render_version: RepresentationRenderVersion = (
        DEFAULT_REPRESENTATION_RENDER_VERSION
    )

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
    # False when the provider did not complete the response or when the
    # response did not satisfy the strict JSON answer contract.
    response_valid: bool
    provider_status: str | None = None
    provider_incomplete_reason: str | None = None
    provider_text_error: str | None = None
    abstained: bool
    accuracy: float = Field(ge=0, le=1)
    semantic_accuracy: float | None = Field(default=None, ge=0, le=1)
    answer_equivalence_judge_valid: bool | None = None
    answer_equivalence_judge_reason: str | None = None
    answer_equivalence_judge_raw_response: str | None = None
    answer_judge_provider_status: str | None = None
    answer_judge_provider_incomplete_reason: str | None = None
    answer_judge_provider_text_error: str | None = None
    token_f1: float = Field(ge=0, le=1)
    anls: float = Field(ge=0, le=1)
    citation_validity: float = Field(ge=0, le=1)
    citation_support: float = Field(ge=0, le=1)
    citation_entailment: float | None = Field(default=None, ge=0, le=1)
    citation_entailment_judge_valid: bool | None = None
    citation_entailment_judge_reason: str | None = None
    citation_entailment_judge_raw_response: str | None = None
    citation_judge_provider_status: str | None = None
    citation_judge_provider_incomplete_reason: str | None = None
    citation_judge_provider_text_error: str | None = None
    citation_present: bool
    # Totals over every call made for this cell: the answer call plus any
    # judge calls. Judge calls depend on the answer (none for abstentions,
    # no citation judge without valid citations, longer prompts for more
    # citations), so these totals are not a representation comparison.
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(ge=0)
    calls: int = Field(default=1, ge=1)
    latency_ms: float = Field(ge=0)
    # Provider-reported served model of the answer call, and of each judge
    # call when one was made. A run refuses to mix served models.
    model_id: str
    answer_judge_model_id: str | None = None
    citation_judge_model_id: str | None = None
    response_id: str | None = None
    provider_usage: dict[str, Any]
    cost_usd: float = Field(ge=0)
    # The answer call alone: the efficiency measure for comparing conditions.
    answer_input_tokens: int = Field(ge=0)
    answer_cached_input_tokens: int = Field(ge=0)
    answer_output_tokens: int = Field(ge=0)
    answer_reasoning_tokens: int = Field(ge=0)
    answer_latency_ms: float = Field(ge=0)
    answer_cost_usd: float = Field(ge=0)
    # Evaluation overhead: every judge call for this cell, summed.
    judge_calls: int = Field(default=0, ge=0)
    judge_input_tokens: int = Field(default=0, ge=0)
    judge_output_tokens: int = Field(default=0, ge=0)
    judge_latency_ms: float = Field(default=0, ge=0)
    judge_cost_usd: float = Field(default=0, ge=0)


class RepresentationSummaryRow(BaseModel):
    """Aggregate metrics for one representation condition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    condition: RepresentationCondition
    question_count: int
    # Share of cells whose response was both provider-completed and parseable.
    response_valid_rate: float = Field(ge=0, le=1)
    # Share of all cells with a valid response that did not abstain.
    answer_rate: float = Field(ge=0, le=1)
    answer_equivalence_judge_valid_rate: float | None = Field(default=None, ge=0, le=1)
    citation_entailment_judge_valid_rate: float | None = Field(default=None, ge=0, le=1)
    mean_accuracy: float
    mean_semantic_accuracy: float | None = None
    mean_token_f1: float
    mean_anls: float
    mean_citation_validity: float
    mean_citation_support: float
    mean_citation_entailment: float | None = None
    citation_present_rate: float
    mean_representation_tokens: float
    # Answer call only: the representation efficiency comparison.
    mean_answer_input_tokens: float
    mean_answer_output_tokens: float
    mean_answer_latency_ms: float
    answer_dollars_per_query: float
    answer_dollars_per_correct: float | None
    answer_dollars_per_semantic_correct: float | None = None
    # All calls (answer plus judges): the total cost of running the cell.
    mean_input_tokens: float
    mean_output_tokens: float
    mean_calls: float
    mean_latency_ms: float
    dollars_per_query: float
    dollars_per_correct: float | None
    dollars_per_semantic_correct: float | None = None
    # Judge calls only: evaluation overhead, not representation cost.
    mean_judge_calls: float = 0
    mean_judge_input_tokens: float = 0
    mean_judge_output_tokens: float = 0
    mean_judge_latency_ms: float = 0
    judge_dollars_per_query: float = 0


class RepresentationBenchmarkSummary(BaseModel):
    """Machine-readable RAW/IR/ENRICHED comparison."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    evaluated_question_ids: tuple[str, ...]
    skipped_question_ids: tuple[str, ...]
    question_only_correct_ids: tuple[str, ...]
    question_only_incorrect_ids: tuple[str, ...]
    question_only_invalid_ids: tuple[str, ...]
    # Exact INSUFFICIENT_EVIDENCE abstentions: the instruction-compliant
    # response to an empty evidence section, kept apart from wrong answers.
    question_only_abstained_ids: tuple[str, ...] = ()
    enrichment_prepare_ms: float = Field(ge=0)
    amortized_enrichment_ms_per_question: float = Field(ge=0)
    rows: tuple[RepresentationSummaryRow, ...]
