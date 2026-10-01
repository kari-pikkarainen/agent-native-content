"""Content-addressed cache for authoritative DoclingDocument artifacts."""

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from docling_core.types.doc import DoclingDocument
from docling_core.types.doc.labels import DocItemLabel
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_COPY_CHUNK_SIZE = 1024 * 1024
# Prefix of the private directory an entry is staged in before publication.
_STAGING_PREFIX = ".partial-"
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
        artifact_dir = self._artifact_dir(source_sha256, parser_config_hash)
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

        # The entry is published as a unit. Both files are written into a
        # private staging directory beside the entry, then one ``os.rename``
        # makes the whole directory appear at the entry path. A process killed
        # at any point before the rename leaves no entry, so a rerun parses
        # again; before, a kill between the two writes left ``document.json``
        # without ``metadata.json``, which every later run refused. Staging
        # names start with ``.partial-`` and are never 64 hex digits, so no
        # entry lookup can resolve to one. A kill can leave one behind; it is
        # never read, and can be deleted.
        # Exclusive ``mkdir`` of a random name rather than ``mkdtemp``, which
        # creates mode 0700 and would publish the entry unreadable to anyone
        # but the owner; ``mkdir`` applies the umask as the old path did.
        artifact_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = artifact_dir.parent / f"{_STAGING_PREFIX}{uuid.uuid4().hex}"
        staging.mkdir()
        try:
            staged_document = staging / document_path.name
            self._save_document_atomic(document, staged_document)
            document_sha256, _ = _hash_and_size(staged_document)
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
            _write_json_atomic(
                staging / metadata_path.name, metadata.model_dump(mode="json")
            )
            try:
                os.rename(staging, artifact_dir)
            except OSError as exc:
                if not artifact_dir.is_dir():
                    raise IngestionError(
                        f"cannot publish ingestion cache entry {artifact_dir}: {exc}"
                    ) from exc
                # Another writer published this entry while we parsed. Theirs
                # is complete by construction; verify and use it, and let the
                # ``finally`` discard ours.
                return self._load_cached(
                    source_sha256=source_sha256,
                    source_size=source_size,
                    parser_config_hash=parser_config_hash,
                    artifact_dir=artifact_dir,
                    metadata_path=metadata_path,
                    document_path=document_path,
                )
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return IngestResult(
            document=document,
            metadata=metadata,
            artifact_dir=artifact_dir,
            document_path=document_path,
            metadata_path=metadata_path,
            reused=False,
        )

    def entry_dir(self, source: Path) -> Path:
        """Return the cache entry ``ingest`` would use for ``source``.

        Validates and hashes the source exactly as ``ingest`` does, and parses
        nothing. Two sources with identical bytes share one entry.
        """
        source = source.resolve()
        self._validate_source(source)
        source_sha256, _size = _hash_and_size(source)
        return self._artifact_dir(source_sha256, self._parser_config_hash())

    @staticmethod
    def has_entry(entry_dir: Path) -> bool:
        """Whether ``ingest`` would reuse this entry rather than parse.

        The same test ``ingest`` applies: either file present means reuse.
        ``ingest`` publishes both files in one rename, so an interrupted write
        leaves no entry at all; a half-entry can only come from outside damage,
        and ``ingest`` then refuses it loudly rather than parsing over it.
        """
        return (entry_dir / "metadata.json").exists() or (
            entry_dir / "document.json"
        ).exists()

    def _artifact_dir(self, source_sha256: str, parser_config_hash: str) -> Path:
        return self.root / source_sha256[:2] / source_sha256 / parser_config_hash

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
