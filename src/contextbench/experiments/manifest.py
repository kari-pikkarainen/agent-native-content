"""Immutable experiment manifest models and environment capture."""

import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

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
    git_dirty: bool
    dataset: str
    dataset_version: str
    dataset_revision: str
    subset_name: str
    subset_sha256: str
    question_ids: tuple[str, ...]
    retrieval_corpus_name: str
    retrieval_corpus_sha256: str
    retrieval_corpus_question_ids: tuple[str, ...]
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
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        commit = _read_git_head(Path.cwd())
        if commit is None:
            raise RuntimeError("could not resolve the current Git commit") from error
        return commit
    return result.stdout.strip()


def current_git_dirty() -> bool:
    """Report whether tracked or untracked files differ from the commit.

    Fails closed: an unavailable or failing Git executable leaves the worktree
    state unknown, and an unknown state is recorded as dirty so that a run can
    never claim reproducibility it has not demonstrated.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return True
    return bool(result.stdout.strip())


def resolve_git_state(
    *,
    git_commit: str | None,
    git_dirty: bool | None = None,
    allow_dirty: bool = False,
    error: type[Exception] = RuntimeError,
) -> tuple[str, bool]:
    """Resolve the provenance recorded in a manifest and refuse dirty runs.

    A caller that supplies ``git_commit`` owns the provenance it records, so the
    worktree is not inspected at all and ``git_dirty`` defaults to ``False``.
    Otherwise both values are read from the worktree, and a dirty worktree
    raises ``error`` unless ``allow_dirty`` is set.
    """
    if git_commit is not None:
        return git_commit, bool(git_dirty)

    resolved_commit = current_git_commit()
    resolved_dirty = current_git_dirty() if git_dirty is None else bool(git_dirty)
    if resolved_dirty and not allow_dirty:
        raise error(
            "refusing to record a benchmark run from a modified worktree: "
            "commit or stash the changes so the result is reproducible from "
            f"{resolved_commit}, or pass --allow-dirty to stamp the run as dirty"
        )
    return resolved_commit, resolved_dirty


def _read_git_head(start: Path) -> str | None:
    """Resolve HEAD directly when the platform Git executable is unavailable."""
    for directory in (start, *start.parents):
        marker = directory / ".git"
        if marker.is_dir():
            git_dir = marker
        elif marker.is_file():
            prefix = "gitdir:"
            content = marker.read_text().strip()
            if not content.lower().startswith(prefix):
                continue
            git_dir = Path(content[len(prefix) :].strip())
            if not git_dir.is_absolute():
                git_dir = directory / git_dir
        else:
            continue

        head = (git_dir / "HEAD").read_text().strip()
        if not head.startswith("ref:"):
            return head or None

        ref_name = head.removeprefix("ref:").strip()
        loose_ref = git_dir / ref_name
        if loose_ref.is_file():
            return loose_ref.read_text().strip() or None

        packed_refs = git_dir / "packed-refs"
        if packed_refs.is_file():
            for line in packed_refs.read_text().splitlines():
                if not line or line.startswith(("#", "^")):
                    continue
                commit, name = line.split(" ", maxsplit=1)
                if name == ref_name:
                    return commit
        return None
    return None


def utc_now() -> datetime:
    return datetime.now(UTC)


def environment_info() -> tuple[str, str]:
    return sys.version.split()[0], platform.platform()
