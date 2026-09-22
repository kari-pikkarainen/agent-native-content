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
            # token count are identical in both positions.
            search_text = (
                contextual_search_text(node.text, node.heading_path)
                if my_config.heading_search_context
                else None
            )
            # The id is derived from node text alone, never from the indexed
            # string, so both positions of ``heading_search_context`` produce
            # identical ids. ``chunk.id`` is a deterministic tie-break sort key
            # in the indexes and in coverage packing, so letting it track
            # ``search_text`` made toggling the factor permute ids and move IR
            # results by a mechanism the structural unit does not have --
            # arm-asymmetric contamination of the very comparison the factor
            # exists to enable. Cache isolation does not need it: every
            # position already rekeys derived indexes through
            # ``RetrievalConfig``, and ``_chunk_from_nodes`` omits
            # ``search_text`` from its payload for the same reason. The
            # ``v3`` marker records that this derivation, not the ``v2`` one,
            # produced the id.
            payload = (
                f"compiler-node-v3\0{document.id}\0{node.id}\0{node.text}"
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
