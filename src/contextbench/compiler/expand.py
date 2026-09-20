"""Deterministic structural expansion for compiler candidates."""

import hashlib
from collections.abc import Mapping, Sequence

from docling_core.types.doc import DoclingDocument

from contextbench.compiler.models import CompilerCandidate, CompilerConfig
from contextbench.ir.models import IRDocument, IRNode, IRNodeKind
from contextbench.ir.tokenizer import TokenCounter
from contextbench.retrieval.chunking import structural_chunks
from contextbench.retrieval.models import (
    RankedEvidence,
    RetrievalArm,
    RetrievalChunk,
    RetrievalScores,
)
from contextbench.retrieval.rerank import Reranker


def expand_candidates(
    query: str,
    ranked: Sequence[RankedEvidence],
    documents: Sequence[IRDocument],
    *,
    source_documents: Mapping[str, DoclingDocument],
    token_budget: int,
    config: CompilerConfig,
    tokenizer: TokenCounter,
    reranker: Reranker,
) -> tuple[CompilerCandidate, ...]:
    """Add heading context, siblings, list neighbors, and table fallbacks."""
    documents_by_id = {document.id: document for document in documents}
    expanded: list[CompilerCandidate] = []
    table_chunks_by_document: dict[str, tuple[RetrievalChunk, ...]] = {}
    expansion_order = 0

    for evidence in ranked:
        document = documents_by_id[evidence.chunk.document_id]
        node = document.node_by_id[evidence.chunk.source_node_ids[0]]
        direct = _candidate_for_node(
            node,
            evidence=evidence,
            config=config,
            tokenizer=tokenizer,
            expansion_order=expansion_order,
        )
        expansion_order += 1
        minimum_table_tokens = _minimum_table_context_tokens(
            node,
            config,
            tokenizer,
        )
        minimum_table_fragment_tokens = _minimum_table_fragment_tokens(
            node,
            config,
            tokenizer,
        )

        if (
            config.preserve_tables
            and node.kind == IRNodeKind.TABLE
            and direct.chunk.token_count > token_budget
            and minimum_table_fragment_tokens <= token_budget
            and document.id in source_documents
        ):
            table_chunks = table_chunks_by_document.get(document.id)
            if table_chunks is None:
                table_config = config.retrieval.model_copy(
                    update={
                        "structural_chunk_tokens": min(
                            config.table_chunk_tokens,
                            token_budget - minimum_table_tokens,
                        )
                    }
                )
                table_chunks = structural_chunks(
                    document,
                    source_documents[document.id],
                    config=table_config,
                    tokenizer=tokenizer,
                )
                table_chunks_by_document[document.id] = table_chunks
            matching = [
                chunk for chunk in table_chunks if node.id in chunk.source_node_ids
            ]
            table_scores = reranker.score(query, matching)
            for chunk, table_score in zip(matching, table_scores, strict=True):
                rendered = _render_table_chunk(
                    node,
                    chunk.text,
                    include_headings=config.include_heading_context,
                )
                expanded.append(
                    CompilerCandidate(
                        chunk=chunk.model_copy(
                            update={
                                "id": _expanded_id(chunk.id, "table", rendered),
                                "arm": RetrievalArm.COMPILER,
                                "text": rendered,
                                "token_count": tokenizer.count(rendered),
                            }
                        ),
                        scores=evidence.scores.model_copy(
                            update={"reranked": table_score}
                        ),
                        origin_rank=evidence.rank,
                        expansion_order=expansion_order,
                        allow_shared_source=True,
                    )
                )
                expansion_order += 1
        else:
            expanded.append(direct)

        if node.kind == IRNodeKind.PARAGRAPH:
            for sibling in _paragraph_siblings(node, document, config):
                expanded.append(
                    _candidate_for_related_node(
                        sibling,
                        evidence=evidence,
                        penalty=config.sibling_score_penalty,
                        relation="sibling",
                        config=config,
                        tokenizer=tokenizer,
                        expansion_order=expansion_order,
                    )
                )
                expansion_order += 1
        if node.kind == IRNodeKind.LIST_ITEM and config.group_adjacent_list_items:
            for neighbor, distance in _list_neighbors(node, document, config):
                expanded.append(
                    _candidate_for_related_node(
                        neighbor,
                        evidence=evidence,
                        penalty=config.list_score_penalty**distance,
                        relation="list-neighbor",
                        config=config,
                        tokenizer=tokenizer,
                        expansion_order=expansion_order,
                    )
                )
                expansion_order += 1

    expanded.sort(
        key=lambda candidate: (
            -candidate.scores.reranked,
            -candidate.scores.fused,
            candidate.origin_rank,
            candidate.expansion_order,
            candidate.chunk.id,
        )
    )
    return tuple(expanded[: config.max_expanded_candidates])


def _candidate_for_node(
    node: IRNode,
    *,
    evidence: RankedEvidence,
    config: CompilerConfig,
    tokenizer: TokenCounter,
    expansion_order: int,
) -> CompilerCandidate:
    rendered = _render_node(node, include_headings=config.include_heading_context)
    return CompilerCandidate(
        chunk=evidence.chunk.model_copy(
            update={
                "id": _expanded_id(evidence.chunk.id, "direct", rendered),
                "text": rendered,
                "token_count": tokenizer.count(rendered),
            }
        ),
        scores=evidence.scores,
        origin_rank=evidence.rank,
        expansion_order=expansion_order,
    )


