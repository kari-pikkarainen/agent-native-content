"""Deterministic query-time joins across explicitly referenced tables."""

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

from contextbench.compiler.models import PRIMARY_EVIDENCE_TIER, CompilerCandidate
from contextbench.ir.models import IRDocument, IRNode, IRNodeKind
from contextbench.ir.tokenizer import TokenCounter
from contextbench.retrieval.models import (
    RetrievalArm,
    RetrievalChunk,
    RetrievalScores,
)
from contextbench.retrieval.rerank import Reranker

_TABLE_REFERENCE = re.compile(
    r"\bTable\s+[A-Z0-9]+(?:[.\-][A-Z0-9]+)+",
    flags=re.IGNORECASE,
)
_IDENTIFIER = re.compile(r"[A-Z0-9][A-Z0-9_.-]{3,}", flags=re.IGNORECASE)
_DATE = re.compile(r"(?:19|20)\d{2}[-/]\d{2}[-/]\d{2}")
_TERM = re.compile(r"[\w]+", flags=re.UNICODE)
_HEADER_STOPWORDS = {"and", "the", "for", "with", "from"}


@dataclass(frozen=True)
class _TableRow:
    reference: str
    node: IRNode
    row_index: int
    headers: tuple[str, ...]
    values: tuple[str, ...]
    key_columns: tuple[int, ...]
    keys: tuple[str, ...]


@dataclass(frozen=True)
class KeyedTableIndex:
    """Query-independent exact-key rows grouped by document and table label."""

    rows_by_document: Mapping[str, Mapping[str, tuple[_TableRow, ...]]]

    @classmethod
    def build(cls, documents: Sequence[IRDocument]) -> "KeyedTableIndex":
        return cls(
            {
                document.id: _rows_by_reference(document, references=None)
                for document in documents
            }
        )

    def rows(self, document_id: str, reference: str) -> tuple[_TableRow, ...]:
        return self.rows_by_document.get(document_id, {}).get(
            _reference_key(reference), ()
        )


def keyed_table_join_candidates(
    query: str,
    documents: Sequence[IRDocument],
    *,
    tokenizer: TokenCounter,
    reranker: Reranker,
    candidate_limit: int,
    empty_marker: str,
    table_index: KeyedTableIndex | None = None,
) -> tuple[CompilerCandidate, ...]:
    """Join rows from named tables on exact normalized identifier cells."""
    references = _query_table_references(query)
    if len(references) < 2:
        return ()

    chunks: list[tuple[RetrievalChunk, float, tuple[str, str, str, str]]] = []
    seen_pairs: set[tuple[str, int, str, int]] = set()
    for document in documents:
        for left_reference, right_reference in combinations(references, 2):
            if table_index is None:
                rows_by_reference = _rows_by_reference(document, references)
                left_rows = rows_by_reference.get(_reference_key(left_reference), ())
                right_rows = rows_by_reference.get(_reference_key(right_reference), ())
            else:
                left_rows = table_index.rows(document.id, left_reference)
                right_rows = table_index.rows(document.id, right_reference)
            right_by_key: dict[str, list[_TableRow]] = {}
            for row in right_rows:
                for key in row.keys:
                    right_by_key.setdefault(key, []).append(row)
            for left in left_rows:
                matches = {
                    (right.node.id, right.row_index): right
                    for key in left.keys
                    for right in right_by_key.get(key, ())
                }
                for right in matches.values():
                    if not _join_satisfies_query(query, left, right):
                        continue
                    pair_key = (
                        left.node.id,
                        left.row_index,
                        right.node.id,
                        right.row_index,
                    )
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    shared_keys = sorted(set(left.keys).intersection(right.keys))
                    text = _render_join(
                        query,
                        left,
                        right,
                        shared_key=shared_keys[0],
                        empty_marker=empty_marker,
                    )
                    chunk = _join_chunk(
                        document,
                        left,
                        right,
                        text=text,
                        tokenizer=tokenizer,
                    )
                    group_key = (
                        document.id,
                        _reference_key(left.reference),
                        _reference_key(right.reference),
                        shared_keys[0],
                    )
                    chunks.append((chunk, _lexical_score(query, text), group_key))

    if not chunks:
        return ()
    prelimit = candidate_limit * 8
    chunks.sort(key=lambda item: (-item[1], item[0].id))
    bounded = chunks[:prelimit]
    reranker_scores = reranker.score(
        query,
        [chunk for chunk, _score, _group_key in bounded],
    )
    scored = sorted(
        zip(bounded, reranker_scores, strict=True),
        key=lambda item: (-item[1], -item[0][1], item[0][0].id),
    )
    selected = []
    seen_groups = set()
    for item in scored:
        group_key = item[0][2]
        if group_key in seen_groups:
            continue
        seen_groups.add(group_key)
        selected.append(item)
        if len(selected) == candidate_limit:
            break
    return tuple(
        CompilerCandidate(
            chunk=chunk,
            scores=RetrievalScores(fused=lexical_score, reranked=reranker_score),
            origin_rank=rank,
            expansion_order=rank - 1,
            # A join is primary evidence: it answers the question the same way
            # a retrieved node does, so it shares the retrieval tier and wins
            # or loses on score and coverage rather than on class.
            priority_tier=PRIMARY_EVIDENCE_TIER,
            allow_shared_source=True,
            operator="keyed_join",
        )
        for rank, (
            (chunk, lexical_score, _group_key),
            reranker_score,
        ) in enumerate(selected, 1)
    )


