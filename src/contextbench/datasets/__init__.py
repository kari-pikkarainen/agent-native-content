"""Benchmark dataset interfaces and adapters."""

from contextbench.datasets.base import (
    BenchmarkDataset,
    BenchmarkQuestion,
    DocumentSource,
    EvidenceItem,
    GoldEvidence,
)
from contextbench.datasets.download import (
    CachedDocument,
    SourceDocumentCache,
    download_release,
)
from contextbench.datasets.subsets import BenchmarkSubset, load_subset
from contextbench.datasets.xl_docbench import XLDocBenchDataset

__all__ = [
    "BenchmarkDataset",
    "BenchmarkQuestion",
    "BenchmarkSubset",
    "CachedDocument",
    "DocumentSource",
    "EvidenceItem",
    "GoldEvidence",
    "SourceDocumentCache",
    "XLDocBenchDataset",
    "download_release",
    "load_subset",
]
