# Agent-Native Content Benchmark

## Prototype and Benchmark Build Specification

> **Status note (2026-10-01).** This is the founding specification: the
> hypothesis, research questions, compared systems, metrics, success and kill
> criteria, and the build sequence. Those parts are still normative. Some
> implementation choices it suggested were superseded during the build and
> are left as written so the record stays honest:
>
> - §4 names `bm25s`, DuckDB and PyArrow/Parquet. The implementation uses a
>   small in-repo BM25 (`retrieval/sparse.py`), JSON Lines artifacts, and no
>   analytical database.
> - §22 lists Parquet artifact files. Runs write `manifest.json`,
>   `retrieval.jsonl`, `contexts.jsonl`, `summary.json` and `report.md`; see
>   the [evaluation protocol](evaluation.md).
> - §23 sketches `index`, `compare` and `report` commands. Indexes are built
>   on demand by the evaluation commands, and comparison reports are written by
>   every run; see `agent-native-content --help`.
> - §24 asks for plots. None are generated; the Markdown reports carry tables.
> - §5's model names are examples. The models actually used are recorded in
>   each run's manifest and in the [results index](../../results/README.md).
>
> The implemented contracts are in the sibling specifications listed in
> [`docs/specs/README.md`](README.md). Where this document and one of them
> disagree on implemented behaviour, the sibling specification wins.

## 1. Objective

Build a research prototype to test this hypothesis:

> A persistent, structure-preserving intermediate representation (IR) plus deterministic query-time context compilation can provide better evidence selection and/or substantially lower context-token consumption than strong conventional RAG.

This is a **falsification prototype**, not a production product.

The prototype must make it easy to conclude that the hypothesis is wrong.

The first goal is NOT to build:

* an enterprise platform;
* a new vector database;
* an agent framework;
* a knowledge graph;
* a generalized multimodal IR;
* a web UI;
* scalable distributed infrastructure.

The goal is to produce trustworthy comparative benchmark results.

---

# 2. Primary research questions

The system must answer four questions.

### RQ1 — Retrieval efficiency

At a fixed context budget, does the context compiler retrieve more of the gold evidence than conventional RAG?

Primary metric:

`gold evidence recall @ token budget`

Test at:

* 2K tokens
* 4K tokens
* 8K tokens
* 16K tokens

---

### RQ2 — Information efficiency

Can the compiler achieve the same evidence recall with materially fewer context tokens?

Primary metric:

`tokens required to achieve target evidence recall`

Example:

Standard RAG:

* 8,000 tokens
* 92% evidence recall

Compiler:

* 4,100 tokens
* 92% evidence recall

This would be a strong result.

---

### RQ3 — Answer quality

Using the same answer model and same answer prompt, does compiled context improve:

* answer accuracy;
* citation/evidence correctness;
* unsupported-claim rate;
* abstention correctness?

---

### RQ4 — Economics

Does the approach reduce:

* input tokens;
* model calls;
* cost per query;
* cost per correct answer;
* latency?

Do not claim economic value from storage savings in v0.

The initial economic thesis is:

> better context selection → fewer tokens/model calls → lower cost and/or better answers.

---

# 3. Systems to compare

Implement four benchmark arms.

## Arm A — Fixed-chunk RAG

This is the conventional baseline.

Pipeline:

`Document → extracted text → 512-token chunks → hybrid retrieval → reranking → token-budget packing`

Configuration:

* target chunk size: 512 tokens
* overlap: 64 tokens
* sparse retrieval: BM25
* dense retrieval: same embedding model as other systems
* fusion: Reciprocal Rank Fusion
* reranker: same reranker used elsewhere
* token-budget-aware final packing

This baseline must be reasonably strong. Do not intentionally make it naive.

---

## Arm B — Structural RAG

Use Docling's document structure and HybridChunker.

Pipeline:

`DoclingDocument → HybridChunker → hybrid retrieval → reranking → token-budget packing`

Keep everything else as close to Arm A as possible.

This is an extremely important baseline.

If:

`Structural RAG ≈ Context Compiler`

then the hypothesis may reduce to:

> better chunking helps.

That would weaken the case for a new infrastructure layer.

