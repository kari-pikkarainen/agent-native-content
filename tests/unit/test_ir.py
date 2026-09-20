"""Tests for the deterministic minimal intermediate representation."""

import json
from pathlib import Path

import pytest
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.base import BoundingBox, Size
from docling_core.types.doc.document import ProvenanceItem, TableCell, TableData
from docling_core.types.doc.labels import DocItemLabel
from pydantic import ValidationError

from contextbench.ingest.cache import IngestMetadata
from contextbench.ir import (
    IRDocument,
    IRNodeKind,
    load_ir_document,
    project_document,
    save_ir_document,
)


class FixtureTokenCounter:
    """Predictable, dependency-free counter for structural unit tests."""

    name = "fixture-words"
    version = "1"

    def count(self, text: str) -> int:
        return len(text.split())


def provenance(page_no: int, text: str, top: float) -> ProvenanceItem:
    return ProvenanceItem(
        page_no=page_no,
        bbox=BoundingBox(l=40, t=top, r=550, b=top - 20),
        charspan=(0, len(text)),
    )


def source_document() -> DoclingDocument:
    document = DoclingDocument(name="quarterly-report")
    document.add_page(1, Size(width=612, height=792))
    document.add_page(2, Size(width=612, height=792))
    title = document.add_title(
        "Quarterly Report",
        prov=provenance(1, "Quarterly Report", 750),
    )
    heading = document.add_heading(
        "Results",
        level=1,
        parent=title,
        prov=provenance(1, "Results", 710),
    )
    document.add_text(
        label=DocItemLabel.TEXT,
        text="Revenue increased strongly.",
        parent=heading,
        prov=provenance(1, "Revenue increased strongly.", 680),
    )
    list_group = document.add_list_group(name="Highlights", parent=heading)
    document.add_list_item(
        text="North America grew.",
        parent=list_group,
        prov=provenance(1, "North America grew.", 650),
    )
    caption = document.add_text(
        label=DocItemLabel.CAPTION,
        text="Revenue by region",
        parent=heading,
        prov=provenance(1, "Revenue by region", 620),
    )
    cells = [
        TableCell(
            start_row_offset_idx=row,
            end_row_offset_idx=row + 1,
            start_col_offset_idx=column,
            end_col_offset_idx=column + 1,
            text=text,
            column_header=row == 0,
        )
        for row, values in enumerate((('Region', 'Revenue'), ('North', '42')))
        for column, text in enumerate(values)
    ]
    document.add_table(
        data=TableData(table_cells=cells, num_rows=2, num_cols=2),
        caption=caption,
        parent=heading,
        prov=provenance(1, "Region Revenue North 42", 590),
    )
    methods = document.add_heading(
        "Methods",
        level=1,
        parent=title,
        prov=provenance(2, "Methods", 750),
    )
    document.add_code(
        "print('measured')",
        parent=methods,
        prov=provenance(2, "print('measured')", 710),
    )
    return document


def ingest_metadata(tmp_path: Path) -> IngestMetadata:
    return IngestMetadata(
        source_path=str((tmp_path / "report.pdf").resolve()),
        source_name="report.pdf",
        source_sha256="a" * 64,
        source_size_bytes=123,
        parser_name="docling",
        parser_version="fixture-parser-1",
        parser_core_version="fixture-core-1",
        parser_config={"pipeline": "fixture"},
        parser_config_hash="b" * 64,
        document_file="document.json",
        document_sha256="c" * 64,
        docling_schema_version="1.0.0",
        page_count=2,
        text_count=7,
        heading_count=3,
        table_count=1,
        created_at="2026-09-19T00:00:00+00:00",
    )


def build_ir(tmp_path: Path) -> IRDocument:
    return project_document(
        source_document(),
        ingest_metadata(tmp_path),
        tokenizer=FixtureTokenCounter(),
    )


def node_with_text(document: IRDocument, text: str):
    return next(node for node in document.nodes if node.text == text)


def test_projection_preserves_structure_provenance_and_table_data(
    tmp_path: Path,
) -> None:
    ir = build_ir(tmp_path)

    title = node_with_text(ir, "Quarterly Report")
    heading = node_with_text(ir, "Results")
    paragraph = node_with_text(ir, "Revenue increased strongly.")
    list_node = node_with_text(ir, "Highlights")
    list_item = node_with_text(ir, "North America grew.")
    caption = node_with_text(ir, "Revenue by region")
    table = next(node for node in ir.nodes if node.kind == IRNodeKind.TABLE)
    code = node_with_text(ir, "print('measured')")

    assert ir.id == f"doc_{'a' * 64}"
    assert ir.source_sha256 == "a" * 64
    assert ir.page_numbers == (1, 2)
    assert ir.tokenizer_name == "fixture-words"
    assert title.kind == IRNodeKind.TITLE
    assert heading.kind == IRNodeKind.HEADING
    assert paragraph.kind == IRNodeKind.PARAGRAPH
    assert list_node.kind == IRNodeKind.LIST
    assert list_item.kind == IRNodeKind.LIST_ITEM
    assert caption.kind == IRNodeKind.CAPTION
    assert code.kind == IRNodeKind.CODE
    assert paragraph.parent_id == heading.id
    assert paragraph.id in heading.children_ids
    assert list_item.parent_id == list_node.id
    assert paragraph.heading_path == ("Quarterly Report", "Results")
    assert code.heading_path == ("Quarterly Report", "Methods")
    assert paragraph.page_start == paragraph.page_end == 1
    assert paragraph.bounding_boxes[0].page_no == 1
    assert paragraph.source_item_ids == ("#/texts/2",)
    assert paragraph.token_count == 3
    assert table.table is not None
    assert table.table.caption == "Revenue by region"
    assert table.table.column_headers == ("Region", "Revenue")
    assert table.table.rows == (("Region", "Revenue"), ("North", "42"))
    assert table.text == "Revenue by region\nRegion | Revenue\nNorth | 42"


