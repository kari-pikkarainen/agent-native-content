# XL10 Compiler Improvement Decision

Selected retrieval run: `xl10-stable-22f00c3`

Current IR-correctness validation: `xl10-source-fallback-24ac563`

Current result-equivalent optimized run: `xl10-ranked-once-5424b34`

This decision follows the initial XL10 smoke run and uses the same 10 questions,
six documents, models, and evidence-only metrics. XL10 is a development smoke
set, not a representative research benchmark; XL100 is still required before
making broader claims.

## Accepted changes

The selected compiler configuration adds three corrections:

1. Furniture nodes are excluded, while heading paths are indexed as search-only
   context and exact source text remains the emitted evidence.
2. Candidate and rerank capacity scale with candidate token mass under explicit
   hard caps, using the same policy for all benchmark arms.
3. Every budget uses the ranking retrieved for the largest configured budget,
   making smaller context packets nested prefixes of one stable ranking.

The final correction also raises the compiler's expanded-candidate ceiling to
500. Structural sibling expansion remains available but is disabled by default.

## Ablation result

The table reports compiler performance at the 16,384-token budget.

| Run | Change | Mean page recall | Full coverage | Mean packed tokens | Decision |
| --- | --- | ---: | ---: | ---: | --- |
| `xl10-20260919-ca0e6e1` | Initial smoke baseline | 0.488 | 0.300 | 2,649 | Superseded |
| `xl10-hygiene-72b45c9` | Retrieval hygiene | 0.537 | 0.300 | 2,454 | Keep |
| `xl10-token-aware-3a43bc5` | Token-aware capacity | 0.687 | 0.300 | 8,376 | Keep |
| `xl10-stable-22f00c3` | Stable ranking and larger expansion cap | 0.769 | 0.400 | 14,036 | Select |
| `xl10-neighbors-606d425` | Default two-hop sibling expansion | 0.691 | 0.300 | 12,189 | Reject |
| `xl10-rerank-fusion-d5df286` | Hybrid/reranker rank fusion | 0.748 | 0.400 | 14,043 | Reject |

Compared with the initial run, the selected configuration raises compiler
16K mean page recall by 0.281 and full-coverage rate by 0.100. It also removes
the artificial low-token plateau. At 2K, compiler recall is 0.592 versus 0.585
for fixed and 0.558 for structural retrieval, so the compiler narrowly leads
on the most constrained budget. At 16K, fixed retrieval remains substantially
better: 0.962 recall versus compiler's 0.769.

## Rejected experiments

Default sibling expansion displaced directly retrieved evidence and reduced
compiler recall at every useful budget, including a drop to 0.691 at 16K. The
feature is therefore opt-in only.

Post-reranker rank fusion improved compiler recall at 2K through 8K but reduced
it at 16K and caused material regressions for the fixed and structural controls.
It also failed to recover the targeted post-structuralism passage. The code was
reverted; its immutable run is retained locally as negative evidence.

## Remaining limitations

The compiler still loses to fixed retrieval as budgets grow. Two hard cases
expose different causes:

- A long comparative literature question is poorly scored by the cross-encoder
  even when lexical/dense retrieval finds the exact passage.
- A table question has incomplete page provenance in the projected IR: one gold
  page is represented only by an empty grouping node, so the compiler cannot
  emit meaningful evidence for that page.

Future work should evaluate query decomposition or a stronger long-query
reranker on a preregistered development split, and separately improve IR table
continuation provenance. Neither should be tuned against these 10 questions.

The immutable run artifacts remain under `artifacts/runs/` and are intentionally
ignored by Git.

## Follow-up: empty normalized source text

The authoritative Docling artifact for one missing gold page contained an empty
normalized `text` value but retained 1,081 characters of source-derived `orig`
text and the correct page-24 provenance box. IR projection now uses that source
text as a fallback rather than emitting an evidence-free node.

The full XL10 regression increased compiler 16K recall from 0.769 to 0.814. On
the affected table question, compiler recall increased from 0.500 to 0.833 and
page 24 became retrievable. Structural results were unchanged. Compiler 2K
recall moved from 0.592 to 0.581, so the next larger evaluation must continue to
report the full budget curve rather than only the high-budget gain.

## Follow-up: one ranking per budget curve

The evaluator now retrieves and reranks once per question/system at the largest
declared budget, then reuses that ranking for budget-dependent compilation and
packing. All 120 non-latency evaluation records and all context packets matched
the preceding run exactly. Observed XL10 wall time fell from about 4.5 minutes
to 2.5 minutes in the same local environment; this timing is operational, not a
benchmark-quality performance claim.
