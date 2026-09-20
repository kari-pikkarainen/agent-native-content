"""Map structurally retrieved source regions back to compiler IR nodes."""

from collections.abc import Sequence

from contextbench.compiler.candidates import node_chunks
from contextbench.ir.models import IRDocument
from contextbench.ir.tokenizer import TokenCounter
from contextbench.retrieval.models import RankedEvidence


def anchor_node_evidence(
    structural_evidence: Sequence[RankedEvidence],
    documents: Sequence[IRDocument],
    *,
    tokenizer: TokenCounter,
    limit: int,
) -> tuple[RankedEvidence, ...]:
    """Project a structural ranking to unique source nodes in ranked order."""
    chunks_by_node = {
        chunk.source_node_ids[0]: chunk
        for chunk in node_chunks(documents, tokenizer=tokenizer)
    }
    seen: set[tuple[str, str]] = set()
    anchored = []
    for evidence in structural_evidence:
        for node_id in evidence.chunk.source_node_ids:
            key = (evidence.chunk.document_id, node_id)
            chunk = chunks_by_node.get(node_id)
            if key in seen or chunk is None:
                continue
            seen.add(key)
            anchored.append(
                RankedEvidence(
                    rank=len(anchored) + 1,
                    chunk=chunk,
                    scores=evidence.scores,
                )
            )
            if len(anchored) == limit:
                return tuple(anchored)
    return tuple(anchored)