def test_projection_is_stable_across_repeated_builds(tmp_path: Path) -> None:
    first = build_ir(tmp_path)
    second = build_ir(tmp_path)

    assert first == second
    assert [node.id for node in first.nodes] == [node.id for node in second.nodes]
    assert [node.ordinal for node in first.nodes] == list(range(len(first.nodes)))


def test_heading_paths_follow_flat_docling_heading_levels(tmp_path: Path) -> None:
    document = DoclingDocument(name="flat")
    document.add_page(1, Size(width=612, height=792))
    document.add_heading("First", level=1)
    document.add_heading("Nested", level=2)
    nested_text = document.add_text(
        label=DocItemLabel.TEXT,
        text="Nested evidence.",
    )
    document.add_heading("Second", level=1)
    second_text = document.add_text(
        label=DocItemLabel.TEXT,
        text="Second evidence.",
    )

    ir = project_document(
        document,
        ingest_metadata(tmp_path),
        tokenizer=FixtureTokenCounter(),
    )

    nested_node = next(
        node for node in ir.nodes if nested_text.self_ref in node.source_item_ids
    )
    second_node = next(
        node for node in ir.nodes if second_text.self_ref in node.source_item_ids
    )
    assert nested_node.heading_path == ("First", "Nested")
    assert second_node.heading_path == ("Second",)


def test_empty_normalized_text_falls_back_to_source_text(tmp_path: Path) -> None:
    document = DoclingDocument(name="formula-fallback")
    document.add_page(1, Size(width=612, height=792))
    formula = document.add_text(
        label=DocItemLabel.FORMULA,
        text="",
        orig="Absolute Global Warming Potential equation",
        prov=provenance(1, "Absolute Global Warming Potential equation", 700),
    )

    ir = project_document(
        document,
        ingest_metadata(tmp_path),
        tokenizer=FixtureTokenCounter(),
    )

    node = next(node for node in ir.nodes if formula.self_ref in node.source_item_ids)
    assert node.text == "Absolute Global Warming Potential equation"
    assert node.page_start == node.page_end == 1
    assert node.token_count == 5


def test_table_spans_are_expanded_into_the_logical_grid(tmp_path: Path) -> None:
    document = DoclingDocument(name="merged-table")
    document.add_page(1, Size(width=612, height=792))
    document.add_table(
        data=TableData(
            num_rows=2,
            num_cols=2,
            table_cells=[
                TableCell(
                    start_row_offset_idx=0,
                    end_row_offset_idx=1,
                    start_col_offset_idx=0,
                    end_col_offset_idx=2,
                    text="Metrics",
                    column_header=True,
                ),
                TableCell(
                    start_row_offset_idx=1,
                    end_row_offset_idx=2,
                    start_col_offset_idx=0,
                    end_col_offset_idx=1,
                    text="Revenue",
                ),
                TableCell(
                    start_row_offset_idx=1,
                    end_row_offset_idx=2,
                    start_col_offset_idx=1,
                    end_col_offset_idx=2,
                    text="42",
                ),
            ],
        )
    )

    ir = project_document(
        document,
        ingest_metadata(tmp_path),
        tokenizer=FixtureTokenCounter(),
    )
    table = next(node.table for node in ir.nodes if node.kind == IRNodeKind.TABLE)

    assert table is not None
    assert table.column_headers == ("Metrics", "Metrics")
    assert table.rows == (("Metrics", "Metrics"), ("Revenue", "42"))


def test_json_round_trip_is_identical_and_canonical(tmp_path: Path) -> None:
    ir = build_ir(tmp_path)
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"

    save_ir_document(ir, first_path)
    restored = load_ir_document(first_path)
    save_ir_document(restored, second_path)

    assert restored == ir
    assert first_path.read_bytes() == second_path.read_bytes()
    serialized = json.loads(first_path.read_text(encoding="utf-8"))
    assert serialized["source_sha256"] == "a" * 64
    assert "embeddings" not in first_path.read_text(encoding="utf-8")
    assert "summaries" not in first_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["nodes"][0]["children_ids"].append("missing"),
            "unknown child",
        ),
        (
            lambda value: value["nodes"][2]["bounding_boxes"][0].update(
                {"page_no": 3}
            ),
            "unknown page",
        ),
        (
            lambda value: (
                value["nodes"][3].update(
                    {"page_start": 3, "page_end": 3, "bounding_boxes": []}
                )
            ),
            "unknown page",
        ),
    ],
)
def test_validation_rejects_inconsistent_graph_or_provenance(
    tmp_path: Path, mutation, message: str
) -> None:
    value = build_ir(tmp_path).model_dump(mode="json")
    mutation(value)

    with pytest.raises(ValidationError, match=message):
        IRDocument.model_validate(value)
