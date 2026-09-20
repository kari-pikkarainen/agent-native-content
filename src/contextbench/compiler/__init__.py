"""Deterministic structure-aware context compilation."""

from contextbench.compiler.compiler import compile_context, compile_context_with_trace
from contextbench.compiler.corpus import CompilerCorpusIndex
from contextbench.compiler.models import (
    COMPILER_VERSION,
    CompilerConfig,
    CompilerQueryCache,
    CompilerTrace,
    DocumentScope,
)

__all__ = [
    "COMPILER_VERSION",
    "CompilerConfig",
    "CompilerCorpusIndex",
    "CompilerQueryCache",
    "CompilerTrace",
    "DocumentScope",
    "compile_context",
    "compile_context_with_trace",
]
