"""Deterministic, extractive construction of agent-usable document features."""

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence

from contextbench.agentdoc.models import (
    AgentDocument,
    AgentEnrichmentConfig,
    AgentFeature,
    AgentFeatureKind,
)
from contextbench.ir.models import IRDocument, IRNode, IRNodeKind

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_DEFINITION = re.compile(r"\b(?:is|are|means|refers to|defined as)\b", re.IGNORECASE)
_NUMERIC = re.compile(r"(?:\d|[%$£€¥])")
_DATE = re.compile(
    r"\b(?:19|20)\d{2}\b|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\b",
    re.IGNORECASE,
)
_EXCEPTION = re.compile(
    r"\b(?:except|unless|however|but not|excluding|subject to)\b", re.IGNORECASE
)
_EXPLICIT_ALIAS = re.compile(
    r"(?P<name>[A-Z][A-Za-z0-9&'’-]*"
    r"(?:\s+(?:[A-Z][A-Za-z0-9&'’-]*|and|of|the|for|&)){1,8})\s+"
    r"\((?P<alias>[A-Z][A-Z0-9.-]{1,})\)"
)
_NORMATIVE = re.compile(
    r"\b(?:must|shall|required|prohibited|only|except|maximum|minimum|"
    r"increase(?:d|s)?|decrease(?:d|s)?|deadline|effective)\b",
    re.IGNORECASE,
)
_SUMMARY_KINDS = {
    IRNodeKind.PARAGRAPH,
    IRNodeKind.LIST_ITEM,
    IRNodeKind.CODE,
    IRNodeKind.OTHER,
}


def enrich_document(
    document: IRDocument,
    *,
    config: AgentEnrichmentConfig | None = None,
) -> AgentDocument:
    """Create reusable salience and navigation features without a query or LLM."""
    resolved = config or AgentEnrichmentConfig()
    nodes = [
        node
        for node in sorted(document.nodes, key=lambda value: value.ordinal)
        if node.content_layer == "body" and node.text.strip()
    ]
    features: list[AgentFeature] = []
    for node in nodes:
        if node.kind in {IRNodeKind.TITLE, IRNodeKind.HEADING}:
            features.append(
                _feature(
                    AgentFeatureKind.OUTLINE,
                    node.text.strip(),
                    document=document,
                    nodes=(node,),
                    importance=0.45,
                    confidence=1.0,
                    attributes={"depth": len(node.heading_path)},
                )
            )

    sections: dict[tuple[str, ...], list[IRNode]] = defaultdict(list)
    for node in nodes:
        if node.kind in _SUMMARY_KINDS:
            sections[node.heading_path].append(node)
    for heading_path, section_nodes in sections.items():
        summary_nodes, text = _section_summary(
            section_nodes,
            sentence_limit=resolved.summary_sentences,
        )
        if text:
            features.append(
                _feature(
                    AgentFeatureKind.SECTION_SUMMARY,
                    text,
                    document=document,
                    nodes=summary_nodes,
                    importance=0.65,
                    confidence=1.0,
                    heading_path=heading_path,
                    attributes={"extractive": True},
                )
            )

    seen_facts: set[str] = set()
    fact_count = 0
    for node in nodes:
        if node.kind not in _SUMMARY_KINDS:
            continue
        for sentence in _sentences(node.text):
            normalized = " ".join(sentence.casefold().split())
            if not normalized or normalized in seen_facts:
                continue
            definition = resolved.include_definitions and bool(
                _DEFINITION.search(sentence)
            )
            numeric = resolved.include_numeric_facts and bool(_NUMERIC.search(sentence))
            date = bool(_DATE.search(sentence))
            exception = bool(_EXCEPTION.search(sentence))
            normative = resolved.include_normative_facts and bool(
                _NORMATIVE.search(sentence)
            )
            if not (definition or numeric or normative):
                continue
            kind = (
                AgentFeatureKind.DEFINITION
                if definition
                else AgentFeatureKind.KEY_FACT
            )
            features.append(
                _feature(
                    kind,
                    sentence,
                    document=document,
                    nodes=(node,),
                    importance=0.9 if definition or normative else 0.78,
                    confidence=1.0,
                    attributes={
                        "extractive": True,
                        "contains_number": numeric,
                        "contains_date": date,
                        "exception": exception,
                        "normative": normative,
                    },
                )
            )
            seen_facts.add(normalized)
            fact_count += 1
            if fact_count >= resolved.max_key_facts:
                break
        if fact_count >= resolved.max_key_facts:
            break

    if resolved.include_explicit_aliases:
        seen_entities: set[tuple[str, str]] = set()
        for node in nodes:
            if node.kind not in _SUMMARY_KINDS:
                continue
            for match in _EXPLICIT_ALIAS.finditer(node.text):
                canonical = match.group("name").strip()
                alias = match.group("alias")
                identity = (canonical.casefold(), alias.casefold())
                if identity in seen_entities:
                    continue
                seen_entities.add(identity)
                features.append(
                    _feature(
                        AgentFeatureKind.ENTITY,
                        match.group(0),
                        document=document,
                        nodes=(node,),
                        importance=0.84,
                        confidence=0.98,
                        attributes={
                            "canonical_name": canonical,
                            "aliases": [alias],
                            "extraction": "explicit_parenthetical_alias",
                        },
                    )
                )
                if resolved.include_relationships:
                    features.append(
                        _feature(
                            AgentFeatureKind.RELATIONSHIP,
                            f"{alias} is an alias of {canonical}.",
                            document=document,
                            nodes=(node,),
                            importance=0.82,
                            confidence=0.98,
                            attributes={
                                "subject": alias,
                                "predicate": "alias_of",
                                "object": canonical,
                            },
                        )
                    )

    if resolved.include_table_schemas:
        table_row_count = 0
        for node in nodes:
            if node.kind != IRNodeKind.TABLE or node.table is None:
                continue
            headers = node.table.column_headers
            schema_text = _table_schema_text(
                node.table.caption,
                headers,
                len(node.table.rows),
            )
            features.append(
                _feature(
                    AgentFeatureKind.TABLE_SCHEMA,
                    schema_text,
                    document=document,
                    nodes=(node,),
                    importance=0.92,
                    confidence=1.0,
                    attributes={
                        "caption": node.table.caption,
                        "columns": list(headers),
                        "row_count": len(node.table.rows),
                    },
                )
            )
            if resolved.include_relationships:
                features.append(
                    _feature(
                        AgentFeatureKind.RELATIONSHIP,
                        f"{node.table.caption or 'Table'} has columns: "
                        f"{', '.join(headers) or '[unlabeled]' }.",
                        document=document,
                        nodes=(node,),
                        importance=0.86,
                        confidence=1.0,
                        attributes={
                            "subject": node.table.caption or node.id,
                            "predicate": "has_columns",
                            "object": list(headers),
                        },
                    )
                )
            if not resolved.include_table_rows:
                continue
            data_rows = node.table.rows
            if headers and data_rows and tuple(data_rows[0]) == tuple(headers):
                data_rows = data_rows[1:]
            width = max((len(row) for row in data_rows), default=len(headers))
            labels = tuple(headers) or tuple(
                f"column_{index + 1}" for index in range(width)
            )
            for row_index, row in enumerate(data_rows, start=1):
                if table_row_count >= resolved.max_table_rows:
                    break
                values = {
                    (
                        labels[index]
                        if index < len(labels)
                        else f"column_{index + 1}"
                    ): value
                    for index, value in enumerate(row)
                }
                row_text = " | ".join(value or "[blank]" for value in row)
                features.append(
                    _feature(
                        AgentFeatureKind.TABLE_ROW,
                        f"Row {row_index}: {row_text}",
                        document=document,
                        nodes=(node,),
                        importance=0.88,
                        confidence=1.0,
                        attributes={
                            "caption": node.table.caption,
                            "row_index": row_index,
                            "values": values,
                        },
                    )
                )
                table_row_count += 1

    _validate_provenance(features, document)
    return AgentDocument(
        document_id=document.id,
        source_uri=document.source_uri,
        source_sha256=document.source_sha256,
        ir_schema_version=document.schema_version,
        config=resolved,
        features=tuple(features),
    )


