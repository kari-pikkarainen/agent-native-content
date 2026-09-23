# Phase 1 close-out: the frozen configuration and the Gate 1 pins

Date: 2026-09-23

Precommit: `c7e56fa`

Canonical run: `xldev24-frozen-c7e56fa`, published under
[`results/`](../../results/README.md) as `xldev24-phase1-frozen`. The decision
evidence behind it is the four-cell run published as `xldev24-freeze-*`.

This record freezes the Phase 1 configuration on development evidence only and
fixes everything `xlholdout6c` will be run against. **The holdout has not been
run.** It stays untouched until the owner approves it.

## The frozen configuration

Siblings **on**, page neighbours **on**. Everything else is the configuration
the benchmark already shipped: headings on, list-item grouping on, table
preservation on, keyed table joins on, `coverage` packing, query faceting on.
The freeze changed two defaults, `include_previous_sibling` and
`include_next_sibling`, from off to on, at `19bf05e`.

### Why siblings

A two-by-two over siblings and page neighbours, keyed joins on throughout,
scored under quote policy v2:

| cell | quote 2K | 4K | 8K | 16K | -3pp margin | 16K page |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| siblings off, neighbours off | .185 | .278 | .347 | .403 | 7/8 | 0.8507 |
| siblings off, neighbours on (previous default) | .185 | .278 | .347 | .417 | 8/8 | 0.8749 |
| siblings on, neighbours off | .199 | .319 | .361 | .417 | **7/8** | 0.8406 |
| **siblings on, neighbours on** | .199 | .319 | .361 | .417 | **8/8** | 0.8507 |

Main effects over the four budgets: sibling expansion **+0.0191** quote recall
and −0.0026 page recall; page neighbours **+0.0017** quote recall and +0.0043
page recall. Siblings carry the quote-recall gain. The two substitute at 16K
rather than complementing: either alone reaches the same quote recall there,
and page neighbours do nothing at the other three budgets.

The main effects were identical under quote policy v1 and v2, so the metric
change moved levels and not the decision.

### Why page neighbours are kept

Siblings on with neighbours off has identical quote recall at every budget but
**fails the preregistered −3pp non-inferiority margin** against fixed RAG at
16K, lower bound −0.0610: removing the neighbours costs 16K page recall.
Keeping them satisfies the margin. Their only cost is the 628 ms of 16K
page-neighbour rerank, which the owner ruled a documented limitation rather
than a Gate 1 blocker.

This was not the first proposal. Siblings on, neighbours off was proposed
first, on quote-recall grounds, and the non-inferiority check added at
`5207e78` caught the margin failure on re-verification. The check was built
two steps before it overturned a recommendation.

### The freeze reproduces

An unflagged run at `c7e56fa` against the measured cell:

- **0 of 384** packets differ in selection, across every arm.
- Page recall differs in **0** records.
- Quote recall differs only on `adubench_single_000129`, the one question the
  v3 matcher fix touches. That is scoring, not selection, and was predicted.
- The compiler config hashes to `104b14de5974064f`, the value every compiler
  packet in the measured run carries.

`COMPILER_VERSION` was deliberately not bumped. A default change is visible in
the config hash every packet carries, and a bump would have made every
verification packet differ in metadata for a reason unrelated to the
configuration.

## Development result at the frozen configuration

Paired source-cluster bootstrap, 10,000 resamples, 18 eligible questions over 9
source clusters. Quote policy v3.

Compiler minus baseline, answerable page recall:

| Budget | vs fixed | vs structural |
| ---: | --- | --- |
| 2K | **+0.333** [+0.157, +0.491] | **+0.247** [+0.041, +0.421] |
| 4K | **+0.283** [+0.140, +0.413] | **+0.229** [+0.056, +0.375] |
| 8K | **+0.161** [+0.024, +0.274] | +0.168 [−0.001, +0.308] |
| 16K | +0.061 [−0.030, +0.127] | **+0.107** [+0.004, +0.225] |

Compiler minus baseline, exact quote recall:

| Budget | vs fixed | vs structural |
| ---: | --- | --- |
| 2K | +0.023 [−0.097, +0.167] | −0.046 [−0.123, +0.018] |
| 4K | **+0.111** [+0.023, +0.233] | **+0.074** [+0.021, +0.130] |
| 8K | +0.014 [−0.133, +0.182] | **+0.088** [+0.012, +0.191] |
| 16K | +0.042 [−0.034, +0.175] | **+0.116** [+0.031, +0.212] |

**The 2K quote deficit against structural chunks no longer excludes zero.** It
did under the previous default, at −0.0741 [−0.1417, −0.0159]. The point
estimate is still negative, so the compiler has not been shown better than
structural chunks on exact evidence at 2K — only no longer measurably worse.

The non-inferiority check is satisfied at 8 of 8 cells, **but the fixed-RAG
cell at 16K passes by 0.00024**: lower bound −0.029759 against a margin of
−0.03. That is a pass under the rule as written and it is inside bootstrap
noise. It is recorded as a pass that a different resampling seed could turn
into a failure, not as a comfortable one. None of the eight is confirmatory:
18 questions over 9 clusters, against a threshold of 34 of each.

## The quote metric

Quote recall was re-scored twice in this phase, and both changes altered the
comparison only. Gold data is untouched, as `AGENTS.md` requires.

- **v2** (`08acd28`): typographic reconciliation, and elided quotes matched by
  their fragments in document order.
- **v3** (`c7e56fa`): a quote with a leading or trailing ellipsis is matched by
  its one fragment, which v2's own stated rule required and its code did not
  do. A quote of markers alone no longer matches a context that happens to
  contain an ellipsis.

