"""Small, transparent BM25 implementation for the benchmark's local scale."""

import math
import re
from collections import Counter
from collections.abc import Sequence

from contextbench.retrieval.models import RetrievalChunk


class BM25Index:
    """In-memory BM25 index with deterministic tie-breaking."""

    def __init__(
        self, chunks: Sequence[RetrievalChunk], *, k1: float, b: float
    ) -> None:
        self.chunks = tuple(chunks)
        self.k1 = k1
        self.b = b
        self._terms = [_tokens(chunk.text) for chunk in self.chunks]
        self._lengths = [len(terms) for terms in self._terms]
        self._average_length = sum(self._lengths) / max(len(self._lengths), 1)
        document_frequency: Counter[str] = Counter()
        for terms in self._terms:
            document_frequency.update(set(terms))
        document_count = len(self.chunks)
        self._idf = {
            term: math.log(1 + (document_count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def search(
        self,
        query: str,
        limit: int,
        *,
        allowed_indices: set[int] | None = None,
    ) -> list[tuple[int, float]]:
        query_terms = _tokens(query)
        scored: list[tuple[int, float]] = []
        for index, terms in enumerate(self._terms):
            if allowed_indices is not None and index not in allowed_indices:
                continue
            frequencies = Counter(terms)
            length = self._lengths[index]
            score = 0.0
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                numerator = frequency * (self.k1 + 1)
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * length / max(self._average_length, 1)
                )
                score += self._idf.get(term, 0.0) * numerator / denominator
            scored.append((index, score))
        scored.sort(key=lambda pair: (-pair[1], self.chunks[pair[0]].id))
        return scored[:limit]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w]+", text.casefold())
