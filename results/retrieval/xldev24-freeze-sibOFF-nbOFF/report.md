# Retrieval Decision Report: xldev24-v2-sibOFF-nbOFF-08acd28

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.728 | 0.417 | 0.389 | 0.292 | 2046.7 | 0.0 | 0.089 | 1155.36 |
| compiler | 4096 | 0.794 | 0.500 | 0.458 | 0.333 | 3922.8 | 413.0 | 0.129 | 1060.85 |
| compiler | 8192 | 0.858 | 0.583 | 0.510 | 0.375 | 7473.4 | 1213.5 | 0.184 | 1071.92 |
| compiler | 16384 | 0.888 | 0.583 | 0.552 | 0.417 | 13286.8 | 1213.5 | 0.241 | 1088.82 |
| fixed | 2048 | 0.468 | 0.292 | 0.382 | 0.333 | 2015.3 | 0.0 | 0.077 | 305.51 |
| fixed | 4096 | 0.594 | 0.333 | 0.406 | 0.333 | 4035.1 | 0.0 | 0.115 | 304.93 |
| fixed | 8192 | 0.739 | 0.417 | 0.510 | 0.375 | 8044.4 | 0.0 | 0.177 | 304.91 |
| fixed | 16384 | 0.843 | 0.583 | 0.521 | 0.375 | 16136.9 | 2283.5 | 0.241 | 305.11 |
| long_context | 2048 | 0.374 | 0.292 | 0.260 | 0.250 | 2048.0 | 0.0 | 0.081 | 61.12 |
| long_context | 4096 | 0.528 | 0.333 | 0.368 | 0.292 | 4096.0 | 0.0 | 0.103 | 60.73 |
| long_context | 8192 | 0.652 | 0.375 | 0.389 | 0.292 | 8192.0 | 0.0 | 0.129 | 61.28 |
| long_context | 16384 | 0.782 | 0.667 | 0.434 | 0.292 | 15981.8 | 4541.5 | 0.168 | 62.96 |
| structural | 2048 | 0.533 | 0.292 | 0.444 | 0.375 | 2031.0 | 0.0 | 0.067 | 334.47 |
| structural | 4096 | 0.634 | 0.333 | 0.444 | 0.375 | 4061.0 | 0.0 | 0.102 | 333.99 |
| structural | 8192 | 0.734 | 0.458 | 0.444 | 0.375 | 8154.2 | 0.0 | 0.128 | 333.97 |
| structural | 16384 | 0.808 | 0.542 | 0.476 | 0.375 | 15065.3 | 1583.0 | 0.150 | 334.13 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.125 full-coverage, +0.194 recall.
- 4096 tokens: compiler vs best baseline: +0.167 full-coverage, +0.159 recall.
- 8192 tokens: compiler vs best baseline: +0.125 full-coverage, +0.124 recall.
- 16384 tokens: compiler vs best baseline: +0.000 full-coverage, +0.045 recall.

## Audited metrics

Page metrics below cover only questions that are marked answerable and carry at least one annotated gold page; a question with no annotated gold page is excluded even when it is marked answerable. Quote metrics include only questions with a non-empty gold quote. Content-verified pages require the full normalized source-node text to be present in the emitted context.

Quote-match policy: **`nfkc-unified-punctuation-ordered-elision-v2`**. Quote figures are comparable only against artifacts carrying the same policy; an artifact without the field is `literal-casefold-v1`, which matched a gold quote only where it appeared verbatim after casefolding and whitespace collapse.

| System | Budget | Answerable gold-page n | Page recall | Content-verified recall | Quoted n | Exact quote recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 18 | 0.637 | 0.631 | 18 | 0.185 |
| compiler | 4096 | 18 | 0.725 | 0.719 | 18 | 0.278 |
| compiler | 8192 | 18 | 0.811 | 0.806 | 18 | 0.347 |
| compiler | 16384 | 18 | 0.851 | 0.845 | 18 | 0.403 |
| fixed | 2048 | 18 | 0.291 | 0.272 | 18 | 0.176 |
| fixed | 4096 | 18 | 0.458 | 0.445 | 18 | 0.208 |
| fixed | 8192 | 18 | 0.653 | 0.634 | 18 | 0.347 |
| fixed | 16384 | 18 | 0.790 | 0.768 | 18 | 0.361 |
| long_context | 2048 | 18 | 0.166 | 0.166 | 18 | 0.014 |
| long_context | 4096 | 18 | 0.370 | 0.370 | 18 | 0.157 |
| long_context | 8192 | 18 | 0.536 | 0.536 | 18 | 0.185 |
| long_context | 16384 | 18 | 0.710 | 0.710 | 18 | 0.245 |
| structural | 2048 | 18 | 0.377 | 0.325 | 18 | 0.259 |
| structural | 4096 | 18 | 0.513 | 0.424 | 18 | 0.259 |
| structural | 8192 | 18 | 0.646 | 0.570 | 18 | 0.259 |
| structural | 16384 | 18 | 0.744 | 0.662 | 18 | 0.301 |

