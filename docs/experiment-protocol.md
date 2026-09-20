# Retrieval Experiment Protocol

This protocol is fixed before inspecting the first XL100 retrieval results. It
tests evidence selection only: no answer-generation model, LLM planner, or
generated answer metric participates in this milestone.

## Development dataset

Milestone 1 pins the conservative XL-DocBench release as follows:

- dataset: `microsoft/XL-DocBench`
- release: `xldocbench_strict_1345_v1`
- revision: `72954bd70ffffe230f08b57c57fa9274ec14d7ea`
- evidence pages: one-based PDF/release indices

The tuning subset is the explicit ordered list in
`configs/subsets/xldev24.json`. It contains 24 questions selected only from
release metadata and source-availability checks: four single-document questions
per domain, including six unanswerable and six table/chart/image questions. It
is disjoint from XL100. The selection minimizes added source bytes after
satisfying its quotas so development runs remain practical. Cross-document
questions remain in the held-out XL100 evaluation rather than expanding the
development corpus with dozens of additional and frequently stale mirrors.

`configs/subsets/xl100.json` remains the held-out final retrieval evaluation:
100 questions balanced across all six domains, including 80 single-document
and 20 cross-document questions. The earlier XL10 smoke subset has already
informed implementation decisions and is therefore only a regression set, not
a final evaluation set. Benchmark commands load every committed list exactly
as stored and never regenerate one implicitly.

The command downloads only the pinned metadata release and the source PDFs
referenced by the selected subset. Each PDF is size-checked against the release record,
content-addressed, parsed through the local Docling pipeline, and projected to
the deterministic IR. A manifest records the subset hash and each source and
parser identity.

## Systems and controlled variables

The comparison includes:

- `fixed` (Arm A): 512-token windows with 64-token overlap;
- `structural` (Arm B): Docling HybridChunker structural chunks;
- `compiler` (Arm D): IR-node retrieval, deterministic structural expansion,
  provenance-aware deduplication, and budget packing.

All three systems share the same tokenizer, BM25 parameters, brute-force dense
similarity, embedding model, reciprocal-rank fusion parameters, candidate
limits, and reranker. The compiler's structural expansion and packing policy is
the treatment under test. Indexes are built once before query timing and are
filtered to the exact source-document scope of each question.

The preregistered budgets are 2,048, 4,096, 8,192, and 16,384 tokens. The CLI
defaults to `BAAI/bge-small-en-v1.5` and
`cross-encoder/ms-marco-MiniLM-L-6-v2`; both model IDs are configurable and the
resolved IDs and implementation versions are recorded. The seed is recorded
even though the current evaluation path contains no randomized operation.

## Per-cell records

Every question × system × budget cell records:

- selected evidence IDs and the complete serialized context packet;
- selected, gold, and matched one-based PDF pages by dataset document ID;
- exact packed token count;
- retrieval/compilation latency in milliseconds;
- evidence-page recall and full-evidence coverage;
- tokens to full evidence, when full coverage is reached;
- approximate context redundancy.

Evidence-page recall is `matched gold pages / gold pages`. Full coverage means
every required `(document ID, page)` pair occurs in the selected evidence. A
question with no annotated gold pages has vacuous recall `1.0`, full coverage
`true`, and tokens-to-full `0`; this convention applies identically to all
systems and must be disclosed when interpreting absolute averages.

Tokens-to-full is the cumulative item-token count at the earliest ranked
context prefix covering every gold page. It is null when the budget never
achieves full coverage. Its reported median is over successful cells only and
must be read together with full-coverage rate.

Redundancy is the fraction of word-token positions covered by a repeated
four-token n-gram previously seen in another selected item. It is an
approximation, not semantic redundancy. Latency includes query embedding,
sparse/dense search, fusion, reranking, and packing or compilation. It excludes
dataset loading, PDF parsing, IR projection, model loading, and index building.
The runner computes one ranking per question and system at the largest declared
budget, then reuses it for every packing budget. Each cell's latency includes
the full shared retrieval cost plus that cell's packing or compilation cost.

## Outputs and immutability

One run is atomically published under `artifacts/runs/<run-id>/` only after all
cells and files are complete. An existing run ID is never overwritten.

```text
manifest.json       dataset, source/parser provenance, git SHA, full configs,
                    model/tokenizer identities, seed, budgets, question IDs
retrieval.jsonl     one metric record per question/system/budget cell
contexts.jsonl      the corresponding complete context packets
summary.json        aggregate rows by system and budget
report.md           human-readable table and evidence-only decision deltas
```

Derived indexes live under `artifacts/indexes/<sha256>/`; their key includes
source/chunk identities, retrieval configuration, and resolved model and
tokenizer versions.

Run the registered experiment with:

```shell
uv sync --extra retrieval
uv run --extra retrieval contextbench eval-retrieval
```

The command reuses verified source and ingestion caches. Use `--run-id` for an
explicit immutable identifier, `--docling-artifacts-dir` for pre-fetched parser
models, and the model options to override the registered defaults. Progress is
written to stderr; stdout contains a final JSON object naming the run directory,
Markdown report, and JSON summary.

## First decision gate

Development stops before generation. Inspect page-recall and full-coverage
curves against actual packed tokens, plus redundancy and tokens-to-full. The
compiler should be materially up and left of both baselines: higher evidence
coverage at fixed budget or comparable coverage with fewer tokens.

If the compiler only matches structural RAG, the result supports better
chunking rather than a new IR/compiler layer. If it fails to beat fixed RAG,
diagnose retrieval, expansion, provenance mapping, and packing from the saved
contexts before changing algorithms. Do not add an LLM planner to rescue weak
retrieval results.
