"""Deterministic JSON serialization for IR documents."""

import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from agent_native_content.ir.models import IRDocument, IRValidationError


def save_ir_document(document: IRDocument, path: Path) -> None:
    """Atomically write canonical, human-readable IR JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp_path = tempfile.mkstemp(
        prefix="ir-", suffix=".json.tmp", dir=path.parent
    )
    os.close(descriptor)
    temp_path = Path(raw_temp_path)
    try:
        value = document.model_dump(mode="json")
        temp_path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def load_ir_document(path: Path) -> IRDocument:
    """Load IR JSON and re-run all schema and graph validation."""
    try:
        return IRDocument.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise IRValidationError(f"IR document not found: {path}") from exc
    except (OSError, ValidationError) as exc:
        raise IRValidationError(f"invalid IR document {path}: {exc}") from exc
