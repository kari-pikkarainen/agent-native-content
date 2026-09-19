"""Deterministic projection from DoclingDocument into the minimal IR."""

import hashlib
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from docling_core.types.doc import (
    DocItem,
    DoclingDocument,
    GroupItem,
    NodeItem,
    PictureItem,
    TableItem,
    TextItem,
)
from docling_core.types.doc.labels import DocItemLabel, GroupLabel

from contextbench.ingest.cache import IngestMetadata
from contextbench.ir.models import (
    IRBoundingBox,
    IRDocument,
    IRNode,
    IRNodeKind,
    IRTable,
)
from contextbench.ir.tokenizer import TiktokenTokenCounter, TokenCounter

_ROOT_REFS = {"#/body", "#/furniture"}
_LIST_GROUP_LABELS = {GroupLabel.LIST, GroupLabel.ORDERED_LIST}
_PARAGRAPH_LABELS = {
    DocItemLabel.TEXT,
    DocItemLabel.PARAGRAPH,
    DocItemLabel.FOOTNOTE,
    DocItemLabel.REFERENCE,
    DocItemLabel.HANDWRITTEN_TEXT,
    DocItemLabel.FIELD_VALUE,
}


class IRProjectionError(RuntimeError):
    """Raised when source structure cannot be projected without data loss."""


def project_document(
    document: DoclingDocument,
    metadata: IngestMetadata,
    *,
    source_uri: str | None = None,
    tokenizer: TokenCounter | None = None,
) -> IRDocument:
    """Project the authoritative parsed artifact into deterministic IR nodes."""
    token_counter = tokenizer or TiktokenTokenCounter()
    document_id = f"doc_{metadata.source_sha256}"
    items = list(_ordered_items(document))
    item_by_ref = {item.self_ref: item for item in items}
    if len(item_by_ref) != len(items):
        raise IRProjectionError("DoclingDocument contains duplicate source item refs")

    node_id_by_ref = {
        source_ref: _stable_node_id(document_id, source_ref)
        for source_ref in item_by_ref
    }
    parent_ref_by_ref: dict[str, str | None] = {}
    child_refs_by_ref: dict[str, list[str]] = defaultdict(list)
    for item in items:
        parent_ref = item.parent.cref if item.parent is not None else None
        if parent_ref in _ROOT_REFS:
            parent_ref = None
        elif parent_ref is not None and parent_ref not in item_by_ref:
            raise IRProjectionError(
                f"source item {item.self_ref} has unknown parent {parent_ref}"
            )
        parent_ref_by_ref[item.self_ref] = parent_ref
        if parent_ref is not None:
            child_refs_by_ref[parent_ref].append(item.self_ref)

    heading_paths = _heading_paths(items)

    nodes = tuple(
        _project_node(
            document=document,
            item=item,
            ordinal=ordinal,
            document_id=document_id,
            node_id_by_ref=node_id_by_ref,
            parent_ref_by_ref=parent_ref_by_ref,
            child_refs_by_ref=child_refs_by_ref,
            heading_path=heading_paths[item.self_ref],
            token_counter=token_counter,
        )
        for ordinal, item in enumerate(items)
    )
    page_numbers = tuple(sorted(document.pages))
    return IRDocument(
        id=document_id,
        source_uri=source_uri or Path(metadata.source_path).as_uri(),
        source_sha256=metadata.source_sha256,
        parser_name=metadata.parser_name,
        parser_version=metadata.parser_version,
        parser_core_version=metadata.parser_core_version,
        tokenizer_name=token_counter.name,
        tokenizer_version=token_counter.version,
        page_count=len(page_numbers),
        page_numbers=page_numbers,
        nodes=nodes,
    )


def _ordered_items(document: DoclingDocument) -> Iterable[NodeItem]:
    seen: set[str] = set()
    # Docling retains the legacy furniture root as a deprecated model field.
    # Read the stored value directly so older artifacts remain fully traversable.
    furniture = document.__dict__.get("furniture")
    roots = (document.body,) if furniture is None else (document.body, furniture)
    for root in roots:
        for item, _level in document.iterate_items(root=root, with_groups=True):
            if item.self_ref in _ROOT_REFS or item.self_ref in seen:
                continue
            seen.add(item.self_ref)
            yield item

    collections = (
        document.groups,
        document.texts,
        document.tables,
        document.pictures,
        document.key_value_items,
        document.form_items,
        document.field_regions,
        document.field_items,
    )
    for collection in collections:
        for item in collection:
            if item.self_ref in seen:
                continue
            seen.add(item.self_ref)
            yield item


def _project_node(
    *,
    document: DoclingDocument,
    item: NodeItem,
    ordinal: int,
    document_id: str,
    node_id_by_ref: dict[str, str],
    parent_ref_by_ref: dict[str, str | None],
    child_refs_by_ref: dict[str, list[str]],
    heading_path: tuple[str, ...],
    token_counter: TokenCounter,
) -> IRNode:
    source_ref = item.self_ref
    kind = _node_kind(item)
    table = _project_table(document, item) if isinstance(item, TableItem) else None
    text = _node_text(document, item, table)
    boxes = _bounding_boxes(item)
    pages = [box.page_no for box in boxes]
    parent_ref = parent_ref_by_ref[source_ref]
    content_layer = getattr(item.content_layer, "value", item.content_layer)
    if content_layer not in {"body", "furniture"}:
        raise IRProjectionError(
            f"source item {source_ref} has unknown content layer {content_layer!r}"
        )
    return IRNode(
        id=node_id_by_ref[source_ref],
        document_id=document_id,
        kind=kind,
        content_layer=content_layer,
        parent_id=node_id_by_ref[parent_ref] if parent_ref is not None else None,
        children_ids=tuple(
            node_id_by_ref[child_ref] for child_ref in child_refs_by_ref[source_ref]
        ),
        ordinal=ordinal,
        text=text,
        heading_path=heading_path,
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        bounding_boxes=boxes,
        source_item_ids=(source_ref,),
        token_count=token_counter.count(text),
        table=table,
    )


