# Retrieval Decision Report: xldev24-rebaseline-e28b247

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.727 | 0.417 | 0.368 | 0.292 | 2046.5 | 0.0 | 0.088 | 1318.81 |
| compiler | 4096 | 0.791 | 0.458 | 0.382 | 0.292 | 3923.0 | 0.0 | 0.122 | 1220.94 |
| compiler | 8192 | 0.868 | 0.583 | 0.476 | 0.375 | 7506.8 | 1230.0 | 0.185 | 1238.63 |
| compiler | 16384 | 0.922 | 0.667 | 0.517 | 0.417 | 16244.9 | 2188.5 | 0.290 | 2282.12 |
| fixed | 2048 | 0.474 | 0.292 | 0.326 | 0.292 | 2013.9 | 0.0 | 0.085 | 385.33 |
| fixed | 4096 | 0.631 | 0.375 | 0.340 | 0.292 | 4031.2 | 0.0 | 0.126 | 382.29 |
| fixed | 8192 | 0.755 | 0.458 | 0.465 | 0.375 | 8035.3 | 0.0 | 0.185 | 383.22 |
| fixed | 16384 | 0.836 | 0.625 | 0.476 | 0.375 | 16168.1 | 2542.0 | 0.241 | 382.30 |
| long_context | 2048 | 0.425 | 0.292 | 0.260 | 0.250 | 2048.0 | 0.0 | 0.084 | 60.94 |
| long_context | 4096 | 0.559 | 0.375 | 0.326 | 0.250 | 4096.0 | 0.0 | 0.098 | 59.85 |
| long_context | 8192 | 0.652 | 0.375 | 0.378 | 0.292 | 8192.0 | 0.0 | 0.130 | 60.20 |
| long_context | 16384 | 0.749 | 0.583 | 0.434 | 0.292 | 15981.8 | 2985.5 | 0.171 | 61.18 |
| structural | 2048 | 0.533 | 0.292 | 0.399 | 0.375 | 2031.0 | 0.0 | 0.067 | 355.37 |
| structural | 4096 | 0.634 | 0.333 | 0.399 | 0.375 | 4061.0 | 0.0 | 0.102 | 354.38 |
| structural | 8192 | 0.734 | 0.458 | 0.399 | 0.375 | 8154.2 | 0.0 | 0.128 | 354.61 |
| structural | 16384 | 0.808 | 0.542 | 0.431 | 0.375 | 15065.3 | 1583.0 | 0.150 | 355.05 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.125 full-coverage, +0.194 recall.
- 4096 tokens: compiler vs best baseline: +0.083 full-coverage, +0.160 recall.
- 8192 tokens: compiler vs best baseline: +0.125 full-coverage, +0.113 recall.
- 16384 tokens: compiler vs best baseline: +0.042 full-coverage, +0.086 recall.

## Audited metrics

Page metrics below cover only questions that are marked answerable and carry at least one annotated gold page; a question with no annotated gold page is excluded even when it is marked answerable. Quote metrics include only questions with a non-empty gold quote. Content-verified pages require the full normalized source-node text to be present in the emitted context.

| System | Budget | Answerable gold-page n | Page recall | Content-verified recall | Quoted n | Exact quote recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 18 | 0.636 | 0.630 | 18 | 0.157 |
| compiler | 4096 | 18 | 0.721 | 0.716 | 18 | 0.176 |
| compiler | 8192 | 18 | 0.824 | 0.819 | 18 | 0.301 |
| compiler | 16384 | 18 | 0.896 | 0.890 | 18 | 0.356 |
| fixed | 2048 | 18 | 0.298 | 0.275 | 18 | 0.102 |
| fixed | 4096 | 18 | 0.508 | 0.484 | 18 | 0.120 |
| fixed | 8192 | 18 | 0.674 | 0.649 | 18 | 0.287 |
| fixed | 16384 | 18 | 0.781 | 0.757 | 18 | 0.301 |
| long_context | 2048 | 18 | 0.233 | 0.233 | 18 | 0.014 |
| long_context | 4096 | 18 | 0.413 | 0.413 | 18 | 0.102 |
| long_context | 8192 | 18 | 0.535 | 0.535 | 18 | 0.171 |
| long_context | 16384 | 18 | 0.665 | 0.665 | 18 | 0.245 |
| structural | 2048 | 18 | 0.377 | 0.325 | 18 | 0.199 |
| structural | 4096 | 18 | 0.513 | 0.424 | 18 | 0.199 |
| structural | 8192 | 18 | 0.646 | 0.570 | 18 | 0.199 |
| structural | 16384 | 18 | 0.744 | 0.662 | 18 | 0.241 |

## Paired source-cluster bootstrap

Intervals are descriptive 95% paired bootstrap intervals. The sampling unit is the sorted source-document scope; 10,000 resamples are used by default.

| Treatment | Baseline | Budget | Metric | n | Clusters | Delta | 95% interval |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| compiler | fixed | 2048 | answerable_page_recall | 18 | 9 | +0.337 | [+0.170, +0.513] |
| compiler | fixed | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.356 | [+0.182, +0.523] |
| compiler | fixed | 2048 | quoted_exact_quote_recall | 18 | 9 | +0.056 | [-0.062, +0.194] |
| compiler | structural | 2048 | answerable_page_recall | 18 | 9 | +0.258 | [+0.051, +0.443] |
| compiler | structural | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.305 | [+0.115, +0.472] |
| compiler | structural | 2048 | quoted_exact_quote_recall | 18 | 9 | -0.042 | [-0.105, +0.000] |
| compiler | fixed | 4096 | answerable_page_recall | 18 | 9 | +0.213 | [+0.067, +0.353] |
| compiler | fixed | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.232 | [+0.087, +0.362] |
| compiler | fixed | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.056 | [-0.067, +0.192] |
| compiler | structural | 4096 | answerable_page_recall | 18 | 9 | +0.209 | [+0.034, +0.368] |
| compiler | structural | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.292 | [+0.144, +0.419] |
| compiler | structural | 4096 | quoted_exact_quote_recall | 18 | 9 | -0.023 | [-0.095, +0.044] |
| compiler | fixed | 8192 | answerable_page_recall | 18 | 9 | +0.150 | [-0.006, +0.274] |
| compiler | fixed | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.169 | [+0.029, +0.286] |
| compiler | fixed | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.014 | [-0.139, +0.188] |
| compiler | structural | 8192 | answerable_page_recall | 18 | 9 | +0.178 | [+0.010, +0.322] |
| compiler | structural | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.249 | [+0.097, +0.377] |
| compiler | structural | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.102 | [+0.024, +0.206] |
| compiler | fixed | 16384 | answerable_page_recall | 18 | 9 | +0.114 | [+0.027, +0.203] |
| compiler | fixed | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.133 | [+0.033, +0.230] |
| compiler | fixed | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.056 | [-0.029, +0.188] |
| compiler | structural | 16384 | answerable_page_recall | 18 | 9 | +0.152 | [+0.042, +0.288] |
| compiler | structural | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.228 | [+0.100, +0.365] |
| compiler | structural | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.116 | [+0.031, +0.213] |

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
