# Retrieval Decision Report: xlholdout6b-metric-audit-bc57f17

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.513 | 0.000 | 0.300 | 0.167 | 2044.3 | n/a | 0.076 | 1395.68 |
| compiler | 4096 | 0.626 | 0.167 | 0.300 | 0.167 | 4092.3 | 4095.0 | 0.108 | 1394.89 |
| compiler | 8192 | 0.815 | 0.333 | 0.439 | 0.167 | 8189.5 | 5387.0 | 0.161 | 1429.16 |
| compiler | 16384 | 0.935 | 0.500 | 0.522 | 0.333 | 16271.7 | 6510.0 | 0.229 | 1844.00 |
| fixed | 2048 | 0.390 | 0.000 | 0.189 | 0.000 | 2024.5 | n/a | 0.055 | 478.30 |
| fixed | 4096 | 0.490 | 0.000 | 0.189 | 0.000 | 4051.8 | n/a | 0.120 | 477.89 |
| fixed | 8192 | 0.856 | 0.500 | 0.356 | 0.167 | 8101.7 | 5067.0 | 0.169 | 478.46 |
| fixed | 16384 | 1.000 | 1.000 | 0.522 | 0.333 | 16196.3 | 8139.0 | 0.223 | 476.86 |
| long_context | 2048 | 0.163 | 0.000 | 0.000 | 0.000 | 2048.0 | n/a | 0.103 | 29.64 |
| long_context | 4096 | 0.250 | 0.167 | 0.000 | 0.000 | 4096.0 | 3988.0 | 0.103 | 29.30 |
| long_context | 8192 | 0.447 | 0.333 | 0.133 | 0.000 | 8192.0 | 6778.5 | 0.120 | 30.08 |
| long_context | 16384 | 0.722 | 0.667 | 0.356 | 0.167 | 16384.0 | 12047.0 | 0.152 | 30.02 |
| structural | 2048 | 0.314 | 0.000 | 0.267 | 0.167 | 2023.7 | n/a | 0.083 | 426.60 |
| structural | 4096 | 0.546 | 0.167 | 0.433 | 0.333 | 4062.3 | 2625.0 | 0.123 | 426.24 |
| structural | 8192 | 0.554 | 0.167 | 0.433 | 0.333 | 8153.0 | 2625.0 | 0.139 | 426.15 |
| structural | 16384 | 0.824 | 0.500 | 0.489 | 0.333 | 16342.0 | 9585.0 | 0.170 | 426.39 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.000 full-coverage, +0.122 recall.
- 4096 tokens: compiler vs best baseline: +0.000 full-coverage, +0.081 recall.
- 8192 tokens: compiler vs best baseline: -0.167 full-coverage, -0.040 recall.
- 16384 tokens: compiler vs best baseline: -0.500 full-coverage, -0.065 recall.

## Audited metrics

Unanswerable questions are excluded from page metrics below. Quote metrics include only questions with a non-empty gold quote. Content-verified pages require the full normalized source-node text to be present in the emitted context.

| System | Budget | Answerable n | Page recall | Content-verified recall | Quoted n | Exact quote recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 6 | 0.513 | 0.513 | 6 | 0.300 |
| compiler | 4096 | 6 | 0.626 | 0.626 | 6 | 0.300 |
| compiler | 8192 | 6 | 0.815 | 0.815 | 6 | 0.439 |
| compiler | 16384 | 6 | 0.935 | 0.935 | 6 | 0.522 |
| fixed | 2048 | 6 | 0.390 | 0.390 | 6 | 0.189 |
| fixed | 4096 | 6 | 0.490 | 0.454 | 6 | 0.189 |
| fixed | 8192 | 6 | 0.856 | 0.819 | 6 | 0.356 |
| fixed | 16384 | 6 | 1.000 | 0.964 | 6 | 0.522 |
| long_context | 2048 | 6 | 0.163 | 0.163 | 6 | 0.000 |
| long_context | 4096 | 6 | 0.250 | 0.250 | 6 | 0.000 |
| long_context | 8192 | 6 | 0.447 | 0.447 | 6 | 0.133 |
| long_context | 16384 | 6 | 0.722 | 0.722 | 6 | 0.356 |
| structural | 2048 | 6 | 0.314 | 0.314 | 6 | 0.267 |
| structural | 4096 | 6 | 0.546 | 0.546 | 6 | 0.433 |
| structural | 8192 | 6 | 0.554 | 0.554 | 6 | 0.433 |
| structural | 16384 | 6 | 0.824 | 0.824 | 6 | 0.489 |

