# Retrieval Decision Report: xldev24-SHIPPED-6cc7fd9

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.728 | 0.417 | 0.354 | 0.292 | 2046.7 | 0.0 | 0.089 | 1259.94 |
| compiler | 4096 | 0.794 | 0.500 | 0.424 | 0.333 | 3922.8 | 413.0 | 0.129 | 1154.42 |
| compiler | 8192 | 0.858 | 0.583 | 0.476 | 0.375 | 7473.4 | 1213.5 | 0.184 | 1170.99 |
| compiler | 16384 | 0.906 | 0.583 | 0.528 | 0.417 | 16220.0 | 1213.5 | 0.284 | 2161.09 |
| fixed | 2048 | 0.468 | 0.292 | 0.347 | 0.333 | 2015.3 | 0.0 | 0.077 | 346.00 |
| fixed | 4096 | 0.594 | 0.333 | 0.361 | 0.333 | 4035.1 | 0.0 | 0.115 | 345.57 |
| fixed | 8192 | 0.739 | 0.417 | 0.465 | 0.375 | 8044.4 | 0.0 | 0.177 | 345.65 |
| fixed | 16384 | 0.843 | 0.583 | 0.476 | 0.375 | 16136.9 | 2283.5 | 0.241 | 345.65 |
| long_context | 2048 | 0.374 | 0.292 | 0.260 | 0.250 | 2048.0 | 0.0 | 0.081 | 56.24 |
| long_context | 4096 | 0.528 | 0.333 | 0.368 | 0.292 | 4096.0 | 0.0 | 0.103 | 55.92 |
| long_context | 8192 | 0.652 | 0.375 | 0.378 | 0.292 | 8192.0 | 0.0 | 0.129 | 56.56 |
| long_context | 16384 | 0.782 | 0.667 | 0.424 | 0.292 | 15981.8 | 4541.5 | 0.168 | 87.48 |
| structural | 2048 | 0.533 | 0.292 | 0.399 | 0.375 | 2031.0 | 0.0 | 0.067 | 356.44 |
| structural | 4096 | 0.634 | 0.333 | 0.399 | 0.375 | 4061.0 | 0.0 | 0.102 | 356.02 |
| structural | 8192 | 0.734 | 0.458 | 0.399 | 0.375 | 8154.2 | 0.0 | 0.128 | 356.11 |
| structural | 16384 | 0.808 | 0.542 | 0.431 | 0.375 | 15065.3 | 1583.0 | 0.150 | 355.88 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.125 full-coverage, +0.194 recall.
- 4096 tokens: compiler vs best baseline: +0.167 full-coverage, +0.159 recall.
- 8192 tokens: compiler vs best baseline: +0.125 full-coverage, +0.124 recall.
- 16384 tokens: compiler vs best baseline: +0.000 full-coverage, +0.064 recall.

## Audited metrics

Page metrics below cover only questions that are marked answerable and carry at least one annotated gold page; a question with no annotated gold page is excluded even when it is marked answerable. Quote metrics include only questions with a non-empty gold quote. Content-verified pages require the full normalized source-node text to be present in the emitted context.

