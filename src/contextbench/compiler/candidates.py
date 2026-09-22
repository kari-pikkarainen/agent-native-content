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

    ``config.compiler_node_heading_search_context`` governs this unit only.
    The structural chunker reads its own
    ``config.structural_heading_search_context``: the two were split once the
    factorial measured heading context to help structural chunks at the
    smaller budgets while costing this unit page recall at every budget, which
    a single shared field made impossible to act on. Both default on, so the
    compiler still does what it has always done unless a run says otherwise.
    ``FactorialConfig.heading_contexts`` deliberately sets both fields from one
    position, so the ablation that produced that finding stays arm-symmetric.
    """
    my_config = config or RetrievalConfig()
    chunks: list[RetrievalChunk] = []
    for document in documents:
        for node in document.nodes:
            if (
                not node.text.strip()
                # Allowlist, matching every other retrieval surface.
                or node.content_layer != "body"
                or node.kind in _NON_EVIDENCE_GROUPS
            ):
                continue
            # Search-only, exactly as on the structural unit: ``text`` and its
            # token count are identical in both positions.
            search_text = (
                contextual_search_text(node.text, node.heading_path)
                if my_config.compiler_node_heading_search_context
                else None
            )
            # The id is derived from node text alone, never from the indexed
            # string, so both positions of the field above produce
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
