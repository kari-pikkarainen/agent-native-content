# Context Compiler v0 Specification

Status: implemented compiler version `0.5.0`.

The context compiler is benchmark Arm D. It consumes canonical IR documents
and produces a deterministic, citation-ready `ContextPacket` for one query. It
does not call an LLM.

## API

```python
compile_context(
    query,
    document_scope,
    token_budget,
    config,
) -> ContextPacket
```

`document_scope` accepts either a sequence of `IRDocument` values or a
`DocumentScope`. The latter can also carry the authoritative Docling documents
needed to split oversized tables. Optional tokenizer, embedding, and reranker
objects may be injected for controlled experiments and offline tests.
Callers evaluating several packing budgets may also pass one precomputed
`ranked_evidence` sequence; the compiler validates its document scope and still
performs budget-dependent structural expansion and packing independently.

`CompilerConfig` contains the nested shared `RetrievalConfig` plus every
structural decision: heading rendering, previous/next paragraph expansion,
sibling penalties, list grouping, table preservation and chunk size, keyed
table joining, and the maximum expanded candidate count.

## Pipeline

### 1. Node candidates

Every content-bearing IR node becomes one retrieval chunk. List container nodes
are omitted because their list items carry the evidence. Each candidate keeps
its IR node ID, Docling source item IDs, heading path, page range, and exact
token count.

### 2. Shared hybrid retrieval

Candidate nodes use the same BM25, dense cosine search, Reciprocal Rank Fusion,
and reranker implementations as baseline Arms A and B. Candidate limits, model
names, tokenizer, BM25 parameters, and RRF constant come from the nested
`RetrievalConfig`.

Deterministic query faceting, enabled by default, splits complex questions at bounded
punctuation and conjunction boundaries after removing common question
scaffolding. Each facet uses the same sparse, dense, fusion, and cross-encoder
stack as the full query. Weighted reciprocal-rank fusion combines the full and
facet rankings back to the original ranking capacity; the full query receives
the configurable `query_facet_full_weight`. Setting
`query_faceting_enabled=false` restores full-query-only retrieval. No LLM or
generated query is used.

### 3. Structural expansion

Heading ancestry is retained as metadata and, by default, rendered before the
evidence text:

```text
Annual Report
> Results
> Europe

Evidence text
```

The compiler does not include entire parent sections.

For a selected paragraph, the immediate previous and next paragraph siblings
can be enabled independently. Siblings must share the same parent and heading
path. Their fused and reranked scores receive the configured penalty.

For a selected list item, adjacent items under the same list parent are included
up to `list_neighbor_limit`. Distance compounds the configured list penalty.
Because cross-encoder logits may be negative, penalties scale positive scores
toward zero and negative scores away from zero so expansion can never outrank
the direct hit merely because its score has a negative sign.

At larger budgets, multi-scale page-neighbor expansion can treat the
highest-ranked node hits as anchors and rerank bounded fixed-token windows whose
page spans fall within `page_neighbor_radius`. The selected defaults use a
three-page radius at 16,384 tokens and above; setting the radius to zero disables
the feature. Expansion is bounded by both origin and candidate limits. It runs
only when unique core candidates cannot fill the requested budget, and its
windows are ranked after core evidence so they backfill unused capacity instead
of displacing direct hits. The emitted windows retain every source node and
source item used to derive them.

When several budgets are compiled for the same query, a query-scoped cache may
reuse deterministic page-window and keyed-table-join rankings. Cache identity
binds the query, source documents, ranked node evidence where applicable, and
the relevant compiler configuration; attempted reuse for different inputs
fails explicitly. Budget-dependent table handling, deduplication, and packing
still execute independently for every requested budget.

### 4. Tables

A table is kept whole whenever its rendered content fits the total request
budget. Its caption, column headers, and logical rows come directly from the IR.

When a whole table is larger than the request budget and the authoritative
Docling document is available, the compiler uses Docling `HybridChunker`. It
reranks the resulting fragments against the query, then prefixes every fragment
with any missing source caption and column headers. The compiler does not invent
semantic row extraction. If the mandatory caption/header context cannot fit, no
partial table is emitted.

When a query explicitly names at least two tables, keyed table joining is
enabled by default. Source table labels are propagated only across matching
continuation schemas. Model- or dataset-identifier columns provide conservative
identifier candidates, and rows join only on exact normalized identifiers.
Explicit blank/empty constraints must match the query-named column. The emitted
candidate contains the key and query-relevant columns, keeps both table nodes
and their Docling item IDs, and is reranked with the shared reranker. At most one
candidate is retained per normalized entity key. No fuzzy matching or generated
entity annotation is used. The policy can be disabled with
`keyed_table_join_enabled=false`.

Joined sources on non-contiguous pages use null page-range metadata rather than
claiming an artificial continuous span. Their exact pages remain recoverable
from the retained IR source node IDs.

### 5. Deduplication

Candidates are considered in their deterministic expanded rank order.
Duplicates are removed using:

- normalized text hashes;
- identical Docling source item sets;
- identical source bounding-box sets;
- contained normalized text on overlapping pages.

Different Docling fragments of one oversized table may share a source item ID;
they remain eligible because their text is different.

### 6. Budget packing

The compiler greedily packs deduplicated evidence in ranked order. Token counts
are recomputed from the final rendered content, including heading and table
prefixes. An item is skipped if adding it would exceed the requested budget;
later smaller items remain eligible.

`ContextPacket.token_count` is the sum of the returned evidence-content token
counts and is validated to be no greater than `token_budget`. Prompt-template
or answer-model system-message overhead is outside this evidence budget and
must be measured separately by generation experiments.

## Output provenance

Every `ContextItem` contains:

- a deterministic evidence ID;
- document ID and source page range;
- heading path;
- final rendered content and token count;
- all supporting IR node IDs;
- all supporting Docling source item IDs;
- dense, sparse, fused, and reranked scores.

The packet metadata records the compiler version, full configuration hash,
embedding model, reranker model, and tokenizer.

## Determinism and exclusions

Stable IR identity, deterministic indexes, explicit tie-breaking, canonical
configuration hashing, source-based deduplication, and greedy packing make
repeated compilation identical for the same inputs and model implementations.

Compiler v0 has no LLM planner, query rewriting, generated summary, entity
graph, fuzzy entity matching, or full-parent-section expansion.
