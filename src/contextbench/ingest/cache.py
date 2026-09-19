"""Content-addressed cache for authoritative DoclingDocument artifacts."""

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_COPY_CHUNK_SIZE = 1024 * 1024
_METADATA_SCHEMA_VERSION = 1


class IngestionError(RuntimeError):
    """Base error for source validation, parsing, or cache integrity failures."""


class IngestionCacheIntegrityError(IngestionError):
    """Raised when a cached artifact differs from its immutable metadata."""


class DocumentParser(Protocol):
    """Parser contract used to keep cache tests independent of model downloads."""

    name: str

    @property
    def version(self) -> str:
        """Return the parser package version."""
        ...

    @property
    def core_version(self) -> str:
        """Return the serialized document-schema package version."""
        ...

    @property
    def config(self) -> dict[str, Any]:
        """Return JSON-serializable parser configuration."""
        ...

    def parse(self, source: Path) -> DoclingDocument:
        """Parse the source into a complete DoclingDocument."""
        ...


class IngestMetadata(BaseModel):
    """Immutable provenance and integrity record for one parsed artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = _METADATA_SCHEMA_VERSION
    source_path: str
    source_name: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_size_bytes: int = Field(ge=1)
    parser_name: str
    parser_version: str
    parser_core_version: str
    parser_config: dict[str, Any]
    parser_config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_file: str
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    docling_schema_version: str
    page_count: int = Field(ge=0)
    text_count: int = Field(ge=0)
    heading_count: int = Field(ge=0)
    table_count: int = Field(ge=0)
    created_at: str


class IngestResult(BaseModel):
    """Loaded result of parsing or reusing one document."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    document: DoclingDocument
    metadata: IngestMetadata
    artifact_dir: Path
    document_path: Path
    metadata_path: Path
    reused: bool


