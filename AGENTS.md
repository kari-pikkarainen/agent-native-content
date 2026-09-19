# Repository purpose

This repository tests whether structure-aware context compilation outperforms
conventional RAG. It is a research benchmark, not a production platform.

# Source of truth

Read before changing architecture:

- `docs/benchmark-spec.md`
- `docs/architecture.md`
- `docs/ir-spec.md`
- `docs/experiment-protocol.md`

# Critical research constraints

1. Do not change gold benchmark data.
2. Do not improve one benchmark arm with a model unavailable to the others.
3. Every benchmark result must be reproducible from a config and Git SHA.
4. Compiler v0 must not use an LLM.
5. Preserve source provenance.
6. Never silently exceed a configured token budget.
7. Do not add infrastructure without an explicit benchmark need.

# Development

Use `uv`.

Before completing a task, run:

```text
uv run ruff check .
uv run pytest
```

# Testing

Network calls must not occur in unit tests. Use cached fixtures.

# Scope

Avoid production features such as authentication, a web UI, Kubernetes,
multi-tenancy, distributed workers, or hosted databases unless the active
execution plan explicitly requires them.
