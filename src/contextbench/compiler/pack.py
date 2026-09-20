"""Exact-token greedy packing for compiler evidence."""

import hashlib
import re
from collections.abc import Sequence

from contextbench.compiler.models import CompilerCandidate
from contextbench.ir.tokenizer import TokenCounter
from contextbench.retrieval.models import ContextItem, ContextPacket


def pack_candidates(
    query: str,
    candidates: Sequence[CompilerCandidate],
    *,
    token_budget: int,
    tokenizer: TokenCounter,
    metadata: dict[str, str],
    coverage_facets: Sequence[str] = (),
) -> ContextPacket:
    """Greedily pack candidates and never exceed the configured budget."""
    items: list[ContextItem] = []
    total = 0
    ordered = _facet_coverage_order(
        candidates,
        coverage_facets,
        token_budget=token_budget,
        tokenizer=tokenizer,
    )
    for candidate in ordered:
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
        total += token_count
    return ContextPacket(
        query=query,
        token_budget=token_budget,
        token_count=total,
        items=tuple(items),
        metadata=metadata,
    )


def _facet_coverage_order(
    candidates: Sequence[CompilerCandidate],
    facets: Sequence[str],
    *,
    token_budget: int,
    tokenizer: TokenCounter,
) -> tuple[CompilerCandidate, ...]:
    """Reserve one fitting high-overlap candidate per lexical query facet."""
    if not facets:
        return tuple(candidates)
    selected_indices: list[int] = []
    selected_tokens = 0
    for facet in facets:
        terms = set(re.findall(r"[\w][\w.-]*", facet.casefold()))
        if not terms:
            continue
        phrase = " ".join(facet.casefold().split())
        choices = []
        for index, candidate in enumerate(candidates):
            if index in selected_indices:
                continue
            token_count = tokenizer.count(candidate.chunk.text)
            if selected_tokens + token_count > token_budget:
                continue
            text = " ".join(candidate.chunk.retrieval_text.casefold().split())
            matched = len(terms.intersection(re.findall(r"[\w][\w.-]*", text)))
            if matched == 0:
                continue
            choices.append(
                (
                    phrase in text,
                    matched / len(terms),
                    matched,
                    -index,
                    index,
                    token_count,
                )
            )
        if not choices:
            continue
        *_score, index, token_count = max(choices)
        selected_indices.append(index)
        selected_tokens += token_count
    selected = set(selected_indices)
    return tuple(
        [candidates[index] for index in selected_indices]
        + [
            candidate
            for index, candidate in enumerate(candidates)
            if index not in selected
        ]
    )
