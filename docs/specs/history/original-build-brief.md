# Original Build Brief: Task Prompts and AGENTS.md Draft

These are sections 32 to 45 of the original benchmark specification, kept
unchanged as a historical record of how the prototype was commissioned. They
describe the intended `AGENTS.md`, the task-by-task build sequence given to a
coding agent, and the kinds of change that were ruled out. They are not
current instructions: the implementation, its command names and its artifact
formats are described in the [README](../../../README.md), the
[architecture](../../architecture.md) and the live
[specifications](../README.md). The current `AGENTS.md` lives at the
repository root.

Moved out of [`benchmark.md`](../benchmark.md) on 2026-10-01.

---

# 32. AGENTS.md contents

Keep AGENTS.md short.

It should say approximately:

```text
# Repository purpose

This repository tests whether structure-aware context compilation
outperforms conventional RAG.

It is a research benchmark, not a production platform.

# Source of truth

Read before changing architecture:

docs/specs/benchmark.md
docs/architecture.md
docs/specs/content-ir.md
docs/specs/evaluation.md

# Critical research constraints

1. Do not change gold benchmark data.
2. Do not improve one benchmark arm with a model unavailable to others.
3. Every benchmark result must be reproducible from a config + git SHA.
4. Compiler v0 must not use an LLM.
5. Preserve source provenance.
6. Never silently exceed a configured token budget.
7. Do not add infrastructure without an explicit benchmark need.

# Development

Use uv.

Before completing a task run:

uv run ruff check .
uv run pytest

# Testing

Network calls must not occur in unit tests.
Use cached fixtures.

# Scope

Avoid production features such as auth, UI, Kubernetes,
multi-tenancy, distributed workers, or hosted databases unless the
active execution plan explicitly requires them.
```

---

# 33. How to use Codex

Do NOT prompt:

> Build the AI Content IR prototype described in the README.

Instead create small issue-style tasks.

Each Codex task should contain:

1. Objective
2. Relevant files
3. Required behavior
4. Explicit non-goals
5. Acceptance tests
6. Commands Codex must run

One task should normally produce one reviewable conceptual change.

---

# 34. Codex Task 1

## Repository bootstrap

Prompt:

```text
Implement Milestone 0 from docs/specs/benchmark.md.

Objective:
Bootstrap the context-ir-bench Python repository.

Requirements:
- Python 3.12+
- uv package management
- src layout
- Typer CLI with a `agent-native-content --help` command
- pytest
- ruff
- basic GitHub Actions CI
- directory layout described in the spec
- placeholder architecture/spec documentation
- AGENTS.md following the project spec

Do not implement document parsing, retrieval, embeddings, or LLM calls.

Acceptance:
1. `uv sync` succeeds.
2. `uv run agent-native-content --help` succeeds.
3. `uv run ruff check .` succeeds.
4. `uv run pytest` succeeds.
5. Working tree is clean after committed/generated artifacts are excluded appropriately.

Before coding, read AGENTS.md and docs/specs/benchmark.md.
At completion summarize files changed and checks run.
```

---

# 35. Codex Task 2

## XL-DocBench adapter

```text
Implement Milestone 1 dataset support.

Read:
- AGENTS.md
- docs/specs/benchmark.md

Implement a normalized BenchmarkQuestion interface and XL-DocBench adapter.

Requirements:
- load the conservative XL-DocBench release
- expose question ID, question text, document IDs, gold answer,
  answerability, and gold evidence pages
- implement deterministic dataset iteration
- implement deterministic xl100 subset generation from a committed
  list of IDs
- add source-document downloader/cache
- calculate SHA-256 for downloaded documents
- failures must be explicit and persisted; do not silently skip them

Unit tests must use local fixtures and must not access the network.

Do not implement Docling ingestion yet.

Acceptance:
- CLI can inspect one question
- CLI can list xl100
- repeated calls produce identical output
- tests and lint pass
```

---

# 36. Codex Task 3

## Docling ingestion

```text
Implement cached Docling ingestion.

Input:
local source document

Output:
serialized DoclingDocument artifact plus metadata.

Requirements:
- source SHA-256 included
- parser version included
- cache invalidated when source hash changes
- repeated ingestion reuses existing artifact
- preserve page provenance, hierarchy, paragraphs, and tables

Create small PDF fixtures for tests or use repository-safe existing fixtures.

Do not build our custom IR in this task.

Add CLI:
agent-native-content ingest <document>

Acceptance:
tests prove cache behavior and basic structural preservation.
```

---

# 37. Codex Task 4

## Minimal IR projection

