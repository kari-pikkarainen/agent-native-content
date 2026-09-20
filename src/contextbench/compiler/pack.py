"""Exact-token greedy packing for compiler evidence."""

import hashlib
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
) -> ContextPacket:
    """Greedily pack candidates and never exceed the configured budget."""
    items: list[ContextItem] = []
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
        total += token_count
    return ContextPacket(
        query=query,
        token_budget=token_budget,
        token_count=total,
        items=tuple(items),
        metadata=metadata,
    )
