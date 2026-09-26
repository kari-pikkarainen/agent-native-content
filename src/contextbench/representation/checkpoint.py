"""Durable per-cell checkpoints that let a representation run resume.

A representation run can take many hours against a slow local model, and a
provider failure used to discard every completed cell. The runner now appends
each completed cell to ``cells.jsonl`` in a staging directory next to the
final run directory, and a rerun with the same explicit run ID resumes from it.

The checkpoint is deliberately strict:

- ``header.json`` records everything that decides what a cell's record would
  be. A resume refuses unless every field except ``created_at`` is identical,
  and the error names the differing fields without printing any value.
- A line counts only once its terminating newline is on disk. A crash in the
  middle of an append leaves a final line without one; it is discarded (and
  cut from the file) on resume, never parsed. Any other unreadable line, an
  unknown or duplicate cell, a record that does not validate, or a prompt that
  no longer renders identically refuses the resume.
- An exclusive lock stops two processes from appending to one checkpoint.
- ``served_model.json`` pins the first provider-reported model ID. A cell
  whose answer and judge calls report different IDs, or whose ID differs from
  the pinned one, is refused before it is written, so a run never mixes
  served models, even across a server restart between attempts. A different
  quantization served under the same ID cannot be detected this way.
- A run started from a modified worktree (``git_dirty: true``) is never
  resumed: the header records only the flag, not the uncommitted code.

The checkpoint holds model outputs, like the published artifacts, and never a
key: the header is built from the config, which cannot hold one.
"""

import fcntl
import json
import os
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from contextbench.representation.models import (
    RepresentationError,
    RepresentationEvaluationRecord,
)

CHECKPOINT_FORMAT = "representation-checkpoint-v1"
HEADER_FILE = "header.json"
CELLS_FILE = "cells.jsonl"
LOCK_FILE = "lock"
SERVED_MODEL_FILE = "served_model.json"
# Informational only: a resumed run keeps the original start time.
CHECKPOINT_UNCOMPARED_FIELDS = frozenset({"created_at"})
_CELL_KEYS = frozenset(
    {"cell_index", "question_id", "condition", "prompt_sha256", "record"}
)
_MISSING = object()


def record_model_ids(record: RepresentationEvaluationRecord) -> set[str]:
    """Every provider-reported model ID behind one cell's calls."""
    return {
        value
        for value in (
            record.model_id,
            record.answer_judge_model_id,
            record.citation_judge_model_id,
        )
        if value is not None
    }


def _single_model_id(record: RepresentationEvaluationRecord) -> str:
    ids = record_model_ids(record)
    if len(ids) != 1:
        raise RepresentationError(
            f"cell {record.question_id}/{record.condition.value}: answer and "
            f"judge calls reported different served models: {sorted(ids)}"
        )
    return next(iter(ids))


def checkpoint_path(runs_dir: Path, run_id: str) -> Path:
    """Staging directory holding the checkpoint of one run ID."""
    return runs_dir / f".partial-{run_id}"


