"""Evidence-page and redundancy metrics."""

import re
from collections.abc import Mapping, Sequence

from contextbench.datasets.base import BenchmarkQuestion
from contextbench.ir.models import IRDocument
from contextbench.retrieval.models import ContextItem, ContextPacket


def evaluate_context(
    question: BenchmarkQuestion,
    packet: ContextPacket,
    documents: Mapping[str, IRDocument],
) -> dict[str, object]:
    """Calculate exact page coverage and approximate text redundancy."""
    ir_id_to_dataset_id = {document.id: key for key, document in documents.items()}
    item_pages = [
        _item_pages(item, documents, ir_id_to_dataset_id) for item in packet.items
    ]
    selected = _merge_pages(item_pages)
    gold = {
        document_id: tuple(sorted(set(pages)))
        for document_id, pages in question.gold_evidence_pages.items()
    }
    matched = {
        document_id: tuple(
            sorted(set(pages).intersection(selected.get(document_id, ())))
        )
        for document_id, pages in gold.items()
    }
    gold_count = sum(len(pages) for pages in gold.values())
    matched_count = sum(len(pages) for pages in matched.values())
    recall = matched_count / gold_count if gold_count else 1.0
    full_coverage = matched_count == gold_count
    quote_count, matched_quote_count, quote_recall, full_quote_coverage = (
        _quote_coverage(question, packet.items)
    )
    return {
        "selected_pages": selected,
        "gold_pages": gold,
        "matched_pages": matched,
        "evidence_page_recall": recall,
        "full_evidence_coverage": full_coverage,
        "gold_quote_count": quote_count,
        "matched_quote_count": matched_quote_count,
        "evidence_quote_recall": quote_recall,
        "full_quote_coverage": full_quote_coverage,
        "tokens_to_full_evidence": _tokens_to_full(
            packet.items,
            item_pages,
            gold,
        ),
        "redundancy": context_redundancy(packet.items),
    }


def _quote_coverage(
    question: BenchmarkQuestion,
    items: Sequence[ContextItem],
) -> tuple[int, int, float, bool]:
    quotes = tuple(
        _normalize_text(item.quote)
        for evidence in question.gold_evidence
        for item in evidence.items
        if item.quote and item.quote.strip()
    )
    if not quotes:
        return 0, 0, 1.0, True
    context = _normalize_text("\n".join(item.content for item in items))
    matched = sum(quote in context for quote in quotes)
    return len(quotes), matched, matched / len(quotes), matched == len(quotes)


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def context_redundancy(items: Sequence[ContextItem], *, ngram_size: int = 4) -> float:
    """Estimate duplicated token share using repeated cross-item word n-grams."""
    total_tokens = 0
    duplicate_positions = 0
    seen_ngrams: set[tuple[str, ...]] = set()
    for item in items:
        terms = re.findall(r"[\w]+", item.content.casefold())
        total_tokens += len(terms)
        duplicated: set[int] = set()
        current: list[tuple[str, ...]] = []
        for start in range(max(len(terms) - ngram_size + 1, 0)):
            ngram = tuple(terms[start : start + ngram_size])
            current.append(ngram)
            if ngram in seen_ngrams:
                duplicated.update(range(start, start + ngram_size))
        duplicate_positions += len(duplicated)
        seen_ngrams.update(current)
    return duplicate_positions / total_tokens if total_tokens else 0.0


def _item_pages(
    item: ContextItem,
    documents: Mapping[str, IRDocument],
    ir_id_to_dataset_id: Mapping[str, str],
) -> dict[str, tuple[int, ...]]:
    dataset_id = ir_id_to_dataset_id[item.document_id]
    document = documents[dataset_id]
    pages = {
        box.page_no
        for node_id in item.source_node_ids
        for box in document.node_by_id[node_id].bounding_boxes
    }
    if not pages and item.page_start is not None and item.page_end is not None:
        pages.update(range(item.page_start, item.page_end + 1))
    return {dataset_id: tuple(sorted(pages))}


def _merge_pages(
    values: Sequence[Mapping[str, tuple[int, ...]]],
) -> dict[str, tuple[int, ...]]:
    merged: dict[str, set[int]] = {}
    for value in values:
        for document_id, pages in value.items():
            merged.setdefault(document_id, set()).update(pages)
    return {
        document_id: tuple(sorted(pages))
        for document_id, pages in sorted(merged.items())
    }


def _tokens_to_full(
    items: Sequence[ContextItem],
    item_pages: Sequence[Mapping[str, tuple[int, ...]]],
    gold: Mapping[str, tuple[int, ...]],
) -> int | None:
    remaining = {
        (document_id, page) for document_id, pages in gold.items() for page in pages
    }
    if not remaining:
        return 0
    tokens = 0
    for item, pages_by_document in zip(items, item_pages, strict=True):
        tokens += item.token_count
        for document_id, pages in pages_by_document.items():
            remaining.difference_update((document_id, page) for page in pages)
        if not remaining:
            return tokens
    return None