## Paired source-cluster bootstrap

Intervals are descriptive 95% paired bootstrap intervals. The sampling unit is the sorted source-document scope; 10,000 resamples are used by default.

| Treatment | Baseline | Budget | Metric | n | Clusters | Delta | 95% interval |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| compiler | fixed | 2048 | answerable_page_recall | 18 | 9 | +0.346 | [+0.165, +0.515] |
| compiler | fixed | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.359 | [+0.181, +0.524] |
| compiler | fixed | 2048 | quoted_exact_quote_recall | 18 | 9 | +0.009 | [-0.105, +0.157] |
| compiler | structural | 2048 | answerable_page_recall | 18 | 9 | +0.259 | [+0.062, +0.435] |
| compiler | structural | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.306 | [+0.124, +0.466] |
| compiler | structural | 2048 | quoted_exact_quote_recall | 18 | 9 | -0.074 | [-0.142, -0.016] |
| compiler | fixed | 4096 | answerable_page_recall | 18 | 9 | +0.266 | [+0.122, +0.406] |
| compiler | fixed | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.275 | [+0.139, +0.404] |
| compiler | fixed | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.069 | [-0.026, +0.208] |
| compiler | structural | 4096 | answerable_page_recall | 18 | 9 | +0.212 | [+0.046, +0.363] |
| compiler | structural | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.295 | [+0.159, +0.413] |
| compiler | structural | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.019 | [-0.061, +0.108] |
| compiler | fixed | 8192 | answerable_page_recall | 18 | 9 | +0.158 | [+0.021, +0.272] |
| compiler | fixed | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.171 | [+0.040, +0.285] |
| compiler | fixed | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.000 | [-0.145, +0.172] |
| compiler | structural | 8192 | answerable_page_recall | 18 | 9 | +0.165 | [-0.006, +0.308] |
| compiler | structural | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.236 | [+0.087, +0.360] |
| compiler | structural | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.088 | [+0.012, +0.194] |
| compiler | fixed | 16384 | answerable_page_recall | 18 | 9 | +0.061 | [-0.047, +0.133] |
| compiler | fixed | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.077 | [-0.031, +0.156] |
| compiler | fixed | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.042 | [-0.036, +0.176] |
| compiler | structural | 16384 | answerable_page_recall | 18 | 9 | +0.107 | [-0.009, +0.229] |
| compiler | structural | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.183 | [+0.051, +0.309] |
| compiler | structural | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.102 | [+0.022, +0.206] |

## Non-inferiority check

Margin: **-0.03** on answerable page recall. A check passes when the lower bound of the paired 95% interval is strictly above the margin. Page recall alone decides the verdict, as specified; the content-verified and quote intervals are shown beside it because page recall has moved opposite to quote recall on this benchmark, and a verdict read without them is a verdict read half-blind.

**A pass is confirmatory only where one unit cannot cross the margin on its own.** That needs at least 34 eligible questions and at least 34 source clusters: below either, a delta moves by more than 0.03 when a single question flips or a single cluster is resampled away, so the interval is being tested against a threshold finer than the instrument that produced it. Every such row is reported as *screening*, and a screening pass is not evidence of non-inferiority.

| Baseline | Budget | Page delta | Page 95% interval | Status | Content-verified delta | Quote delta |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| fixed | 2048 | +0.346 | [+0.165, +0.515] | screening pass | +0.359 [+0.181, +0.524] | +0.009 [-0.105, +0.157] |
| structural | 2048 | +0.259 | [+0.062, +0.435] | screening pass | +0.306 [+0.124, +0.466] | -0.074 [-0.142, -0.016] |
| fixed | 4096 | +0.266 | [+0.122, +0.406] | screening pass | +0.275 [+0.139, +0.404] | +0.069 [-0.026, +0.208] |
| structural | 4096 | +0.212 | [+0.046, +0.363] | screening pass | +0.295 [+0.159, +0.413] | +0.019 [-0.061, +0.108] |
| fixed | 8192 | +0.158 | [+0.021, +0.272] | screening pass | +0.171 [+0.040, +0.285] | +0.000 [-0.145, +0.172] |
| structural | 8192 | +0.165 | [-0.006, +0.308] | screening pass | +0.236 [+0.087, +0.360] | +0.088 [+0.012, +0.194] |
| fixed | 16384 | +0.061 | [-0.047, +0.133] | screening fail | +0.077 [-0.031, +0.156] | +0.042 [-0.036, +0.176] |
| structural | 16384 | +0.107 | [-0.009, +0.229] | screening pass | +0.183 [+0.051, +0.309] | +0.102 [+0.022, +0.206] |

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