@dataclass
class RepresentationCheckpoint:
    """An open, locked checkpoint and the cells already completed in it."""

    path: Path
    records: dict[int, RepresentationEvaluationRecord]
    created_at: str
    resumed: bool
    cells_loaded: int
    partial_lines_discarded: int
    served_model_id: str | None
    _lock: Any = field(repr=False)

    @classmethod
    def open(
        cls,
        path: Path,
        header: Mapping[str, Any],
        *,
        cells: Sequence[tuple[str, str]],
        prompt_sha256: Sequence[str],
        explicit_run_id: bool,
    ) -> "RepresentationCheckpoint":
        """Create a new checkpoint or resume a matching existing one."""
        if len(cells) != len(prompt_sha256):
            raise ValueError("every planned cell needs a prompt hash")
        current = _json_roundtrip(header)
        if not path.exists():
            _create(path, current)
            lock = _lock(path)
            return cls(
                path=path,
                records={},
                created_at=str(current["created_at"]),
                resumed=False,
                cells_loaded=0,
                partial_lines_discarded=0,
                served_model_id=None,
                _lock=lock,
            )
        if not explicit_run_id:
            raise RepresentationError(
                f"a checkpoint already exists at {path}; resuming requires "
                "passing its run ID explicitly with --run-id"
            )
        lock = _lock(path)
        try:
            stored = _read_header(path)
            if stored.get("git_dirty") is not False:
                # Only the flag is recorded, so uncommitted code changes
                # between attempts could not be detected.
                raise RepresentationError(
                    f"checkpoint {path} was started from a modified worktree "
                    "(git_dirty: true) and cannot be resumed; delete it and "
                    "start the run over from a committed worktree"
                )
            differing = _differing_fields(stored, current)
            if differing:
                raise RepresentationError(
                    f"checkpoint {path} does not match this run; differing "
                    f"fields: {', '.join(differing)}. Rerun with the original "
                    "code, settings and inputs, or delete the checkpoint "
                    "directory to start the run over"
                )
            records, discarded = _load_cells(
                path / CELLS_FILE, cells=cells, prompt_sha256=prompt_sha256
            )
            served_model_id = _read_served_model(path)
            if records and served_model_id is None:
                raise RepresentationError(
                    f"checkpoint {path} has cells but no pinned served model"
                )
            for index, record in sorted(records.items()):
                if _single_model_id(record) != served_model_id:
                    raise RepresentationError(
                        f"checkpoint cell {index} was answered by another "
                        "served model than the one pinned in the checkpoint"
                    )
        except BaseException:
            _unlock(lock)
            raise
        return cls(
            path=path,
            records=records,
            created_at=str(stored["created_at"]),
            resumed=True,
            cells_loaded=len(records),
            partial_lines_discarded=discarded,
            served_model_id=served_model_id,
            _lock=lock,
        )

    def append(
        self,
        index: int,
        *,
        prompt_sha256: str,
        record: RepresentationEvaluationRecord,
    ) -> None:
        """Durably record one completed cell as a single JSON line."""
        if index in self.records:
            raise RepresentationError(f"cell {index} is already checkpointed")
        # Checked before anything is written: a record from another served
        # model must never enter the checkpoint.
        model_id = _single_model_id(record)
        if self.served_model_id is None:
            _write_served_model(self.path, model_id)
            self.served_model_id = model_id
        elif model_id != self.served_model_id:
            raise RepresentationError(
                f"the provider now reports served model {model_id!r}, but this "
                f"run's checkpoint {self.path} was made with "
                f"{self.served_model_id!r}; its {len(self.records)} completed "
                "cells are kept. Serve the original model and rerun the same "
                "command to resume"
            )
        line = (
            json.dumps(
                {
                    "cell_index": index,
                    "question_id": record.question_id,
                    "condition": record.condition.value,
                    "prompt_sha256": prompt_sha256,
                    "record": record.model_dump(mode="json"),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        with (self.path / CELLS_FILE).open("ab") as handle:
            handle.write(line.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        self.records[index] = record

    def close(self) -> None:
        """Release the lock; the checkpoint stays on disk for a resume."""
        _unlock(self._lock)
        self._lock = None

    def remove(self) -> None:
        """Delete the checkpoint once the run is published."""
        self.close()
        shutil.rmtree(self.path, ignore_errors=True)


def _json_roundtrip(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _canonical(value: object) -> str:
    # Distinguishes 1, 1.0 and true, which Python equality would not.
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _differing_fields(
    stored: Mapping[str, Any],
    current: Mapping[str, Any],
    prefix: str = "",
) -> list[str]:
    """Name every field whose value differs, descending into objects."""
    names: list[str] = []
    for key in sorted(set(stored) | set(current)):
        if not prefix and key in CHECKPOINT_UNCOMPARED_FIELDS:
            continue
        name = f"{prefix}{key}"
        old = stored.get(key, _MISSING)
        new = current.get(key, _MISSING)
        if isinstance(old, dict) and isinstance(new, dict):
            names.extend(_differing_fields(old, new, f"{name}."))
        elif old is _MISSING or new is _MISSING or _canonical(old) != _canonical(new):
            names.append(name)
    return names


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_synced(path: Path, data: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _create(path: Path, header: Mapping[str, Any]) -> None:
    """Publish a new checkpoint whose header is complete before it is visible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f"{path.name}.tmp-", dir=path.parent))
    try:
        _write_synced(
            staging / HEADER_FILE,
            (
                json.dumps(header, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n"
            ).encode("utf-8"),
        )
        _write_synced(staging / CELLS_FILE, b"")
        _fsync_directory(staging)
        # Fails rather than merging if another process created it meanwhile.
        staging.rename(path)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    _fsync_directory(path.parent)


def _write_served_model(path: Path, model_id: str) -> None:
    """Pin the served model once, atomically and durably."""
    temporary = path / f"{SERVED_MODEL_FILE}.tmp"
    _write_synced(
        temporary,
        (json.dumps({"served_model_id": model_id}, ensure_ascii=False) + "\n").encode(
            "utf-8"
        ),
    )
    temporary.replace(path / SERVED_MODEL_FILE)
    _fsync_directory(path)


def _read_served_model(path: Path) -> str | None:
    target = path / SERVED_MODEL_FILE
    if not target.exists():
        return None
    try:
        value = json.loads(target.read_text(encoding="utf-8"))["served_model_id"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        raise RepresentationError(
            f"checkpoint {path} has an unreadable served-model file"
        ) from None
    if not isinstance(value, str):
        raise RepresentationError(
            f"checkpoint {path} has an unreadable served-model file"
        )
    return value


def _lock(path: Path) -> int:
    descriptor = os.open(path / LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(descriptor)
        raise RepresentationError(
            f"checkpoint {path} is in use by another process"
        ) from None
    return descriptor


def _unlock(descriptor: int | None) -> None:
    if descriptor is None:
        return
    fcntl.flock(descriptor, fcntl.LOCK_UN)
    os.close(descriptor)


def _read_header(path: Path) -> dict[str, Any]:
    try:
        value = json.loads((path / HEADER_FILE).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise RepresentationError(
            f"checkpoint {path} has no readable header; inspect or delete it"
        ) from None
    if not isinstance(value, dict) or value.get("format") != CHECKPOINT_FORMAT:
        raise RepresentationError(
            f"checkpoint {path} has an unsupported header format"
        )
    return value


def _load_cells(
    path: Path,
    *,
    cells: Sequence[tuple[str, str]],
    prompt_sha256: Sequence[str],
) -> tuple[dict[int, RepresentationEvaluationRecord], int]:
    """Load committed cells, discarding one uncommitted final fragment."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise RepresentationError(f"checkpoint cells file is missing: {path}") from None
    committed_end = data.rfind(b"\n") + 1
    discarded = int(committed_end < len(data))
    records: dict[int, RepresentationEvaluationRecord] = {}
    for number, raw in enumerate(data[:committed_end].split(b"\n")[:-1], 1):
        index, record = _parse_cell(
            raw, number=number, cells=cells, prompt_sha256=prompt_sha256
        )
        if index in records:
            raise RepresentationError(
                f"checkpoint line {number} repeats cell {index} "
                f"({cells[index][0]}/{cells[index][1]})"
            )
        records[index] = record
    if discarded:
        # Cut the unterminated fragment so the next append starts a new line.
        with path.open("r+b") as handle:
            handle.truncate(committed_end)
            handle.flush()
            os.fsync(handle.fileno())
    return records, discarded


def _parse_cell(
    raw: bytes,
    *,
    number: int,
    cells: Sequence[tuple[str, str]],
    prompt_sha256: Sequence[str],
) -> tuple[int, RepresentationEvaluationRecord]:
    def refuse(reason: str) -> RepresentationError:
        return RepresentationError(f"checkpoint line {number} {reason}")

    try:
        entry = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise refuse("is not valid JSON") from None
    if not isinstance(entry, dict) or set(entry) != _CELL_KEYS:
        raise refuse("is not a checkpointed cell")
    index = entry["cell_index"]
    if (
        not isinstance(index, int)
        or isinstance(index, bool)
        or not 0 <= index < len(cells)
    ):
        raise refuse("names a cell outside this run")
    if (entry["question_id"], entry["condition"]) != tuple(cells[index]):
        raise refuse("names a cell outside this run")
    if entry["prompt_sha256"] != prompt_sha256[index]:
        raise refuse(
            "was made from a prompt that no longer renders identically"
        )
    try:
        record = RepresentationEvaluationRecord.model_validate(entry["record"])
    except ValidationError:
        raise refuse("holds a record that does not validate") from None
    if (record.question_id, record.condition.value) != tuple(cells[index]):
        raise refuse("holds a record for another cell")
    return index, record
