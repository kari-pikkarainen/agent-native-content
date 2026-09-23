# Retrieval Decision Report: xldev24-ranked-3b77e75

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.648 | 0.333 | 0.410 | 0.375 | 2045.8 | 0.0 | 0.144 | 1175.31 |
| compiler | 4096 | 0.705 | 0.333 | 0.434 | 0.375 | 3922.7 | 0.0 | 0.181 | 1071.94 |
| compiler | 8192 | 0.787 | 0.458 | 0.486 | 0.375 | 7469.5 | 0.0 | 0.225 | 1071.93 |
| compiler | 16384 | 0.875 | 0.583 | 0.528 | 0.417 | 16218.1 | 1220.5 | 0.300 | 1752.83 |
| fixed | 2048 | 0.468 | 0.292 | 0.347 | 0.333 | 2015.3 | 0.0 | 0.077 | 303.96 |
| fixed | 4096 | 0.594 | 0.333 | 0.361 | 0.333 | 4035.1 | 0.0 | 0.115 | 303.32 |
| fixed | 8192 | 0.739 | 0.417 | 0.465 | 0.375 | 8044.4 | 0.0 | 0.177 | 303.23 |
| fixed | 16384 | 0.843 | 0.583 | 0.476 | 0.375 | 16136.9 | 2283.5 | 0.241 | 303.31 |
| long_context | 2048 | 0.374 | 0.292 | 0.260 | 0.250 | 2048.0 | 0.0 | 0.081 | 21.55 |
| long_context | 4096 | 0.528 | 0.333 | 0.368 | 0.292 | 4096.0 | 0.0 | 0.103 | 21.30 |
| long_context | 8192 | 0.652 | 0.375 | 0.378 | 0.292 | 8192.0 | 0.0 | 0.129 | 21.93 |
| long_context | 16384 | 0.782 | 0.667 | 0.424 | 0.292 | 15981.8 | 4541.5 | 0.168 | 23.37 |
| structural | 2048 | 0.533 | 0.292 | 0.399 | 0.375 | 2031.0 | 0.0 | 0.067 | 331.25 |
| structural | 4096 | 0.634 | 0.333 | 0.399 | 0.375 | 4061.0 | 0.0 | 0.102 | 330.77 |
| structural | 8192 | 0.734 | 0.458 | 0.399 | 0.375 | 8154.2 | 0.0 | 0.128 | 330.70 |
| structural | 16384 | 0.808 | 0.542 | 0.431 | 0.375 | 15065.3 | 1583.0 | 0.150 | 330.64 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.042 full-coverage, +0.115 recall.
- 4096 tokens: compiler vs best baseline: +0.000 full-coverage, +0.070 recall.
- 8192 tokens: compiler vs best baseline: +0.000 full-coverage, +0.052 recall.
- 16384 tokens: compiler vs best baseline: +0.000 full-coverage, +0.032 recall.

## Audited metrics

Page metrics below cover only questions that are marked answerable and carry at least one annotated gold page; a question with no annotated gold page is excluded even when it is marked answerable. Quote metrics include only questions with a non-empty gold quote. Content-verified pages require the full normalized source-node text to be present in the emitted context.

| System | Budget | Answerable gold-page n | Page recall | Content-verified recall | Quoted n | Exact quote recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 18 | 0.530 | 0.525 | 18 | 0.213 |
| compiler | 4096 | 18 | 0.607 | 0.601 | 18 | 0.245 |
| compiler | 8192 | 18 | 0.716 | 0.710 | 18 | 0.315 |
| compiler | 16384 | 18 | 0.833 | 0.827 | 18 | 0.370 |
| fixed | 2048 | 18 | 0.291 | 0.272 | 18 | 0.130 |
| fixed | 4096 | 18 | 0.458 | 0.445 | 18 | 0.148 |
| fixed | 8192 | 18 | 0.653 | 0.634 | 18 | 0.287 |
| fixed | 16384 | 18 | 0.790 | 0.768 | 18 | 0.301 |
| long_context | 2048 | 18 | 0.166 | 0.166 | 18 | 0.014 |
| long_context | 4096 | 18 | 0.370 | 0.370 | 18 | 0.157 |
| long_context | 8192 | 18 | 0.536 | 0.536 | 18 | 0.171 |
| long_context | 16384 | 18 | 0.710 | 0.710 | 18 | 0.231 |
| structural | 2048 | 18 | 0.377 | 0.325 | 18 | 0.199 |
| structural | 4096 | 18 | 0.513 | 0.424 | 18 | 0.199 |
| structural | 8192 | 18 | 0.646 | 0.570 | 18 | 0.199 |
| structural | 16384 | 18 | 0.744 | 0.662 | 18 | 0.241 |

## Paired source-cluster bootstrap

Intervals are descriptive 95% paired bootstrap intervals. The sampling unit is the sorted source-document scope; 10,000 resamples are used by default.

| Treatment | Baseline | Budget | Metric | n | Clusters | Delta | 95% interval |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| compiler | fixed | 2048 | answerable_page_recall | 18 | 9 | +0.239 | [+0.057, +0.422] |
| compiler | fixed | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.253 | [+0.077, +0.430] |
| compiler | fixed | 2048 | quoted_exact_quote_recall | 18 | 9 | +0.083 | [+0.000, +0.214] |
| compiler | structural | 2048 | answerable_page_recall | 18 | 9 | +0.153 | [-0.041, +0.342] |
| compiler | structural | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.200 | [+0.024, +0.366] |
| compiler | structural | 2048 | quoted_exact_quote_recall | 18 | 9 | +0.014 | [-0.036, +0.088] |
| compiler | fixed | 4096 | answerable_page_recall | 18 | 9 | +0.148 | [-0.005, +0.336] |
| compiler | fixed | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.156 | [+0.019, +0.330] |
| compiler | fixed | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.097 | [+0.000, +0.222] |
| compiler | structural | 4096 | answerable_page_recall | 18 | 9 | +0.094 | [-0.081, +0.289] |
| compiler | structural | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.177 | [+0.030, +0.337] |
| compiler | structural | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.046 | [+0.000, +0.115] |
| compiler | fixed | 8192 | answerable_page_recall | 18 | 9 | +0.063 | [-0.073, +0.194] |
| compiler | fixed | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.076 | [-0.054, +0.207] |
| compiler | fixed | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.028 | [-0.078, +0.176] |
| compiler | structural | 8192 | answerable_page_recall | 18 | 9 | +0.070 | [-0.101, +0.221] |
| compiler | structural | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.141 | [+0.006, +0.265] |
| compiler | structural | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.116 | [+0.031, +0.211] |
| compiler | fixed | 16384 | answerable_page_recall | 18 | 9 | +0.043 | [-0.079, +0.140] |
| compiler | fixed | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.059 | [-0.062, +0.153] |
| compiler | fixed | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.069 | [+0.000, +0.191] |
| compiler | structural | 16384 | answerable_page_recall | 18 | 9 | +0.089 | [-0.057, +0.247] |
| compiler | structural | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.165 | [+0.044, +0.304] |
| compiler | structural | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.130 | [+0.054, +0.219] |

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
