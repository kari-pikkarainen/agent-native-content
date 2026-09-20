"""Deterministic structure-aware context compilation."""

from contextbench.compiler.compiler import compile_context
from contextbench.compiler.models import (
    COMPILER_VERSION,
    CompilerConfig,
    DocumentScope,
)

__all__ = [
    "COMPILER_VERSION",
    "CompilerConfig",
    "DocumentScope",
    "compile_context",
]