def _candidate_for_related_node(
    node: IRNode,
    *,
    evidence: RankedEvidence,
    penalty: float,
    relation: str,
    config: CompilerConfig,
    tokenizer: TokenCounter,
    expansion_order: int,
) -> CompilerCandidate:
    rendered = _render_node(node, include_headings=config.include_heading_context)
    chunk = RetrievalChunk(
        id=_expanded_id(evidence.chunk.id, relation, node.id),
        arm=RetrievalArm.COMPILER,
        document_id=node.document_id,
        text=rendered,
        token_count=tokenizer.count(rendered),
        heading_path=node.heading_path,
        page_start=node.page_start,
        page_end=node.page_end,
        source_node_ids=(node.id,),
        source_item_ids=node.source_item_ids,
    )
    return CompilerCandidate(
        chunk=chunk,
        scores=_penalize(evidence.scores, penalty),
        origin_rank=evidence.rank,
        expansion_order=expansion_order,
    )


def _paragraph_siblings(
    node: IRNode,
    document: IRDocument,
    config: CompilerConfig,
) -> tuple[IRNode, ...]:
    siblings = _siblings(node, document)
    index = siblings.index(node)
    selected: list[IRNode] = []
    if config.include_previous_sibling and index > 0:
        selected.append(siblings[index - 1])
    if config.include_next_sibling and index + 1 < len(siblings):
        selected.append(siblings[index + 1])
    return tuple(
        sibling
        for sibling in selected
        if sibling.kind == IRNodeKind.PARAGRAPH
        and sibling.heading_path == node.heading_path
    )


def _list_neighbors(
    node: IRNode,
    document: IRDocument,
    config: CompilerConfig,
) -> tuple[tuple[IRNode, int], ...]:
    siblings = _siblings(node, document)
    index = siblings.index(node)
    selected: list[tuple[IRNode, int]] = []
    for distance in range(1, config.list_neighbor_limit + 1):
        for position in (index - distance, index + distance):
            if 0 <= position < len(siblings):
                neighbor = siblings[position]
                if neighbor.kind == IRNodeKind.LIST_ITEM:
                    selected.append((neighbor, distance))
    return tuple(selected)


def _siblings(node: IRNode, document: IRDocument) -> list[IRNode]:
    if node.parent_id is not None:
        parent = document.node_by_id[node.parent_id]
        return [document.node_by_id[node_id] for node_id in parent.children_ids]
    return [candidate for candidate in document.nodes if candidate.parent_id is None]


def _render_node(node: IRNode, *, include_headings: bool) -> str:
    headings = node.heading_path
    if headings and headings[-1].strip().casefold() == node.text.strip().casefold():
        headings = headings[:-1]
    return _render_content(node.text, headings, include_headings=include_headings)


def _minimum_table_context_tokens(
    node: IRNode,
    config: CompilerConfig,
    tokenizer: TokenCounter,
) -> int:
    if node.table is None:
        return 0
    lines = []
    if node.table.caption:
        lines.append(node.table.caption)
    if node.table.column_headers:
        lines.append(" | ".join(node.table.column_headers))
    minimum = "\n".join(lines)
    rendered = _render_content(
        minimum,
        node.heading_path,
        include_headings=config.include_heading_context,
    )
    return tokenizer.count(rendered)


def _minimum_table_fragment_tokens(
    node: IRNode,
    config: CompilerConfig,
    tokenizer: TokenCounter,
) -> int:
    if node.table is None or not node.table.rows:
        return _minimum_table_context_tokens(node, config, tokenizer)
    rows = node.table.rows
    if node.table.column_headers and rows[0] == node.table.column_headers:
        rows = rows[1:]
    if not rows:
        return _minimum_table_context_tokens(node, config, tokenizer)
    counts = [
        tokenizer.count(
            _render_table_chunk(
                node,
                " | ".join(row),
                include_headings=config.include_heading_context,
            )
        )
        for row in rows
    ]
    return min(counts)


def _render_table_chunk(
    node: IRNode,
    text: str,
    *,
    include_headings: bool,
) -> str:
    if node.table is None:
        return _render_content(
            text,
            node.heading_path,
            include_headings=include_headings,
        )
    prefixes = []
    normalized_text = " ".join(text.split()).casefold()
    if node.table.caption and node.table.caption.casefold() not in normalized_text:
        prefixes.append(node.table.caption)
    if node.table.column_headers:
        headers = " | ".join(node.table.column_headers)
        if headers.casefold() not in normalized_text:
            prefixes.append(headers)
    table_text = "\n".join((*prefixes, text))
    return _render_content(
        table_text,
        node.heading_path,
        include_headings=include_headings,
    )


def _render_content(
    text: str,
    heading_path: tuple[str, ...],
    *,
    include_headings: bool,
) -> str:
    if not include_headings or not heading_path:
        return text
    heading_text = "\n".join(
        heading if index == 0 else f"> {heading}"
        for index, heading in enumerate(heading_path)
    )
    return f"{heading_text}\n\n{text}"


def _penalize(scores: RetrievalScores, penalty: float) -> RetrievalScores:
    return scores.model_copy(
        update={
            "fused": scores.fused * penalty,
            "reranked": scores.reranked * penalty,
        }
    )


def _expanded_id(base_id: str, relation: str, value: str) -> str:
    payload = f"compiler-expanded-v1\0{base_id}\0{relation}\0{value}".encode()
    return f"chunk_{hashlib.sha256(payload).hexdigest()}"
