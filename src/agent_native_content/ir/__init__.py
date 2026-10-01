"""Minimal structure-preserving intermediate representation."""

from agent_native_content.ir.models import (
    IRBoundingBox,
    IRDocument,
    IRNode,
    IRNodeKind,
    IRTable,
)
from agent_native_content.ir.project import IRProjectionError, project_document
from agent_native_content.ir.serialization import load_ir_document, save_ir_document
from agent_native_content.ir.tokenizer import (
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
