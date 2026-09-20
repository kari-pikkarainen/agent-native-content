# Architecture

This document will describe the implemented system boundaries and data flow.
The authoritative target architecture is currently defined in
[`benchmark-spec.md`](benchmark-spec.md).

The benchmark will compare four independent arms while sharing retrieval
models, token accounting, and evaluation machinery wherever fairness requires
it. The canonical parsed document and normalized IR will remain separate from
derived retrieval indexes and immutable experiment outputs.

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
and remain outside it. See [`ir-spec.md`](ir-spec.md) for the normative schema.

The first two retrieval arms consume that IR through a shared local hybrid
stack. Fixed windows and Docling HybridChunker structural chunks are indexed
separately under deterministic content/config hashes, while BM25, dense search,
RRF, reranking, and budget packing remain identical. See
[`retrieval-spec.md`](retrieval-spec.md) for the baseline contract.

## Compiler boundary

Arm D indexes content-bearing IR nodes through the shared hybrid retrieval
stack, then performs deterministic structural expansion before packing. Heading
paths add context without pulling full parent sections; paragraph siblings and
adjacent list items are controlled explicitly; tables remain whole or fall back
to reranked Docling fragments with repeated caption/header context.

Deduplication uses normalized content plus exact source IDs and bounding boxes.
Final rendered evidence is recounted and greedily packed under a hard token
budget. Every output maps back to IR nodes and authoritative Docling item IDs.
See [`compiler-spec.md`](compiler-spec.md) for the normative behavior.

## Evaluation boundary

The evidence-only evaluator builds one index per A/B/D arm over the complete
subset corpus, then filters every retrieval call to the document IDs authorized
by that question. Index creation and model loading remain outside query latency.
Each selected item is mapped from IR document and node IDs back to dataset
document IDs and exact PDF pages before page recall, coverage, tokens-to-full,
and redundancy are calculated.

Runs are assembled in a temporary sibling directory and atomically renamed to
their final immutable `artifacts/runs/<run-id>` location. The manifest binds the
results to the Git commit, pinned dataset/subset, source hashes, parser
versions, complete configuration, model/tokenizer versions, seed, and ordered
question IDs. Raw contexts remain available for failure analysis; the JSON and
Markdown summaries are derived from the per-cell records. See
[`experiment-protocol.md`](experiment-protocol.md) for metric definitions and
the first decision gate.