class IngestionCache:
    """Create and verify content-addressed DoclingDocument artifacts."""

    def __init__(self, root: Path, parser: DocumentParser) -> None:
        self.root = root
        self.parser = parser

    def ingest(self, source: Path) -> IngestResult:
        """Parse a local source or return its verified cached representation."""
        source = source.resolve()
        self._validate_source(source)
        source_sha256, source_size = _hash_and_size(source)
        parser_config_hash = self._parser_config_hash()
        artifact_dir = (
            self.root
            / source_sha256[:2]
            / source_sha256
            / parser_config_hash[:16]
        )
        metadata_path = artifact_dir / "metadata.json"
        document_path = artifact_dir / "document.json"

        if metadata_path.exists() or document_path.exists():
            return self._load_cached(
                source_sha256=source_sha256,
                source_size=source_size,
                parser_config_hash=parser_config_hash,
                artifact_dir=artifact_dir,
                metadata_path=metadata_path,
                document_path=document_path,
            )

        try:
            document = self.parser.parse(source)
        except Exception as exc:
            raise IngestionError(f"failed to parse {source}: {exc}") from exc

        artifact_dir.mkdir(parents=True, exist_ok=True)
        self._save_document_atomic(document, document_path)
        document_sha256, _ = _hash_and_size(document_path)
        counts = _document_counts(document)
        metadata = IngestMetadata(
            source_path=str(source),
            source_name=source.name,
            source_sha256=source_sha256,
            source_size_bytes=source_size,
            parser_name=self.parser.name,
            parser_version=self.parser.version,
            parser_core_version=self.parser.core_version,
            parser_config=self.parser.config,
            parser_config_hash=parser_config_hash,
            document_file=document_path.name,
            document_sha256=document_sha256,
            docling_schema_version=document.version,
            **counts,
            created_at=datetime.now(UTC).isoformat(),
        )
        _write_json_atomic(metadata_path, metadata.model_dump(mode="json"))
        return IngestResult(
            document=document,
            metadata=metadata,
            artifact_dir=artifact_dir,
            document_path=document_path,
            metadata_path=metadata_path,
            reused=False,
        )

    def _load_cached(
        self,
        *,
        source_sha256: str,
        source_size: int,
        parser_config_hash: str,
        artifact_dir: Path,
        metadata_path: Path,
        document_path: Path,
    ) -> IngestResult:
        if not metadata_path.is_file() or not document_path.is_file():
            raise IngestionCacheIntegrityError(
                f"incomplete ingestion cache entry: {artifact_dir}"
            )
        try:
            metadata = IngestMetadata.model_validate_json(
                metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            raise IngestionCacheIntegrityError(
                f"invalid ingestion metadata {metadata_path}: {exc}"
            ) from exc

        expected = {
            "source_sha256": source_sha256,
            "source_size_bytes": source_size,
            "parser_name": self.parser.name,
            "parser_version": self.parser.version,
            "parser_core_version": self.parser.core_version,
            "parser_config_hash": parser_config_hash,
            "document_file": document_path.name,
        }
        for field, value in expected.items():
            if getattr(metadata, field) != value:
                raise IngestionCacheIntegrityError(
                    f"cache metadata mismatch for {field}: "
                    f"{getattr(metadata, field)!r} != {value!r}"
                )

        actual_document_sha256, _ = _hash_and_size(document_path)
        if actual_document_sha256 != metadata.document_sha256:
            raise IngestionCacheIntegrityError(
                f"serialized DoclingDocument changed: {document_path}"
            )
        try:
            document = DoclingDocument.load_from_json(document_path)
        except Exception as exc:
            raise IngestionCacheIntegrityError(
                f"cannot load serialized DoclingDocument {document_path}: {exc}"
            ) from exc
        if document.version != metadata.docling_schema_version:
            raise IngestionCacheIntegrityError(
                "DoclingDocument schema version differs from cache metadata"
            )
        if _document_counts(document) != {
            "page_count": metadata.page_count,
            "text_count": metadata.text_count,
            "heading_count": metadata.heading_count,
            "table_count": metadata.table_count,
        }:
            raise IngestionCacheIntegrityError(
                "DoclingDocument structural counts differ from cache metadata"
            )
        return IngestResult(
            document=document,
            metadata=metadata,
            artifact_dir=artifact_dir,
            document_path=document_path,
            metadata_path=metadata_path,
            reused=True,
        )

    def _parser_config_hash(self) -> str:
        value = {
            "parser_name": self.parser.name,
            "parser_version": self.parser.version,
            "parser_core_version": self.parser.core_version,
            "config": self.parser.config,
        }
        try:
            serialized = json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        except (TypeError, ValueError) as exc:
            message = f"parser config is not JSON serializable: {exc}"
            raise IngestionError(message) from exc
        return hashlib.sha256(serialized).hexdigest()

    @staticmethod
    def _validate_source(source: Path) -> None:
        if not source.exists():
            raise IngestionError(f"source document not found: {source}")
        if not source.is_file():
            raise IngestionError(f"source document is not a file: {source}")
        if source.stat().st_size == 0:
            raise IngestionError(f"source document is empty: {source}")

    @staticmethod
    def _save_document_atomic(document: DoclingDocument, path: Path) -> None:
        temp_path = _temporary_path(path.parent)
        try:
            document.save_as_json(
                temp_path,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)


def _document_counts(document: DoclingDocument) -> dict[str, int]:
    heading_labels = {DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER}
    return {
        "page_count": len(document.pages),
        "text_count": len(document.texts),
        "heading_count": sum(item.label in heading_labels for item in document.texts),
        "table_count": len(document.tables),
    }


def _hash_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as file:
        while chunk := file.read(_COPY_CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _temporary_path(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(
        prefix="ingest-", suffix=".tmp", dir=directory
    )
    os.close(descriptor)
    return Path(raw_path)


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    temp_path = _temporary_path(path.parent)
    try:
        temp_path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