def keyed_table_join_cache_key(
    query: str,
    documents: Sequence[IRDocument],
    *,
    candidate_limit: int,
    empty_marker: str,
) -> str:
    """Hash all inputs that determine query-scoped keyed joins."""
    payload = "\0".join(
        (
            "compiler-keyed-table-join-v1",
            query,
            str(candidate_limit),
            empty_marker,
            *(f"{document.id}:{document.source_sha256}" for document in documents),
        )
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _query_table_references(query: str) -> tuple[str, ...]:
    references = []
    seen = set()
    for match in _TABLE_REFERENCE.finditer(query):
        reference = " ".join(match.group().split())
        key = _reference_key(reference)
        if key not in seen:
            seen.add(key)
            references.append(reference)
    return tuple(references)


def _rows_by_reference(
    document: IRDocument,
    references: Sequence[str] | None,
) -> dict[str, tuple[_TableRow, ...]]:
    requested = (
        {_reference_key(reference) for reference in references}
        if references is not None
        else None
    )
    labels = _table_labels(document.nodes)
    rows: dict[str, list[_TableRow]] = {}
    for node in document.nodes:
        if node.kind != IRNodeKind.TABLE or node.table is None:
            continue
        node_labels = labels.get(node.id, ())
        selected_labels = [
            label
            for label in node_labels
            if requested is None or _reference_key(label) in requested
        ]
        if not selected_labels:
            continue
        key_columns = _key_columns(node.table.column_headers)
        if not key_columns:
            continue
        table_rows = node.table.rows
        if node.table.column_headers and table_rows[:1] == (
            node.table.column_headers,
        ):
            table_rows = table_rows[1:]
        for row_index, values in enumerate(table_rows):
            keys = _row_keys(values, key_columns, node.table.column_headers)
            if not keys:
                continue
            for label in selected_labels:
                key = _reference_key(label)
                rows.setdefault(key, []).append(
                    _TableRow(
                        reference=label,
                        node=node,
                        row_index=row_index,
                        headers=node.table.column_headers,
                        values=values,
                        key_columns=key_columns,
                        keys=keys,
                    )
                )
    return {key: tuple(value) for key, value in rows.items()}


def _table_labels(nodes: Sequence[IRNode]) -> dict[str, tuple[str, ...]]:
    """Associate explicit table labels with same-schema continuation nodes."""
    pending: tuple[str, ...] = ()
    by_headers: dict[tuple[str, ...], tuple[str, ...]] = {}
    labels_by_node: dict[str, tuple[str, ...]] = {}
    for node in nodes:
        stripped = node.text.lstrip()
        if (
            node.kind == IRNodeKind.CAPTION
            or stripped.casefold().startswith("table ")
            or stripped.casefold().startswith("[start table ")
        ):
            pending = tuple(dict.fromkeys(_TABLE_REFERENCE.findall(node.text)))
        if node.kind != IRNodeKind.TABLE or node.table is None:
            continue
        signature = tuple(
            " ".join(header.casefold().split())
            for header in node.table.column_headers
        )
        own = tuple(
            dict.fromkeys(_TABLE_REFERENCE.findall(node.table.caption or ""))
        )
        labels = own or pending or by_headers.get(signature, ())
        if labels:
            labels_by_node[node.id] = labels
            if signature:
                by_headers[signature] = labels
        pending = ()
    return labels_by_node


def _key_columns(headers: tuple[str, ...]) -> tuple[int, ...]:
    return tuple(
        index
        for index, header in enumerate(headers)
        if _key_kind(header) is not None
    )


def _row_keys(
    values: tuple[str, ...],
    columns: tuple[int, ...],
    headers: tuple[str, ...],
) -> tuple[str, ...]:
    keys = []
    for index in columns:
        if index >= len(values):
            continue
        kind = _key_kind(headers[index]) if index < len(headers) else None
        value = " ".join(values[index].split())
        if kind == "date":
            keys.extend(
                f"date:{match.replace('/', '-')}" for match in _DATE.findall(value)
            )
        elif kind == "dataset":
            if 4 <= len(value) <= 120:
                keys.append(f"dataset:{value.casefold()}")
        else:
            for match in _IDENTIFIER.findall(value):
                normalized = match.casefold().strip("._-")
                if (
                    len(normalized) >= 4
                    and any(character.isalpha() for character in normalized)
                    and any(character.isdigit() for character in normalized)
                ):
                    keys.append(f"identifier:{normalized}")
    return tuple(dict.fromkeys(keys))


def _key_kind(header: str) -> str | None:
    compact = _compact(header)
    if "date" in compact:
        return "date"
    if compact in {"dataset", "datasetname"}:
        return "dataset"
    if (
        "model" in compact
        or "datasetid" in compact
        or "productcode" in compact
        or "partnumber" in compact
        or "accession" in compact
        or compact in {"sku", "isin", "cusip", "securityid"}
    ):
        return "identifier"
    return None


def _render_join(
    query: str,
    left: _TableRow,
    right: _TableRow,
    *,
    shared_key: str,
    empty_marker: str,
) -> str:
    display_key = shared_key.split(":", 1)[-1]
    lines = [f"Joined table key: {display_key}"]
    for row in (left, right):
        lines.append(row.reference)
        selected = _selected_columns(query, row)
        values = []
        for index in selected:
            value = row.values[index].strip() or empty_marker
            header = row.headers[index].strip()
            values.append(f"{header}: {value}" if header else value)
        lines.append(" | ".join(values))
    return "\n".join(lines)


def _selected_columns(query: str, row: _TableRow) -> tuple[int, ...]:
    query_compact = _compact(query)
    query_terms = set(_terms(query))
    selected = set(row.key_columns)
    for index, header in enumerate(row.headers):
        header_compact = _compact(header)
        header_terms = {
            term for term in _terms(header) if term not in _HEADER_STOPWORDS
        }
        if (
            (len(header_terms) > 1 and header_compact in query_compact)
            or header_terms.intersection(query_terms)
        ):
            selected.add(index)
    return tuple(sorted(selected))


def _join_satisfies_query(
    query: str,
    left: _TableRow,
    right: _TableRow,
) -> bool:
    query_terms = set(_terms(query))
    if "blank" not in query_terms and "empty" not in query_terms:
        return True
    constrained: list[tuple[_TableRow, int]] = []
    for row in (left, right):
        for index, header in enumerate(row.headers):
            header_terms = {
                term for term in _terms(header) if term not in _HEADER_STOPWORDS
            }
            if _compact(header) in query_terms or (
                header_terms and header_terms.issubset(query_terms)
            ):
                constrained.append((row, index))
    if constrained:
        return any(not row.values[index].strip() for row, index in constrained)
    return any(
        index not in row.key_columns and not row.values[index].strip()
        for row in (left, right)
        for index in _selected_columns(query, row)
    )


def _join_chunk(
    document: IRDocument,
    left: _TableRow,
    right: _TableRow,
    *,
    text: str,
    tokenizer: TokenCounter,
) -> RetrievalChunk:
    source_node_ids = tuple(dict.fromkeys((left.node.id, right.node.id)))
    source_item_ids = tuple(
        dict.fromkeys((*left.node.source_item_ids, *right.node.source_item_ids))
    )
    same_page = (
        left.node.page_start is not None
        and left.node.page_start == left.node.page_end
        and left.node.page_start == right.node.page_start == right.node.page_end
    )
    payload = (
        f"compiler-keyed-table-join-v1\0{document.id}\0{left.node.id}\0"
        f"{left.row_index}\0{right.node.id}\0{right.row_index}\0{text}"
    ).encode()
    return RetrievalChunk(
        id=f"chunk_{hashlib.sha256(payload).hexdigest()}",
        arm=RetrievalArm.COMPILER,
        document_id=document.id,
        text=text,
        token_count=tokenizer.count(text),
        heading_path=_common_heading_path(
            left.node.heading_path,
            right.node.heading_path,
        ),
        page_start=left.node.page_start if same_page else None,
        page_end=left.node.page_end if same_page else None,
        source_node_ids=source_node_ids,
        source_item_ids=source_item_ids,
    )


def _common_heading_path(
    left: tuple[str, ...],
    right: tuple[str, ...],
) -> tuple[str, ...]:
    shared = []
    for left_heading, right_heading in zip(left, right, strict=False):
        if left_heading != right_heading:
            break
        shared.append(left_heading)
    return tuple(shared)


def _lexical_score(query: str, text: str) -> float:
    query_terms = set(_terms(query))
    return len(query_terms.intersection(_terms(text))) / max(len(query_terms), 1)


def _terms(text: str) -> tuple[str, ...]:
    return tuple(_TERM.findall(text.casefold()))


def _compact(text: str) -> str:
    return "".join(_terms(text))


def _reference_key(reference: str) -> str:
    return " ".join(reference.casefold().split())
