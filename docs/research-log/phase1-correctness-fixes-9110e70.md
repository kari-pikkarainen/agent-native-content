# Phase 1 tasks 1 to 3: three correctness fixes, measured

Date: 2026-09-22

Commits: `ebf507a`, `a982699`, `a508be5`, `14c25aa`, `9110e70`, `1e58c16`

Canonical run: `xldev24-irorder-9110e70`, published under
[`results/`](../../results/README.md) as `xldev24-phase1-fixes`. Baseline for
every delta here: `xldev24-rebaseline`, the Gate 0 run at `e28b247`.

Both runs are clean-worktree, with the embedding model pinned to
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` and the reranker to
`233902d25c440f23af6f7d6e94d2946bac0bee0a`.

## Scope

Tasks 1 to 3 of [Phase 1](../plans/2026-09-21-improvement-plan.md). Each was
delivered as its own commit with its own `xldev24` measurement, then reviewed
and verified independently against the frozen revision.

These are **correctness fixes, not tuning**. The measurement is a record, not
an acceptance gate. A defect does not get to stay because removing it cost
page recall. That distinction matters here, because two of the three moved the
numbers against the compiler.

## Task 1: keyed joins gated core evidence out of the packet

`priority_tier` is a hard gate, not a tie-break: `_coverage_selection`
considers only the lowest tier that still fits. Expansion bumped every
already-expanded candidate up a tier whenever keyed joins fired, and appended
the joins at tier 0, so while any join still fit, no direct retrieval hit
could be selected at all. With the join limit at 16 the packet could in
principle have held no retrieval evidence whatever.

**Measured effect on `xldev24`: none.** All 96 compiler packets are
byte-identical to the baseline, at evidence-id level, not merely on summary
metrics. The one development question that produces keyed joins produces
exactly one, and with a single join the bump was self-cancelling: the join
took the first pick, the remaining tier became the minimum, and core evidence
was selectable again. The defect needs two or more joins to bite and the
development set never supplies them.

The suite is therefore the only thing standing between this defect and a
regression, which is why the page-neighbour half of the fix needed a test at a
16K budget. Before that test the entire suite was blind to it: moving page
neighbours back to the primary tier fails exactly one test out of 252.

## Task 2: candidate classes were ordered on incomparable scales

The compiler orders on `RetrievalScores.reranked` in three places. That field
did not hold one quantity. Under the shipped defaults `retrieve_faceted`
overwrote both `fused` and `reranked` with the RRF sum, near `0.033`, while
keyed joins and table fragments carried raw cross-encoder scores and
page-neighbour windows carried penalized ones. In a real benchmark packet the
keyed join sat at `reranked` 4.729 above core evidence at 0.049. It led on
units, not on relevance.

The fix was a deletion. `rerank_many` had already computed a real
cross-encoder score for every candidate in every facet ranking and the code
discarded it one line later, so keeping it costs no extra model invocation and
no extra query-candidate pair. `fused` was then the remaining mixed-unit key
in the cross-class sort -- an RRF sum for anything retrieved, a lexical
overlap ratio for a join that was never retrieved -- and it is dropped from
that sort while kept in the page-neighbour internal sort, which compares
within one class.

**Measured effect: flat.** Page `-0.0031` mean, quote `+0.0139` mean, three
questions moving across four budgets. On 18 eligible questions that is not
distinguishable from noise and is not claimed as an improvement.

One movement is worth naming because it connects two findings.
`adubench_single_000266` goes from 0.000 to 1.000 quote recall at 4K. That is
the question where the compiler selects the correct gold pages but packs a
sibling node lacking the quoted span -- the case that drove the entire
heading-free regression recorded in
[the heading ablation](compiler-heading-free-edd196f.md). A table fragment
leading on units was displacing the node carrying the quote. Part of what
looked like a node-boundary problem was a scale problem.

The contract is now in [the retrieval specification](../specs/retrieval.md)
rather than in a docstring, including the part that is not flattering:
`reranked` is one unit but not one meaning. Siblings and list neighbours are
never scored on their own text; they carry the anchor's score times a
multiplicative penalty, which is not a principled operation on a signed
log-odds value. That is recorded as an open question, not fixed.

## Task 3: ordinals did not follow source order, and furniture reached the arms

The larger half had never been recorded. `_ordered_items` left two
`iterate_items` defaults alone: `included_content_layers` defaults to body
only, and Docling descends through a furniture item without yielding it, so a
running header inside the body tree was invisible to the walk;
`traverse_pictures` defaults to false, so the text Docling nests under a
full-page picture -- how an image-first page is represented -- was skipped.
Across the 28 cached documents those two defaults hid **29,785 of 72,745
items, 40.9 per cent, in every document** and up to 69.8 per cent in one.
Nothing was structurally unreachable. The collections sweep was not recovering
orphans; it was re-appending content the walk had been told to skip, in
collection order, after the whole document.

That put one multi-page page inversion in every document. `fixed_chunks`
concatenates node text in ordinal order, so windows spliced page 65 onto page
1, and 445 of 4,895 claimed a page span over three pages, several the entire
document.

| | before | after |
| --- | ---: | ---: |
| multi-page inversions | 28 | **0** |
| widest fixed-window page span | 314 | **11** |
| items projected | 72,745 | 72,745 |
| furniture nodes retained in the IR | 5,804 | 5,804 |

Separately, `compiler/candidates.py` had always excluded furniture and
`fixed_chunks` had not, so the baseline spent tokens on running headers the
compiler never saw. Structural chunking was already clean and is now pinned by
a test. The two defects interact: with ordinals repaired, furniture
interleaves in reading order rather than arriving in one block, and would have
touched 2,617 of 4,895 windows instead of 235.

Provenance holds. IR node ids, structural chunk ids and compiler node-chunk
ids are bit-identical; 481 of 502 fixed chunk ids are replaced, because the
chunk-id payload includes the ordinal.

## The result we did not expect

Both the implementer and the coordinator predicted the fixed arm would improve
and the compiler's margin would narrow. **Both were wrong, and in the opposite
direction.**

Fixed page recall **fell** by 0.0173 on average. The mechanism was measured,
not guessed: the fixed arm selects an identical number of windows before and
after -- 4, 8, 16 and 32.1 per question -- but distinct pages per window fell
from **2.427 to 1.823** at 2K and from 2.000 to 1.565 at 8K. A window splicing
page 65 onto page 1 is credited with two distant pages for one window's
tokens. The corrupted stream was handing the baseline free page coverage.

Fixed **quote** recall rose over the same change, by 0.0278 at both 2K and 4K,
because coherent windows carry complete quoted spans.

So page recall was rewarding incoherent windows, on the baseline arm, where no
compiler design decision can be blamed for it. This project has argued since
Gate 0 that page recall can overstate an improvement. This is the cleanest
demonstration of that so far, and it cuts against the arm the project is
advocating rather than for it.

## Per-arm before and after

Answerable-eligible page and content-verified recall, quoted-eligible quote
recall. 18 eligible questions on each metric, 24 questions in the subset.

#### fixed

| Budget | page | content-verified | quote |
| ---: | --- | --- | --- |
| 2K | 0.2984 → 0.2910 (-0.0075) | 0.2747 → 0.2720 (-0.0027) | 0.1019 → 0.1296 (+0.0278) |
| 4K | 0.5078 → 0.4584 (-0.0494) | 0.4841 → 0.4445 (-0.0396) | 0.1204 → 0.1481 (+0.0278) |
| 8K | 0.6739 → 0.6526 (-0.0213) | 0.6494 → 0.6342 (-0.0152) | 0.2870 → 0.2870 (0.0000) |
| 16K | 0.7813 → 0.7902 (+0.0089) | 0.7573 → 0.7685 (+0.0112) | 0.3009 → 0.3009 (0.0000) |

#### structural

| Budget | page | content-verified | quote |
| ---: | --- | --- | --- |
| 2K | 0.3774 → 0.3774 (0.0000) | 0.3251 → 0.3251 (0.0000) | 0.1991 → 0.1991 (0.0000) |
| 4K | 0.5126 → 0.5126 (0.0000) | 0.4239 → 0.4239 (0.0000) | 0.1991 → 0.1991 (0.0000) |
| 8K | 0.6460 → 0.6460 (0.0000) | 0.5696 → 0.5696 (0.0000) | 0.1991 → 0.1991 (0.0000) |
| 16K | 0.7439 → 0.7439 (0.0000) | 0.6625 → 0.6625 (0.0000) | 0.2407 → 0.2407 (0.0000) |

#### compiler

| Budget | page | content-verified | quote |
| ---: | --- | --- | --- |
| 2K | 0.6359 → 0.6367 (+0.0008) | 0.6303 → 0.6311 (+0.0008) | 0.1574 → 0.1389 (-0.0185) |
| 4K | 0.7212 → 0.7248 (+0.0036) | 0.7157 → 0.7192 (+0.0036) | 0.1759 → 0.2315 (+0.0556) |
| 8K | 0.8243 → 0.8111 (-0.0133) | 0.8188 → 0.8055 (-0.0133) | 0.3009 → 0.3009 (0.0000) |
| 16K | 0.8956 → 0.8749 (-0.0207) | 0.8901 → 0.8694 (-0.0207) | 0.3565 → 0.3704 (+0.0139) |

#### long_context

| Budget | page | content-verified | quote |
| ---: | --- | --- | --- |
| 2K | 0.2335 → 0.1659 (-0.0676) | 0.2335 → 0.1659 (-0.0676) | 0.0139 → 0.0139 (0.0000) |
| 4K | 0.4125 → 0.3705 (-0.0420) | 0.4125 → 0.3705 (-0.0420) | 0.1019 → 0.1574 (+0.0556) |
| 8K | 0.5354 → 0.5359 (+0.0005) | 0.5354 → 0.5359 (+0.0005) | 0.1713 → 0.1713 (0.0000) |
| 16K | 0.6649 → 0.7095 (+0.0447) | 0.6649 → 0.7095 (+0.0447) | 0.2454 → 0.2315 (-0.0139) |

`structural` is unchanged to four decimals at every budget and metric, which
is the check that the IR repair reached only the surfaces it should:
`structural_chunks` reads the Docling document rather than the node ordinals,
so it is byte-identical by construction. `long_context` moves because it
truncates in ordinal order, so the head of a document is now genuinely its
head.

## Paired intervals, and what they do not support

Paired source-cluster bootstrap, 10,000 resamples, 18 eligible questions over
9 source clusters.

Compiler minus fixed, `answerable_page_recall`:

| Budget | before | after |
| ---: | --- | --- |
| 2K | **+0.3375** [+0.1696, +0.5132] | **+0.3457** [+0.1654, +0.5152] |
| 4K | **+0.2134** [+0.0666, +0.3534] | **+0.2664** [+0.1220, +0.4063] |
| 8K | +0.1504 [−0.0063, +0.2740] | **+0.1585** [+0.0208, +0.2717] |
| 16K | **+0.1143** [+0.0267, +0.2034] | +0.0847 [−0.0103, +0.1653] |

**Gate 0's criterion still holds.** The interval excludes zero at 2K and 4K
against both baselines. 8K against fixed now excludes zero where it did not;
16K against fixed no longer does.

Compiler minus fixed, `quoted_exact_quote_recall`:

| Budget | before | after |
| ---: | --- | --- |
| 2K | +0.0556 [−0.0625, +0.1944] | +0.0093 [−0.1053, +0.1569] |
| 4K | +0.0556 [−0.0667, +0.1923] | +0.0833 [0.0000, +0.2188] |
| 8K | +0.0139 [−0.1389, +0.1875] | +0.0139 [−0.1389, +0.1875] |
| 16K | +0.0556 [−0.0294, +0.1875] | +0.0694 [0.0000, +0.1912] |

**Every one of these includes zero, before and after, at every budget.** The
compiler's exact-quote-recall advantage over fixed RAG has never been
distinguishable from zero on this development set. The published advantage
rests entirely on page recall. That was as true at Gate 0 as it is now; it was
simply never stated in interval terms.

Against the structural baseline the picture is worse at the budget the
compiler is supposed to own. Compiler minus structural, quote recall at 2K,
moves from −0.0417 [−0.1053, 0.0000] to **−0.0602 [−0.1250, −0.0114]** — an
interval excluding zero, in the negative direction. Phase 1's goal is that the
compiler is never worse at any budget. On this metric against this baseline it
now measurably is. The fixes did not cause that so much as expose it: the
before-interval already sat against the boundary.

## Decision

The three fixes stand. None is reverted, and none was scoped or tuned to
protect the compiler's margin — task 3 in particular was expected to cost the
compiler and was delivered anyway.

Phase 1's remaining tasks should be read against two facts established here.
The compiler has no demonstrated exact-quote advantage over fixed RAG at any
budget, and it has a demonstrated quote-recall deficit against structural
chunks at 2K. Task 4's budget-adaptive packing and its −3 pp non-inferiority
report should therefore be judged on quote recall as well as page recall, or
it will report an improvement the stricter metric does not support.

## Known weaknesses

- 24 development questions, 18 eligible, 9 source clusters. Intervals are wide
  and several deltas here rest on one or two questions.
- No holdout was run. `xlholdout6c` stays frozen until Gate 1.
- No answer-quality or economic result exists; task 10 is still unrun.
- Latency is not comparable across runs on this harness: two runs producing
  byte-identical packets differed by up to 471 ms per question. Task 5's
  target needs a within-run measurement.
- `_index_key` hashes an ordered list of chunk ids and is blind to chunk
  content not carried in the id. It rekeyed correctly here because ordinals
  permuted. The hazard is recorded and left open.
- Siblings and list neighbours are ordered by a multiplicative penalty applied
  to a signed cross-encoder score, which is not a principled demotion. Open.
