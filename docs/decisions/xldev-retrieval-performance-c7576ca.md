# XLDev retrieval performance decisions through `c7576ca`

## Scope

All tuning used development questions only. The two-question table diagnostic
used `configs/subsets/xldev2-tables.json`; the cross-domain diagnostic used
`configs/subsets/xldev6-perf.json`. Both declared `configs/subsets/xldev24.json`
as the fixed 11-document retrieval corpus. XL100 and the holdout subset were not
inspected.

Latency is directional because repeated local cross-encoder runs showed thermal
variance. Selection equality and evidence metrics are the quality gate.

## Selected changes

### Batched facet reranking (`8f7ffdc`)

The control `xldev2-perf-baseline-f9c62a7` reranked the full query and every
facet in separate model calls. Run `xldev2-batched-facets-8f7ffdc` submitted the
same query-candidate pairs in one batch. All recall, coverage, token, and
redundancy values were identical. Mean compiler latency fell 13–17% across the
four budgets (about 0.7–0.85 seconds).

### Verified persisted indexes (`d2b18fc`)

The runner now loads a content/config/model-verified index artifact instead of
re-embedding unchanged chunks. The same two-question command fell from roughly
eight minutes during repeated index construction to 90.5 seconds with cached
indexes. Index creation remains outside recorded query latency.

### Page-neighbor prelimit (`339af56`)

Fixed windows are distance/rank bounded before reranking. The two-question run
`xldev2-page-prerank-339af56` produced identical contexts. Its documents did not
exceed the 64-window final capacity, so it did not demonstrate a speedup; the
change is retained as a worst-case bound.

### Vectorized scoped dense search (`63a2d72`)

Run `xldev2-vectorized-dense-63a2d72` produced identical non-latency records in
all 24 question/system/budget cells. Compiler timing improved by about 0.1
seconds, below run-to-run variance. Document-to-index maps now avoid scanning
the complete chunk list for every scoped query.

### Corpus and table indexes (`478b733`, `a151676`)

Node maps, sibling adjacency, fixed page windows, table labels, continuation
maps, and exact-key table rows are now derived once outside query timing. Runs
`xldev2-corpus-index-478b733` and `xldev2-table-index-a151676` preserved every
selected context. The latter recorded about 2.9 seconds compiler latency at
4–16K, versus 5.8–6.0 seconds in the prior run, but thermal variance prevents
assigning the entire delta to this change.

## Rejected defaults retained only as ablation controls

### Single-pass facet reranking (`17fd45a`)

Reranking one fused 250-candidate pool reduced compiler latency by about 45%,
but `xldev2-single-pass-facets-17fd45a` lost 0.070 recall at 8K and 0.045 at
16K. Batched semantics remain the default.

### Compiler candidate caps (`e5ff569`, `1ca7d1b`)

On the six-question cross-domain slice, a 128-candidate global cap reduced mean
recall by roughly 0.05–0.06 and reduced full coverage at multiple budgets. A
96-candidate cap was worse. Capping only supplemental facets at 96 still lost
0.022–0.043 recall at 2–4K. Both full-query and facet defaults therefore remain
250; CLI controls remain available for future ablations.

## Additional instrumentation

Commit `c7576ca` adds exact normalized quote coverage alongside page coverage.
This addresses the known weakness of broad page-level gold labels for compact
rows and joins. New runs report both metrics; historical artifacts remain
immutable.
