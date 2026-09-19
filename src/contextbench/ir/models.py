"""Canonical Pydantic models for the minimal benchmark IR."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

IR_SCHEMA_VERSION = "1.0.0"


class IRValidationError(ValueError):
    """Raised when an IR document violates graph or provenance invariants."""


class IRNodeKind(StrEnum):
    """Small source-derived node vocabulary used by retrieval experiments."""

    TITLE = "title"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    LIST_ITEM = "list_item"
    TABLE = "table"
    TABLE_CHUNK = "table_chunk"
    CAPTION = "caption"
    FIGURE = "figure"
    CODE = "code"
    OTHER = "other"


class IRBoundingBox(BaseModel):
    """One source bounding box, retaining its page and coordinate origin."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page_no: int = Field(ge=1)
    left: float
    top: float
    right: float
    bottom: float
    coord_origin: Literal["TOPLEFT", "BOTTOMLEFT"]


class IRTable(BaseModel):
    """Minimal logical table content retained alongside the searchable text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    caption: str | None = None
    column_headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()

    @model_validator(mode="after")
    def dimensions_are_consistent(self) -> "IRTable":
        widths = {len(row) for row in self.rows}
        if len(widths) > 1:
            raise ValueError("all table rows must have the same width")
        width = next(iter(widths), 0)
        if self.column_headers and len(self.column_headers) != width:
            raise ValueError("column_headers must match table row width")
        return self


class IRNode(BaseModel):
    """One normalized, source-traceable document structure node."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    document_id: str
    kind: IRNodeKind
    content_layer: Literal["body", "furniture"]
    parent_id: str | None = None
    children_ids: tuple[str, ...] = ()
    ordinal: int = Field(ge=0)
    text: str
    heading_path: tuple[str, ...] = ()
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    bounding_boxes: tuple[IRBoundingBox, ...] = ()
    source_item_ids: tuple[str, ...]
    token_count: int = Field(ge=0)
    table: IRTable | None = None

    @model_validator(mode="after")
    def local_invariants_hold(self) -> "IRNode":
        if not self.source_item_ids:
            raise ValueError("source_item_ids must not be empty")
        if len(self.source_item_ids) != len(set(self.source_item_ids)):
            raise ValueError("source_item_ids must be unique within a node")
        if len(self.children_ids) != len(set(self.children_ids)):
            raise ValueError("children_ids must not contain duplicates")
        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("page_start and page_end must both be set or both be null")
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_start > self.page_end
        ):
            raise ValueError("page_start must not exceed page_end")
        if self.bounding_boxes and self.page_start is None:
            raise ValueError("bounding boxes require a page range")
        if self.table is not None and self.kind not in {
            IRNodeKind.TABLE,
            IRNodeKind.TABLE_CHUNK,
        }:
            raise ValueError("table metadata is only valid on table nodes")
        if (
            self.kind in {IRNodeKind.TABLE, IRNodeKind.TABLE_CHUNK}
            and self.table is None
        ):
            raise ValueError("table nodes require table metadata")
        return self


class IRDocument(BaseModel):
    """Deterministic normalized projection of one DoclingDocument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = IR_SCHEMA_VERSION
    id: str
    source_uri: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_name: str
    parser_version: str
    parser_core_version: str
    tokenizer_name: str
    tokenizer_version: str
    page_count: int = Field(ge=0)
    page_numbers: tuple[int, ...] = ()
    nodes: tuple[IRNode, ...]

    @model_validator(mode="after")
    def graph_and_provenance_are_valid(self) -> "IRDocument":
        if self.page_numbers != tuple(sorted(set(self.page_numbers))):
            raise ValueError("page_numbers must be sorted and unique")
        if any(page < 1 for page in self.page_numbers):
            raise ValueError("page_numbers must be positive")
        if self.page_count != len(self.page_numbers):
            raise ValueError("page_count must equal the number of page_numbers")

        by_id = {node.id: node for node in self.nodes}
        if len(by_id) != len(self.nodes):
            raise ValueError("node IDs must be unique")
        if {node.ordinal for node in self.nodes} != set(range(len(self.nodes))):
            raise ValueError("node ordinals must be unique and contiguous from zero")

        valid_pages = set(self.page_numbers)
        for node in self.nodes:
            if node.document_id != self.id:
                raise ValueError(f"node {node.id} has the wrong document_id")
            if node.parent_id == node.id:
                raise ValueError(f"node {node.id} cannot be its own parent")
            if node.parent_id is not None and node.parent_id not in by_id:
                raise ValueError(f"node {node.id} has an unknown parent")
            for child_id in node.children_ids:
                if child_id not in by_id:
                    raise ValueError(f"node {node.id} has an unknown child")
                if by_id[child_id].parent_id != node.id:
                    raise ValueError(f"parent/child mismatch for {child_id}")
            if node.parent_id is not None:
                parent = by_id[node.parent_id]
                if node.id not in parent.children_ids:
                    raise ValueError(f"child/parent mismatch for {node.id}")
            if node.page_start is not None and (
                node.page_start not in valid_pages or node.page_end not in valid_pages
            ):
                raise ValueError(f"node {node.id} references an unknown page")
            node_pages = {box.page_no for box in node.bounding_boxes}
            if not node_pages.issubset(valid_pages):
                raise ValueError(f"node {node.id} references an unknown page")
            if node_pages and (
                node.page_start != min(node_pages) or node.page_end != max(node_pages)
            ):
                raise ValueError(f"node {node.id} page range does not match its boxes")

        self._validate_acyclic_and_reachable(by_id)
        return self

    def _validate_acyclic_and_reachable(self, by_id: dict[str, IRNode]) -> None:
        state: dict[str, int] = {}

        def visit(node_id: str) -> None:
            if state.get(node_id) == 1:
                raise ValueError(f"cycle detected at node {node_id}")
            if state.get(node_id) == 2:
                return
            state[node_id] = 1
            for child_id in by_id[node_id].children_ids:
                visit(child_id)
            state[node_id] = 2

        roots = [node.id for node in self.nodes if node.parent_id is None]
        for root_id in roots:
            visit(root_id)
        if len(state) != len(self.nodes):
            raise ValueError("all nodes must be reachable from a root")

    @property
    def node_by_id(self) -> dict[str, IRNode]:
        """Return a convenient non-serialized node lookup."""
        return {node.id: node for node in self.nodes}
