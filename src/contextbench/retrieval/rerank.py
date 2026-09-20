"""Deterministic reranking adapters shared by both baseline arms."""

import re
from collections.abc import Sequence
from importlib.metadata import version
from typing import Protocol

from contextbench.retrieval.models import RetrievalChunk


class Reranker(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def score(self, query: str, chunks: Sequence[RetrievalChunk]) -> list[float]: ...


class LexicalOverlapReranker:
    """Transparent fallback reranker that rewards query-term coverage."""

    name = "lexical-overlap-v1"

    @property
    def version(self) -> str:
        return "1"

    def score(self, query: str, chunks: Sequence[RetrievalChunk]) -> list[float]:
        query_terms = set(_terms(query))
        return [
            len(query_terms.intersection(_terms(chunk.text))) / max(len(query_terms), 1)
            for chunk in chunks
        ]


class SentenceTransformerCrossEncoderReranker:
    """Lazy CrossEncoder adapter for configured benchmark reranker runs."""

    def __init__(self, model_name: str) -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "SentenceTransformers is required for the configured reranker"
            ) from exc
        self._model_name = model_name
        self._model = CrossEncoder(model_name)

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def version(self) -> str:
        return version("sentence-transformers")

    def score(self, query: str, chunks: Sequence[RetrievalChunk]) -> list[float]:
        values = self._model.predict([(query, chunk.text) for chunk in chunks])
        return [float(value) for value in values]


def _terms(text: str) -> list[str]:
    return re.findall(r"[\w]+", text.casefold())
