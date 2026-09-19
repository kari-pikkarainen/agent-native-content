"""Pinned release and immutable source-document downloads."""

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Protocol
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, ValidationError

from contextbench.datasets.base import (
    DatasetError,
    DatasetIntegrityError,
    DocumentSource,
)
from contextbench.datasets.xl_docbench import (
    RELEASE_FILE_SHA256,
    RELEASE_REVISION,
)

RELEASE_BASE_URL = (
    "https://huggingface.co/datasets/microsoft/XL-DocBench/resolve/"
    f"{RELEASE_REVISION}"
)
_COPY_CHUNK_SIZE = 1024 * 1024


class ReadableResponse(Protocol):
    """The response behavior required by the download functions."""

    def read(self, size: int = -1) -> bytes:
        """Read response bytes."""
        ...


ResponseContext = AbstractContextManager[ReadableResponse]
Opener = Callable[[str], ResponseContext]


class DocumentDownloadError(DatasetError):
    """Raised when a source document cannot be downloaded and verified."""


class CacheIntegrityError(DatasetIntegrityError):
    """Raised when a cached source document no longer matches its record."""


class CachedDocument(BaseModel):
    """Verified result of a source-document cache lookup."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    source_url: str
    path: Path
    sha256: str
    size_bytes: int
    reused: bool


class _CacheRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    source_url: str
    relative_path: str
    sha256: str
    size_bytes: int
    downloaded_at: str


@contextmanager
def _url_opener(url: str) -> Iterator[BinaryIO]:
    request = Request(url, headers={"User-Agent": "context-ir-bench/0.1"})
    with urlopen(request, timeout=120) as response:  # noqa: S310
        yield response


def sha256_file(path: Path) -> str:
    """Hash a file without loading the whole document into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(_COPY_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def download_release(
    destination: Path,
    *,
    opener: Opener = _url_opener,
    expected_hashes: Mapping[str, str] = RELEASE_FILE_SHA256,
) -> Path:
    """Download the pinned release metadata without overwriting changed files."""
    for relative_path, expected_sha256 in expected_hashes.items():
        destination_path = destination / relative_path
        if destination_path.exists():
            actual_sha256 = sha256_file(destination_path)
            if actual_sha256 != expected_sha256:
                raise DatasetIntegrityError(
                    f"refusing to overwrite changed release file {destination_path}: "
                    f"SHA-256 is {actual_sha256}, expected {expected_sha256}"
                )
            continue

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"{RELEASE_BASE_URL}/{relative_path}"
        try:
            _download_verified_file(
                url,
                destination_path,
                opener=opener,
                expected_sha256=expected_sha256,
            )
        except Exception as exc:
            if isinstance(exc, DatasetError):
                raise
            raise DocumentDownloadError(
                f"failed to download XL-DocBench release file {url}: {exc}"
            ) from exc
    return destination


class SourceDocumentCache:
    """Permanent, content-addressed cache for benchmark source documents."""

    def __init__(self, root: Path, *, opener: Opener = _url_opener) -> None:
        self.root = root
        self.opener = opener

    def fetch(self, source: DocumentSource) -> CachedDocument:
        """Return a verified cached document, downloading it only when absent."""
        try:
            return self._fetch(source)
        except (CacheIntegrityError, DocumentDownloadError) as exc:
            self._record_failure(source, exc)
            raise
        except Exception as exc:
            wrapped = DocumentDownloadError(
                f"failed to download {source.id} from {source.url}: {exc}"
            )
            self._record_failure(source, wrapped)
            raise wrapped from exc

    def _fetch(self, source: DocumentSource) -> CachedDocument:
        document_dir = self.root / "documents" / source.id
        record_path = document_dir / "record.json"
        if record_path.exists():
            return self._reuse(source, record_path)

        document_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self._temporary_path(document_dir)
        try:
            sha256, size_bytes = self._download_source(source, temp_path)
            final_path = document_dir / f"{sha256}.pdf"
            os.replace(temp_path, final_path)
            record = _CacheRecord(
                document_id=source.id,
                source_url=source.url,
                relative_path=final_path.name,
                sha256=sha256,
                size_bytes=size_bytes,
                downloaded_at=datetime.now(UTC).isoformat(),
            )
            self._write_json_atomic(record_path, record.model_dump(mode="json"))
        finally:
            temp_path.unlink(missing_ok=True)

        return CachedDocument(
            document_id=source.id,
            source_url=source.url,
            path=final_path,
            sha256=sha256,
            size_bytes=size_bytes,
            reused=False,
        )

    def _reuse(self, source: DocumentSource, record_path: Path) -> CachedDocument:
        try:
            record = _CacheRecord.model_validate_json(
                record_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as exc:
            message = f"invalid cache record {record_path}: {exc}"
            raise CacheIntegrityError(message) from exc
        if record.document_id != source.id or record.source_url != source.url:
            raise CacheIntegrityError(
                f"cached source identity changed for {source.id}; refusing replacement"
            )

        path = record_path.parent / record.relative_path
        if not path.is_file():
            raise CacheIntegrityError(f"cached document is missing: {path}")
        actual_size = path.stat().st_size
        actual_sha256 = sha256_file(path)
        if actual_size != record.size_bytes or actual_sha256 != record.sha256:
            raise CacheIntegrityError(
                f"cached document changed for {source.id}: expected "
                f"{record.sha256}/{record.size_bytes}, got "
                f"{actual_sha256}/{actual_size}"
            )
        return CachedDocument(
            document_id=source.id,
            source_url=source.url,
            path=path,
            sha256=record.sha256,
            size_bytes=record.size_bytes,
            reused=True,
        )

    def _download_source(
        self, source: DocumentSource, destination: Path
    ) -> tuple[str, int]:
        digest = hashlib.sha256()
        size_bytes = 0
        prefix = bytearray()
        try:
            with self.opener(source.url) as response, destination.open("wb") as output:
                while chunk := response.read(_COPY_CHUNK_SIZE):
                    output.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)
                    if len(prefix) < 1024:
                        prefix.extend(chunk[: 1024 - len(prefix)])
        except Exception as exc:
            raise DocumentDownloadError(
                f"failed to download {source.id} from {source.url}: {exc}"
            ) from exc

        if b"%PDF-" not in prefix:
            raise DocumentDownloadError(
                f"downloaded content for {source.id} is not a PDF"
            )
        if size_bytes != source.file_size_bytes:
            raise DocumentDownloadError(
                f"downloaded size changed for {source.id}: got {size_bytes}, "
                f"expected {source.file_size_bytes}"
            )
        return digest.hexdigest(), size_bytes

    def _record_failure(self, source: DocumentSource, error: Exception) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        failure = {
            "timestamp": datetime.now(UTC).isoformat(),
            "document_id": source.id,
            "url": source.url,
            "error_type": type(error).__name__,
            "error": str(error),
        }
        with (self.root / "failures.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(failure, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _temporary_path(directory: Path) -> Path:
        descriptor, path = tempfile.mkstemp(
            prefix="download-", suffix=".tmp", dir=directory
        )
        os.close(descriptor)
        return Path(path)

    @staticmethod
    def _write_json_atomic(path: Path, value: dict[str, object]) -> None:
        temp_path = SourceDocumentCache._temporary_path(path.parent)
        try:
            temp_path.write_text(
                json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)


def _download_verified_file(
    url: str,
    destination: Path,
    *,
    opener: Opener,
    expected_sha256: str,
) -> None:
    temp_path = SourceDocumentCache._temporary_path(destination.parent)
    try:
        digest = hashlib.sha256()
        with opener(url) as response, temp_path.open("wb") as output:
            while chunk := response.read(_COPY_CHUNK_SIZE):
                output.write(chunk)
                digest.update(chunk)
        actual_sha256 = digest.hexdigest()
        if actual_sha256 != expected_sha256:
            raise DatasetIntegrityError(
                f"downloaded release file {url} has SHA-256 {actual_sha256}, "
                f"expected {expected_sha256}"
            )
        os.replace(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)
