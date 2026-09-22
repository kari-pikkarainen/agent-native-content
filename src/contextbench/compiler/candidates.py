"""IR-node candidate construction for compiler retrieval."""

import hashlib
from collections.abc import Sequence

from contextbench.ir.models import IRDocument, IRNodeKind
from contextbench.ir.tokenizer import TokenCounter
from contextbench.retrieval.chunking import contextual_search_text
from contextbench.retrieval.models import RetrievalArm, RetrievalChunk, RetrievalConfig

_NON_EVIDENCE_GROUPS = {IRNodeKind.LIST}


def node_chunks(
    documents: Sequence[IRDocument],
    *,
    tokenizer: TokenCounter,
    config: RetrievalConfig | None = None,
) -> tuple[RetrievalChunk, ...]:
    """Represent each content-bearing IR node as a retrieval candidate.

    ``config.heading_search_context`` is the same factor the structural
    chunker reads, so an ablation can turn heading context off on both
    heading-bearing content units rather than on one of them. It defaults on,
    which is what the compiler has always done.
    """
    my_config = config or RetrievalConfig()
    chunks: list[RetrievalChunk] = []
    for document in documents:
        for node in document.nodes:
            if (
                not node.text.strip()
                or node.content_layer == "furniture"
                or node.kind in _NON_EVIDENCE_GROUPS
            ):
                continue
            # Search-only, exactly as on the structural unit: ``text`` and its
            # token count are identical in both positions, and the id payload
            # tracks the indexed string so the two positions cannot share a
            # cached candidate id.
            search_text = (
                contextual_search_text(node.text, node.heading_path)
                if my_config.heading_search_context
                else None
            )
            payload = (
                f"compiler-node-v2\0{document.id}\0{node.id}\0"
                f"{search_text if search_text is not None else node.text}"
            ).encode()
            chunks.append(
                RetrievalChunk(
                    id=f"chunk_{hashlib.sha256(payload).hexdigest()}",
                    arm=RetrievalArm.COMPILER,
                    document_id=document.id,
                    text=node.text,
                    search_text=search_text,
                    token_count=tokenizer.count(node.text),
                    heading_path=node.heading_path,
                    page_start=node.page_start,
                    page_end=node.page_end,
                    source_node_ids=(node.id,),
                    source_item_ids=node.source_item_ids,
                )
            )
    return tuple(chunks)
