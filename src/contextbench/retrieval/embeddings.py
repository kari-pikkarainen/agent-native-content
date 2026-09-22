"""Configurable dense embeddings for local retrieval."""

import hashlib
import math
import re
from collections.abc import Callable, Sequence
from importlib.metadata import version
from typing import Any, Protocol


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

    @property
    def revision(self) -> str | None:
        """Pinned model-weight commit, or None for offline deterministic models."""
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

    @property
    def revision(self) -> str | None:
        """Report no hub identity: the weights are computed, not downloaded."""
        return None

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

    def __init__(
        self,
        model_name: str,
        *,
        revision: str | None,
        batch_size: int = 32,
        loader: Callable[..., Any] | None = None,
    ) -> None:
        """Load a hub model at an explicitly pinned commit.

        ``revision`` is required and must be non-empty. Resolving the hub
        default branch instead would let an upstream weight update silently
        change embeddings while every recorded identity stayed the same, so
        an absent pin fails here rather than producing an unreproducible run.
        """
        if revision is None or not revision.strip():
            raise ValueError(
                "a pinned model revision is required for hub-backed dense "
                f"model {model_name!r}: pass the resolved commit hash so the "
                "run stays reproducible when the hub branch moves"
            )
        if loader is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "SentenceTransformers is required for configured dense model "
                    f"{model_name!r}; install the retrieval extras"
                ) from exc
            loader = SentenceTransformer
        self._model_name = model_name
        self._revision = revision
        self._batch_size = batch_size
        self._model = loader(model_name, revision=revision)

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def version(self) -> str:
        return version("sentence-transformers")

    @property
    def revision(self) -> str | None:
        return self._revision

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
