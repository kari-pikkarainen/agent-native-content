"""IR-node candidate construction for compiler retrieval."""

import hashlib
from collections.abc import Sequence

from contextbench.ir.models import IRDocument, IRNodeKind
from contextbench.ir.tokenizer import TokenCounter
from contextbench.retrieval.models import RetrievalArm, RetrievalChunk

_NON_EVIDENCE_GROUPS = {IRNodeKind.LIST}


def node_chunks(
    documents: Sequence[IRDocument],
    *,
    tokenizer: TokenCounter,
) -> tuple[RetrievalChunk, ...]:
    """Represent each content-bearing IR node as a retrieval candidate."""
    chunks: list[RetrievalChunk] = []
    for document in documents:
        for node in document.nodes:
            if not node.text.strip() or node.kind in _NON_EVIDENCE_GROUPS:
                continue
            payload = f"compiler-node-v1\0{document.id}\0{node.id}".encode()
            chunks.append(
                RetrievalChunk(
                    id=f"chunk_{hashlib.sha256(payload).hexdigest()}",
                    arm=RetrievalArm.COMPILER,
                    document_id=document.id,
                    text=node.text,
                    token_count=tokenizer.count(node.text),
                    heading_path=node.heading_path,
                    page_start=node.page_start,
                    page_end=node.page_end,
                    source_node_ids=(node.id,),
                    source_item_ids=node.source_item_ids,
                )
            )
    return tuple(chunks)
