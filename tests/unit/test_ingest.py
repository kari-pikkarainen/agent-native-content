"""Tests for content-addressed Docling ingestion."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.base import BoundingBox, Size
from docling_core.types.doc.document import ProvenanceItem, TableCell, TableData
from docling_core.types.doc.labels import DocItemLabel
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas
from typer.testing import CliRunner

import contextbench.ingest as ingest_package
from contextbench.cli import app
from contextbench.ingest.cache import (
    IngestionCache,
    IngestionCacheIntegrityError,
)
from contextbench.ingest.docling_adapter import DoclingParser


class StructuredFixtureParser:
    """Offline parser double returning a representative DoclingDocument."""

    name = "docling"

    def __init__(self, *, parser_version: str = "fixture-1") -> None:
        self.parser_version = parser_version
        self.calls = 0

    @property
    def version(self) -> str:
        return self.parser_version

    @property
    def core_version(self) -> str:
        return "fixture-core-1"

    @property
    def config(self) -> dict[str, Any]:
        return {"pipeline": "offline-fixture", "tables": True}

    def parse(self, source: Path) -> DoclingDocument:
        self.calls += 1
        assert source.read_bytes().startswith(b"%PDF-")
        return structured_document()


@pytest.fixture
def source_pdf(tmp_path: Path) -> Path:
    """Create a small, valid two-page PDF without any network dependency."""
    path = tmp_path / "structured.pdf"
    canvas = Canvas(str(path), pagesize=letter, pageCompression=0)
    canvas.setTitle("Benchmark Report")
    canvas.setFont("Helvetica-Bold", 18)
    canvas.drawString(72, 740, "Benchmark Report")
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawString(72, 700, "Results")
    canvas.setFont("Helvetica", 11)
    canvas.drawString(72, 670, "Revenue increased.")
    canvas.rect(72, 580, 300, 60)
    canvas.line(72, 610, 372, 610)
    canvas.line(220, 580, 220, 640)
    canvas.drawString(82, 620, "Metric")
    canvas.drawString(230, 620, "Value")
    canvas.drawString(82, 590, "Revenue")
    canvas.drawString(230, 590, "42")
    canvas.showPage()
    canvas.setFont("Helvetica", 11)
    canvas.drawString(72, 740, "Conclusion paragraph.")
    canvas.save()
    return path


def provenance(page_no: int, text: str, top: float) -> ProvenanceItem:
    return ProvenanceItem(
        page_no=page_no,
        bbox=BoundingBox(l=40, t=top, r=550, b=top - 20),
        charspan=(0, len(text)),
    )


def structured_document() -> DoclingDocument:
    document = DoclingDocument(name="structured")
    document.add_page(1, Size(width=612, height=792))
    document.add_page(2, Size(width=612, height=792))
    title = document.add_title(
        "Benchmark Report",
        prov=provenance(1, "Benchmark Report", 750),
    )
    heading = document.add_heading(
        "Results",
        level=1,
        parent=title,
        prov=provenance(1, "Results", 710),
    )
    paragraph = "Revenue increased."
    document.add_text(
        label=DocItemLabel.TEXT,
        text=paragraph,
        parent=heading,
        prov=provenance(1, paragraph, 680),
    )

    cells = []
    for row, values in enumerate((("Metric", "Value"), ("Revenue", "42"))):
        for column, text in enumerate(values):
            cells.append(
                TableCell(
                    start_row_offset_idx=row,
                    end_row_offset_idx=row + 1,
                    start_col_offset_idx=column,
                    end_col_offset_idx=column + 1,
                    text=text,
                    column_header=row == 0,
                )
            )
    table_text = "Metric Value Revenue 42"
    document.add_table(
        data=TableData(table_cells=cells, num_rows=2, num_cols=2),
        parent=heading,
        prov=provenance(1, table_text, 620),
    )
    conclusion = "Conclusion paragraph."
    document.add_text(
        label=DocItemLabel.TEXT,
        text=conclusion,
        parent=title,
        prov=provenance(2, conclusion, 750),
    )
    return document


def test_ingestion_serializes_structure_and_provenance(
    tmp_path: Path, source_pdf: Path
) -> None:
    parser = StructuredFixtureParser()
    result = IngestionCache(tmp_path / "cache", parser).ingest(source_pdf)

    assert result.reused is False
    assert parser.calls == 1
    assert result.metadata.source_sha256 == hashlib.sha256(
        source_pdf.read_bytes()
    ).hexdigest()
    assert result.metadata.parser_name == "docling"
    assert result.metadata.parser_version == "fixture-1"
    assert result.metadata.page_count == 2
    assert result.metadata.heading_count == 2
    assert result.metadata.text_count == 4
    assert result.metadata.table_count == 1
    assert result.artifact_dir.name == result.metadata.parser_config_hash

    loaded = DoclingDocument.load_from_json(result.document_path)
    assert len(loaded.pages) == 2
    assert [item.text for item in loaded.texts] == [
        "Benchmark Report",
        "Results",
        "Revenue increased.",
        "Conclusion paragraph.",
    ]
    assert loaded.texts[2].parent == loaded.texts[1].get_ref()
    assert loaded.tables[0].parent == loaded.texts[1].get_ref()
    assert [item.prov[0].page_no for item in loaded.texts] == [1, 1, 1, 2]
    assert loaded.tables[0].prov[0].page_no == 1
    assert loaded.tables[0].data.num_rows == 2
    assert loaded.tables[0].data.num_cols == 2
    assert [cell.text for cell in loaded.tables[0].data.table_cells] == [
        "Metric",
        "Value",
        "Revenue",
        "42",
    ]


def test_repeated_ingestion_reuses_verified_cache(
    tmp_path: Path, source_pdf: Path
) -> None:
    parser = StructuredFixtureParser()
    cache = IngestionCache(tmp_path / "cache", parser)

    first = cache.ingest(source_pdf)
    first_bytes = first.document_path.read_bytes()
    second = cache.ingest(source_pdf)

    assert parser.calls == 1
    assert second.reused is True
    assert second.artifact_dir == first.artifact_dir
    assert second.document_path.read_bytes() == first_bytes
    assert second.metadata == first.metadata


def test_source_change_invalidates_cache(tmp_path: Path, source_pdf: Path) -> None:
    parser = StructuredFixtureParser()
    cache = IngestionCache(tmp_path / "cache", parser)
    first = cache.ingest(source_pdf)

    with source_pdf.open("ab") as file:
        file.write(b"\n% source revision\n")
    second = cache.ingest(source_pdf)

    assert parser.calls == 2
    assert second.reused is False
    assert second.metadata.source_sha256 != first.metadata.source_sha256
    assert second.artifact_dir != first.artifact_dir


def test_parser_version_invalidates_cache(tmp_path: Path, source_pdf: Path) -> None:
    first_parser = StructuredFixtureParser(parser_version="fixture-1")
    second_parser = StructuredFixtureParser(parser_version="fixture-2")
    root = tmp_path / "cache"

    first = IngestionCache(root, first_parser).ingest(source_pdf)
    second = IngestionCache(root, second_parser).ingest(source_pdf)

    assert first_parser.calls == 1
    assert second_parser.calls == 1
    assert second.artifact_dir != first.artifact_dir
    assert second.metadata.parser_version == "fixture-2"


def test_modified_serialized_document_is_rejected(
    tmp_path: Path, source_pdf: Path
) -> None:
    cache = IngestionCache(tmp_path / "cache", StructuredFixtureParser())
    first = cache.ingest(source_pdf)
    first.document_path.write_text("{}", encoding="utf-8")

    with pytest.raises(
        IngestionCacheIntegrityError, match="serialized DoclingDocument changed"
    ):
        cache.ingest(source_pdf)


def test_docling_parser_config_disables_remote_services() -> None:
    config = DoclingParser().config

    assert config["pipeline"] == "standard_pdf"
    assert config["enable_remote_services"] is False
    assert config["do_table_structure"] is True
    assert config["do_picture_description"] is False


def test_ingest_cli_reports_cache_reuse(
    tmp_path: Path,
    source_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = StructuredFixtureParser()
    monkeypatch.setattr(
        ingest_package,
        "DoclingParser",
        lambda artifacts_path=None: parser,
    )
    runner = CliRunner()
    arguments = [
        "ingest",
        str(source_pdf),
        "--cache-dir",
        str(tmp_path / "cache"),
    ]

    first = runner.invoke(app, arguments)
    second = runner.invoke(app, arguments)

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert json.loads(first.stdout)["reused"] is False
    assert json.loads(second.stdout)["reused"] is True
    assert parser.calls == 1
