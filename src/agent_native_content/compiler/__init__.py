"""Deterministic structure-aware context compilation."""

from agent_native_content.compiler.compiler import (
    compile_context,
    compile_context_with_trace,
)
from agent_native_content.compiler.corpus import CompilerCorpusIndex
from agent_native_content.compiler.models import (
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
