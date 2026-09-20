# Experiment: XL10 retrieval smoke test

Run: `xl10-20260919-ca0e6e1`

This is a pipeline-validation run over 10 single-document questions sharing six
source PDFs. It covers all six XL-DocBench domains but is not representative of
XL100 and cannot support research claims. One unanswerable question has no gold
pages and therefore receives vacuous page recall of 1.0 for every system under
the preregistered metric convention.

## Result

| System | Budget | Mean page recall | Full coverage | Mean packed tokens |
| --- | ---: | ---: | ---: | ---: |
| Compiler | 2,048 | 0.424 | 0.200 | 1,090 |
| Fixed | 2,048 | 0.527 | 0.400 | 2,025 |
| Structural | 2,048 | 0.519 | 0.300 | 2,025 |
| Compiler | 4,096 | 0.468 | 0.300 | 1,854 |
| Fixed | 4,096 | 0.730 | 0.400 | 4,020 |
| Structural | 4,096 | 0.571 | 0.300 | 3,755 |
| Compiler | 8,192 | 0.488 | 0.300 | 2,649 |
| Fixed | 8,192 | 0.823 | 0.500 | 8,061 |
| Structural | 8,192 | 0.613 | 0.300 | 5,074 |
| Compiler | 16,384 | 0.488 | 0.300 | 2,649 |
| Fixed | 16,384 | 0.853 | 0.600 | 10,042 |
| Structural | 16,384 | 0.613 | 0.300 | 5,074 |

The compiler is below the best baseline at every registered budget. At 16K it
trails fixed RAG by 0.365 mean page recall and 0.300 full-coverage rate. Removing
the vacuous unanswerable question does not change the conclusion: answerable-only
16K recall is approximately 0.431 for compiler, 0.837 for fixed, and 0.570 for
structural.

## Diagnostic signal

The compiler plateaus at only 2,649 mean packed tokens from the 8K budget onward;
structural RAG plateaus at 5,074, while fixed RAG reaches 10,042 at 16K. All arms
share a 20-candidate rerank limit, but their candidates have very different
token mass. The shared count limit therefore prevents the finer-grained compiler
nodes from using the available budget. Several compiler questions plateau below
700 tokens, and `adubench_single_000803` returns one 15-token item with zero gold
page recall at every budget.

This does not establish that candidate capacity is the only problem. Even at 2K,
where all systems use similar aggregate token budgets, fixed and structural RAG
have higher recall. Raw contexts and per-question records should be inspected for
query mismatch, node granularity, table expansion, and deduplication effects.

## Decision

Do not treat this smoke run as justification for generation evaluation. First,
make retrieval capacity comparable in token opportunity rather than only
candidate count, investigate the zero/low-token compiler failures, preregister
any correction, and rerun XL10. XL100 remains required before broader claims.

The immutable machine-readable artifacts remain local at
`artifacts/runs/xl10-20260919-ca0e6e1/` as intended by `.gitignore`.