| System | Budget | Answerable gold-page n | Page recall | Content-verified recall | Quoted n | Exact quote recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 18 | 0.637 | 0.631 | 18 | 0.139 |
| compiler | 4096 | 18 | 0.725 | 0.719 | 18 | 0.231 |
| compiler | 8192 | 18 | 0.811 | 0.806 | 18 | 0.301 |
| compiler | 16384 | 18 | 0.875 | 0.869 | 18 | 0.370 |
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
| compiler | fixed | 2048 | answerable_page_recall | 18 | 9 | +0.346 | [+0.165, +0.515] |
| compiler | fixed | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.359 | [+0.181, +0.524] |
| compiler | fixed | 2048 | quoted_exact_quote_recall | 18 | 9 | +0.009 | [-0.105, +0.157] |
| compiler | structural | 2048 | answerable_page_recall | 18 | 9 | +0.259 | [+0.062, +0.435] |
| compiler | structural | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.306 | [+0.124, +0.466] |
| compiler | structural | 2048 | quoted_exact_quote_recall | 18 | 9 | -0.060 | [-0.125, -0.011] |
| compiler | fixed | 4096 | answerable_page_recall | 18 | 9 | +0.266 | [+0.122, +0.406] |
| compiler | fixed | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.275 | [+0.139, +0.404] |
| compiler | fixed | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.083 | [+0.000, +0.219] |
| compiler | structural | 4096 | answerable_page_recall | 18 | 9 | +0.212 | [+0.046, +0.363] |
| compiler | structural | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.295 | [+0.159, +0.413] |
| compiler | structural | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.032 | [-0.028, +0.111] |
| compiler | fixed | 8192 | answerable_page_recall | 18 | 9 | +0.158 | [+0.021, +0.272] |
| compiler | fixed | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.171 | [+0.040, +0.285] |
| compiler | fixed | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.014 | [-0.139, +0.188] |
| compiler | structural | 8192 | answerable_page_recall | 18 | 9 | +0.165 | [-0.006, +0.308] |
| compiler | structural | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.236 | [+0.087, +0.360] |
| compiler | structural | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.102 | [+0.024, +0.206] |
| compiler | fixed | 16384 | answerable_page_recall | 18 | 9 | +0.085 | [-0.010, +0.165] |
| compiler | fixed | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.101 | [+0.002, +0.186] |
| compiler | fixed | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.069 | [+0.000, +0.191] |
| compiler | structural | 16384 | answerable_page_recall | 18 | 9 | +0.131 | [+0.016, +0.273] |
| compiler | structural | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.207 | [+0.075, +0.348] |
| compiler | structural | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.130 | [+0.054, +0.219] |

## Non-inferiority check

Margin: **-0.03** on answerable page recall. A check passes when the lower bound of the paired 95% interval is strictly above the margin. Page recall alone decides the verdict, as specified; the content-verified and quote intervals are shown beside it because page recall has moved opposite to quote recall on this benchmark, and a verdict read without them is a verdict read half-blind.

**A pass is confirmatory only where one unit cannot cross the margin on its own.** That needs at least 34 eligible questions and at least 34 source clusters: below either, a delta moves by more than 0.03 when a single question flips or a single cluster is resampled away, so the interval is being tested against a threshold finer than the instrument that produced it. Every such row is reported as *screening*, and a screening pass is not evidence of non-inferiority.

| Baseline | Budget | Page delta | Page 95% interval | Status | Content-verified delta | Quote delta |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| fixed | 2048 | +0.346 | [+0.165, +0.515] | screening pass | +0.359 [+0.181, +0.524] | +0.009 [-0.105, +0.157] |
| structural | 2048 | +0.259 | [+0.062, +0.435] | screening pass | +0.306 [+0.124, +0.466] | -0.060 [-0.125, -0.011] |
| fixed | 4096 | +0.266 | [+0.122, +0.406] | screening pass | +0.275 [+0.139, +0.404] | +0.083 [+0.000, +0.219] |
| structural | 4096 | +0.212 | [+0.046, +0.363] | screening pass | +0.295 [+0.159, +0.413] | +0.032 [-0.028, +0.111] |
| fixed | 8192 | +0.158 | [+0.021, +0.272] | screening pass | +0.171 [+0.040, +0.285] | +0.014 [-0.139, +0.188] |
| structural | 8192 | +0.165 | [-0.006, +0.308] | screening pass | +0.236 [+0.087, +0.360] | +0.102 [+0.024, +0.206] |
| fixed | 16384 | +0.085 | [-0.010, +0.165] | screening pass | +0.101 [+0.002, +0.186] | +0.069 [+0.000, +0.191] |
| structural | 16384 | +0.131 | [+0.016, +0.273] | screening pass | +0.207 [+0.075, +0.348] | +0.130 [+0.054, +0.219] |

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