---

## Arm C — Long-context baseline

No retrieval or minimal retrieval.

Provide the model with as much relevant source material as fits within a large context window.

Implement this only after Arms A, B and D are working.

Purpose:

Test the objection:

> Modern models have huge context windows, so retrieval infrastructure is becoming unnecessary.

Measure accuracy and economics.

---

## Arm D — IR + Context Compiler

Pipeline:

`Document → DoclingDocument → normalized IR → hybrid candidate retrieval → structural expansion → reranking → deduplication → budget-aware packing`

This is the experimental system.

---

# 4. Technology choices

Use a deliberately simple local stack.

## Language

Python 3.12+

## Package/environment management

Use `uv`.

Commit:

* `pyproject.toml`
* `uv.lock`

## Core libraries

Use:

* Docling — parsing/document structure
* Pydantic — internal models
* Typer — CLI
* NumPy — local dense retrieval
* sentence-transformers — embeddings/reranker
* bm25s — sparse retrieval
* DuckDB — experiment/result analysis
* PyArrow/Parquet — experiment artifacts
* tiktoken or equivalent fixed tokenizer — benchmark token accounting
* pytest — tests
* ruff — formatting/linting

Do not add infrastructure unless justified by benchmark requirements.

Specifically do NOT initially use:

* PostgreSQL
* Elasticsearch
* Qdrant
* Pinecone
* Redis
* Kubernetes
* Docker services

For the first benchmark, brute-force dense cosine search is acceptable.

Scale is not the question yet.

---

# 5. Model choices

All model choices must be configurable.

Recommended default local embedding model:

`BAAI/bge-small-en-v1.5`

or another small, well-supported sentence-transformer if compatibility requires it.

Recommended local reranker:

a compact cross-encoder suitable for running on a Mac.

Do not use an LLM for retrieval planning in v0.

For answer generation, expose a provider interface.

Implement an OpenAI provider first, but keep the benchmark code provider-independent.

Initial evaluation model configurations:

### Cheap evaluation

`gpt-5.6-luna`

### Confirmation run

`gpt-5.6-sol`

Do not hard-code these throughout the application. They belong in experiment configuration.

---

# 6. Repository structure

The implemented repository separates reusable code, benchmark definitions,
canonical public results, and generated local artifacts:

```text
agent-native-content/
├── benchmarks/xl-docbench/subsets/
├── docs/
│   ├── vision.md
│   ├── architecture.md
│   ├── specs/
│   ├── adr/
│   └── research-log/
├── results/
│   ├── retrieval/
│   └── representation/
├── data/
│   ├── raw/
│   ├── cache/
│   └── processed/
├── artifacts/
│   ├── indexes/
│   ├── runs/
│   ├── generation-runs/
│   └── representation-runs/
├── src/agent_native_content/
└── tests/
    ├── fixtures/
    ├── unit/
    └── integration/
```

---

# 7. Raw document representation

Do not replace Docling's representation unnecessarily.

Store the complete serialized `DoclingDocument` as the authoritative parsed artifact.

Then create a much smaller normalized projection for our algorithms.

---

# 8. Minimal IR

The IR must initially contain only information necessary to test structural retrieval.

Example conceptual schema:

```text
IRDocument

id
source_uri
source_sha256
parser_name
parser_version

nodes[]
```

Each node:

```text
IRNode

id
document_id

kind:
    title
    heading
    paragraph
    list
    list_item
    table
    table_chunk
    caption
    figure
    code
    other

parent_id
children_ids

ordinal

text

heading_path[]

page_start
page_end

bounding_boxes[]

source_item_ids[]

token_count
```

For tables optionally preserve:

```text
table:
    caption
    column_headers[]
    rows[][]
```

Do NOT add in v0:

* entities;
* entity graph;
* relationship extraction;
* summaries;
* generated keywords;
* LLM annotations;
* embeddings inside the IR;
* task-specific metadata.

Embeddings are indexes derived from the IR, not part of the canonical representation.

---

# 9. Fundamental IR principle

The IR must preserve the distinction between:

### Source truth

What came from the original document.

### Derived indexes

Embeddings, BM25 statistics, retrieval scores, etc.

