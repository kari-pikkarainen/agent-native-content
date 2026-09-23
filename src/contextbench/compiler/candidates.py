"""IR-node candidate construction for compiler retrieval."""

import hashlib
import json
from collections.abc import Sequence

from contextbench.compiler.models import NodeMergePolicy
from contextbench.ir.models import IRDocument, IRNode, IRNodeKind
from contextbench.ir.tokenizer import TokenCounter
from contextbench.retrieval.chunking import contextual_search_text
from contextbench.retrieval.models import RetrievalArm, RetrievalChunk, RetrievalConfig

_NON_EVIDENCE_GROUPS = {IRNodeKind.LIST}


def node_chunks(
    documents: Sequence[IRDocument],
    *,
    tokenizer: TokenCounter,
    config: RetrievalConfig | None = None,
    merge: NodeMergePolicy | None = None,
) -> tuple[RetrievalChunk, ...]:
    """Represent each content-bearing IR node as a retrieval candidate.

    With ``merge`` set, runs of source-adjacent tiny prose nodes are then
    joined into larger units by ``merge_node_units``; every other candidate,
    and every candidate when ``merge`` is ``None``, is the one-node chunk this
    function has always produced, id included.

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
        document_chunks: list[tuple[IRNode, RetrievalChunk]] = []
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
            document_chunks.append(
                (node, RetrievalChunk(
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
                ))
            )
        if merge is None:
            chunks.extend(chunk for _node, chunk in document_chunks)
        else:
            chunks.extend(
                merge_node_units(
                    document_chunks,
                    policy=merge,
                    tokenizer=tokenizer,
                    heading_search_context=(
                        my_config.compiler_node_heading_search_context
                    ),
                )
            )
    return tuple(chunks)


# Prose only. Headings and titles are already rendered as each unit's heading
# trail; tables and table chunks keep their own fragment and keyed-join paths;
# captions belong to the table or figure beside them; code and ``other`` have
# no prose joiner that is safe to assume. Any of these ends a run.
MERGEABLE_NODE_KINDS = frozenset({IRNodeKind.PARAGRAPH, IRNodeKind.LIST_ITEM})
MERGED_UNIT_JOINER = "\n"
_MERGED_ID_DOMAIN = "compiler-merged-v1"


def merged_unit_id(document_id: str, node_ids: Sequence[str], text: str) -> str:
    """Deterministic id of a merged unit, disjoint from every one-node id.

    The preimage starts with its own domain marker, where a one-node id's
    starts with ``compiler-node-v3``, so no merged preimage equals a one-node
    preimage whatever the ids and text: a collision would need a SHA-256
    collision. The node ids and text are framed by JSON, so no two distinct
    (document, node run, text) triples share a preimage either.
    """
    payload = _MERGED_ID_DOMAIN + "\0" + json.dumps(
        [document_id, list(node_ids), text],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"chunk_{hashlib.sha256(payload.encode()).hexdigest()}"


def merge_node_units(
    node_candidates: Sequence[tuple[IRNode, RetrievalChunk]],
    *,
    policy: NodeMergePolicy,
    tokenizer: TokenCounter,
    heading_search_context: bool,
) -> tuple[RetrievalChunk, ...]:
    """Join runs of source-adjacent tiny prose nodes of one document.

    Deterministic and query-independent: one left-to-right pass over the
    document's node candidates in reading order. A node joins the open run
    only if all of these hold:

    - its kind is in ``MERGEABLE_NODE_KINDS`` and it has a page range;
    - it is under ``policy.min_tokens`` on its own (a node at or above the
      minimum is already a unit and stays alone, with its one-node id);
    - it has the run's ``heading_path`` exactly;
    - the run with it spans at most ``policy.max_page_span`` pages;
    - the joined text stays within ``policy.max_tokens``.

    Any other candidate between two tiny nodes ends the run, so a run is
    always contiguous among the document's candidates. A run closes as soon as
    it reaches ``policy.target_tokens``. A run of one node -- a tiny node with
    no mergeable neighbour -- is emitted as the unchanged one-node candidate,
    never dropped and never re-identified.
    """
    units: list[RetrievalChunk] = []
    run: list[tuple[IRNode, RetrievalChunk]] = []
    run_text = ""

    def close() -> None:
        nonlocal run, run_text
        if len(run) == 1:
            units.append(run[0][1])
        elif run:
            units.append(
                _merged_chunk(
                    run,
                    run_text,
                    tokenizer=tokenizer,
                    heading_search_context=heading_search_context,
                )
            )
        run = []
        run_text = ""

    for node, chunk in node_candidates:
        if (
            node.kind not in MERGEABLE_NODE_KINDS
            or node.page_start is None
            or node.page_end is None
            or chunk.token_count >= policy.min_tokens
        ):
            close()
            units.append(chunk)
            continue
        if run:
            first = run[0][0]
            joined = run_text + MERGED_UNIT_JOINER + node.text
            span = _page_span(node, *(member for member, _chunk in run))
            if (
                node.heading_path == first.heading_path
                and span <= policy.max_page_span
                and tokenizer.count(joined) <= policy.max_tokens
            ):
                run.append((node, chunk))
                run_text = joined
                if tokenizer.count(run_text) >= policy.target_tokens:
                    close()
                continue
            close()
        run = [(node, chunk)]
        run_text = node.text
    close()
    return tuple(units)


def _page_span(*nodes: IRNode) -> int:
    starts = [node.page_start for node in nodes if node.page_start is not None]
    ends = [node.page_end for node in nodes if node.page_end is not None]
    return max(ends) - min(starts) + 1


def _merged_chunk(
    run: Sequence[tuple[IRNode, RetrievalChunk]],
    text: str,
    *,
    tokenizer: TokenCounter,
    heading_search_context: bool,
) -> RetrievalChunk:
    nodes = [node for node, _chunk in run]
    first = nodes[0]
    node_ids = tuple(node.id for node in nodes)
    item_ids: list[str] = []
    seen_items: set[str] = set()
    for node in nodes:
        for item_id in node.source_item_ids:
            if item_id not in seen_items:
                seen_items.add(item_id)
                item_ids.append(item_id)
    return RetrievalChunk(
        id=merged_unit_id(first.document_id, node_ids, text),
        arm=RetrievalArm.COMPILER,
        document_id=first.document_id,
        text=text,
        search_text=(
            contextual_search_text(text, first.heading_path)
            if heading_search_context
            else None
        ),
        token_count=tokenizer.count(text),
        heading_path=first.heading_path,
        # Every member has a page range; ``merge_node_units`` admits no other.
        page_start=min(n.page_start for n in nodes if n.page_start is not None),
        page_end=max(n.page_end for n in nodes if n.page_end is not None),
        source_node_ids=node_ids,
        source_item_ids=tuple(item_ids),
    )
