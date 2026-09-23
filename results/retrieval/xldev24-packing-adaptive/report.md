# Retrieval Decision Report: xldev24-adaptive-3b77e75

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.715 | 0.417 | 0.382 | 0.292 | 2045.3 | 0.0 | 0.100 | 1146.74 |
| compiler | 4096 | 0.786 | 0.500 | 0.424 | 0.333 | 3922.5 | 413.0 | 0.141 | 1049.76 |
| compiler | 8192 | 0.842 | 0.542 | 0.465 | 0.375 | 7473.5 | 826.0 | 0.193 | 1055.51 |
| compiler | 16384 | 0.893 | 0.625 | 0.528 | 0.417 | 16216.5 | 1601.0 | 0.287 | 1755.58 |
| fixed | 2048 | 0.468 | 0.292 | 0.347 | 0.333 | 2015.3 | 0.0 | 0.077 | 316.88 |
| fixed | 4096 | 0.594 | 0.333 | 0.361 | 0.333 | 4035.1 | 0.0 | 0.115 | 316.19 |
| fixed | 8192 | 0.739 | 0.417 | 0.465 | 0.375 | 8044.4 | 0.0 | 0.177 | 316.25 |
| fixed | 16384 | 0.843 | 0.583 | 0.476 | 0.375 | 16136.9 | 2283.5 | 0.241 | 316.33 |
| long_context | 2048 | 0.374 | 0.292 | 0.260 | 0.250 | 2048.0 | 0.0 | 0.081 | 41.89 |
| long_context | 4096 | 0.528 | 0.333 | 0.368 | 0.292 | 4096.0 | 0.0 | 0.103 | 41.31 |
| long_context | 8192 | 0.652 | 0.375 | 0.378 | 0.292 | 8192.0 | 0.0 | 0.129 | 41.90 |
| long_context | 16384 | 0.782 | 0.667 | 0.424 | 0.292 | 15981.8 | 4541.5 | 0.168 | 43.20 |
| structural | 2048 | 0.533 | 0.292 | 0.399 | 0.375 | 2031.0 | 0.0 | 0.067 | 332.00 |
| structural | 4096 | 0.634 | 0.333 | 0.399 | 0.375 | 4061.0 | 0.0 | 0.102 | 331.43 |
| structural | 8192 | 0.734 | 0.458 | 0.399 | 0.375 | 8154.2 | 0.0 | 0.128 | 331.39 |
| structural | 16384 | 0.808 | 0.542 | 0.431 | 0.375 | 15065.3 | 1583.0 | 0.150 | 331.34 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.125 full-coverage, +0.182 recall.
- 4096 tokens: compiler vs best baseline: +0.167 full-coverage, +0.151 recall.
- 8192 tokens: compiler vs best baseline: +0.083 full-coverage, +0.108 recall.
- 16384 tokens: compiler vs best baseline: +0.042 full-coverage, +0.050 recall.

## Audited metrics

Page metrics below cover only questions that are marked answerable and carry at least one annotated gold page; a question with no annotated gold page is excluded even when it is marked answerable. Quote metrics include only questions with a non-empty gold quote. Content-verified pages require the full normalized source-node text to be present in the emitted context.

| System | Budget | Answerable gold-page n | Page recall | Content-verified recall | Quoted n | Exact quote recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 18 | 0.621 | 0.615 | 18 | 0.176 |
| compiler | 4096 | 18 | 0.714 | 0.709 | 18 | 0.231 |
| compiler | 8192 | 18 | 0.790 | 0.784 | 18 | 0.287 |
| compiler | 16384 | 18 | 0.857 | 0.851 | 18 | 0.370 |
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
| compiler | fixed | 2048 | answerable_page_recall | 18 | 9 | +0.330 | [+0.135, +0.508] |
| compiler | fixed | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.343 | [+0.150, +0.516] |
| compiler | fixed | 2048 | quoted_exact_quote_recall | 18 | 9 | +0.046 | [-0.067, +0.188] |
| compiler | structural | 2048 | answerable_page_recall | 18 | 9 | +0.243 | [+0.029, +0.429] |
| compiler | structural | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.290 | [+0.092, +0.459] |
| compiler | structural | 2048 | quoted_exact_quote_recall | 18 | 9 | -0.023 | [-0.097, +0.044] |
| compiler | fixed | 4096 | answerable_page_recall | 18 | 9 | +0.256 | [+0.101, +0.400] |
| compiler | fixed | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.264 | [+0.117, +0.397] |
| compiler | fixed | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.083 | [+0.000, +0.219] |
| compiler | structural | 4096 | answerable_page_recall | 18 | 9 | +0.202 | [+0.029, +0.357] |
| compiler | structural | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.285 | [+0.139, +0.407] |
| compiler | structural | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.032 | [-0.028, +0.111] |
| compiler | fixed | 8192 | answerable_page_recall | 18 | 9 | +0.137 | [-0.013, +0.258] |
| compiler | fixed | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.150 | [+0.008, +0.270] |
| compiler | fixed | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.000 | [-0.145, +0.172] |
| compiler | structural | 8192 | answerable_page_recall | 18 | 9 | +0.144 | [-0.041, +0.297] |
| compiler | structural | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.215 | [+0.050, +0.349] |
| compiler | structural | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.088 | [+0.012, +0.194] |
| compiler | fixed | 16384 | answerable_page_recall | 18 | 9 | +0.067 | [-0.041, +0.152] |
| compiler | fixed | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.083 | [-0.021, +0.168] |
| compiler | fixed | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.069 | [+0.000, +0.191] |
| compiler | structural | 16384 | answerable_page_recall | 18 | 9 | +0.113 | [-0.012, +0.257] |
| compiler | structural | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.189 | [+0.053, +0.331] |
| compiler | structural | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.130 | [+0.054, +0.219] |

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
