"""Provider-neutral answer-generation evaluation."""

from contextbench.generation.models import (
    AnswerModelConfig,
    AnswerRequest,
    GenerationBenchmarkSummary,
    GenerationConfig,
    GenerationEvaluationRecord,
    GenerationSummaryRow,
    PricingMetadata,
    ProviderAnswer,
)
from contextbench.generation.providers import AnswerProvider, OpenAIAnswerProvider
from contextbench.generation.runner import (
    GenerationError,
    GenerationRun,
    is_abstention,
    parse_answer_response,
    parse_citation_entailment_response,
    render_answer_prompt,
    render_citation_entailment_prompt,
    render_grounded_prompt,
    response_cost,
    run_generation_benchmark,
)

__all__ = [
    "AnswerModelConfig",
    "AnswerProvider",
    "AnswerRequest",
    "GenerationBenchmarkSummary",
    "GenerationConfig",
    "GenerationError",
    "GenerationEvaluationRecord",
    "GenerationRun",
    "GenerationSummaryRow",
    "is_abstention",
    "OpenAIAnswerProvider",
    "PricingMetadata",
    "ProviderAnswer",
    "parse_answer_response",
    "parse_citation_entailment_response",
    "render_answer_prompt",
    "render_citation_entailment_prompt",
    "render_grounded_prompt",
    "response_cost",
    "run_generation_benchmark",
]
