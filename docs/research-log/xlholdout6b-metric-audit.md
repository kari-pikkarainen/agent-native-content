# XLHoldout6b metric audit and manual error analysis

## Decision

The six-question audit preserves the compiler's low-budget page-recall effect,
but manual inspection shows that neither page recall nor exact quote recall is
a reliable proxy for answerability on every question. Proceed to guarded
answer generation at 2K and 4K; do not broaden the retrieval claim.

This reuses a previously inspected holdout and is therefore a diagnostic
reinterpretation, not a new holdout result.

## Audited result

All six questions are answerable and have non-empty gold quotes, so removing
vacuous successes does not change this subset's averages. Conservative
content-verified page recall requires the full normalized source-node text to
be emitted before crediting its pages.

| Budget | Compiler vs fixed, page | Compiler vs fixed, verified | Compiler vs structural, page | Compiler vs structural, verified |
| --- | ---: | ---: | ---: | ---: |
| 2K | +12.2 pp | +12.2 pp | +19.9 pp | +19.9 pp |
| 4K | +13.6 pp | +17.2 pp | +8.1 pp | +8.1 pp |
| 8K | -4.0 pp | -0.4 pp | +26.1 pp | +26.1 pp |
| 16K | -6.5 pp | -2.9 pp | +11.1 pp | +11.1 pp |

The descriptive source-cluster bootstrap interval excludes zero for compiler
versus fixed at 2K (`+3.3` to `+23.3` pp) and 4K (`+6.1` to `+21.1` pp) on
ordinary page recall. The sample has only six source clusters, so these are
descriptive intervals rather than general evidence.

Exact quote recall is less favorable. At 4K, compiler is 13.3 points below
structural RAG, with a wide interval (`-50.0` to `+10.0` pp). Compiler is 11.1
points above fixed RAG at 2K and 4K, but both intervals include zero.

The run produced 96 unique question/system/budget cells, 24 compiler stage
records, and no over-budget contexts. Its manifest binds the result to commit
`bc57f17`.

## Manual inspection at 2K and 4K

### Genuine compiler win: `adubench_single_000618`

At 2K the compiler gains 33.3 page-recall points over both baselines and is the
only system to reproduce the gold quote. It selects the specific page-72
crisis-management passage that states the multilingual interpretation
capability. Fixed and structural retrieval select nearby remote-hearing and IT
discussion, including close paraphrases, but not the registered passage. This
is a credible selection-policy win.

### Likely compiler win obscured by OCR: `adubench_single_000288`

At 4K the compiler gains 25.0 page-recall points over both baselines and emits
the contributor entry containing the requested Derek Attridge title, plus
several linked front-matter sections. Exact quote recall remains zero because
the gold quote preserves spaced OCR characters while the IR normalizes the
name. The context appears sufficient for the answer despite the literal-match
failure.

### Page-recall win with weak answer evidence: `adubench_single_000761`

At 2K the compiler gains 20.0 page-recall points over the best baseline by
selecting many isolated chart fragments and pages. It does not preserve the
complete Chart 12 title or values as one coherent unit. Structural RAG selects
the relevant chart section and recovers both registered quotes. The compiler's
page-recall advantage is unlikely to imply better answerability here.

### Page-recall loss with likely sufficient answer evidence: `adubench_single_000740`

At 4K the compiler trails structural RAG by 16.7 page-recall points. However,
it emits the 5.8-million incidence value, the DAPT definition, and the
12-month post-CABG recommendation from a duplicate recommendation table on a
non-gold page. The wording uses the acronym `CABG`, so the exact gold quote is
not matched either. The packed content nevertheless appears sufficient to
compute the answer. Both page and quote metrics under-credit this cell.

## Implications

1. The low-budget retrieval effect survives stricter source-content
   accounting on this subset.
2. Exact quotes catch some false page-recall wins, but OCR differences,
   abbreviations, and duplicate content create false negatives.
3. Page recall rewards broad page coverage even when chart fragments are not
   assembled into usable evidence.
4. The next experiment must measure answer correctness and semantic citation
   support on the saved 2K and 4K contexts.

Canonical source-text-free records are published under
`results/retrieval/xlholdout6b-metric-audit/`.
