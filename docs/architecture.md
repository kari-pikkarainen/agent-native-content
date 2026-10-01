# Architecture

This document describes the implemented system boundaries and data flow. The
research questions, success criteria and kill conditions that the architecture
serves are defined in the [benchmark specification](specs/benchmark.md).

The benchmark compares four independent arms while sharing retrieval models,
token accounting, and evaluation machinery wherever fairness requires it. The
canonical parsed document and normalized intermediate representation (IR) are
kept separate from derived retrieval indexes and immutable experiment outputs.

Architecture decisions should favor the smallest implementation capable of
testing the research hypothesis.

## Ingestion boundary

Source documents are immutable inputs identified by SHA-256. The ingestion
layer converts each local PDF into Docling's complete `DoclingDocument` JSON;
this remains the authoritative parsed artifact. A separate metadata record
captures:

- source path, size, and SHA-256;
- Docling and Docling Core versions;
- the complete intentional parser configuration and its SHA-256;
- serialized document SHA-256 and Docling schema version;
- page, text, heading, and table counts.

The cache key is:

```text
source SHA-256 / parser-and-configuration SHA-256
```

A source-byte, parser-version, Docling Core version, model-artifact location,
or pipeline-setting change therefore selects a new cache entry. Cache hits
verify document integrity and structural counts before deserialization. Partial
Docling conversions are rejected rather than cached.

The normalized benchmark IR is a separate deterministic projection from this
artifact. It must not replace or mutate the serialized `DoclingDocument`.

## IR boundary

The IR projection normalizes Docling items into a small validated graph while
preserving source references, hierarchy, heading context, tables, page boxes,
and token counts. Document and node identities derive from immutable source
identity and Docling references, making repeated builds stable. Canonical JSON
round-trips through the same validation rules.

The IR contains source truth only. Embeddings, lexical statistics, retrieval
scores, generated annotations, and later experiment outputs are derived state
and remain outside it. See the [Content IR specification](specs/content-ir.md)
for the normative schema.

An optional agent-document layer derives query-independent affordances without
mutating the IR. Its outline, extractive section previews, key facts,
definitions, and table schemas retain node/item/page provenance and are
published as JSON-LD (JSON for Linked Data) plus semantic HTML. This layer is
versioned and replaceable; see the [agent-ready content
specification](specs/agent-document.md).

The first two retrieval arms consume that IR through a shared local hybrid
stack. Fixed windows and Docling HybridChunker structural chunks are indexed
separately under deterministic content/config hashes, while BM25 lexical
search, dense search, reciprocal-rank fusion (RRF), reranking, and budget
packing remain identical. See the [retrieval specification](specs/retrieval.md)
for the baseline contract.

## Compiler boundary

Arm D indexes content-bearing IR nodes through the shared hybrid retrieval
stack, then performs deterministic structural expansion before packing. Heading
paths add context without pulling full parent sections; paragraph siblings and
adjacent list items are controlled explicitly; tables remain whole or fall back
to reranked Docling fragments with repeated caption/header context. Queries that
explicitly reference multiple tables may also produce compact, provenance-
preserving row joins on exact normalized model/dataset identifiers.

Query-independent compiler state is derived once per corpus: node and sibling
lookups, fixed page windows, table-label continuations, and exact-key row
postings. Query faceting retrieves the same bounded candidate pools as before,
but all full-query and facet pairs are submitted to the shared cross-encoder in
one batch. Persisted retrieval indexes are reused only after their chunks,
configuration, model versions, tokenizer version, and vector shape validate.

Deduplication uses normalized content plus exact source IDs and bounding boxes.
Final rendered evidence is recounted and greedily packed under a hard token
budget. Every output maps back to IR nodes and authoritative Docling item IDs.
See the [context compiler specification](specs/context-compiler.md) for the
normative behavior.

## Evaluation boundary

The evidence-only evaluator builds one index per A/B/D arm over the complete
retrieval corpus and projects Arm C into source-ordered body chunks without an
index. The corpus defaults to the evaluation subset but may be a declared
parent subset for small diagnostics. Every arm is filtered to the document IDs
authorized by that question. Index creation, Arm C projection, and model
loading remain outside query latency.
Each selected item is mapped from IR document and node IDs back to dataset
document IDs and exact PDF pages before page recall, coverage, tokens-to-full,
and redundancy are calculated.
When the dataset supplies evidence quotes, the evaluator also records exact
normalized quote recall and full quote coverage. This stricter diagnostic helps
distinguish compact row-level evidence from coincidental coverage of a broadly
annotated page.

An opt-in compiler-stage audit snapshots immutable candidate pools at raw node
retrieval, faceted fusion, structural expansion, and deduplication, then
compares them with final packing and structural retrieval. It also records the
union of faceted compiler and structural candidates. This diagnostic path uses
the same indexes, document filters, maximum retrieval budget, and compiler
implementation as the scored run; it does not alter selected evidence.

Runs are assembled in a temporary sibling directory and atomically renamed to
their final immutable `artifacts/runs/<run-id>` location. The manifest binds the
results to the Git commit, pinned dataset, evaluation and retrieval-corpus
subsets, source hashes, parser versions, complete configuration,
model/tokenizer versions, seed, and ordered question IDs. Raw contexts remain
available for failure analysis; the JSON and Markdown summaries are derived
from the per-cell records. See
[evaluation protocol](specs/evaluation.md) for metric definitions and
the first decision gate.

The separate factorial evaluator reuses the same fixed, structural, and IR-node
indexes but crosses each content unit with ranked single-query retrieval and
faceted coverage-aware retrieval. It performs common provenance deduplication
and deliberately omits structural compiler operators. Its immutable outputs
live under `artifacts/factorial-runs/<run-id>/`; see the
[factorial specification](specs/factorial.md).

## Generation boundary

Answer generation reads immutable `contexts.jsonl` packets rather than running
retrieval again. A provider-neutral interface receives one fully rendered
prompt and returns answer text plus provider-reported usage. Every arm in a run
shares the exact prompt template, requested model, reasoning setting, output
limit, deterministic benchmark scorer, and explicit pricing metadata.

The OpenAI adapter is optional and uses the Responses API. The runner requires
strict JSON containing an answer and evidence-ID citations; invalid responses
score zero rather than being repaired. It records native XL-DocBench relaxed
accuracy, token F1, average normalized Levenshtein similarity (ANLS), citation-
ID validity, abstention correctness, tokens, latency, and dollars per
query/correct answer. Completed artifacts are atomically published under
`artifacts/generation-runs/<run-id>/` and bind the results to hashes of the
source retrieval manifest and contexts.

The separate gold-evidence representation runner bypasses retrieval entirely.
It precomputes agent enrichment once per document, fixes the authorized source
nodes from released evidence pages, and renders RAW, IR, ENRICHED and INDEXED
prompts over those identical nodes. An opt-in QUESTION_ONLY control renders no
evidence at all. Optional same-model judges add a representation-blind
semantic answer-equivalence score, kept separate from deterministic accuracy,
and a citation-entailment score that never judges an abstention; the
provider-call ceiling counts every enabled judge for every cell. Answer-call
efficiency (tokens, latency, cost) is recorded separately from judge overhead
and from all-call totals, so judges do not confound the representation
comparison. Its immutable contexts and results live under
`artifacts/representation-runs/<run-id>/`. Provider completion and parsing are
reported separately from answer correctness: failed calls retain their usage
and diagnostics, score zero, and contribute to a per-condition valid-response
rate.
