"""Configurable dense embeddings for local retrieval."""

import hashlib
import math
import re
from collections.abc import Sequence
from importlib.metadata import version
from typing import Protocol


class EmbeddingModel(Protocol):
    """Dense embedding contract shared by both baseline arms."""

    @property
    def name(self) -> str:
        """Stable configured model name."""
        ...

    @property
    def version(self) -> str:
        """Implementation version."""
        ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts into normalized vectors."""
        ...


class HashEmbeddingModel:
    """Offline deterministic feature-hash embedding for fixtures and smoke runs."""

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    @property
    def name(self) -> str:
        return f"hash-{self.dimensions}-v1"

    @property
    def version(self) -> str:
        return "1"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        terms = _terms(text)
        for term in terms:
            digest = hashlib.sha256(term.encode()).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimensions
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class SentenceTransformerEmbeddingModel:
    """Lazy SentenceTransformers adapter for benchmark model runs."""

    def __init__(self, model_name: str, *, batch_size: int = 32) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "SentenceTransformers is required for configured dense model "
                f"{model_name!r}; install the retrieval extras"
            ) from exc
        self._model_name = model_name
        self._batch_size = batch_size
        self._model = SentenceTransformer(model_name)

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def version(self) -> str:
        return version("sentence-transformers")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        values = self._model.encode(
            list(texts),
            batch_size=self._batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return values.tolist()


def _terms(text: str) -> list[str]:
    return re.findall(r"[\w]+", text.casefold())
