"""Gold-evidence representation efficiency experiments."""

from contextbench.representation.models import (
    RepresentationBenchmarkSummary,
    RepresentationCondition,
    RepresentationEvaluationRecord,
    RepresentationExperimentConfig,
    RepresentationSummaryRow,
)
from contextbench.representation.runner import (
    RepresentationError,
    RepresentationRun,
    render_representation,
    run_gold_representation_benchmark,
)
from contextbench.representation.xl_docbench import run_xl_gold_representation

__all__ = [
    "RepresentationBenchmarkSummary",
    "RepresentationCondition",
    "RepresentationError",
    "RepresentationEvaluationRecord",
    "RepresentationExperimentConfig",
    "RepresentationRun",
    "RepresentationSummaryRow",
    "render_representation",
    "run_gold_representation_benchmark",
    "run_xl_gold_representation",
]
