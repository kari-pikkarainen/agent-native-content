"""Acceptance tests for reusable agent-document enrichment and bundles."""

import hashlib
import json
from pathlib import Path

import pytest
from test_ir import FixtureTokenCounter, ingest_metadata, source_document

from contextbench.agentdoc import (
    AgentBundleError,
    AgentFeatureKind,
    create_agent_bundle,
    enrich_document,
    features_for_nodes,
)
from contextbench.ir import project_document


def _document(tmp_path: Path):
    return project_document(
        source_document(),
        ingest_metadata(tmp_path),
        tokenizer=FixtureTokenCounter(),
    )


def test_enrichment_is_deterministic_source_grounded_and_query_independent(
    tmp_path: Path,
) -> None:
    document = _document(tmp_path)

    first = enrich_document(document)
    second = enrich_document(document)

    assert first == second
    assert first.features
    assert {feature.kind for feature in first.features} >= {
        AgentFeatureKind.OUTLINE,
        AgentFeatureKind.SECTION_SUMMARY,
        AgentFeatureKind.KEY_FACT,
        AgentFeatureKind.TABLE_SCHEMA,
    }
    node_ids = set(document.node_by_id)
    assert all(set(feature.source_node_ids) <= node_ids for feature in first.features)
    assert all(feature.source_item_ids for feature in first.features)
    assert any(
        feature.text == "Revenue increased strongly."
        and feature.attributes.get("normative") is True
        for feature in first.features
    )
    table = next(
        feature
        for feature in first.features
        if feature.kind == AgentFeatureKind.TABLE_SCHEMA
    )
    assert table.attributes == {
        "caption": "Revenue by region",
        "columns": ["Region", "Revenue"],
        "row_count": 2,
    }


def test_features_can_be_restricted_to_authorized_gold_nodes(tmp_path: Path) -> None:
    document = _document(tmp_path)
    enrichment = enrich_document(document)
    page_one_nodes = {
        node.id
        for node in document.nodes
        if node.page_start == node.page_end == 1
    }

    selected = features_for_nodes(enrichment, page_one_nodes)

    assert selected
    assert all(set(feature.source_node_ids) <= page_one_nodes for feature in selected)
    assert all(feature.page_start == feature.page_end == 1 for feature in selected)


def test_bundle_writes_verified_jsonld_html_and_optional_source(tmp_path: Path) -> None:
    source_path = tmp_path / "report.pdf"
    source_path.write_bytes(b"fixture-pdf")
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    metadata = ingest_metadata(tmp_path).model_copy(
        update={
            "source_path": str(source_path),
            "source_name": source_path.name,
            "source_sha256": source_sha256,
            "source_size_bytes": source_path.stat().st_size,
        }
    )
    document = project_document(
        source_document(),
        metadata,
        tokenizer=FixtureTokenCounter(),
    )
    output_dir = tmp_path / "agent-document"

    manifest = create_agent_bundle(
        document,
        output_dir,
        source_path=source_path,
        include_source=True,
    )

    assert {path.name for path in output_dir.iterdir()} == {
        "agent.html",
        "content.json",
        "enrichments.jsonld",
        "manifest.json",
        "source.pdf",
    }
    assert (output_dir / "source.pdf").read_bytes() == b"fixture-pdf"
    assert hashlib.sha256((output_dir / "content.json").read_bytes()).hexdigest() == (
        manifest.ir_sha256
    )
    assert hashlib.sha256(
        (output_dir / "enrichments.jsonld").read_bytes()
    ).hexdigest() == manifest.enrichments_sha256
    jsonld = json.loads((output_dir / "enrichments.jsonld").read_text())
    assert jsonld["@type"] == "cb:AgentDocument"
    assert jsonld["features"]
    rendered = (output_dir / "agent.html").read_text()
    assert '<script type="application/ld+json">' in rendered
    assert "<article>" in rendered
    assert "<table " in rendered
    assert "Revenue increased strongly." in rendered

    with pytest.raises(AgentBundleError, match="already exists"):
        create_agent_bundle(document, output_dir)


def test_bundle_refuses_source_bytes_that_do_not_match_ir(tmp_path: Path) -> None:
    source_path = tmp_path / "wrong.pdf"
    source_path.write_bytes(b"wrong")

    with pytest.raises(AgentBundleError, match="hash does not match"):
        create_agent_bundle(
            _document(tmp_path),
            tmp_path / "agent-document",
            source_path=source_path,
            include_source=True,
        )