The canonical IR must remain valid if tomorrow we change:

* embedding model;
* reranker;
* answer model;
* retrieval algorithm.

---

# 10. Context Compiler v0

Expose one principal API:

```text
compile_context(
    query,
    document_scope,
    token_budget,
    config
) -> ContextPacket
```

The compiler should initially be deterministic.

No LLM planner.

---

# 11. Compiler algorithm v0

## Step 1 — Candidate retrieval

Retrieve independently:

* top N sparse candidates **that match at least one query term**;
* top N dense candidates **whose cosine similarity to the query is strictly
  positive**.

Both channels refuse non-matches before ranking, and N is a ceiling rather
than a quota: a channel returns fewer than N candidates when fewer than N
qualify, and returns nothing when none does. Do not pad a short channel to N.
Padding hands a candidate a rank, and therefore reciprocal-rank-fusion credit,
ordered by chunk ID -- a hash, not relevance. An empty result from both
channels is a legitimate outcome and must propagate as an empty packet; see
`docs/specs/retrieval.md` for the decision and the measurements behind it.

Suggested initial value:

`N = 40`

---

## Step 2 — Fusion

Combine sparse and dense rankings using Reciprocal Rank Fusion.

Keep fusion configuration explicit.

---

## Step 3 — Reranking

Cross-encoder rerank approximately the top 40 combined candidates.

Keep approximately top 12–20 depending on experiment config.

---

## Step 4 — Structural expansion

For selected nodes:

Include structural information where useful.

Rules for v0:

### Headings

Attach heading ancestry as metadata/context.

Do NOT automatically include full parent sections.

Example:

```text
Annual Report
> Results
> Europe
```

### Paragraphs

Optionally include immediate previous/next sibling with a score penalty.

Make this configurable.

### Tables

Always preserve:

* caption;
* column headers;
* relevant table content.

If the table fits the remaining token budget, include it whole.

For oversized tables, initially use Docling's table chunking behavior rather than inventing semantic row extraction.

### Lists

Keep logically adjacent list items together when practical.

---

## Step 5 — Deduplication

Remove duplicate or overlapping evidence using:

* source spans;
* Docling source item IDs;
* normalized text hashes.

Never include identical material twice simply because dense and sparse retrieval both found it.

---

## Step 6 — Budget packing

Pack evidence according to the fixed token budget.

Every included item must carry:

```text
evidence_id
document_id
page
node_id
source location
retrieval score
```

The answer model must be able to cite these IDs.

---

# 12. ContextPacket

Example conceptual representation:

```text
ContextPacket

query
token_budget
token_count

items[]

metadata:
    compiler_version
    retrieval_config
    embedding_model
    reranker_model
```

Each item:

```text
ContextItem

evidence_id
document_id
page_start
page_end

heading_path

content

source_node_ids[]

scores:
    dense
    sparse
    fused
    reranked
```

---

# 13. XL-DocBench support

Implement an XL-DocBench dataset adapter.

The current release references original public source documents rather than redistributing every source file.

The adapter must therefore:

1. load benchmark metadata;
2. download referenced documents;
3. cache downloaded files permanently;
4. calculate SHA-256;
5. record failed URLs;
6. never silently change a document;
7. expose questions and gold evidence through one normalized interface.

Example interface:

```text
BenchmarkQuestion

id
question
document_ids[]
gold_answer
gold_evidence[]
answerable
```

---

# 14. Initial benchmark subset

Do not immediately run all questions.

Create a deterministic 100-question development subset.

Stratify it across:

* single-document;
* cross-document;
* one evidence page;
* multiple evidence pages;
* tables;
* text;
* different professional domains.

Store the selected IDs in version control:

```text
benchmarks/xl-docbench/subsets/xl100.json
```

Never regenerate the sample implicitly.

Use a separate holdout sample before making final claims.

---

# 15. Evidence evaluation

Before using any LLM answer generation, evaluate retrieval itself.

For each query and each system, record:

```text
selected evidence
selected pages
context tokens
gold pages
gold evidence matches
latency
```

Primary metrics:

### Evidence page recall

Fraction of required gold evidence pages represented.

