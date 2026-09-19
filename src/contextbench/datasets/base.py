"""Normalized interfaces shared by benchmark dataset adapters."""

import re
from collections.abc import Iterator
from typing import Annotated, Any, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

PositivePage = Annotated[int, Field(ge=1)]
AnswerValue = str | int | float | bool | None


class DatasetError(RuntimeError):
    """Base exception for invalid or unavailable benchmark data."""


class DatasetFormatError(DatasetError):
    """Raised when benchmark data does not match the expected release schema."""


class DatasetIntegrityError(DatasetError):
    """Raised when pinned benchmark data has changed or is internally invalid."""


class EvidenceItem(BaseModel):
    """A source annotation supplied by a benchmark author."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    locator: str | None = None
    pages: tuple[PositivePage, ...] = ()
    quote: str | None = None
    source_type: str | None = None
    evidence_kind: str | None = None
    page_numbering: str | None = None
    mentioned_elements: tuple[str, ...] = ()


class GoldEvidence(BaseModel):
    """Gold evidence associated with one source document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    pages: tuple[PositivePage, ...]
    page_numbering: str
    items: tuple[EvidenceItem, ...] = ()


class BenchmarkQuestion(BaseModel):
    """Dataset-neutral question representation used by benchmark systems."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    question: str
    document_ids: tuple[str, ...]
    gold_answer: AnswerValue
    answer_format: str
    verification_rule: str
    gold_evidence: tuple[GoldEvidence, ...]
    answerable: bool
    task_type: Literal["single_doc", "cross_doc"]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def gold_evidence_pages(self) -> dict[str, tuple[int, ...]]:
        """Return one-based PDF evidence pages keyed by document ID."""
        return {evidence.document_id: evidence.pages for evidence in self.gold_evidence}


class DocumentSource(BaseModel):
    """Public source document referenced by a benchmark release."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    url: str
    title: str | None
    domain: str
    page_count: int = Field(ge=1)
    file_size_bytes: int = Field(ge=1)
    source_host: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def id_is_safe_for_cache_path(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
            raise ValueError("document ID contains unsafe path characters")
        return value

    @field_validator("url")
    @classmethod
    def url_is_public_http(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("document URL must be an absolute HTTP(S) URL")
        return value


class BenchmarkDataset(Protocol):
    """Minimal behavior required from every benchmark dataset adapter."""

    @property
    def release_version(self) -> str:
        """Return the immutable dataset release identifier."""
        ...

    def iter_questions(self) -> Iterator[BenchmarkQuestion]:
        """Iterate over every question in deterministic ID order."""
        ...

    def get_question(self, question_id: str) -> BenchmarkQuestion:
        """Return one question or raise ``KeyError``."""
        ...

    def iter_documents(self) -> Iterator[DocumentSource]:
        """Iterate over source documents in deterministic ID order."""
        ...

    def get_document(self, document_id: str) -> DocumentSource:
        """Return one source document or raise ``KeyError``."""
        ...
