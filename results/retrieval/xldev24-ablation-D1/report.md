# Retrieval Decision Report: xldev24-D1-6cc7fd9

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.727 | 0.375 | 0.326 | 0.250 | 2047.7 | 0.0 | 0.066 | 1144.11 |
| compiler | 4096 | 0.811 | 0.542 | 0.403 | 0.333 | 3899.2 | 780.0 | 0.092 | 1155.44 |
| compiler | 8192 | 0.860 | 0.583 | 0.424 | 0.333 | 7141.4 | 1133.5 | 0.134 | 1166.34 |
| compiler | 16384 | 0.884 | 0.583 | 0.476 | 0.375 | 12221.0 | 1133.5 | 0.179 | 1177.31 |
| fixed | 2048 | 0.468 | 0.292 | 0.347 | 0.333 | 2015.3 | 0.0 | 0.077 | 374.07 |
| fixed | 4096 | 0.594 | 0.333 | 0.361 | 0.333 | 4035.1 | 0.0 | 0.115 | 373.78 |
| fixed | 8192 | 0.739 | 0.417 | 0.465 | 0.375 | 8044.4 | 0.0 | 0.177 | 373.87 |
| fixed | 16384 | 0.843 | 0.583 | 0.476 | 0.375 | 16136.9 | 2283.5 | 0.241 | 373.52 |
| long_context | 2048 | 0.374 | 0.292 | 0.260 | 0.250 | 2048.0 | 0.0 | 0.081 | 89.99 |
| long_context | 4096 | 0.528 | 0.333 | 0.368 | 0.292 | 4096.0 | 0.0 | 0.103 | 88.56 |
| long_context | 8192 | 0.652 | 0.375 | 0.378 | 0.292 | 8192.0 | 0.0 | 0.129 | 89.09 |
| long_context | 16384 | 0.782 | 0.667 | 0.424 | 0.292 | 15981.8 | 4541.5 | 0.168 | 90.69 |
| structural | 2048 | 0.533 | 0.292 | 0.399 | 0.375 | 2031.0 | 0.0 | 0.067 | 357.52 |
| structural | 4096 | 0.634 | 0.333 | 0.399 | 0.375 | 4061.0 | 0.0 | 0.102 | 357.16 |
| structural | 8192 | 0.734 | 0.458 | 0.399 | 0.375 | 8154.2 | 0.0 | 0.128 | 357.10 |
| structural | 16384 | 0.808 | 0.542 | 0.431 | 0.375 | 15065.3 | 1583.0 | 0.150 | 356.94 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.083 full-coverage, +0.194 recall.
- 4096 tokens: compiler vs best baseline: +0.208 full-coverage, +0.177 recall.
- 8192 tokens: compiler vs best baseline: +0.125 full-coverage, +0.126 recall.
- 16384 tokens: compiler vs best baseline: +0.000 full-coverage, +0.041 recall.

## Audited metrics

Page metrics below cover only questions that are marked answerable and carry at least one annotated gold page; a question with no annotated gold page is excluded even when it is marked answerable. Quote metrics include only questions with a non-empty gold quote. Content-verified pages require the full normalized source-node text to be present in the emitted context.