### Full evidence coverage

Boolean:

Did the selected context contain evidence from every required gold evidence page?

### Recall @ token budget

For:

* 2K
* 4K
* 8K
* 16K

### Tokens to full evidence

Minimum number of selected context tokens required to include all gold evidence.

### Redundancy

Approximate proportion of context that duplicates other selected material.

---

# 16. Important fairness requirement

All Arms A, B and D must use the same:

* embedding model;
* sparse retrieval system;
* dense similarity implementation;
* fusion strategy where applicable;
* reranker;
* tokenizer for budget accounting.

The principal experimental variable must be:

> representation and context-selection strategy.

Do not accidentally compare:

“poor RAG model”

against

“better models plus compiler.”

---

# 17. Generation evaluation

Only add answer generation after retrieval evaluation works.

Use exactly the same answer prompt across systems.

Example behavior:

```text
Answer using only the provided evidence.

If the evidence is insufficient, return INSUFFICIENT_EVIDENCE.

Cite evidence IDs supporting each factual claim.
```

Record:

* answer text;
* citations;
* input tokens;
* output tokens;
* provider usage;
* latency;
* model ID;
* reasoning configuration;
* API cost.

---

# 18. Answer metrics

Use benchmark-native deterministic scoring whenever possible.

Record at minimum:

* benchmark accuracy;
* token F1 / appropriate benchmark metric;
* citation support;
* insufficient-evidence accuracy;
* input tokens;
* output tokens;
* calls;
* dollars per query;
* dollars per correct answer;
* response valid rate, and the judge valid rate when a judge is enabled.

A response the provider did not complete is a failed call, not a wrong answer.
Each cell records `response_valid`, the provider's `status` and
`incomplete_reason`, and the same fields for the judge call; each summary row
records the resulting `response_valid_rate` and
`citation_entailment_judge_valid_rate`. Without those rates an arm whose calls
were truncated is indistinguishable from an arm that answered badly.

---

# 19. Gold-evidence compression experiment

Implement this as a separate experiment.

Purpose:

Separate representation quality from retrieval quality.

For each query:

### Condition 1

Gold evidence pages → plain extracted text → answer model.

### Condition 2

Gold evidence pages → IR → context compiler → answer model.

Compare:

* accuracy;
* context tokens;
* citations;
* cost.

This directly tests:

> Does the representation itself communicate the same evidence more efficiently?

If the answer is no, the value is probably in retrieval rather than the IR itself.

That is an important result.

---

# 20. T²-RAGBench

After the first XL-DocBench results, implement T²-RAGBench.

Purpose:

Test whether the result generalizes to:

* financial documents;
* numerical reasoning;
* tables plus text.

Do not optimize specifically for XL-DocBench before running this second benchmark.

---

# 21. Experiment reproducibility

Every benchmark run must write a manifest.

Example:

```text
run_id
timestamp
git_commit
git_dirty

dataset
dataset_revision
question_ids

parser
parser_version

system
system_config_hash

embedding_model
embedding_revision
reranker_model
reranker_revision
answer_model
temperature
seed

tokenizer
token_budget

random_seed

environment info
```

`temperature` and `seed` are the answer model's configured sampling settings,
recorded by every run that calls an answer model: a generation run writes them
as top-level manifest fields, and the representation run carries them inside
its frozen `config` block. `null` records that the setting was not sent at all
and the provider default applied, which is not the same as a value of zero;
many reasoning models reject an explicit temperature. Both are distinct from
`random_seed`, which is the benchmark's own seed.

`embedding_revision` and `reranker_revision` record the exact model weights,
because a model ID alone names a moving branch. A hub-backed model is loaded at
an explicit revision or not at all; the offline deterministic models record no
revision, and their model names say so.

`git_dirty` records whether the worktree differed from `git_commit`. The
check fails closed, so an unknown worktree state, such as one left by a
missing or failing Git executable, is also recorded as dirty. A run
from a modified worktree is refused unless it is explicitly stamped dirty,
and a dirty run is not a reproducible result.

Outputs should be immutable.

Never overwrite an existing completed benchmark run.

---

# 22. Experiment artifacts

