"""Committed benchmark subset manifests."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from contextbench.datasets.base import DatasetFormatError


class BenchmarkSubset(BaseModel):
    """An immutable, ordered list of question IDs for a dataset release."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    dataset: str
    release_version: str
    release_revision: str
    selection_seed: int
    selection_method: str
    strata: dict[str, Any] = Field(default_factory=dict)
    question_ids: tuple[str, ...]

    @model_validator(mode="after")
    def question_ids_are_unique(self) -> "BenchmarkSubset":
        if not self.question_ids:
            raise ValueError("question_ids must not be empty")
        if len(self.question_ids) != len(set(self.question_ids)):
            raise ValueError("question_ids must not contain duplicates")
        return self


def load_subset(path: Path) -> BenchmarkSubset:
    """Load and validate a committed subset manifest."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return BenchmarkSubset.model_validate(raw)
    except FileNotFoundError as exc:
        raise DatasetFormatError(f"subset manifest not found: {path}") from exc
    except (json.JSONDecodeError, ValidationError) as exc:
        raise DatasetFormatError(f"invalid subset manifest {path}: {exc}") from exc