## Paired source-cluster bootstrap

Intervals are descriptive 95% paired bootstrap intervals. The sampling unit is the sorted source-document scope; 10,000 resamples are used by default.

| Treatment | Baseline | Budget | Metric | n | Clusters | Delta | 95% interval |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| compiler | fixed | 2048 | answerable_page_recall | 6 | 6 | +0.122 | [+0.033, +0.233] |
| compiler | fixed | 2048 | answerable_content_verified_page_recall | 6 | 6 | +0.122 | [+0.033, +0.233] |
| compiler | fixed | 2048 | quoted_exact_quote_recall | 6 | 6 | +0.111 | [-0.167, +0.500] |
| compiler | structural | 2048 | answerable_page_recall | 6 | 6 | +0.199 | [+0.104, +0.289] |
| compiler | structural | 2048 | answerable_content_verified_page_recall | 6 | 6 | +0.199 | [+0.108, +0.289] |
| compiler | structural | 2048 | quoted_exact_quote_recall | 6 | 6 | +0.033 | [-0.467, +0.500] |
| compiler | fixed | 4096 | answerable_page_recall | 6 | 6 | +0.136 | [+0.061, +0.211] |
| compiler | fixed | 4096 | answerable_content_verified_page_recall | 6 | 6 | +0.172 | [+0.067, +0.269] |
| compiler | fixed | 4096 | quoted_exact_quote_recall | 6 | 6 | +0.111 | [-0.167, +0.500] |
| compiler | structural | 4096 | answerable_page_recall | 6 | 6 | +0.081 | [-0.042, +0.192] |
| compiler | structural | 4096 | answerable_content_verified_page_recall | 6 | 6 | +0.081 | [-0.042, +0.192] |
| compiler | structural | 4096 | quoted_exact_quote_recall | 6 | 6 | -0.133 | [-0.500, +0.100] |
| compiler | fixed | 8192 | answerable_page_recall | 6 | 6 | -0.040 | [-0.199, +0.188] |
| compiler | fixed | 8192 | answerable_content_verified_page_recall | 6 | 6 | -0.004 | [-0.154, +0.217] |
| compiler | fixed | 8192 | quoted_exact_quote_recall | 6 | 6 | +0.083 | [+0.000, +0.250] |
| compiler | structural | 8192 | answerable_page_recall | 6 | 6 | +0.261 | [+0.122, +0.400] |
| compiler | structural | 8192 | answerable_content_verified_page_recall | 6 | 6 | +0.261 | [+0.122, +0.400] |
| compiler | structural | 8192 | quoted_exact_quote_recall | 6 | 6 | +0.006 | [-0.217, +0.178] |
| compiler | fixed | 16384 | answerable_page_recall | 6 | 6 | -0.065 | [-0.121, -0.017] |
| compiler | fixed | 16384 | answerable_content_verified_page_recall | 6 | 6 | -0.029 | [-0.071, +0.000] |
| compiler | fixed | 16384 | quoted_exact_quote_recall | 6 | 6 | +0.000 | [+0.000, +0.000] |
| compiler | structural | 16384 | answerable_page_recall | 6 | 6 | +0.111 | [+0.028, +0.208] |
| compiler | structural | 16384 | answerable_content_verified_page_recall | 6 | 6 | +0.111 | [+0.028, +0.208] |
| compiler | structural | 16384 | quoted_exact_quote_recall | 6 | 6 | +0.033 | [+0.000, +0.100] |

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
