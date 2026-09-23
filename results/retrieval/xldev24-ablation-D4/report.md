# Retrieval Decision Report: xldev24-D4-6cc7fd9

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.714 | 0.375 | 0.323 | 0.250 | 2046.9 | 0.0 | 0.092 | 1400.40 |
| compiler | 4096 | 0.802 | 0.542 | 0.413 | 0.333 | 4094.1 | 844.0 | 0.130 | 1339.64 |
| compiler | 8192 | 0.856 | 0.583 | 0.444 | 0.333 | 7772.5 | 1392.0 | 0.183 | 1355.88 |
| compiler | 16384 | 0.876 | 0.583 | 0.486 | 0.375 | 13953.0 | 1392.0 | 0.239 | 1372.68 |
| fixed | 2048 | 0.468 | 0.292 | 0.347 | 0.333 | 2015.3 | 0.0 | 0.077 | 358.50 |
| fixed | 4096 | 0.594 | 0.333 | 0.361 | 0.333 | 4035.1 | 0.0 | 0.115 | 358.01 |
| fixed | 8192 | 0.739 | 0.417 | 0.465 | 0.375 | 8044.4 | 0.0 | 0.177 | 358.09 |
| fixed | 16384 | 0.843 | 0.583 | 0.476 | 0.375 | 16136.9 | 2283.5 | 0.241 | 358.11 |
| long_context | 2048 | 0.374 | 0.292 | 0.260 | 0.250 | 2048.0 | 0.0 | 0.081 | 64.31 |
| long_context | 4096 | 0.528 | 0.333 | 0.368 | 0.292 | 4096.0 | 0.0 | 0.103 | 64.10 |
| long_context | 8192 | 0.652 | 0.375 | 0.378 | 0.292 | 8192.0 | 0.0 | 0.129 | 64.62 |
| long_context | 16384 | 0.782 | 0.667 | 0.424 | 0.292 | 15981.8 | 4541.5 | 0.168 | 65.63 |
| structural | 2048 | 0.533 | 0.292 | 0.399 | 0.375 | 2031.0 | 0.0 | 0.067 | 347.59 |
| structural | 4096 | 0.634 | 0.333 | 0.399 | 0.375 | 4061.0 | 0.0 | 0.102 | 347.17 |
| structural | 8192 | 0.734 | 0.458 | 0.399 | 0.375 | 8154.2 | 0.0 | 0.128 | 347.09 |
| structural | 16384 | 0.808 | 0.542 | 0.431 | 0.375 | 15065.3 | 1583.0 | 0.150 | 347.13 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.083 full-coverage, +0.181 recall.
- 4096 tokens: compiler vs best baseline: +0.208 full-coverage, +0.167 recall.
- 8192 tokens: compiler vs best baseline: +0.125 full-coverage, +0.122 recall.
- 16384 tokens: compiler vs best baseline: +0.000 full-coverage, +0.034 recall.

## Audited metrics

Page metrics below cover only questions that are marked answerable and carry at least one annotated gold page; a question with no annotated gold page is excluded even when it is marked answerable. Quote metrics include only questions with a non-empty gold quote. Content-verified pages require the full normalized source-node text to be present in the emitted context.

