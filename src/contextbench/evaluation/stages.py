"""Candidate-stage evidence metrics for compiler failure analysis."""

from collections.abc import Mapping, Sequence

from contextbench.compiler.models import CompilerCandidate
from contextbench.datasets.base import BenchmarkQuestion
from contextbench.evaluation.models import CandidateStageMetrics
from contextbench.ir.models import IRDocument
from contextbench.retrieval.models import ContextPacket, RetrievalChunk


def evaluate_candidate_stage(
    question: BenchmarkQuestion,
    chunks: Sequence[RetrievalChunk],
    documents: Mapping[str, IRDocument],
) -> CandidateStageMetrics:
    """Measure page recall over a bounded, unpacked candidate sequence."""
    unique = _unique_chunks(chunks)
    selected = _selected_pages(unique, documents)
    matched, recall, full_coverage = _coverage(question, selected)
    return CandidateStageMetrics(
        candidate_count=len(unique),
        candidate_tokens=sum(chunk.token_count for chunk in unique),
        selected_pages=selected,
        matched_pages=matched,
        evidence_page_recall=recall,
        full_evidence_coverage=full_coverage,
    )


def evaluate_compiler_candidates(
    question: BenchmarkQuestion,
    candidates: Sequence[CompilerCandidate],
    documents: Mapping[str, IRDocument],
) -> CandidateStageMetrics:
    """Measure page recall over compiler candidates."""
    return evaluate_candidate_stage(
        question,
        [candidate.chunk for candidate in candidates],
        documents,
    )


def evaluate_packed_stage(
    question: BenchmarkQuestion,
    packet: ContextPacket,
    documents: Mapping[str, IRDocument],
) -> CandidateStageMetrics:
    """Measure the same stage fields for the final packed output."""
    chunks = [
        RetrievalChunk(
            id=item.evidence_id,
            arm="compiler",
            document_id=item.document_id,
            text=item.content,
            token_count=item.token_count,
            heading_path=item.heading_path,
            page_start=item.page_start,
            page_end=item.page_end,
            source_node_ids=item.source_node_ids,
            source_item_ids=item.source_item_ids,
        )
        for item in packet.items
    ]
    return evaluate_candidate_stage(question, chunks, documents)


def gold_pages(question: BenchmarkQuestion) -> dict[str, tuple[int, ...]]:
    """Return canonical sorted gold pages for an audit record."""
    return {
        document_id: tuple(sorted(set(pages)))
        for document_id, pages in question.gold_evidence_pages.items()
    }


def _unique_chunks(chunks: Sequence[RetrievalChunk]) -> tuple[RetrievalChunk, ...]:
    seen: set[tuple[str, str]] = set()
    unique = []
    for chunk in chunks:
        key = (chunk.document_id, chunk.id)
        if key not in seen:
            seen.add(key)
            unique.append(chunk)
    return tuple(unique)


def _selected_pages(
    chunks: Sequence[RetrievalChunk],
    documents: Mapping[str, IRDocument],
) -> dict[str, tuple[int, ...]]:
    ir_id_to_dataset_id = {document.id: key for key, document in documents.items()}
    selected: dict[str, set[int]] = {}
    for chunk in chunks:
        dataset_id = ir_id_to_dataset_id[chunk.document_id]
        document = documents[dataset_id]
        pages = {
            box.page_no
            for node_id in chunk.source_node_ids
            for box in document.node_by_id[node_id].bounding_boxes
        }
        if not pages and chunk.page_start is not None and chunk.page_end is not None:
            pages.update(range(chunk.page_start, chunk.page_end + 1))
        selected.setdefault(dataset_id, set()).update(pages)
    return {
        document_id: tuple(sorted(pages))
        for document_id, pages in sorted(selected.items())
    }


def _coverage(
    question: BenchmarkQuestion,
    selected: Mapping[str, tuple[int, ...]],
) -> tuple[dict[str, tuple[int, ...]], float, bool]:
    gold = gold_pages(question)
    matched = {
        document_id: tuple(
            sorted(set(pages).intersection(selected.get(document_id, ())))
        )
        for document_id, pages in gold.items()
    }
    gold_count = sum(len(pages) for pages in gold.values())
    matched_count = sum(len(pages) for pages in matched.values())
    return (
        matched,
        matched_count / gold_count if gold_count else 1.0,
        matched_count == gold_count,
    )
