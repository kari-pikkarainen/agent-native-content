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
