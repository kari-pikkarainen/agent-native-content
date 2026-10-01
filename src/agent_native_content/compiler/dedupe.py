"""Provenance-aware candidate deduplication."""

import hashlib
import re
from collections.abc import Sequence

from agent_native_content.compiler.models import CompilerCandidate
from agent_native_content.ir.models import IRDocument
from agent_native_content.retrieval.models import RetrievalArm


def deduplicate_candidates(
    candidates: Sequence[CompilerCandidate],
    documents: Sequence[IRDocument],
) -> tuple[CompilerCandidate, ...]:
    """Remove exact text, source-item, and source-box duplicates.

    With merged units in the pool (``compiler/candidates.merge_node_units``)
    one more rule applies: a node-evidence candidate is dropped if any of its
    nodes is already in a kept node-evidence candidate. A merged unit's source
    key is the union of its members' items, so the source-item rule alone
    would keep both a unit and a sibling that is one of its members. The rule
    is gated on a merged unit being present, so a pool without one -- every
    pool when merging is off -- is deduplicated exactly as before.
    """
    documents_by_id = {document.id: document for document in documents}
    seen_text: set[str] = set()
    seen_normalized: list[tuple[str, int | None, int | None, str]] = []
    seen_sources: set[tuple[str, ...]] = set()
    seen_spans: set[tuple[object, ...]] = set()
    kept: list[CompilerCandidate] = []
    check_nodes = any(_is_merged_unit(candidate) for candidate in candidates)
    seen_nodes: set[tuple[str, str]] = set()

    for candidate in candidates:
        chunk = candidate.chunk
        node_keys = (
            [(chunk.document_id, node_id) for node_id in chunk.source_node_ids]
            if check_nodes and candidate.operator in _NODE_EVIDENCE_OPERATORS
            else []
        )
        if any(key in seen_nodes for key in node_keys):
            continue
        text_hash = hashlib.sha256(_normalize(chunk.text).encode()).hexdigest()
        normalized = _normalize(chunk.text)
        source_key = (chunk.document_id, *sorted(chunk.source_item_ids))
        span_key = _span_key(candidate, documents_by_id[chunk.document_id])
        if text_hash in seen_text:
            continue
        if any(
            chunk.document_id == document_id
            and normalized in existing
            and _pages_overlap(
                chunk.page_start,
                chunk.page_end,
                page_start,
                page_end,
            )
            for document_id, page_start, page_end, existing in seen_normalized
        ):
            continue
        if not candidate.allow_shared_source and source_key in seen_sources:
            continue
        if not candidate.allow_shared_source and span_key and span_key in seen_spans:
            continue
        kept.append(candidate)
        seen_nodes.update(node_keys)
        seen_text.add(text_hash)
        seen_normalized.append(
            (chunk.document_id, chunk.page_start, chunk.page_end, normalized)
        )
        if not candidate.allow_shared_source:
            seen_sources.add(source_key)
            if span_key:
                seen_spans.add(span_key)
    return tuple(kept)


# Candidates that are IR nodes rendered as themselves: direct retrieval, and
# the siblings and list neighbours expansion adds. Table fragments, keyed
# joins and page-neighbour windows are views that share nodes by design.
_NODE_EVIDENCE_OPERATORS = frozenset({"retrieval", "sibling", "list_neighbor"})


def _is_merged_unit(candidate: CompilerCandidate) -> bool:
    return (
        candidate.operator == "retrieval"
        and candidate.chunk.arm == RetrievalArm.COMPILER
        and len(candidate.chunk.source_node_ids) > 1
    )


def _span_key(
    candidate: CompilerCandidate,
    document: IRDocument,
) -> tuple[object, ...]:
    boxes = []
    for node_id in candidate.chunk.source_node_ids:
        node = document.node_by_id[node_id]
        boxes.extend(
            (
                box.page_no,
                round(box.left, 4),
                round(box.top, 4),
                round(box.right, 4),
                round(box.bottom, 4),
                box.coord_origin,
            )
            for box in node.bounding_boxes
        )
    return (document.id, *sorted(boxes)) if boxes else ()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _pages_overlap(
    first_start: int | None,
    first_end: int | None,
    second_start: int | None,
    second_end: int | None,
) -> bool:
    if (
        first_start is None
        or first_end is None
        or second_start is None
        or second_end is None
    ):
        return True
    return first_start <= second_end and second_start <= first_end