```text
Implement docs/specs/content-ir.md.

Project a DoclingDocument into our minimal IRDocument/IRNode representation.

Important:
The DoclingDocument remains the authoritative parsed artifact.
The IR is a normalized projection for retrieval experiments.

Requirements:
- stable deterministic IDs
- node kinds
- parent/child links
- heading path
- text
- page provenance
- source item IDs
- table metadata
- token counts
- JSON serialization

Do not add embeddings, summaries, entities, graphs, or LLM-derived metadata.

Add validation ensuring the IR graph is internally consistent.

Acceptance:
round-trip tests and deterministic-build tests pass.
```

---

# 38. Codex Task 5

## Strong RAG baselines

```text
Implement benchmark Arms A and B.

Arm A:
fixed 512-token chunks with 64-token overlap.

Arm B:
Docling HybridChunker structural chunks.

Both must share:
- embedding model
- BM25 implementation
- RRF fusion
- reranker
- token accounting
- final context packing

Make all parameters config-driven.

Store derived indexes under artifacts/indexes using deterministic
content/config hashes.

Do not implement the experimental compiler.

Acceptance:
For a fixture query both systems return ranked evidence,
provenance, scores, and context token counts.
All tests pass.
```

---

# 39. Codex Task 6

## Context Compiler v0

```text
Implement benchmark Arm D according to docs/specs/benchmark.md.

The compiler must be deterministic and may not call an LLM.

Pipeline:
1. sparse + dense candidate retrieval
2. RRF
3. reranking
4. heading/structural expansion
5. configurable sibling expansion
6. table preservation
7. provenance-aware deduplication
8. token-budget packing

Expose:
compile_context(query, document_scope, token_budget, config)

Every ContextItem must map back to source document/page/node.

Hard requirement:
returned token count must never exceed the configured budget.

Add unit tests for:
- headings
- siblings
- duplicate removal
- tables
- token boundaries
- provenance
```

---

# 40. Codex Task 7

## Retrieval benchmark

```text
Implement evidence-only benchmarking for A/B/D.

Do not call any answer LLM.

Run each query at token budgets:
2048, 4096, 8192, 16384.

Record:
- selected evidence IDs
- source pages
- gold pages
- token count
- retrieval latency
- evidence page recall
- full evidence coverage
- redundancy

Every run must produce a manifest containing:
git SHA, dataset version, configs, model IDs, seed, and question IDs.

Store outputs under immutable run directories.

Add comparison reporting.

Acceptance:
A single CLI command can execute the xl100 retrieval benchmark and
produce a Markdown + JSON summary.
```

---

# 41. First decision gate

STOP development after Task 7 and inspect the results.

The main plot should be:

```text
gold evidence recall
        ↑
        |
        |           compiler
        |        /
        |      /
        |  structural RAG
        | /
        | fixed RAG
        └──────────────────→
           context tokens
```

We want the compiler curve materially **up and left**.

If it isn't, diagnose why before adding more machinery.

Do not add an LLM planner to rescue weak results.

---

# 42. Codex Task 8

Only if Task 7 justifies continuing:

```text
Implement generation evaluation.

Create a provider-neutral AnswerProvider interface and an OpenAI
implementation.

All systems must use exactly the same:
- answer model
- model settings
- answer prompt
- maximum output
- evaluation logic

Require evidence-ID citations.

Capture provider-reported token usage and latency.

Implement cost-per-query and cost-per-correct-answer calculations from
configurable pricing metadata.

Do not modify retrieval algorithms in this task.
```

---

# 43. Codex Task 9

## Gold evidence experiment

```text
Implement the gold-evidence compression experiment.

For every benchmark question with available gold evidence:

Condition RAW:
gold evidence -> plain extraction -> answer model

Condition IR:
gold evidence -> IR/context compiler -> answer model

Retrieval must not be involved.

Measure:
- input tokens
- accuracy
- citation correctness
- latency
- cost

Purpose:
determine whether the IR/context representation itself is more
information-efficient independent of retrieval.
```

---

# 44. Codex Task 10

## Robustness

```text
Add:
- held-out XL-DocBench evaluation
- T2-RAGBench adapter
- long-context baseline
- compiler ablations
- second answer-model tier

Do not tune parameters against the held-out sets.

Produce one final comparison report clearly distinguishing:
development results
holdout results
cross-dataset results.
```

---

# 45. What we should NOT allow Codex to do

Reject PRs/tasks that introduce these without experimental justification:

* agent orchestration;
* autonomous query planning;
* generated ontology;
* knowledge graphs;
* LLM-generated document summaries;
* production API;
* React UI;
* cloud deployment;
* queueing systems;
* database clusters;
* user management;
* permissions;
* generic plugin architecture.

Those may become useful later.

Right now they obscure the experiment.

---
