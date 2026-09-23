# Context Compiler Specification

Status: implemented compiler version `0.7.0`.

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
table joining, retrieval-unit merging, and the maximum expanded candidate count
with its optional token-mass floor.

## Pipeline

### 1. Node candidates

Every content-bearing IR node becomes one retrieval chunk. List container nodes
are omitted because their list items carry the evidence. Each candidate keeps
its IR node ID, Docling source item IDs, heading path, page range, and exact
token count.

#### Retrieval-unit merging (optional, off by default)

Some documents are shredded into thousands of tiny nodes: on the cached
`xldev24` document behind `adubench_single_001102`, `000440` and `000441`, all
17,435 body nodes are paragraphs under one heading path, with a median of
5 tokens. The IR is correct to keep them apart, but one node is then too small
to be a retrieval unit. With `node_merge_enabled=true`, `merge_node_units`
(`compiler/candidates.py`) joins such nodes into larger units after the node
candidates above are built. The IR, its node set and its node IDs are not
touched; the fixed and structural arms read none of this.

The rule is deterministic and query-independent: one left-to-right pass over
a document's node candidates in reading order. A node joins the open run only
if all of these hold:

- its kind is `paragraph` or `list_item`, and it has a page range;
- it is under `node_merge_min_tokens` (64) on its own;
- its `heading_path` equals the run's exactly;
- the run with it covers at most `node_merge_max_page_span` pages (1: one
  page);
- the joined text, members separated by a newline, stays within
  `node_merge_max_tokens` (256).

Any other candidate between two tiny nodes closes the run: a heading, table,
caption, code or `other` node, or a node at or above the minimum, which stays
alone. A run also closes once it reaches `node_merge_target_tokens` (128). A
run of one node, which is a tiny node with no mergeable neighbour, is emitted
as the unchanged one-node candidate and is never dropped. None of the four
values is tuned. 64 and 256 are the initial bounds, and 128 lies between them.

A merged unit's `source_node_ids` are its members in reading order. Its
`source_item_ids` are the members' items in reading order, each kept at its
first occurrence. Its page range runs from the members' first page to their
last. Every member's bounding boxes stay reachable through its node ID. Its
ID is `sha256("compiler-merged-v1\0" + json([document, node_ids, text]))`.
That preimage can never equal a one-node preimage, which starts with
`compiler-node-v3`. One-node IDs are unchanged whether merging is on or off.
Merged chunks change the compiler's derived-index key through its chunk
content digest, so merged and unmerged indexes never share a cache entry.
Enabling merging with nothing small enough to merge leaves the chunks, and
the key, identical.

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
can be enabled independently. Both are **on by default** since the Phase 1
freeze at `19bf05e`, where they were measured as the expansion operator that
recovers exact quoted evidence. Siblings must share the same parent and heading
path. Their fused and reranked scores receive the configured penalty; the
sibling's own text is not scored, so its `reranked` value is the anchor's,
shrunk by that penalty.

A merged unit is rendered whole under its shared heading trail. Siblings and
list neighbours are taken exactly as above, but only outward: previous
neighbours of its first member and next neighbours of its last. Every member
lies between those two in reading order, so no member is ever re-added as a
neighbour of its own unit.

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

When the pool contains a merged unit, one more rule applies. A node-evidence
candidate (direct retrieval, sibling or list neighbour) is dropped if any of
its nodes is already in a kept node-evidence candidate. Without it, a sibling
that is a member of another retrieved unit could appear alone and again
inside that unit, because the unit's source-item set is a union and so never
equals the sibling's. The rule is gated on a merged unit being present, so a
pool without one is deduplicated exactly as before.

The deduplicated pool is then cut to `max_expanded_candidates` (500).
`expanded_candidate_token_mass_multiple` (default `None`, meaning the count
cap alone, as before) puts a token-mass floor under that cut. The count cap
cuts only once the kept candidates' rendered cost has reached the multiple
times the token budget. Rendered cost is content tokens plus per-item framing
under the run's budget accounting. A pool of tiny candidates therefore cannot
run out before the budget is spent. The floor only lengthens the prefix the
count cap keeps and never removes a candidate.

### 6. Budget packing

The compiler greedily packs deduplicated evidence in ranked order. Token counts
are recomputed from the final rendered content, including heading and table
prefixes. An item is skipped if adding it would exceed the requested budget;
later smaller items remain eligible.

The selected `coverage` strategy greedily rewards marginal query-term, query-
facet, named-table, page, and heading coverage while retaining reranker rank as
a relevance prior. It never exceeds the token budget and records the selected
strategy in packet metadata. The prior `ranked` strategy remains available as
an explicit control.

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
- all supporting IR node IDs (every member, in reading order, for a merged
  unit);
- all supporting Docling source item IDs;
- dense, sparse, fused, and reranked scores.

The packet metadata records the compiler version, full configuration hash,
embedding model, reranker model, and tokenizer.

It also records the packing strategy and the specialized operators actually
present in the packet. Query faceting requires a splittable complex query;
keyed joining requires at least two explicit table references and a valid exact
join; page-neighbor backfill requires the configured large budget and unused
core capacity.

## Determinism and exclusions

Stable IR identity, deterministic indexes, explicit tie-breaking, canonical
configuration hashing, source-based deduplication, and greedy packing make
repeated compilation identical for the same inputs and model implementations.

Compiler v0 has no LLM planner, query rewriting, generated summary, entity
graph, fuzzy entity matching, or full-parent-section expansion.
