"""Tests for immutable dataset and source-document downloads."""

import hashlib
import io
import json
from pathlib import Path

import pytest

from contextbench.datasets.base import DatasetIntegrityError, DocumentSource
from contextbench.datasets.download import (
    CacheIntegrityError,
    DocumentDownloadError,
    SourceDocumentCache,
    download_release,
)

PDF_BYTES = b"%PDF-1.7\nfixture document\n%%EOF\n"


def source(**updates: object) -> DocumentSource:
    values: dict[str, object] = {
        "id": "doc_fixture",
        "url": "https://example.test/document.pdf",
        "title": "Fixture",
        "domain": "test",
        "page_count": 1,
        "file_size_bytes": len(PDF_BYTES),
        "source_host": "example.test",
    }
    values.update(updates)
    return DocumentSource.model_validate(values)


def bytes_opener(data: bytes):  # type: ignore[no-untyped-def]
    def open_url(url: str) -> io.BytesIO:
        assert url.startswith("https://")
        return io.BytesIO(data)

    return open_url


def test_source_cache_downloads_hashes_and_reuses(tmp_path: Path) -> None:
    cache = SourceDocumentCache(tmp_path, opener=bytes_opener(PDF_BYTES))

    downloaded = cache.fetch(source())
    assert downloaded.reused is False
    assert downloaded.path.read_bytes() == PDF_BYTES
    assert downloaded.sha256 == hashlib.sha256(PDF_BYTES).hexdigest()

    def unexpected_network_call(url: str) -> io.BytesIO:
        raise AssertionError(f"unexpected network call: {url}")

    reused = SourceDocumentCache(tmp_path, opener=unexpected_network_call).fetch(
        source()
    )
    assert reused.reused is True
    assert reused.path == downloaded.path


def test_source_cache_rejects_changed_url_and_persists_failure(tmp_path: Path) -> None:
    SourceDocumentCache(tmp_path, opener=bytes_opener(PDF_BYTES)).fetch(source())
    changed = source(url="https://example.test/replacement.pdf")

    with pytest.raises(CacheIntegrityError, match="source identity changed"):
        SourceDocumentCache(tmp_path, opener=bytes_opener(PDF_BYTES)).fetch(changed)

    failures = (tmp_path / "failures.jsonl").read_text(encoding="utf-8").splitlines()
    failure = json.loads(failures[-1])
    assert failure["document_id"] == "doc_fixture"
    assert failure["error_type"] == "CacheIntegrityError"


def test_source_cache_detects_modified_file(tmp_path: Path) -> None:
    cache = SourceDocumentCache(tmp_path, opener=bytes_opener(PDF_BYTES))
    downloaded = cache.fetch(source())
    downloaded.path.write_bytes(b"changed")

    with pytest.raises(CacheIntegrityError, match="cached document changed"):
        cache.fetch(source())


def test_source_cache_records_download_failure(tmp_path: Path) -> None:
    def failing_opener(url: str) -> io.BytesIO:
        raise OSError(f"offline: {url}")

    with pytest.raises(DocumentDownloadError, match="offline"):
        SourceDocumentCache(tmp_path, opener=failing_opener).fetch(source())

    failures = (tmp_path / "failures.jsonl").read_text(encoding="utf-8")
    assert "doc_fixture" in failures
    assert "offline" in failures


def test_source_cache_rejects_non_pdf(tmp_path: Path) -> None:
    payload = b"<html>not a PDF</html>"
    invalid = source(file_size_bytes=len(payload))

    with pytest.raises(DocumentDownloadError, match="not a PDF"):
        SourceDocumentCache(tmp_path, opener=bytes_opener(payload)).fetch(invalid)


def test_pinned_release_download_is_hash_verified_and_reused(tmp_path: Path) -> None:
    files = {
        "manifest.json": b'{"release":"fixture"}\n',
        "data/questions.jsonl": b'{"id":"one"}\n',
    }
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}

    def release_opener(url: str) -> io.BytesIO:
        relative_path = next(name for name in files if url.endswith(name))
        return io.BytesIO(files[relative_path])

    destination = tmp_path / "release"
    download_release(destination, opener=release_opener, expected_hashes=hashes)

    def unexpected_network_call(url: str) -> io.BytesIO:
        raise AssertionError(f"unexpected network call: {url}")

    download_release(
        destination, opener=unexpected_network_call, expected_hashes=hashes
    )
    assert (destination / "data" / "questions.jsonl").read_bytes() == files[
        "data/questions.jsonl"
    ]


def test_pinned_release_refuses_to_overwrite_changed_file(tmp_path: Path) -> None:
    destination = tmp_path / "release"
    destination.mkdir()
    (destination / "manifest.json").write_bytes(b"changed")
    expected = {"manifest.json": hashlib.sha256(b"expected").hexdigest()}

    with pytest.raises(DatasetIntegrityError, match="refusing to overwrite"):
        download_release(
            destination,
            opener=bytes_opener(b"expected"),
            expected_hashes=expected,
        )
