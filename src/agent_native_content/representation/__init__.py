"""Gold-evidence representation efficiency experiments."""

from agent_native_content.representation.models import (
    DEFAULT_REPRESENTATION_CONDITIONS,
    RepresentationBenchmarkSummary,
    RepresentationCondition,
    RepresentationEvaluationRecord,
    RepresentationExperimentConfig,
    RepresentationSummaryRow,
)
from agent_native_content.representation.runner import (
    RepresentationError,
    RepresentationRun,
    render_representation,
    representation_call_ceiling,
    representation_prompt_hashes,
    run_gold_representation_benchmark,
)
from agent_native_content.representation.xl_docbench import run_xl_gold_representation

__all__ = [
    "DEFAULT_REPRESENTATION_CONDITIONS",
    "RepresentationBenchmarkSummary",
    "RepresentationCondition",
    "RepresentationError",
    "RepresentationEvaluationRecord",
    "RepresentationExperimentConfig",
    "RepresentationRun",
    "RepresentationSummaryRow",
    "render_representation",
    "representation_call_ceiling",
    "representation_prompt_hashes",
    "run_gold_representation_benchmark",
    "run_xl_gold_representation",
]
