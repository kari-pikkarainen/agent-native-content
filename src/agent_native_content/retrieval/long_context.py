"""Deterministic source-order chunks for the long-context baseline."""

from collections.abc import Sequence

from agent_native_content.ir.models import IRDocument, IRNodeKind
from agent_native_content.ir.tokenizer import TokenCounter
from agent_native_content.retrieval.models import (
    RankedEvidence,
    RetrievalArm,
    RetrievalChunk,
    RetrievalScores,
)


def long_context_chunks(
    documents: Sequence[IRDocument],
    *,
    tokenizer: TokenCounter,
) -> tuple[RetrievalChunk, ...]:
    """Project body content into source-order chunks without retrieval."""
    chunks: list[RetrievalChunk] = []
    for document in documents:
        for node in sorted(document.nodes, key=lambda value: value.ordinal):
            text = node.text.strip()
            if (
                not text
                or node.content_layer != "body"
                or node.kind == IRNodeKind.LIST
            ):
                continue
            chunks.append(
                RetrievalChunk(
                    id=f"long-context:{node.id}",
                    arm=RetrievalArm.LONG_CONTEXT,
                    document_id=document.id,
                    text=text,
                    token_count=tokenizer.count(text),
                    heading_path=node.heading_path,
                    page_start=node.page_start,
                    page_end=node.page_end,
                    source_node_ids=(node.id,),
                    source_item_ids=node.source_item_ids,
                )
            )
    return tuple(chunks)


def rank_long_context(
    chunks: Sequence[RetrievalChunk],
    *,
    document_ids: set[str],
) -> tuple[RankedEvidence, ...]:
    """Return relevant documents in their original order with no retrieval scores."""
    return tuple(
        RankedEvidence(rank=rank, chunk=chunk, scores=RetrievalScores())
        for rank, chunk in enumerate(
            (chunk for chunk in chunks if chunk.document_id in document_ids),
            start=1,
        )
    )
