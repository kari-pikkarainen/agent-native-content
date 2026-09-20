"""Provider-neutral answer-generation evaluation."""

from contextbench.generation.models import (
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
    parse_answer_response,
    render_answer_prompt,
    run_generation_benchmark,
)

__all__ = [
    "AnswerProvider",
    "AnswerRequest",
    "GenerationBenchmarkSummary",
    "GenerationConfig",
    "GenerationError",
    "GenerationEvaluationRecord",
    "GenerationRun",
    "GenerationSummaryRow",
    "OpenAIAnswerProvider",
    "PricingMetadata",
    "ProviderAnswer",
    "parse_answer_response",
    "render_answer_prompt",
    "run_generation_benchmark",
]