def features_for_nodes(
    enrichment: AgentDocument,
    node_ids: set[str],
) -> tuple[AgentFeature, ...]:
    """Select features grounded wholly in an authorized source-node set."""
    return tuple(
        feature
        for feature in enrichment.features
        if set(feature.source_node_ids).issubset(node_ids)
    )


def _section_summary(
    nodes: Sequence[IRNode],
    *,
    sentence_limit: int,
) -> tuple[tuple[IRNode, ...], str]:
    selected_nodes: list[IRNode] = []
    selected_sentences: list[str] = []
    for node in nodes:
        for sentence in _sentences(node.text):
            selected_sentences.append(sentence)
            if node not in selected_nodes:
                selected_nodes.append(node)
            if len(selected_sentences) >= sentence_limit:
                return tuple(selected_nodes), " ".join(selected_sentences)
    return tuple(selected_nodes), " ".join(selected_sentences)


def _sentences(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for line in text.splitlines():
        values.extend(
            sentence.strip()
            for sentence in _SENTENCE_BOUNDARY.split(line.strip())
            if sentence.strip()
        )
    return tuple(values)


def _table_schema_text(
    caption: str | None,
    headers: Sequence[str],
    row_count: int,
) -> str:
    label = caption or "Uncaptioned table"
    columns = ", ".join(header or "[blank]" for header in headers)
    return f"{label}. Columns: {columns or '[unlabeled]'}. Rows: {row_count}."


def _feature(
    kind: AgentFeatureKind,
    text: str,
    *,
    document: IRDocument,
    nodes: Sequence[IRNode],
    importance: float,
    confidence: float,
    attributes: dict[str, object],
    heading_path: tuple[str, ...] | None = None,
) -> AgentFeature:
    node_ids = tuple(node.id for node in nodes)
    item_ids = tuple(
        dict.fromkeys(item for node in nodes for item in node.source_item_ids)
    )
    pages = [
        page
        for node in nodes
        for page in (node.page_start, node.page_end)
        if page is not None
    ]
    payload = json.dumps(
        {
            "document_id": document.id,
            "kind": kind.value,
            "node_ids": node_ids,
            "text": text,
            "attributes": attributes,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return AgentFeature(
        id=f"feature_{hashlib.sha256(payload).hexdigest()}",
        kind=kind,
        document_id=document.id,
        text=text,
        importance=importance,
        confidence=confidence,
        heading_path=(
            heading_path if heading_path is not None else nodes[0].heading_path
        ),
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        source_node_ids=node_ids,
        source_item_ids=item_ids,
        attributes=attributes,
    )


def _validate_provenance(
    features: Iterable[AgentFeature],
    document: IRDocument,
) -> None:
    nodes = document.node_by_id
    for feature in features:
        missing = set(feature.source_node_ids).difference(nodes)
        if missing:
            raise ValueError(
                f"agent feature has unknown source nodes: {sorted(missing)}"
            )
