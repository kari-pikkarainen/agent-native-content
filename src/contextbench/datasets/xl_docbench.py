"""Adapter for the pinned conservative XL-DocBench release."""

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from contextbench.datasets.base import (
    BenchmarkQuestion,
    DatasetFormatError,
    DatasetIntegrityError,
    DocumentSource,
    EvidenceItem,
    GoldEvidence,
)
from contextbench.datasets.subsets import BenchmarkSubset

DATASET_NAME = "microsoft/XL-DocBench"
RELEASE_VERSION = "xldocbench_strict_1345_v1"
RELEASE_REVISION = "72954bd70ffffe230f08b57c57fa9274ec14d7ea"
RELEASE_FILES = (
    "manifest.json",
    "data/documents.jsonl",
    "data/qa_single_doc.jsonl",
    "data/qa_cross_doc.jsonl",
)
RELEASE_FILE_SHA256 = {
    "manifest.json": "501d322125fca14e65f16f99a9113d9a9467da5974b3eda3c76ab6af4a9766f7",
    "data/documents.jsonl": (
        "f63f9188f29fde8b9f0bc1dee32e594f62616966903458fc90ea772de62d3a38"
    ),
    "data/qa_single_doc.jsonl": (
        "ab214f9fee45f763810a0f316911da19915a7c2ee9a0dfaff55f799df283a62d"
    ),
    "data/qa_cross_doc.jsonl": (
        "18d514bb3c77e8e3b30ddc514116074b787fafd54153ff208817d24007ef4a13"
    ),
}


