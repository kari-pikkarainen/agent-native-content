"""Acceptance tests for reusable agent-document enrichment and bundles."""

import hashlib
import json
from pathlib import Path

import pytest
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.base import Size
from docling_core.types.doc.document import TableCell, TableData
from docling_core.types.doc.labels import DocItemLabel
from test_ir import (
    FixtureTokenCounter,
    ingest_metadata,
    provenance,
    source_document,
)

from agent_native_content.agentdoc import (
    AgentBundleError,
    AgentFeatureKind,
    create_agent_bundle,
    enrich_document,
    features_for_nodes,
    select_agent_features,
)
from agent_native_content.ir import project_document


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
        AgentFeatureKind.RELATIONSHIP,
        AgentFeatureKind.TABLE_SCHEMA,
        AgentFeatureKind.TABLE_ROW,
    }
    node_ids = set(document.node_by_id)
    assert all(set(feature.source_node_ids) <= node_ids for feature in first.features)
    assert all(feature.source_item_ids for feature in first.features)
    assert all(0 <= feature.confidence <= 1 for feature in first.features)
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
    row = next(
        feature
        for feature in first.features
        if feature.kind == AgentFeatureKind.TABLE_ROW
    )
    assert row.attributes["values"] == {"Region": "North", "Revenue": "42"}


def test_explicit_aliases_create_entities_and_typed_relationships(
    tmp_path: Path,
) -> None:
    source = source_document()
    source.add_text(
        label=DocItemLabel.TEXT,
        text=(
            "National Aeronautics and Space Administration (NASA) "
            "published the requirement."
        ),
        prov=provenance(2, "National Aeronautics and Space Administration", 650),
    )
    document = project_document(
        source,
        ingest_metadata(tmp_path),
        tokenizer=FixtureTokenCounter(),
    )

    enrichment = enrich_document(document)

    entity = next(
        feature
        for feature in enrichment.features
        if feature.kind == AgentFeatureKind.ENTITY
    )
    relationship = next(
        feature
        for feature in enrichment.features
        if feature.kind == AgentFeatureKind.RELATIONSHIP
        and feature.attributes.get("predicate") == "alias_of"
    )
    assert entity.attributes["canonical_name"] == (
        "National Aeronautics and Space Administration"
    )
    assert entity.attributes["aliases"] == ["NASA"]
    assert relationship.attributes == {
        "subject": "NASA",
        "predicate": "alias_of",
        "object": "National Aeronautics and Space Administration",
    }


def test_quantities_definitions_dates_and_references_are_machine_usable(
    tmp_path: Path,
) -> None:
    source = source_document()
    source.add_text(
        label=DocItemLabel.TEXT,
        text=(
            "API means application programming interface. "
            "Operating margin was 42% in 2025 and remained 42%. See Table A.1."
        ),
        prov=provenance(2, "API means application programming interface", 620),
    )
    document = project_document(
        source,
        ingest_metadata(tmp_path),
        tokenizer=FixtureTokenCounter(),
    )

    enrichment = enrich_document(document)
    quantity = next(
        feature
        for feature in enrichment.features
        if feature.kind == AgentFeatureKind.QUANTITY
    )
    definition = next(
        feature
        for feature in enrichment.features
        if feature.kind == AgentFeatureKind.RELATIONSHIP
        and feature.attributes.get("predicate") == "defined_as"
    )
    reference = next(
        feature
        for feature in enrichment.features
        if feature.kind == AgentFeatureKind.RELATIONSHIP
        and feature.attributes.get("predicate") == "references"
    )
    dated_fact = next(
        feature
        for feature in enrichment.features
        if feature.kind == AgentFeatureKind.KEY_FACT
        and feature.attributes.get("dates") == ["2025"]
    )

    assert quantity.attributes == {"value": "42", "unit": "%", "scale": None}
    assert sum(
        feature.kind == AgentFeatureKind.QUANTITY
        and feature.attributes["value"] == "42"
        for feature in enrichment.features
    ) == 1
    assert definition.attributes == {
        "subject": "API",
        "predicate": "defined_as",
        "object": "application programming interface",
    }
    assert reference.attributes["object"] == "Table A.1"
    assert dated_fact.attributes["contains_date"] is True


def test_duplicate_table_rows_have_distinct_stable_feature_ids(
    tmp_path: Path,
) -> None:
    source = DoclingDocument(name="duplicate-rows")
    source.add_page(1, Size(width=612, height=792))
    rows = (("Metric", "Value"), ("Revenue", "42"), ("Revenue", "42"))
    cells = [
        TableCell(
            start_row_offset_idx=row,
            end_row_offset_idx=row + 1,
            start_col_offset_idx=column,
            end_col_offset_idx=column + 1,
            text=text,
            column_header=row == 0,
        )
        for row, values in enumerate(rows)
        for column, text in enumerate(values)
    ]
    source.add_table(
        data=TableData(table_cells=cells, num_rows=3, num_cols=2),
        prov=provenance(1, "Metric Value Revenue 42 Revenue 42", 700),
    )
    document = project_document(
        source,
        ingest_metadata(tmp_path),
        tokenizer=FixtureTokenCounter(),
    )

    enrichment = enrich_document(document)
    table_rows = [
        feature
        for feature in enrichment.features
        if feature.kind == AgentFeatureKind.TABLE_ROW
    ]

    assert [feature.attributes["row_index"] for feature in table_rows] == [1, 2]
    assert len({feature.id for feature in table_rows}) == 2
    assert enrichment == enrich_document(document)


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


def test_feature_selection_is_query_aware_bounded_and_source_authorized(
    tmp_path: Path,
) -> None:
    document = _document(tmp_path)
    enrichment = enrich_document(document)
    table_node = next(node for node in document.nodes if node.table is not None)

    selected = select_agent_features(
        "What was North revenue?",
        {document.id: enrichment},
        {document.id: {table_node.id}},
        tokenizer=FixtureTokenCounter(),
        kinds=set(AgentFeatureKind),
        max_features=2,
        token_budget=12,
    )

    assert selected
    assert len(selected) <= 2
    assert sum(item.token_count for item in selected) <= 12
    assert all(
        set(item.feature.source_node_ids) == {table_node.id} for item in selected
    )
    assert any("North" in item.feature.text for item in selected)


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
