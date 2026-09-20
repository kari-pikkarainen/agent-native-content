"""IR-node candidate construction for compiler retrieval."""

import hashlib
import re
from collections.abc import Sequence

from contextbench.ir.models import IRDocument, IRNode, IRNodeKind
from contextbench.ir.tokenizer import TokenCounter
from contextbench.retrieval.models import RetrievalArm, RetrievalChunk

_NON_EVIDENCE_GROUPS = {IRNodeKind.LIST}
_TABLE_LABEL = re.compile(
    r"\bTable\s+[A-Z0-9]+(?:[.\-][A-Z0-9]+)+",
    flags=re.IGNORECASE,
)


def node_chunks(
    documents: Sequence[IRDocument],
    *,
    tokenizer: TokenCounter,
    table_rows: bool = False,
    table_row_group_size: int = 1,
    table_empty_cell_marker: str = "[blank]",
) -> tuple[RetrievalChunk, ...]:
    """Represent each content-bearing IR node as a retrieval candidate."""
    chunks: list[RetrievalChunk] = []
    for document in documents:
        table_search_labels = _table_search_labels(document.nodes)
        for node in document.nodes:
            if (
                not node.text.strip()
                or node.content_layer == "furniture"
                or node.kind in _NON_EVIDENCE_GROUPS
            ):
                continue
            if table_rows and node.kind == IRNodeKind.TABLE:
                row_chunks = _table_row_chunks(
                    document,
                    node,
                    tokenizer=tokenizer,
                    group_size=table_row_group_size,
                    empty_marker=table_empty_cell_marker,
                    search_labels=table_search_labels.get(node.id, ()),
                )
                if row_chunks:
                    chunks.extend(row_chunks)
                    continue
            search_text = _contextual_search_text(node.text, node.heading_path)
            payload = (
                f"compiler-node-v2\0{document.id}\0{node.id}\0{search_text}"
            ).encode()
            chunks.append(
                RetrievalChunk(
                    id=f"chunk_{hashlib.sha256(payload).hexdigest()}",
                    arm=RetrievalArm.COMPILER,
                    document_id=document.id,
                    text=node.text,
                    search_text=search_text,
                    token_count=tokenizer.count(node.text),
                    heading_path=node.heading_path,
                    page_start=node.page_start,
                    page_end=node.page_end,
                    source_node_ids=(node.id,),
                    source_item_ids=node.source_item_ids,
                )
            )
    return tuple(chunks)


def _table_row_chunks(
    document: IRDocument,
    node: IRNode,
    *,
    tokenizer: TokenCounter,
    group_size: int,
    empty_marker: str,
    search_labels: tuple[str, ...],
) -> tuple[RetrievalChunk, ...]:
    if node.table is None or not node.table.rows:
        return ()
    rows = node.table.rows
    if node.table.column_headers and rows[0] == node.table.column_headers:
        rows = rows[1:]
    chunks = []
    for start in range(0, len(rows), group_size):
        group = rows[start : start + group_size]
        text = _render_table_rows(
            group,
            caption=node.table.caption,
            headers=node.table.column_headers,
            empty_marker=empty_marker,
        )
        if not text.strip():
            continue
        aliases = _compact_header_aliases(node.table.column_headers)
        search_text = _contextual_search_text(
            "\n".join((*search_labels, *aliases, text)),
            node.heading_path,
        )
        payload = (
            f"compiler-table-row-v1\0{document.id}\0{node.id}\0{start}\0"
            f"{search_text}"
        ).encode()
        chunks.append(
            RetrievalChunk(
                id=f"chunk_{hashlib.sha256(payload).hexdigest()}",
                arm=RetrievalArm.COMPILER,
                document_id=document.id,
                text=text,
                search_text=search_text,
                token_count=tokenizer.count(text),
                heading_path=node.heading_path,
                page_start=node.page_start,
                page_end=node.page_end,
                source_node_ids=(node.id,),
                source_item_ids=node.source_item_ids,
            )
        )
    return tuple(chunks)


def _render_table_rows(
    rows: Sequence[tuple[str, ...]],
    *,
    caption: str | None,
    headers: tuple[str, ...],
    empty_marker: str,
) -> str:
    lines = [caption] if caption else []
    for row in rows:
        values = tuple(value.strip() or empty_marker for value in row)
        if headers and len(headers) == len(values):
            lines.append(
                " | ".join(
                    f"{header}: {value}" if header else value
                    for header, value in zip(headers, values, strict=True)
                )
            )
        else:
            lines.append(" | ".join(values))
    return "\n".join(lines)


def _compact_header_aliases(headers: tuple[str, ...]) -> tuple[str, ...]:
    aliases = []
    for header in headers:
        compact = re.sub(r"[^\w]+", "", header, flags=re.UNICODE)
        if compact and compact.casefold() != header.casefold():
            aliases.append(compact)
    return tuple(dict.fromkeys(aliases))


def _table_search_labels(nodes: Sequence[IRNode]) -> dict[str, tuple[str, ...]]:
    """Carry source table labels across header-matched continuation fragments."""
    pending: tuple[str, ...] = ()
    by_headers: dict[tuple[str, ...], tuple[str, ...]] = {}
    labels_by_node: dict[str, tuple[str, ...]] = {}
    for node in nodes:
        stripped = node.text.lstrip()
        if (
            node.kind == IRNodeKind.CAPTION
            or stripped.casefold().startswith("table ")
            or stripped.casefold().startswith("[start table ")
        ):
            pending = tuple(dict.fromkeys(_TABLE_LABEL.findall(node.text)))
        if node.kind != IRNodeKind.TABLE or node.table is None:
            continue
        signature = tuple(
            " ".join(header.casefold().split())
            for header in node.table.column_headers
        )
        own = tuple(
            dict.fromkeys(_TABLE_LABEL.findall(node.table.caption or ""))
        )
        labels = own or pending or by_headers.get(signature, ())
        if labels:
            labels_by_node[node.id] = labels
            if signature:
                by_headers[signature] = labels
        pending = ()
    return labels_by_node


def _contextual_search_text(text: str, heading_path: tuple[str, ...]) -> str:
    headings = heading_path
    if headings and headings[-1].strip().casefold() == text.strip().casefold():
        headings = headings[:-1]
    return "\n".join((*headings, text))
