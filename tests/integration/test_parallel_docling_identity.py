"""Real Docling: a parallel parse caches the same bytes as a sequential one.

Opt-in (``CONTEXTBENCH_DOCLING_PARALLEL=1``): it runs the full Docling
pipeline -- OCR and table structure on -- over small fixture PDFs, which
needs the models already in the local Hugging Face cache and a minute of
CPU. Unit tests cover the pool with a stand-in parser; this closes the gap
that stand-in cannot, that Docling itself is deterministic across processes.
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "unit"))
from parallel_fixtures import FixtureSource, FixtureSourceCache  # noqa: E402

from contextbench.ingest import DoclingParser, IngestionCache  # noqa: E402
from contextbench.ingest.parallel import warm_ingestion_cache  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.environ.get("CONTEXTBENCH_DOCLING_PARALLEL") != "1",
    reason="set CONTEXTBENCH_DOCLING_PARALLEL=1 to run real Docling parses",
)


def _fixture_pdfs(directory: Path) -> dict[str, Path]:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

    directory.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    paths = {}
    for index in range(3):
        path = directory / f"fixture_{index}.pdf"
        document = SimpleDocTemplate(str(path), pagesize=letter, invariant=1)
        rows = [["Region", "Revenue", "Growth"]] + [
            [f"R{index}{row}", str(100 * row + index), f"{row + index}%"]
            for row in range(1, 5)
        ]
        table = Table(rows)
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
        document.build(
            [
                Paragraph(f"Fixture report {index}", styles["Title"]),
                Paragraph("Results", styles["Heading1"]),
                Paragraph(
                    f"Revenue in fixture {index} increased across all regions.",
                    styles["BodyText"],
                ),
                table,
            ]
        )
        paths[f"fixture_{index}"] = path
    return paths


def _entries(root: Path) -> dict[str, tuple[bytes, dict]]:
    result = {}
    for metadata_path in sorted(root.glob("*/*/*/metadata.json")):
        metadata = json.loads(metadata_path.read_bytes())
        metadata.pop("created_at")
        result[str(metadata_path.parent.relative_to(root))] = (
            (metadata_path.parent / "document.json").read_bytes(),
            metadata,
        )
    return result


def test_docling_artifacts_are_identical_across_worker_counts(tmp_path: Path) -> None:
    paths = _fixture_pdfs(tmp_path / "pdfs")
    sources = [FixtureSource(id=key, url=f"file://{key}") for key in paths]

    sequential = tmp_path / "workers-1"
    cache = IngestionCache(sequential, DoclingParser())
    for key in paths:
        cache.ingest(paths[key])

    parallel = tmp_path / "workers-2"
    warm_ingestion_cache(
        sources,
        source_cache=FixtureSourceCache(paths),
        ingestion_cache=IngestionCache(parallel, DoclingParser()),
        workers=2,
    )

    expected = _entries(sequential)
    actual = _entries(parallel)
    assert len(expected) == 3
    assert actual.keys() == expected.keys()
    for key in expected:
        assert actual[key][0] == expected[key][0], key
        assert actual[key][1] == expected[key][1], key
        # A real parse with the recorded pipeline: OCR and table structure on,
        # and the fixture's table recovered.
        metadata = expected[key][1]
        assert metadata["parser_config"]["do_ocr"] is True
        assert metadata["parser_config"]["do_table_structure"] is True
        assert metadata["table_count"] == 1
        assert metadata["page_count"] == 1
