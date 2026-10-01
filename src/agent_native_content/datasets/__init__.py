"""Benchmark dataset interfaces and adapters."""

from agent_native_content.datasets.base import (
    BenchmarkDataset,
    BenchmarkQuestion,
    DocumentSource,
    EvidenceItem,
    GoldEvidence,
)
from agent_native_content.datasets.download import (
    CachedDocument,
    SourceDocumentCache,
    download_release,
)
from agent_native_content.datasets.subsets import BenchmarkSubset, load_subset
from agent_native_content.datasets.xl_docbench import XLDocBenchDataset

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
