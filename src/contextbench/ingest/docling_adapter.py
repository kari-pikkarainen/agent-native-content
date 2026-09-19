"""Narrow adapter around Docling's local PDF conversion pipeline."""

from importlib.metadata import version
from pathlib import Path
from typing import Any

from docling_core.types.doc import DoclingDocument


class DoclingConversionError(RuntimeError):
    """Raised when Docling cannot produce a complete document."""


class DoclingParser:
    """Parse local PDFs with Docling's standard, structure-aware pipeline."""

    name = "docling"

    def __init__(self, *, artifacts_path: Path | None = None) -> None:
        self.artifacts_path = artifacts_path.resolve() if artifacts_path else None

    @property
    def version(self) -> str:
        return version("docling")

    @property
    def core_version(self) -> str:
        return version("docling-core")

    @property
    def config(self) -> dict[str, Any]:
        """Return every intentional pipeline choice used in the cache key."""
        return {
            "pipeline": "standard_pdf",
            "artifacts_path": (
                str(self.artifacts_path) if self.artifacts_path is not None else None
            ),
            "enable_remote_services": False,
            "do_ocr": True,
            "do_table_structure": True,
            "do_picture_classification": False,
            "do_picture_description": False,
            "do_chart_extraction": False,
            "do_code_enrichment": False,
            "do_formula_enrichment": False,
            "generate_page_images": False,
            "generate_picture_images": False,
            "generate_table_images": False,
        }

    def parse(self, source: Path) -> DoclingDocument:
        """Convert one local PDF without enabling any remote model service."""
        if source.suffix.lower() != ".pdf":
            raise DoclingConversionError(f"only PDF input is supported: {source}")

        # These imports initialize Docling's conversion stack, so keep them off
        # cache-hit and CLI-help paths.
        from docling.datamodel.base_models import ConversionStatus, InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        options = PdfPipelineOptions(
            artifacts_path=self.artifacts_path,
            enable_remote_services=False,
            do_ocr=True,
            do_table_structure=True,
            do_picture_classification=False,
            do_picture_description=False,
            do_chart_extraction=False,
            do_code_enrichment=False,
            do_formula_enrichment=False,
            generate_page_images=False,
            generate_picture_images=False,
            generate_table_images=False,
        )
        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
        )
        result = converter.convert(source, raises_on_error=True)
        if result.status is not ConversionStatus.SUCCESS:
            raise DoclingConversionError(
                f"Docling returned {result.status.value} for {source}; "
                "partial documents are not cacheable"
            )
        return result.document
