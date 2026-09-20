"""Deterministic query-time selection over reusable agent-document features."""

import json
import re
from collections.abc import Mapping, Set
from dataclasses import dataclass

from contextbench.agentdoc.models import (
    AgentDocument,
    AgentFeature,
    AgentFeatureKind,
)
from contextbench.ir.tokenizer import TokenCounter

_TERM = re.compile(r"[\w][\w.-]*", flags=re.UNICODE)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "what",
    "which",
    "with",
}


@dataclass(frozen=True)
class SelectedAgentFeature:
    """A selected feature plus deterministic lexical-selection evidence."""

    feature: AgentFeature
    matched_terms: tuple[str, ...]
    score: float
    token_count: int


def select_agent_features(
    query: str,
    enrichments: Mapping[str, AgentDocument],
    nodes_by_document: Mapping[str, set[str]],
    *,
    tokenizer: TokenCounter,
    kinds: Set[AgentFeatureKind],
    max_features: int,
    token_budget: int,
) -> tuple[SelectedAgentFeature, ...]:
    """Select a compact, source-authorized feature index for one query."""
    query_terms = _terms(query)
    candidates: list[tuple[AgentFeature, frozenset[str], int]] = []
    for document_id in sorted(nodes_by_document):
        enrichment = enrichments[document_id]
        allowed_nodes = nodes_by_document[document_id]
        for feature in enrichment.features:
            if feature.kind not in kinds:
                continue
            if not set(feature.source_node_ids).issubset(allowed_nodes):
                continue
            matched = frozenset(query_terms.intersection(_feature_terms(feature)))
            rendered_tokens = tokenizer.count(compact_feature_text(feature))
            if rendered_tokens <= token_budget:
                candidates.append((feature, matched, rendered_tokens))

    selected: list[SelectedAgentFeature] = []
    remaining = token_budget
    covered: set[str] = set()
    while candidates and len(selected) < max_features:
        ranked = sorted(
            candidates,
            key=lambda value: _selection_key(
                value[0],
                value[1],
                covered=covered,
                token_count=value[2],
            ),
        )
        feature, matched, token_count = ranked[0]
        candidates.remove(ranked[0])
        if token_count > remaining:
            continue
        marginal = matched.difference(covered)
        if not matched and selected:
            continue
        score = (
            10.0 * len(marginal)
            + 2.0 * len(matched)
            + feature.importance * feature.confidence
        )
        selected.append(
            SelectedAgentFeature(
                feature=feature,
                matched_terms=tuple(sorted(matched)),
                score=score,
                token_count=token_count,
            )
        )
        remaining -= token_count
        covered.update(matched)

    return tuple(selected)


def compact_feature_text(feature: AgentFeature) -> str:
    """Render one feature without repeating canonical provenance or schemas."""
    return " ".join(feature.text.split())


def feature_type_counts(
    enrichments: Mapping[str, AgentDocument],
    nodes_by_document: Mapping[str, set[str]],
    *,
    kinds: Set[AgentFeatureKind],
) -> dict[str, int]:
    """Count available source-authorized feature types for a compact manifest."""
    counts: dict[str, int] = {}
    for document_id in sorted(nodes_by_document):
        allowed_nodes = nodes_by_document[document_id]
        for feature in enrichments[document_id].features:
            if (
                feature.kind in kinds
                and set(feature.source_node_ids).issubset(allowed_nodes)
            ):
                counts[feature.kind.value] = counts.get(feature.kind.value, 0) + 1
    return dict(sorted(counts.items()))


def _selection_key(
    feature: AgentFeature,
    matched: frozenset[str],
    *,
    covered: set[str],
    token_count: int,
) -> tuple[object, ...]:
    marginal = matched.difference(covered)
    return (
        -len(marginal),
        -len(matched),
        -(feature.importance * feature.confidence),
        token_count,
        feature.page_start or 0,
        feature.id,
    )


def _feature_terms(feature: AgentFeature) -> set[str]:
    searchable = " ".join(
        (
            feature.text,
            " ".join(feature.heading_path),
            json.dumps(feature.attributes, ensure_ascii=False, sort_keys=True),
        )
    )
    return _terms(searchable)


def _terms(value: str) -> set[str]:
    return {
        match.group(0).casefold()
        for match in _TERM.finditer(value)
        if match.group(0).casefold() not in _STOPWORDS
    }