| System | Budget | Answerable gold-page n | Page recall | Content-verified recall | Quoted n | Exact quote recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 18 | 0.637 | 0.637 | 18 | 0.102 |
| compiler | 4096 | 18 | 0.748 | 0.748 | 18 | 0.204 |
| compiler | 8192 | 18 | 0.813 | 0.813 | 18 | 0.231 |
| compiler | 16384 | 18 | 0.845 | 0.845 | 18 | 0.301 |
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
| compiler | fixed | 2048 | answerable_page_recall | 18 | 9 | +0.346 | [+0.173, +0.503] |
| compiler | fixed | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.365 | [+0.201, +0.514] |
| compiler | fixed | 2048 | quoted_exact_quote_recall | 18 | 9 | -0.028 | [-0.088, +0.000] |
| compiler | structural | 2048 | answerable_page_recall | 18 | 9 | +0.259 | [+0.062, +0.430] |
| compiler | structural | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.311 | [+0.130, +0.461] |
| compiler | structural | 2048 | quoted_exact_quote_recall | 18 | 9 | -0.097 | [-0.224, -0.011] |
| compiler | fixed | 4096 | answerable_page_recall | 18 | 9 | +0.290 | [+0.153, +0.422] |
| compiler | fixed | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.304 | [+0.177, +0.424] |
| compiler | fixed | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.056 | [+0.000, +0.125] |
| compiler | structural | 4096 | answerable_page_recall | 18 | 9 | +0.235 | [+0.072, +0.383] |
| compiler | structural | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.324 | [+0.200, +0.432] |
| compiler | structural | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.005 | [-0.150, +0.115] |
| compiler | fixed | 8192 | answerable_page_recall | 18 | 9 | +0.161 | [+0.025, +0.276] |
| compiler | fixed | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.179 | [+0.048, +0.292] |
| compiler | fixed | 8192 | quoted_exact_quote_recall | 18 | 9 | -0.056 | [-0.167, +0.031] |
| compiler | structural | 8192 | answerable_page_recall | 18 | 9 | +0.167 | [-0.005, +0.312] |
| compiler | structural | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.244 | [+0.095, +0.367] |
| compiler | structural | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.032 | [-0.132, +0.178] |
| compiler | fixed | 16384 | answerable_page_recall | 18 | 9 | +0.055 | [-0.050, +0.127] |
| compiler | fixed | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.077 | [-0.031, +0.156] |
| compiler | fixed | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.000 | [-0.037, +0.037] |
| compiler | structural | 16384 | answerable_page_recall | 18 | 9 | +0.101 | [-0.015, +0.224] |
| compiler | structural | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.183 | [+0.051, +0.309] |
| compiler | structural | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.060 | [-0.118, +0.202] |

## Non-inferiority check

Margin: **-0.03** on answerable page recall. A check passes when the lower bound of the paired 95% interval is strictly above the margin. Page recall alone decides the verdict, as specified; the content-verified and quote intervals are shown beside it because page recall has moved opposite to quote recall on this benchmark, and a verdict read without them is a verdict read half-blind.

**A pass is confirmatory only where one unit cannot cross the margin on its own.** That needs at least 34 eligible questions and at least 34 source clusters: below either, a delta moves by more than 0.03 when a single question flips or a single cluster is resampled away, so the interval is being tested against a threshold finer than the instrument that produced it. Every such row is reported as *screening*, and a screening pass is not evidence of non-inferiority.

| Baseline | Budget | Page delta | Page 95% interval | Status | Content-verified delta | Quote delta |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| fixed | 2048 | +0.346 | [+0.173, +0.503] | screening pass | +0.365 [+0.201, +0.514] | -0.028 [-0.088, +0.000] |
| structural | 2048 | +0.259 | [+0.062, +0.430] | screening pass | +0.311 [+0.130, +0.461] | -0.097 [-0.224, -0.011] |
| fixed | 4096 | +0.290 | [+0.153, +0.422] | screening pass | +0.304 [+0.177, +0.424] | +0.056 [+0.000, +0.125] |
| structural | 4096 | +0.235 | [+0.072, +0.383] | screening pass | +0.324 [+0.200, +0.432] | +0.005 [-0.150, +0.115] |
| fixed | 8192 | +0.161 | [+0.025, +0.276] | screening pass | +0.179 [+0.048, +0.292] | -0.056 [-0.167, +0.031] |
| structural | 8192 | +0.167 | [-0.005, +0.312] | screening pass | +0.244 [+0.095, +0.367] | +0.032 [-0.132, +0.178] |
| fixed | 16384 | +0.055 | [-0.050, +0.127] | screening fail | +0.077 [-0.031, +0.156] | +0.000 [-0.037, +0.037] |
| structural | 16384 | +0.101 | [-0.015, +0.224] | screening pass | +0.183 [+0.051, +0.309] | +0.060 [-0.118, +0.202] |

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