def _node_kind(item: NodeItem) -> IRNodeKind:
    if isinstance(item, GroupItem):
        return (
            IRNodeKind.LIST if item.label in _LIST_GROUP_LABELS else IRNodeKind.OTHER
        )
    if isinstance(item, TableItem):
        return IRNodeKind.TABLE
    if isinstance(item, PictureItem):
        return IRNodeKind.FIGURE
    if not isinstance(item, DocItem):
        return IRNodeKind.OTHER
    if item.label == DocItemLabel.TITLE:
        return IRNodeKind.TITLE
    if item.label in {DocItemLabel.SECTION_HEADER, DocItemLabel.FIELD_HEADING}:
        return IRNodeKind.HEADING
    if item.label == DocItemLabel.LIST_ITEM:
        return IRNodeKind.LIST_ITEM
    if item.label == DocItemLabel.CAPTION:
        return IRNodeKind.CAPTION
    if item.label in {DocItemLabel.PICTURE, DocItemLabel.CHART}:
        return IRNodeKind.FIGURE
    if item.label == DocItemLabel.CODE:
        return IRNodeKind.CODE
    if item.label in _PARAGRAPH_LABELS:
        return IRNodeKind.PARAGRAPH
    return IRNodeKind.OTHER


def _node_text(
    document: DoclingDocument, item: NodeItem, table: IRTable | None
) -> str:
    if table is not None:
        lines = [table.caption] if table.caption else []
        lines.extend(" | ".join(row) for row in table.rows)
        return "\n".join(lines)
    if isinstance(item, TextItem):
        return item.text
    if isinstance(item, PictureItem):
        return item.caption_text(document)
    if isinstance(item, GroupItem):
        return item.name or ""
    value = getattr(item, "text", "")
    return value if isinstance(value, str) else ""


def _project_table(document: DoclingDocument, item: TableItem) -> IRTable:
    data = item.data
    rows = [["" for _ in range(data.num_cols)] for _ in range(data.num_rows)]
    header_parts: list[list[str]] = [[] for _ in range(data.num_cols)]
    ordered_cells = sorted(
        data.table_cells,
        key=lambda cell: (cell.start_row_offset_idx, cell.start_col_offset_idx),
    )
    for cell in ordered_cells:
        row_start = cell.start_row_offset_idx
        row_end = cell.end_row_offset_idx
        column_start = cell.start_col_offset_idx
        column_end = cell.end_col_offset_idx
        if not (
            0 <= row_start < row_end <= data.num_rows
            and 0 <= column_start < column_end <= data.num_cols
        ):
            raise IRProjectionError(
                f"table {item.self_ref} contains an out-of-bounds cell"
            )
        for row in range(row_start, row_end):
            for column in range(column_start, column_end):
                rows[row][column] = cell.text
        if cell.column_header:
            for header_column in range(column_start, column_end):
                if cell.text not in header_parts[header_column]:
                    header_parts[header_column].append(cell.text)
    column_headers = tuple(" / ".join(parts) for parts in header_parts)
    if not any(column_headers):
        column_headers = ()
    caption = item.caption_text(document).strip() or None
    return IRTable(
        caption=caption,
        column_headers=column_headers,
        rows=tuple(tuple(row) for row in rows),
    )


def _bounding_boxes(item: NodeItem) -> tuple[IRBoundingBox, ...]:
    if not isinstance(item, DocItem):
        return ()
    return tuple(
        IRBoundingBox(
            page_no=provenance.page_no,
            left=provenance.bbox.l,
            top=provenance.bbox.t,
            right=provenance.bbox.r,
            bottom=provenance.bbox.b,
            coord_origin=provenance.bbox.coord_origin.value,
        )
        for provenance in item.prov
    )


def _heading_paths(items: list[NodeItem]) -> dict[str, tuple[str, ...]]:
    """Resolve section context from document order and Docling heading levels."""
    title: str | None = None
    headings: list[tuple[int, str]] = []
    paths: dict[str, tuple[str, ...]] = {}
    for item in items:
        content_layer = getattr(item.content_layer, "value", item.content_layer)
        if content_layer != "body":
            paths[item.self_ref] = ()
            continue

        kind = _node_kind(item)
        text = _node_text_for_heading(item)
        if kind == IRNodeKind.TITLE:
            title = text or None
            headings.clear()
        elif kind == IRNodeKind.HEADING and text:
            level = getattr(item, "level", None)
            normalized_level = level if isinstance(level, int) and level > 0 else 1
            while headings and headings[-1][0] >= normalized_level:
                headings.pop()
            headings.append((normalized_level, text))

        prefix = (title,) if title else ()
        paths[item.self_ref] = prefix + tuple(text for _level, text in headings)
    return paths


def _node_text_for_heading(item: NodeItem) -> str:
    return item.text if isinstance(item, TextItem) else ""


def _stable_node_id(document_id: str, source_ref: str) -> str:
    value = f"contextbench-ir-v1\0{document_id}\0{source_ref}".encode()
    return f"node_{hashlib.sha256(value).hexdigest()}"
