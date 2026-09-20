# Experiment: Second directional holdout for coverage packing

Date: 2026-09-20

Precommit: `c8066d6`

Canonical run: `xlholdout6b-coverage-c8066d6`

## Scope

The manifest was committed before retrieval. It selects one answerable,
single-document XL100 question per domain using only metadata, deterministic
tie-breaking, source availability, and source integrity. Its six documents are
disjoint from XL10, XLDev24, and the first holdout and contain 838 pages. No
answer-generation model was used.

All six sources required first-use ingestion. The completed parsed artifacts
are now content-addressed and reusable. OCR reported empty image regions and
bounded table-cell matching warnings; conversion completed successfully, but
the result remains directional rather than a final claim.

## Result

| Budget | Compiler recall | Best baseline | Delta | Compiler coverage | Best coverage |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2K | 0.513 | 0.390 fixed | +0.122 | 0.000 | 0.000 |
| 4K | 0.626 | 0.546 structural | +0.081 | 0.167 | 0.167 |
| 8K | 0.815 | 0.856 fixed | -0.040 | 0.333 | 0.500 |
| 16K | 0.935 | 1.000 fixed | -0.065 | 0.500 | 1.000 |

At 16K, compiler and fixed quote recall both equal 0.522. Compiler latency is
approximately 4.7-5.4 seconds, versus 1.4 seconds for fixed and 2.2 seconds for
structural retrieval. Source-order long context is much faster but materially
worse on mean recall except where relevant evidence happens to occur early.

## Decision

Keep coverage packing as the compiler default because it consistently improved
the prior compiler on balanced XLDev24. Do not claim general superiority over
RAG and do not run the full XL100: the new holdout supports a low-budget
retrieval advantage but rejects high-budget dominance. Freeze this result and
return to development or answer-quality validation without tuning on these six
questions.

The next decisive experiment is answer generation over already-saved contexts
and the RAW/IR/ENRICHED/INDEXED gold-evidence representations. It requires an
explicit model, current prices, and provider-call ceiling; none was inferred or
spent in this holdout run.