Store results as Parquet where convenient.

Suggested files:

```text
artifacts/runs/<run_id>/

manifest.json
queries.parquet
retrieval.parquet
contexts.jsonl
answers.jsonl
metrics.json
summary.json
```

This allows later analysis using DuckDB.

---

# 23. CLI

Provide a usable command-line interface.

Target shape:

```text
agent-native-content dataset download xl-docbench

agent-native-content ingest xl-docbench

agent-native-content index --system fixed-rag

agent-native-content index --system structural-rag

agent-native-content index --system compiler

agent-native-content eval-retrieval \
  --system compiler \
  --subset xl100 \
  --budget 4096

agent-native-content eval-generation \
  --system compiler \
  --subset xl100 \
  --budget 4096

agent-native-content compare <run-a> <run-b> <run-c>

agent-native-content report <run-id>
```

Exact syntax may differ, but functionality should be equivalent.

---

# 24. Reports

Generate CSV/JSON plus a simple Markdown report.

The comparison report should show:

| System | Evidence recall | Full coverage | Context tokens | Answer accuracy | Cost/query | Cost/correct |
| ------ | --------------: | ------------: | -------------: | --------------: | ---------: | -----------: |

Also produce plots for:

### Plot 1

`Evidence recall vs context-token budget`

### Plot 2

`Answer accuracy vs context-token budget`

### Plot 3

`Answer accuracy vs cost/query`

### Plot 4

`Tokens/query distribution`

### Plot 5

Compiler gain/loss by question type.

---

# 25. Required ablations

If Compiler D beats the baselines, identify why.

Run compiler variants with:

### D1

No structural expansion.

### D2

Headings only.

### D3

Headings + sibling expansion.

### D4

Headings + siblings + table preservation.

This prevents attributing improvements vaguely to “the IR.”

### Field settings, and the shipped reference

The four names above do not fix the `CompilerConfig` fields they correspond
to. Those are recorded as data in
`src/agent_native_content/evaluation/ablations.py` and checked by a test, so a
published ablation can be read back without reconstructing it from shell
history. That module also records two decisions this section leaves open:
that “sibling expansion” in D3 includes adjacent list-item grouping, with the
alternative reading and why it was rejected; and that keyed table joins and
page-neighbour windows stay off throughout D1 to D4, since the ladder stops at
table preservation.

The module adds a fifth entry, `SHIPPED`, which is **not** an ablation from
this section. It is the configuration the benchmark actually publishes, and it
lies beyond D4: it adds keyed joins and page neighbours. It is listed because
none of D1 to D4 is the configuration behind any headline number, so a reader
comparing the ladder to a published result without it would be comparing
against something unlisted.

---

# 26. Success criteria

Pre-register these before looking at results.

## Strong technical validation

Any of:

### Criterion A

At least 50% fewer context tokens with no more than 1 percentage point answer-accuracy degradation.

OR

### Criterion B

At least 5 percentage points higher answer accuracy at approximately equal context budget.

OR

### Criterion C

At least 10 percentage points higher full-evidence coverage at the same token budget.

The best result would satisfy two simultaneously.

Example:

`+6 pp accuracy AND -35% input tokens`

---

# 27. Weak result

If improvement is:

* under 10% token reduction;
* under ~2 pp accuracy;
* inconsistent between datasets;

then do NOT describe this as validation of a new infrastructure layer.

It is probably an implementation optimization.

---

# 28. Important kill condition

If:

`Structural RAG ≈ Compiler`

within roughly:

* 2 percentage points answer accuracy; and
* 15% context tokens,

then investigate whether the compiler is merely sophisticated structural chunking.

Do not continue building a platform unless another significant advantage appears.

---

# 29. Second kill condition

If long-context reading produces:

* better accuracy;
* acceptable latency;
* comparable or lower cost;

then the context-compilation thesis is materially weakened.

Document the result rather than changing the benchmark until the compiler wins.

---

# 30. Third kill condition

Run the winning configuration on:

1. development XL-DocBench sample;
2. held-out XL-DocBench sample;
3. T²-RAGBench;
4. at least two answer-model tiers.

If gains disappear outside the development configuration, treat them as benchmark overfitting.