Every artifact records `quote_match_policy`, so figures scored under different
policies cannot be compared silently.

### What the remaining misses are

Of 46 development gold quotes, 20 match their own document under v2 and 26 do
not. Each of the 26 was classified from its failure signature — the longest
matching prefix and suffix, and whether the quote's words occur on the page
the annotator cited:

| Class | n | Examples |
| --- | ---: | --- |
| Matcher bug, fixed in v3 | 2 | a trailing `...` whose one fragment is present |
| Malformed elision marker | 1 | two dots, `..`, which is not a marker |
| Annotator transcription | 9 | heading and list joined with `: `; `Culverts,18`; a leading `: '` from a citation list; a trailing full stop the source lacks; an editorial insertion in square brackets |
| OCR error in the gold quote | 3 | `166os` for `1660s`; `group Il and Ill` for `II and III`; `Intravenousadministration ofradiocontrastmediacan` |
| Structured-content rendering | 3 | a table read as prose; a pipe-rendered table caption; a formula subscript |
| Elided reading across table cells | 5 | fragments present on the cited page but not in parse order |
| Near-verbatim, one divergence | 3 | a hyphenation or line break |

For most of the 26 the quote's words are on the cited page: the content is in
the parse and the gold string is not a verbatim transcription of it. The
ceiling on quote recall is set by how the gold quotes were written, not by the
parse or the matcher.

Only the 2 matcher-bug cases were fixed. Matching the other 24 would make the
metric agree with the annotator's reading rather than measure retrieval, and
the owner ruled out loosening the matcher to raise scores.

**Three gold quotes contain OCR errors of their own.** They are defects in the
benchmark's gold data, and they stay unmatchable for every arm at every
budget. `AGENTS.md` forbids changing gold data, so they are recorded here
rather than repaired.

This also corrects a figure given during the analysis. The earlier statement
that 17 quotes were "genuinely absent from the parse" came from a corpus-wide,
alphanumeric-only comparison. Scoped to each quote's own document under the
shipped matcher it is 26, and "absent from the parse" was the wrong frame.

## Latency: a documented limitation, not a gate

Phase 1 targeted compiler latency of at most twice fixed RAG and **did not meet
it**. Within one process, on the pinned models, the ratios were 2.29, 2.32,
2.40 and 3.92 at 2K, 4K, 8K and 16K before the freeze. The frozen run records
1,295, 1,203, 1,231 and 1,924 ms against 333 ms for fixed RAG, but cross-run
latency on this harness has differed by up to 471 ms on byte-identical
packets, so those per-run figures are not the measurement the target is
stated on.

The owner ruled that the miss does not block Gate 1. The Gate 1 rule was
preregistered without a latency clause, and adding one after seeing the target
fail would be changing the criterion after the result.

What was learned is recorded in the latency commit, `a421321`: cost is
dominated by the number of reranked pairs, not their tokens; the task's own two
requirements are mutually exclusive, because the cross-encoder is not
invariant to batch composition; and the remaining lever at 16K is the
page-neighbour rerank, which the freeze keeps for the margin.

## Gate 1: the rule and the pins

The rule, as preregistered in
[the plan](../plans/2026-09-21-improvement-plan.md), not changed here:

> It passes when, on `xlholdout6c`, the compiler's paired point estimate
> against fixed RAG is positive at 2K and 4K and its interval at 8K and 16K
> does not lie entirely below the −3 pp margin.

The gated metric is answerable page recall, the metric the margin is stated
on. Content-verified and exact quote recall are reported beside it and do not
gate.

Two things the rule is not. It is **not** the non-inferiority check: at 8K and
16K the rule asks only that the upper bound of the interval sit above −0.03,
which is much weaker than asking the lower bound to. And it is **not**
confirmatory: six holdout questions cannot bound a loss margin, which the plan
already says.

The run will be made against exactly this:

| Pin | Value |
| --- | --- |
| Code commit | `c7e56fa`. The run may be made at a later commit only if `git diff --name-only c7e56fa HEAD -- src benchmarks pyproject.toml uv.lock` is empty, checked and recorded at run time; the commits recording this close-out change none of them |
| Subset | `benchmarks/xl-docbench/subsets/xlholdout6c.json`, sha256 `f8bee8e5038cab2c92868b108ebf160114d2c82633662e475f6760006e0c7adc` |
| Compiler config hash | `104b14de5974064f` |
| Run config hash | `b2b8bbaa3eee2d52cff4d2bf0bbe1dccf4fb56a17bef2f46f221d6d3182e9941` |
| Quote match policy | `nfkc-unified-punctuation-ordered-elision-v3` |
| Embedding model | `BAAI/bge-small-en-v1.5` at `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` at `233902d25c440f23af6f7d6e94d2946bac0bee0a` |
| Dataset revision | `72954bd70ffffe230f08b57c57fa9274ec14d7ea` |
| Invocation | `uv run contextbench eval-retrieval --subset-file benchmarks/xl-docbench/subsets/xlholdout6c.json`, no compiler flags |

It is run once. It is published whatever it shows. The configuration is not
revised after it.

## Known weaknesses

- 24 development questions, 18 eligible per metric, 9 source clusters. Several
  effects in this phase rest on one or a few questions and are recorded as
  such.
- The 16K non-inferiority pass against fixed RAG has 0.00024 of headroom.
- The configuration was selected on the same 24 questions it is reported on.
- The quote-recall ceiling is set by gold-quote construction, including three
  gold quotes with OCR errors that no arm can match.
- No answer-quality result exists. Whether better page selection produces
  better answers is the question Phase 2 exists to answer.
