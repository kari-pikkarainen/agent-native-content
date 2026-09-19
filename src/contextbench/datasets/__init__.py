"""Benchmark dataset interfaces and adapters."""

from contextbench.datasets.base import (
    BenchmarkDataset,
    BenchmarkQuestion,
    DocumentSource,
    EvidenceItem,
    GoldEvidence,
)
from contextbench.datasets.subsets import BenchmarkSubset, load_subset
from contextbench.datasets.xl_docbench import XLDocBenchDataset

__all__ = [
    "BenchmarkDataset",
    "BenchmarkQuestion",
    "BenchmarkSubset",
    "DocumentSource",
    "EvidenceItem",
    "GoldEvidence",
    "XLDocBenchDataset",
    "load_subset",
]
