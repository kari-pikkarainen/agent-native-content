# Context IR Benchmark

A research prototype for testing whether a persistent, structure-preserving
intermediate representation and deterministic query-time context compilation
can improve evidence selection or reduce context-token usage relative to strong
RAG baselines.

This repository is intended to falsify that hypothesis, not to serve as a
production platform. See [the benchmark specification](docs/benchmark-spec.md)
for the research questions, comparison arms, success criteria, and kill
conditions.

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)

## Development

```shell
uv sync
uv run contextbench --help
uv run ruff check .
uv run pytest
```

The initial scaffold intentionally contains no document parsing, retrieval,
embedding, or model integration.

## XL-DocBench dataset

The adapter is pinned to Microsoft's conservative
`xldocbench_strict_1345_v1` release. Download its metadata, inspect a question,
or list the committed development subset with:

```shell
uv run contextbench dataset download xl-docbench
uv run contextbench dataset inspect xl-docbench <question-id>
uv run contextbench dataset list xl-docbench --subset-file configs/subsets/xl100.json
```

Add `--sources` to the download command to cache the referenced PDFs. Source
files are content-addressed after their release-recorded size is verified;
subsequent use rechecks SHA-256 and refuses silent replacement. Failed URLs are
recorded in `data/cache/xl-docbench/failures.jsonl`.
