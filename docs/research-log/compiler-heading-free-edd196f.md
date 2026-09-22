# Ablation: removing heading context from compiler node search

Date: 2026-09-22

Precommit: `edd196f`

Canonical run: `xldev24-headingfree-edd196f`, published under
[`results/`](../../results/README.md) as `xldev24-compiler-headingfree`.

Baseline for every comparison here: `xldev24-rebaseline`, the Gate 0
development run at `e28b247`.

## Question

The [Gate 0 decision](gate0-rebaseline-67aef47.md) recorded a heading tax: in
the matched factorial, heading search context cost the IR unit between 2 and 5
points of page recall at every budget. It named removing that trail as one of
Phase 1's cheapest available improvements.

This run tests that directly, on the full retrieval pipeline rather than the
factorial harness. `edd196f` split the single `heading_search_context` switch
into `structural_heading_search_context` and
`compiler_node_heading_search_context`, so the compiler can be measured
heading-free while the structural baseline is left exactly as Gate 0 published
it. Both still default to on; this run sets only the compiler's to off.

The acceptance rule was fixed before the run: **adopt only if page recall
improves without reducing exact quote recall.**

## Arm isolation

The `fixed`, `structural` and `long_context` arms are bit-identical across the
two runs on every recall metric at every budget, maximum absolute difference
`0.00e+00`. The split does what it claims: nothing outside the compiler moved.

## Result

Compiler arm, heading context off minus on. Page and content-verified recall
are over the 18 answerable questions with an annotated gold page; quote recall
is over the 18 quoted-eligible questions.

| Budget | page | content-verified | quote |
| ---: | ---: | ---: | ---: |
| 2K | **+0.0232** | **+0.0232** | **+0.0185** |
| 4K | **+0.0336** | **+0.0336** | **+0.0417** |
| 8K | **+0.0357** | **+0.0357** | **−0.0370** |
| 16K | **+0.0162** | **+0.0162** | **−0.0370** |
| mean | +0.0272 | +0.0272 | −0.0035 |

Page recall improves at all four budgets, confirming the factorial's heading
tax on the full pipeline and at a comparable magnitude. Quote recall splits:
it gains at 2K and 4K and loses 3.7 points at 8K and 16K.

**The acceptance rule is not met.** The change is not adopted. The default
stays on.

Secondary effects, recorded but not decisive: mean retrieval latency falls 4 to
7 per cent at every budget, and mean redundancy falls between 0.013 and 0.032.
Both follow from the shorter indexed string and the wider dedupe scope.

## What the quote regression actually is

The summary figure overstates its own generality. At 16K only **2 of 18**
quoted-eligible questions change at all, and one of them accounts for the whole
loss:

| Budget | question | quote recall | page recall |
| ---: | --- | --- | --- |
| 8K | `adubench_single_000266` | 1.000 → **0.000** | 1.000 → 1.000 |
| 8K | `adubench_single_000817` | 1.000 → 0.500 | 1.000 → 1.000 |
| 8K | `adubench_single_000503` | 0.000 → 0.333 | 0.900 → 0.900 |
| 8K | `adubench_single_000505` | 0.000 → 0.500 | 0.600 → 0.800 |
| 16K | `adubench_single_000266` | 1.000 → **0.000** | 1.000 → 1.000 |
| 16K | `adubench_single_000503` | 0.000 → 0.333 | 0.900 → 1.000 |

At 16K, `(−1.000 + 0.333) / 18 = −0.0370` reproduces the reported delta
exactly. One question is the result.

`adubench_single_000266` is the informative case. Pages 13 and 14 of
`doc_000134` are its gold pages, and **both runs select both pages** —
`matched_pages` is identical and page recall is 1.000 either way. What changes
is which node on those pages is packed: 45 of 54 evidence ids are shared at
16K, and the heading-free run swaps a sibling in. The exact quoted span sits in
the node it drops.

So this is not a targeting failure. Heading-free search does not wander to the
wrong pages; it lands on the right page and selects a node that does not
contain the quote. That is the node-boundary problem the Gate 0 log recorded in
the factorial, now visible as a single-question swing large enough to reverse a
summary metric on an 18-question set.

## Decision

Rejected under the stated rule, and the rule is kept rather than relaxed after
seeing the number. Relaxing it here would be choosing the criterion from the
result.

But the finding should not be recorded as "heading removal costs quote recall".
It is not supported at that strength by two changed questions out of eighteen.
The defensible statement is narrower:

- The heading tax on **page recall** is real, reproduced outside the factorial,
  and consistent across budgets.
- Whether removing heading context costs **quote recall** is not resolved by
  this run. `xldev24` cannot resolve it: the effect lives in one or two
  questions, well inside what 18 questions can distinguish from noise.

The Gate 0 log's forward-looking claim — that heading removal is one of Phase
1's cheapest available improvements — is therefore withdrawn as premature. It
was stated on page recall alone, which is the reading Phase 1's joint-metric
rule exists to prevent.

The configuration remains reachable and measured. It is not the shipped
default, and it should be revisited only alongside a fix for node-boundary
granularity, which is what would make `adubench_single_000266` stop depending
on which sibling is packed.

## Known weaknesses

- One development set, 24 questions, 18 eligible on each metric. No interval is
  reported for these deltas because the paired bootstrap over 18 questions
  would not separate a two-question effect from zero, and reporting one would
  lend the number more authority than it has.
- Page and content-verified recall move identically to four decimals at every
  budget here. On this subset they are not independent metrics.
- The run is compiler-only. The structural arm's heading behaviour is unchanged
  and untested by this ablation.
