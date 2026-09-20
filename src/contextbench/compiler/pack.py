"""Exact-token greedy packing for compiler evidence."""

import hashlib
import re
from collections.abc import Sequence
from typing import Literal

from contextbench.compiler.facets import query_facets
from contextbench.compiler.models import CompilerCandidate
from contextbench.ir.tokenizer import TokenCounter
from contextbench.retrieval.models import ContextItem, ContextPacket

_TERM = re.compile(r"[\w][\w.-]*", flags=re.UNICODE)
_TABLE_REFERENCE = re.compile(
    r"\bTable\s+[A-Z0-9]+(?:[.\-][A-Z0-9]+)+",
    flags=re.IGNORECASE,
)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "was",
    "were",
    "what",
    "which",
    "with",
}


def pack_candidates(
    query: str,
    candidates: Sequence[CompilerCandidate],
    *,
    token_budget: int,
    tokenizer: TokenCounter,
    strategy: Literal["ranked", "coverage"] = "ranked",
    metadata: dict[str, str],
) -> ContextPacket:
    """Pack candidates deterministically and never exceed the token budget."""
    if strategy == "coverage":
        candidates = _coverage_selection(
            query,
            candidates,
            token_budget=token_budget,
            tokenizer=tokenizer,
        )
    items: list[ContextItem] = []
    used_operators = {
        value
        for value in metadata.get("active_operators", "").split(",")
        if value
    }
    total = 0
    for candidate in candidates:
        chunk = candidate.chunk
        token_count = tokenizer.count(chunk.text)
        if total + token_count > token_budget:
            continue
        evidence_payload = f"compiler-evidence-v1\0{chunk.id}\0{chunk.text}".encode()
        items.append(
            ContextItem(
                evidence_id=(
                    f"evidence_{hashlib.sha256(evidence_payload).hexdigest()}"
                ),
                document_id=chunk.document_id,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                heading_path=chunk.heading_path,
                content=chunk.text,
                token_count=token_count,
                source_node_ids=chunk.source_node_ids,
                source_item_ids=chunk.source_item_ids,
                scores=candidate.scores,
            )
        )
        if candidate.operator != "retrieval":
            used_operators.add(candidate.operator)
        total += token_count
    return ContextPacket(
        query=query,
        token_budget=token_budget,
        token_count=total,
        items=tuple(items),
        metadata={
            **metadata,
            "active_operators": ",".join(sorted(used_operators)),
        },
    )


def _coverage_selection(
    query: str,
    candidates: Sequence[CompilerCandidate],
    *,
    token_budget: int,
    tokenizer: TokenCounter,
) -> tuple[CompilerCandidate, ...]:
    """Select evidence by marginal query, facet, reference, and source coverage."""
    query_terms = _terms(query)
    facet_terms = tuple(
        _terms(facet)
        for facet in query_facets(query, limit=4, min_terms=2)
    )
    query_references = {
        _normalize(reference) for reference in _TABLE_REFERENCE.findall(query)
    }
    prepared = [
        (
            candidate,
            tokenizer.count(candidate.chunk.text),
            _terms(candidate.chunk.retrieval_text),
            {
                _normalize(reference)
                for reference in _TABLE_REFERENCE.findall(
                    candidate.chunk.retrieval_text
                )
            },
        )
        for candidate in candidates
    ]
    selected: list[CompilerCandidate] = []
    remaining = token_budget
    covered_terms: set[str] = set()
    covered_facets: set[int] = set()
    covered_references: set[str] = set()
    covered_pages: set[tuple[str, int]] = set()
    covered_headings: set[tuple[str, ...]] = set()
    while prepared:
        fitting = [value for value in prepared if value[1] <= remaining]
        if not fitting:
            break
        minimum_tier = min(value[0].priority_tier for value in fitting)
        tier = [value for value in fitting if value[0].priority_tier == minimum_tier]
        best = min(
            tier,
            key=lambda value: _coverage_key(
                value,
                query_terms=query_terms,
                facet_terms=facet_terms,
                query_references=query_references,
                covered_terms=covered_terms,
                covered_facets=covered_facets,
                covered_references=covered_references,
                covered_pages=covered_pages,
                covered_headings=covered_headings,
            ),
        )
        prepared.remove(best)
        candidate, token_count, terms, references = best
        selected.append(candidate)
        remaining -= token_count
        matched_terms = terms.intersection(query_terms)
        covered_terms.update(matched_terms)
        covered_facets.update(
            index
            for index, required in enumerate(facet_terms)
            if required and len(required.intersection(terms)) / len(required) >= 0.5
        )
        covered_references.update(references.intersection(query_references))
        covered_pages.update(_page_keys(candidate))
        if candidate.chunk.heading_path:
            covered_headings.add(candidate.chunk.heading_path)
    return tuple(selected)


def _coverage_key(
    value: tuple[CompilerCandidate, int, set[str], set[str]],
    *,
    query_terms: set[str],
    facet_terms: tuple[set[str], ...],
    query_references: set[str],
    covered_terms: set[str],
    covered_facets: set[int],
    covered_references: set[str],
    covered_pages: set[tuple[str, int]],
    covered_headings: set[tuple[str, ...]],
) -> tuple[object, ...]:
    candidate, token_count, terms, references = value
    matched_terms = terms.intersection(query_terms)
    new_terms = matched_terms.difference(covered_terms)
    matched_facets = {
        index
        for index, required in enumerate(facet_terms)
        if required and len(required.intersection(terms)) / len(required) >= 0.5
    }
    new_facets = matched_facets.difference(covered_facets)
    new_references = references.intersection(query_references).difference(
        covered_references
    )
    new_pages = _page_keys(candidate).difference(covered_pages)
    new_heading = bool(
        candidate.chunk.heading_path
        and candidate.chunk.heading_path not in covered_headings
    )
    utility = (
        8.0 * len(new_references)
        + 6.0 * len(new_facets)
        + 2.0 * len(new_terms)
        + 0.25 * len(new_pages)
        + 0.25 * new_heading
        + 4.0 / candidate.origin_rank
    )
    density = utility / max(token_count, 1)
    return (
        -utility,
        -density,
        -candidate.scores.reranked,
        candidate.origin_rank,
        candidate.expansion_order,
        candidate.chunk.id,
    )


def _page_keys(candidate: CompilerCandidate) -> set[tuple[str, int]]:
    chunk = candidate.chunk
    if chunk.page_start is None or chunk.page_end is None:
        return set()
    return {
        (chunk.document_id, page)
        for page in range(chunk.page_start, chunk.page_end + 1)
    }


def _terms(value: str) -> set[str]:
    return {
        match.group(0).casefold()
        for match in _TERM.finditer(value)
        if match.group(0).casefold() not in _STOPWORDS
    }


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())
