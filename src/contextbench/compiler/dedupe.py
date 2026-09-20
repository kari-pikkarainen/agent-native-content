"""Provenance-aware candidate deduplication."""

import hashlib
import re
from collections.abc import Sequence

from contextbench.compiler.models import CompilerCandidate
from contextbench.ir.models import IRDocument


def deduplicate_candidates(
    candidates: Sequence[CompilerCandidate],
    documents: Sequence[IRDocument],
) -> tuple[CompilerCandidate, ...]:
    """Remove exact text, source-item, and source-box duplicates."""
    documents_by_id = {document.id: document for document in documents}
    seen_text: set[str] = set()
    seen_normalized: list[tuple[str, int | None, int | None, str]] = []
    seen_sources: set[tuple[str, ...]] = set()
    seen_spans: set[tuple[object, ...]] = set()
    kept: list[CompilerCandidate] = []

    for candidate in candidates:
        chunk = candidate.chunk
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
        seen_text.add(text_hash)
        seen_normalized.append(
            (chunk.document_id, chunk.page_start, chunk.page_end, normalized)
        )
        if not candidate.allow_shared_source:
            seen_sources.add(source_key)
            if span_key:
                seen_spans.add(span_key)
    return tuple(kept)


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
