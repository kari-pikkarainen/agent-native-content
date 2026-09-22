"""Deterministic reranking adapters shared by both baseline arms."""

import re
from collections.abc import Callable, Sequence
from importlib.metadata import version
from typing import Any, Protocol

from contextbench.retrieval.models import RetrievalChunk


class Reranker(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def revision(self) -> str | None:
        """Pinned model-weight commit, or None for offline deterministic models."""
        ...

    def score(self, query: str, chunks: Sequence[RetrievalChunk]) -> list[float]: ...

    def score_pairs(
        self,
        pairs: Sequence[tuple[str, RetrievalChunk]],
    ) -> list[float]: ...


class LexicalOverlapReranker:
    """Transparent fallback reranker that rewards query-term coverage."""

    name = "lexical-overlap-v1"

    @property
    def version(self) -> str:
        return "1"

    @property
    def revision(self) -> str | None:
        """Report no hub identity: the scores are computed, not downloaded."""
        return None

    def score(self, query: str, chunks: Sequence[RetrievalChunk]) -> list[float]:
        query_terms = set(_terms(query))
        return [
            len(query_terms.intersection(_terms(chunk.retrieval_text)))
            / max(len(query_terms), 1)
            for chunk in chunks
        ]

    def score_pairs(
        self,
        pairs: Sequence[tuple[str, RetrievalChunk]],
    ) -> list[float]:
        return [
            self.score(query, (chunk,))[0]
            for query, chunk in pairs
        ]


class SentenceTransformerCrossEncoderReranker:
    """Lazy CrossEncoder adapter for configured benchmark reranker runs."""

    def __init__(
        self,
        model_name: str,
        *,
        revision: str | None,
        loader: Callable[..., Any] | None = None,
    ) -> None:
        """Load a hub cross-encoder at an explicitly pinned commit.

        ``revision`` is required and must be non-empty. Without it the hub
        default branch decides which weights score the candidates, and an
        upstream update would change rankings while the recorded model
        identity stayed the same.
        """
        if revision is None or not revision.strip():
            raise ValueError(
                "a pinned model revision is required for hub-backed reranker "
                f"{model_name!r}: pass the resolved commit hash so the run "
                "stays reproducible when the hub branch moves"
            )
        if loader is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:
                raise RuntimeError(
                    "SentenceTransformers is required for the configured reranker"
                ) from exc
            loader = CrossEncoder
        self._model_name = model_name
        self._revision = revision
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

    def score(self, query: str, chunks: Sequence[RetrievalChunk]) -> list[float]:
        return self.score_pairs([(query, chunk) for chunk in chunks])

    def score_pairs(
        self,
        pairs: Sequence[tuple[str, RetrievalChunk]],
    ) -> list[float]:
        # Unverified on an empty ``pairs``: it is reachable in principle --
        # ``retrieve()`` calls ``rerank(query, ())`` when both channels refuse
        # every chunk, which reaches ``self._model.predict([])`` -- but no test
        # covers it and no benchmark run can hit it. The positivity guards only
        # empty a channel under the offline ``hash-256-v1`` embedding, and this
        # adapter is only used with a hub-backed model, whose similarities are
        # all strictly positive on every published run (see
        # ``docs/specs/retrieval.md``). If a future embedder can produce an
        # empty candidate set, verify what SentenceTransformers' ``predict``
        # returns for an empty batch before relying on this path; do not assume
        # it is ``[]``.
        values = self._model.predict(
            [(query, chunk.retrieval_text) for query, chunk in pairs]
        )
        return [float(value) for value in values]


def _terms(text: str) -> list[str]:
    return re.findall(r"[\w]+", text.casefold())
