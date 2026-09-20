"""Immutable experiment manifest models and environment capture."""

import platform
import subprocess
import sys
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict


class DocumentProvenance(BaseModel):
    """Immutable source and parser identity for one benchmark document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ir_document_id: str
    source_sha256: str
    parser_name: str
    parser_version: str
    parser_core_version: str


class RunManifest(BaseModel):
    """Complete reproducibility record for one retrieval benchmark run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    created_at: str
    git_commit: str
    dataset: str
    dataset_version: str
    dataset_revision: str
    subset_name: str
    subset_sha256: str
    question_ids: tuple[str, ...]
    documents: dict[str, DocumentProvenance]
    systems: tuple[str, ...]
    token_budgets: tuple[int, ...]
    seed: int
    config: dict[str, object]
    config_sha256: str
    embedding_model: str
    embedding_version: str
    reranker_model: str
    reranker_version: str
    tokenizer: str
    tokenizer_version: str
    python_version: str
    platform: str


def current_git_commit() -> str:
    """Return the exact checked-out commit or fail clearly outside Git."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def utc_now() -> datetime:
    return datetime.now(UTC)


def environment_info() -> tuple[str, str]:
    return sys.version.split()[0], platform.platform()
