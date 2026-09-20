"""Deterministic structural expansion for compiler candidates."""

import hashlib
import json
import re
from collections.abc import Mapping, Sequence

from docling_core.types.doc import DoclingDocument

from contextbench.compiler.models import (
    CompilerCandidate,
    CompilerConfig,
    CompilerQueryCache,
)
from contextbench.ir.models import IRDocument, IRNode, IRNodeKind
from contextbench.ir.tokenizer import TokenCounter
from contextbench.retrieval.chunking import fixed_chunks, structural_chunks
from contextbench.retrieval.models import (
    RankedEvidence,
    RetrievalArm,
    RetrievalChunk,
    RetrievalScores,
)
from contextbench.retrieval.rerank import Reranker

_TABLE_REFERENCE = re.compile(
    r"\btable\s+([A-Z0-9][A-Z0-9.\-–—]*)",
    flags=re.IGNORECASE,
)


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
    query_cache: CompilerQueryCache | None = None,
) -> tuple[CompilerCandidate, ...]:
    """Add heading context, siblings, list neighbors, and table fallbacks."""
    documents_by_id = {document.id: document for document in documents}
    expanded: list[CompilerCandidate] = []
    table_chunks_by_document: dict[str, tuple[RetrievalChunk, ...]] = {}
    table_references = _table_references(query)
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
            for sibling, distance in _paragraph_siblings(node, document, config):
                expanded.append(
                    _candidate_for_related_node(
                        sibling,
                        evidence=evidence,
                        penalty=config.sibling_score_penalty**distance,
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
        if (
            node.kind == IRNodeKind.TABLE
            and token_budget >= config.table_neighbor_min_budget
            and table_references
            and _matches_table_reference(node, table_references)
        ):
            for neighbor, distance in _table_neighbors(node, document, config):
                expanded.append(
                    _candidate_for_related_node(
                        neighbor,
                        evidence=evidence,
                        penalty=config.table_neighbor_score_penalty**distance,
                        relation="table-neighbor",
                        config=config,
                        tokenizer=tokenizer,
                        expansion_order=expansion_order,
                    )
                )
                expansion_order += 1

    if (
        config.page_neighbor_radius > 0
        and token_budget >= config.page_neighbor_min_budget
        and _unique_candidate_capacity(expanded, token_budget) < token_budget
    ):
        def factory() -> tuple[CompilerCandidate, ...]:
            return _page_neighbor_candidates(
                query,
                ranked,
                documents,
                config=config,
                tokenizer=tokenizer,
                reranker=reranker,
            )

        page_neighbors = (
            query_cache.page_neighbors(
                _page_neighbor_cache_key(query, ranked, documents, config),
                factory,
            )
            if query_cache is not None
            else factory()
        )
        expanded.extend(
            candidate.model_copy(
                update={"expansion_order": expansion_order + offset}
            )
            for offset, candidate in enumerate(page_neighbors)
        )

    expanded.sort(
        key=lambda candidate: (
            candidate.priority_tier,
            -candidate.scores.reranked,
            -candidate.scores.fused,
            candidate.origin_rank,
            candidate.expansion_order,
            candidate.chunk.id,
        )
    )
    return tuple(expanded)


def _unique_candidate_capacity(
    candidates: Sequence[CompilerCandidate],
    token_budget: int,
) -> int:
    """Estimate packable core capacity without counting expanded duplicates."""
    seen_sources: set[tuple[str, ...]] = set()
    total = 0
    for candidate in candidates:
        chunk = candidate.chunk
        if chunk.token_count > token_budget:
            continue
        source_key = (chunk.document_id, *sorted(chunk.source_item_ids))
        if not candidate.allow_shared_source and source_key in seen_sources:
            continue
        if not candidate.allow_shared_source:
            seen_sources.add(source_key)
        total += chunk.token_count
    return total


def _page_neighbor_candidates(
    query: str,
    ranked: Sequence[RankedEvidence],
    documents: Sequence[IRDocument],
    *,
    config: CompilerConfig,
    tokenizer: TokenCounter,
    reranker: Reranker,
) -> tuple[CompilerCandidate, ...]:
    """Rerank bounded fixed windows near the strongest node-level hits."""
    documents_by_id = {document.id: document for document in documents}
    chunks_by_document: dict[str, tuple[RetrievalChunk, ...]] = {}
    nearby: dict[str, tuple[RetrievalChunk, RankedEvidence, int]] = {}
    for evidence in ranked[: config.page_neighbor_origin_limit]:
        anchor = evidence.chunk
        if anchor.page_start is None or anchor.page_end is None:
            continue
        document = documents_by_id[anchor.document_id]
        page_chunks = chunks_by_document.get(document.id)
        if page_chunks is None:
            page_chunks = fixed_chunks(
                document,
                config=config.retrieval,
                tokenizer=tokenizer,
            )
            chunks_by_document[document.id] = page_chunks
        for chunk in page_chunks:
            if chunk.page_start is None or chunk.page_end is None:
                continue
            distance = _page_range_distance(
                anchor.page_start,
                anchor.page_end,
                chunk.page_start,
                chunk.page_end,
            )
            if distance > config.page_neighbor_radius:
                continue
            previous = nearby.get(chunk.id)
            if previous is None or (distance, evidence.rank) < (
                previous[2],
                previous[1].rank,
            ):
                nearby[chunk.id] = (chunk, evidence, distance)

    candidates = tuple(nearby.values())
    if not candidates:
        return ()
    scores = reranker.score(
        query,
        [chunk for chunk, _evidence, _distance in candidates],
    )
    expanded = []
    for offset, ((chunk, evidence, distance), score) in enumerate(
        zip(candidates, scores, strict=True)
    ):
        penalty = config.page_neighbor_score_penalty ** max(distance, 1)
        expanded.append(
            CompilerCandidate(
                chunk=chunk.model_copy(
                    update={
                        "id": _expanded_id(chunk.id, "page-neighbor", str(distance)),
                        "arm": RetrievalArm.COMPILER,
                    }
                ),
                scores=evidence.scores.model_copy(
                    update={
                        "fused": evidence.scores.fused * penalty,
                        "reranked": _penalized_reranker_score(score, penalty),
                    }
                ),
                origin_rank=evidence.rank,
                expansion_order=offset,
                priority_tier=1,
            )
        )
    expanded.sort(
        key=lambda candidate: (
            -candidate.scores.reranked,
            -candidate.scores.fused,
            candidate.origin_rank,
            candidate.chunk.id,
        )
    )
    return tuple(expanded[: config.page_neighbor_candidate_limit])


def _page_neighbor_cache_key(
    query: str,
    ranked: Sequence[RankedEvidence],
    documents: Sequence[IRDocument],
    config: CompilerConfig,
) -> str:
    payload = {
        "query": query,
        "documents": [(document.id, document.source_sha256) for document in documents],
        "ranked": [
            (evidence.rank, evidence.chunk.id, evidence.scores.model_dump(mode="json"))
            for evidence in ranked
        ],
        "config": config.model_dump(mode="json"),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def _page_range_distance(
    first_start: int,
    first_end: int,
    second_start: int,
    second_end: int,
) -> int:
    if first_end < second_start:
        return second_start - first_end
    if second_end < first_start:
        return first_start - second_end
    return 0


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
) -> tuple[tuple[IRNode, int], ...]:
    siblings = _siblings(node, document)
    index = siblings.index(node)
    selected: list[tuple[IRNode, int]] = []
    for distance in range(1, config.sibling_neighbor_limit + 1):
        positions = []
        if config.include_previous_sibling:
            positions.append(index - distance)
        if config.include_next_sibling:
            positions.append(index + distance)
        for position in positions:
            if 0 <= position < len(siblings):
                selected.append((siblings[position], distance))
    return tuple(
        (sibling, distance)
        for sibling, distance in selected
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


def _table_references(query: str) -> tuple[str, ...]:
    references = []
    for match in _TABLE_REFERENCE.finditer(query):
        identifier = match.group(1).rstrip(".,;:")
        reference = f"table {identifier}".casefold()
        if reference not in references:
            references.append(reference)
    return tuple(references)


def _matches_table_reference(node: IRNode, references: Sequence[str]) -> bool:
    normalized = " ".join(node.text.casefold().split())
    return any(reference in normalized for reference in references)


def _table_neighbors(
    node: IRNode,
    document: IRDocument,
    config: CompilerConfig,
) -> tuple[tuple[IRNode, int], ...]:
    if node.table is None or config.table_neighbor_limit == 0:
        return ()
    tables = [candidate for candidate in document.nodes if candidate.table is not None]
    index = tables.index(node)
    width = _table_width(node)
    selected: list[tuple[IRNode, int]] = []
    for direction in (-1, 1):
        previous = node
        for distance in range(1, config.table_neighbor_limit + 1):
            position = index + direction * distance
            if not 0 <= position < len(tables):
                break
            neighbor = tables[position]
            if (
                neighbor.heading_path != node.heading_path
                or _table_width(neighbor) != width
                or not _pages_are_contiguous(previous, neighbor)
            ):
                break
            selected.append((neighbor, distance))
            previous = neighbor
    return tuple(selected)


def _table_width(node: IRNode) -> int:
    if node.table is None:
        return 0
    if node.table.column_headers:
        return len(node.table.column_headers)
    return len(node.table.rows[0]) if node.table.rows else 0


def _pages_are_contiguous(first: IRNode, second: IRNode) -> bool:
    if (
        first.page_start is None
        or first.page_end is None
        or second.page_start is None
        or second.page_end is None
    ):
        return False
    return _page_range_distance(
        first.page_start,
        first.page_end,
        second.page_start,
        second.page_end,
    ) <= 1


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
            "reranked": _penalized_reranker_score(scores.reranked, penalty),
        }
    )


def _penalized_reranker_score(score: float, penalty: float) -> float:
    """Lower a signed reranker score without reversing negative logits."""
    if score > 0:
        return score * penalty
    if score < 0:
        return score / penalty
    return penalty - 1


def _expanded_id(base_id: str, relation: str, value: str) -> str:
    payload = f"compiler-expanded-v1\0{base_id}\0{relation}\0{value}".encode()
    return f"chunk_{hashlib.sha256(payload).hexdigest()}"