---

# 31. Development sequence

## Milestone 0 — Repository bootstrap

Build:

* Python project;
* uv configuration;
* CLI skeleton;
* ruff;
* pytest;
* AGENTS.md;
* architecture docs;
* CI.

Acceptance:

```text
uv sync
uv run ruff check .
uv run pytest
```

all succeed.

No benchmark code yet.

---

## Milestone 1 — Dataset layer

Implement:

* normalized dataset interface;
* XL-DocBench adapter;
* deterministic xl100 subset;
* source downloader/cache.

Acceptance:

A CLI command can print:

```text
question ID
question
source document IDs
gold answer
gold evidence pages
```

for all xl100 questions.

Tests must not require live network access.

---

## Milestone 2 — Docling ingestion

Implement:

```text
source document
→ DoclingDocument
→ serialized cache
```

Acceptance:

For fixture documents, the pipeline preserves:

* headings;
* paragraphs;
* tables;
* page provenance.

Running ingestion twice must reuse the cache.

---

## Milestone 3 — Minimal IR

Implement:

`DoclingDocument → IRDocument`

Acceptance tests:

* parent/child relationships valid;
* page references valid;
* stable node IDs across repeated builds;
* serialized round-trip reproduces the same IR;
* source hashes preserved.

---

## Milestone 4 — Baselines A and B

Implement:

A. fixed-chunk RAG

B. Docling structural/hybrid RAG

Include:

* dense index;
* BM25;
* RRF;
* reranker;
* budget packing.

Acceptance:

Run retrieval evaluation on at least 10 fixture questions.

Output reproducible selected evidence and token counts.

---

## Milestone 5 — Compiler D

Implement:

* candidate retrieval;
* hierarchy expansion;
* sibling expansion;
* table preservation;
* deduplication;
* budget packing.

Acceptance:

Compiler never exceeds requested context budget.

Every output item is traceable to exact source provenance.

No LLM call is made during compilation.

---

## Milestone 6 — Retrieval benchmark

Run xl100 at:

```text
2048
4096
8192
16384
```

tokens for:

A
B
D

Produce first decision report.

Do NOT add generation before reviewing this result.

---

## Milestone 7 — Generation

Implement answer-provider abstraction and OpenAI provider.

Run one cheap model across A/B/D using exactly the same prompt.

Generate accuracy/cost curves.

---

## Milestone 8 — Confirmation

Add:

* strong model;
* long-context baseline;
* gold-evidence compression;
* ablations;
* T²-RAGBench.

Only after this milestone should we decide whether the technical thesis has meaningful support.

---

# 32–45. Build brief (moved)

Sections 32 to 45 — the AGENTS.md draft, the task-by-task coding-agent brief
and the list of disallowed changes — were moved unchanged to
[`history/original-build-brief.md`](history/original-build-brief.md) on
2026-10-01. They record how the prototype was commissioned and are not current
instructions.

---


# 46. What success looks like

The ideal final result is something like:

```text
XL-DocBench holdout

                         Fixed    Structural   Compiler
Accuracy                 57.1%       60.4%       66.0%
Evidence coverage @4K    61.2%       67.9%       79.4%
Median context tokens    7,620       6,880       4,310
Cost / correct answer    $0.038      $0.034      $0.022
```

These numbers are illustrative only.

A result resembling this would justify building a more general Content IR/context compiler.

---

# 47. What failure looks like

Also consider this a successful research outcome:

```text
Structural RAG:
65.1% accuracy
4,800 tokens

Compiler:
65.8% accuracy
4,600 tokens
```

That would tell us:

> The complicated new layer adds little beyond existing structure-aware chunking.

At that point we should not turn it into a startup simply because the architecture is intellectually appealing.

---

# 48. Product work begins only after technical validation

Only after the benchmark survives the kill criteria should we investigate:

* multiple content types;
* incremental updates;
* persistent Content IR;
* permissions;
* reusable derived representations;
* semantic caching;
* source versioning;
* context APIs;
* enterprise deployment;
* commercial customer datasets.

The prototype should answer:

> Is there a real technical advantage?

before we ask:

> How should the product be architected?