class XLDocBenchDataset:
    """Load XL-DocBench from its small, source-document-free release files."""

    def __init__(self, root: Path, *, verify_release: bool = True) -> None:
        self.root = root
        self._manifest = self._read_json(root / "manifest.json")
        self._validate_manifest()
        if verify_release:
            self._verify_release_files()

        self._documents = self._load_documents(root / "data" / "documents.jsonl")
        self._questions = self._load_questions()
        self._validate_counts()

    @property
    def release_version(self) -> str:
        return RELEASE_VERSION

    @property
    def release_revision(self) -> str:
        return RELEASE_REVISION

    def iter_questions(self) -> Iterator[BenchmarkQuestion]:
        yield from self._questions.values()

    def get_question(self, question_id: str) -> BenchmarkQuestion:
        try:
            return self._questions[question_id]
        except KeyError as exc:
            raise KeyError(f"unknown XL-DocBench question: {question_id}") from exc

    def iter_documents(self) -> Iterator[DocumentSource]:
        yield from self._documents.values()

    def get_document(self, document_id: str) -> DocumentSource:
        try:
            return self._documents[document_id]
        except KeyError as exc:
            raise KeyError(f"unknown XL-DocBench document: {document_id}") from exc

    def iter_subset(self, subset: BenchmarkSubset) -> Iterator[BenchmarkQuestion]:
        """Iterate in the exact order recorded by the subset manifest."""
        if subset.dataset != DATASET_NAME:
            raise DatasetIntegrityError(
                f"subset targets {subset.dataset!r}, expected {DATASET_NAME!r}"
            )
        if subset.release_version != self.release_version:
            raise DatasetIntegrityError(
                "subset release version does not match loaded XL-DocBench release"
            )
        if subset.release_revision != self.release_revision:
            raise DatasetIntegrityError(
                "subset release revision does not match the pinned release"
            )
        for question_id in subset.question_ids:
            try:
                yield self._questions[question_id]
            except KeyError as exc:
                raise DatasetIntegrityError(
                    f"subset references unknown question: {question_id}"
                ) from exc

    def _load_questions(self) -> dict[str, BenchmarkQuestion]:
        raw_rows = [
            *self._read_jsonl(self.root / "data" / "qa_single_doc.jsonl"),
            *self._read_jsonl(self.root / "data" / "qa_cross_doc.jsonl"),
        ]
        questions: dict[str, BenchmarkQuestion] = {}
        for raw in raw_rows:
            question = self._normalize_question(raw)
            if question.id in questions:
                raise DatasetIntegrityError(f"duplicate question ID: {question.id}")
            questions[question.id] = question
        return dict(sorted(questions.items()))

    def _load_documents(self, path: Path) -> dict[str, DocumentSource]:
        documents: dict[str, DocumentSource] = {}
        for raw in self._read_jsonl(path):
            try:
                document = DocumentSource(
                    id=raw["document_id"],
                    url=raw["url"],
                    title=raw["title"],
                    domain=raw["domain"],
                    page_count=raw["page_count"],
                    file_size_bytes=raw["file_size_bytes"],
                    source_host=raw["source_host"],
                    metadata={
                        "doc_type": raw.get("doc_type"),
                        "pdf_type": raw.get("pdf_type"),
                        "public_metadata": raw.get("public_metadata", {}),
                    },
                )
            except (KeyError, ValidationError) as exc:
                message = f"invalid document row in {path}: {exc}"
                raise DatasetFormatError(message) from exc
            if document.id in documents:
                raise DatasetIntegrityError(f"duplicate document ID: {document.id}")
            documents[document.id] = document
        return dict(sorted(documents.items()))

    def _normalize_question(self, raw: dict[str, Any]) -> BenchmarkQuestion:
        try:
            task_type = raw["task_type"]
            raw_documents = (
                [raw["document"]] if task_type == "single_doc" else raw["documents"]
            )
            document_ids = tuple(document["document_id"] for document in raw_documents)
            for document in raw_documents:
                source = self.get_document(document["document_id"])
                if document["url"] != source.url:
                    raise DatasetIntegrityError(
                        f"question {raw['question_id']} has a source URL that differs "
                        f"from the document manifest for {source.id}"
                    )

            gold_evidence = tuple(
                self._normalize_evidence(document)
                for document in raw_documents
                if document.get("evidence_pages") or document.get("evidence_items")
            )
            answer = raw["answer"]
            metadata = raw["metadata"]
            return BenchmarkQuestion(
                id=raw["question_id"],
                question=raw["question"],
                document_ids=document_ids,
                gold_answer=answer.get("value"),
                answer_format=answer["format"],
                verification_rule=answer["verification_rule"],
                gold_evidence=gold_evidence,
                answerable=not bool(metadata["is_unanswerable"]),
                task_type=task_type,
                metadata=dict(metadata),
            )
        except DatasetIntegrityError:
            raise
        except (KeyError, TypeError, ValidationError) as exc:
            question_id = raw.get("question_id", "<missing>")
            raise DatasetFormatError(f"invalid question {question_id}: {exc}") from exc

    @staticmethod
    def _normalize_evidence(raw: dict[str, Any]) -> GoldEvidence:
        return GoldEvidence(
            document_id=raw["document_id"],
            pages=tuple(raw.get("evidence_pages", ())),
            page_numbering=raw.get("evidence_page_numbering", "pdf_index"),
            items=tuple(
                EvidenceItem(
                    locator=item.get("locator"),
                    pages=tuple(item.get("pages", ())),
                    quote=item.get("quote"),
                    source_type=item.get("source_type"),
                    evidence_kind=item.get("evidence_kind"),
                    page_numbering=item.get("page_numbering"),
                    mentioned_elements=tuple(item.get("mentioned_elements", ())),
                )
                for item in raw.get("evidence_items", ())
            ),
        )

    def _validate_manifest(self) -> None:
        version = self._manifest.get("release_version")
        if version != RELEASE_VERSION:
            message = (
                f"unsupported XL-DocBench release {version!r}; "
                f"expected {RELEASE_VERSION!r}"
            )
            raise DatasetIntegrityError(
                message
            )

    def _validate_counts(self) -> None:
        expected_documents = self._manifest.get("document_count")
        expected_questions = self._manifest.get("qa_count")
        if expected_documents != len(self._documents):
            raise DatasetIntegrityError(
                f"document count mismatch: manifest={expected_documents}, "
                f"loaded={len(self._documents)}"
            )
        if expected_questions != len(self._questions):
            raise DatasetIntegrityError(
                f"question count mismatch: manifest={expected_questions}, "
                f"loaded={len(self._questions)}"
            )

    def _verify_release_files(self) -> None:
        for relative_path, expected_sha256 in RELEASE_FILE_SHA256.items():
            path = self.root / relative_path
            try:
                actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            except FileNotFoundError as exc:
                raise DatasetFormatError(f"release file not found: {path}") from exc
            if actual_sha256 != expected_sha256:
                raise DatasetIntegrityError(
                    f"release file changed: {path} has SHA-256 {actual_sha256}, "
                    f"expected {expected_sha256}"
                )

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise DatasetFormatError(f"release file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise DatasetFormatError(f"invalid JSON in {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise DatasetFormatError(f"expected a JSON object in {path}")
        return value

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError as exc:
            raise DatasetFormatError(f"release file not found: {path}") from exc
        rows: list[dict[str, Any]] = []
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetFormatError(
                    f"invalid JSON in {path} at line {line_number}: {exc}"
                ) from exc
            if not isinstance(row, dict):
                raise DatasetFormatError(
                    f"expected a JSON object in {path} at line {line_number}"
                )
            rows.append(row)
        return rows
