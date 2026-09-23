"""Docling fixtures for retrieval-unit merging.

Kept free of any import introduced with merging, so the same builders can be
run against the pre-merging compiler to pin its packets.
"""

from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.base import Size
from docling_core.types.doc.labels import DocItemLabel
from test_ir import provenance


def run_source(count: int = 9) -> DoclingDocument:
    """One heading over ``count`` two-word paragraphs on page 1."""
    document = DoclingDocument(name="merge-run")
    document.add_page(1, Size(width=612, height=792))
    title = document.add_title("Ledger", prov=provenance(1, "Ledger", 770))
    heading = document.add_heading(
        "Alpha",
        level=1,
        parent=title,
        prov=provenance(1, "Alpha", 750),
    )
    for index in range(count):
        text = f"entry{index} value{index}"
        document.add_text(
            label=DocItemLabel.TEXT,
            text=text,
            parent=heading,
            prov=provenance(1, text, 730 - index * 20),
        )
    return document


def shredded_source(pages: int = 3, per_page: int = 30) -> DoclingDocument:
    """Spreadsheet-like shredding: many four-word paragraphs, one heading."""
    document = DoclingDocument(name="merge-shredded")
    for page in range(1, pages + 1):
        document.add_page(page, Size(width=612, height=792))
    title = document.add_title("Register", prov=provenance(1, "Register", 780))
    heading = document.add_heading(
        "Entries",
        level=1,
        parent=title,
        prov=provenance(1, "Entries", 765),
    )
    for page in range(1, pages + 1):
        for row in range(per_page):
            index = (page - 1) * per_page + row
            text = f"row {index} amount {index * 7}"
            document.add_text(
                label=DocItemLabel.TEXT,
                text=text,
                parent=heading,
                prov=provenance(page, text, 740 - row * 20),
            )
    return document
