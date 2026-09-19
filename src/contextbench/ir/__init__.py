"""Minimal structure-preserving intermediate representation."""

from contextbench.ir.models import (
    IRBoundingBox,
    IRDocument,
    IRNode,
    IRNodeKind,
    IRTable,
)
from contextbench.ir.project import IRProjectionError, project_document
from contextbench.ir.serialization import load_ir_document, save_ir_document
from contextbench.ir.tokenizer import (
    DEFAULT_ENCODING,
    TiktokenTokenCounter,
    TokenCounter,
)

__all__ = [
    "DEFAULT_ENCODING",
    "IRBoundingBox",
    "IRDocument",
    "IRNode",
    "IRNodeKind",
    "IRProjectionError",
    "IRTable",
    "TiktokenTokenCounter",
    "TokenCounter",
    "load_ir_document",
    "project_document",
    "save_ir_document",
]