| System | Budget | Answerable gold-page n | Page recall | Content-verified recall | Quoted n | Exact quote recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 18 | 0.619 | 0.619 | 18 | 0.097 |
| compiler | 4096 | 18 | 0.736 | 0.736 | 18 | 0.218 |
| compiler | 8192 | 18 | 0.808 | 0.808 | 18 | 0.259 |
| compiler | 16384 | 18 | 0.835 | 0.835 | 18 | 0.315 |
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
| compiler | fixed | 2048 | answerable_page_recall | 18 | 9 | +0.328 | [+0.147, +0.490] |
| compiler | fixed | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.347 | [+0.172, +0.501] |
| compiler | fixed | 2048 | quoted_exact_quote_recall | 18 | 9 | -0.032 | [-0.108, +0.028] |
| compiler | structural | 2048 | answerable_page_recall | 18 | 9 | +0.241 | [+0.030, +0.419] |
| compiler | structural | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.294 | [+0.103, +0.451] |
| compiler | structural | 2048 | quoted_exact_quote_recall | 18 | 9 | -0.102 | [-0.235, +0.000] |
| compiler | fixed | 4096 | answerable_page_recall | 18 | 9 | +0.277 | [+0.128, +0.412] |
| compiler | fixed | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.291 | [+0.150, +0.415] |
| compiler | fixed | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.069 | [+0.000, +0.132] |
| compiler | structural | 4096 | answerable_page_recall | 18 | 9 | +0.223 | [+0.044, +0.374] |
| compiler | structural | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.312 | [+0.174, +0.423] |
| compiler | structural | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.019 | [-0.139, +0.125] |
| compiler | fixed | 8192 | answerable_page_recall | 18 | 9 | +0.156 | [+0.018, +0.270] |
| compiler | fixed | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.174 | [+0.043, +0.286] |
| compiler | fixed | 8192 | quoted_exact_quote_recall | 18 | 9 | -0.028 | [-0.150, +0.071] |
| compiler | structural | 8192 | answerable_page_recall | 18 | 9 | +0.162 | [-0.011, +0.307] |
| compiler | structural | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.239 | [+0.090, +0.361] |
| compiler | structural | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.060 | [-0.114, +0.202] |
| compiler | fixed | 16384 | answerable_page_recall | 18 | 9 | +0.045 | [-0.065, +0.119] |
| compiler | fixed | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.067 | [-0.046, +0.144] |
| compiler | fixed | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.014 | [+0.000, +0.039] |
| compiler | structural | 16384 | answerable_page_recall | 18 | 9 | +0.091 | [-0.029, +0.215] |
| compiler | structural | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.173 | [+0.040, +0.296] |
| compiler | structural | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.074 | [-0.103, +0.210] |

## Non-inferiority check

Margin: **-0.03** on answerable page recall. A check passes when the lower bound of the paired 95% interval is strictly above the margin. Page recall alone decides the verdict, as specified; the content-verified and quote intervals are shown beside it because page recall has moved opposite to quote recall on this benchmark, and a verdict read without them is a verdict read half-blind.

**A pass is confirmatory only where one unit cannot cross the margin on its own.** That needs at least 34 eligible questions and at least 34 source clusters: below either, a delta moves by more than 0.03 when a single question flips or a single cluster is resampled away, so the interval is being tested against a threshold finer than the instrument that produced it. Every such row is reported as *screening*, and a screening pass is not evidence of non-inferiority.

| Baseline | Budget | Page delta | Page 95% interval | Status | Content-verified delta | Quote delta |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| fixed | 2048 | +0.328 | [+0.147, +0.490] | screening pass | +0.347 [+0.172, +0.501] | -0.032 [-0.108, +0.028] |
| structural | 2048 | +0.241 | [+0.030, +0.419] | screening pass | +0.294 [+0.103, +0.451] | -0.102 [-0.235, +0.000] |
| fixed | 4096 | +0.277 | [+0.128, +0.412] | screening pass | +0.291 [+0.150, +0.415] | +0.069 [+0.000, +0.132] |
| structural | 4096 | +0.223 | [+0.044, +0.374] | screening pass | +0.312 [+0.174, +0.423] | +0.019 [-0.139, +0.125] |
| fixed | 8192 | +0.156 | [+0.018, +0.270] | screening pass | +0.174 [+0.043, +0.286] | -0.028 [-0.150, +0.071] |
| structural | 8192 | +0.162 | [-0.011, +0.307] | screening pass | +0.239 [+0.090, +0.361] | +0.060 [-0.114, +0.202] |
| fixed | 16384 | +0.045 | [-0.065, +0.119] | screening fail | +0.067 [-0.046, +0.144] | +0.014 [+0.000, +0.039] |
| structural | 16384 | +0.091 | [-0.029, +0.215] | screening pass | +0.173 [+0.040, +0.296] | +0.074 [-0.103, +0.210] |

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
