# Retrieval Decision Report: xldev24-headingfree-edd196f

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.744 | 0.417 | 0.382 | 0.292 | 2045.3 | 0.0 | 0.073 | 1256.27 |
| compiler | 4096 | 0.816 | 0.500 | 0.413 | 0.292 | 3920.6 | 382.0 | 0.109 | 1169.21 |
| compiler | 8192 | 0.895 | 0.625 | 0.448 | 0.292 | 7503.7 | 1019.0 | 0.167 | 1161.92 |
| compiler | 16384 | 0.934 | 0.750 | 0.490 | 0.375 | 16312.3 | 1877.0 | 0.258 | 2119.36 |
| fixed | 2048 | 0.474 | 0.292 | 0.326 | 0.292 | 2013.9 | 0.0 | 0.085 | 327.94 |
| fixed | 4096 | 0.631 | 0.375 | 0.340 | 0.292 | 4031.2 | 0.0 | 0.126 | 327.40 |
| fixed | 8192 | 0.755 | 0.458 | 0.465 | 0.375 | 8035.3 | 0.0 | 0.185 | 327.43 |
| fixed | 16384 | 0.836 | 0.625 | 0.476 | 0.375 | 16168.1 | 2542.0 | 0.241 | 327.55 |
| long_context | 2048 | 0.425 | 0.292 | 0.260 | 0.250 | 2048.0 | 0.0 | 0.084 | 49.17 |
| long_context | 4096 | 0.559 | 0.375 | 0.326 | 0.250 | 4096.0 | 0.0 | 0.098 | 49.37 |
| long_context | 8192 | 0.652 | 0.375 | 0.378 | 0.292 | 8192.0 | 0.0 | 0.130 | 49.34 |
| long_context | 16384 | 0.749 | 0.583 | 0.434 | 0.292 | 15981.8 | 2985.5 | 0.171 | 50.76 |
| structural | 2048 | 0.533 | 0.292 | 0.399 | 0.375 | 2031.0 | 0.0 | 0.067 | 346.65 |
| structural | 4096 | 0.634 | 0.333 | 0.399 | 0.375 | 4061.0 | 0.0 | 0.102 | 346.18 |
| structural | 8192 | 0.734 | 0.458 | 0.399 | 0.375 | 8154.2 | 0.0 | 0.128 | 346.17 |
| structural | 16384 | 0.808 | 0.542 | 0.431 | 0.375 | 15065.3 | 1583.0 | 0.150 | 346.10 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.125 full-coverage, +0.211 recall.
- 4096 tokens: compiler vs best baseline: +0.125 full-coverage, +0.185 recall.
- 8192 tokens: compiler vs best baseline: +0.167 full-coverage, +0.140 recall.
- 16384 tokens: compiler vs best baseline: +0.125 full-coverage, +0.098 recall.

## Audited metrics

Page metrics below cover only questions that are marked answerable and carry at least one annotated gold page; a question with no annotated gold page is excluded even when it is marked answerable. Quote metrics include only questions with a non-empty gold quote. Content-verified pages require the full normalized source-node text to be present in the emitted context.

| System | Budget | Answerable gold-page n | Page recall | Content-verified recall | Quoted n | Exact quote recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 18 | 0.659 | 0.654 | 18 | 0.176 |
| compiler | 4096 | 18 | 0.755 | 0.749 | 18 | 0.218 |
| compiler | 8192 | 18 | 0.860 | 0.855 | 18 | 0.264 |
| compiler | 16384 | 18 | 0.912 | 0.906 | 18 | 0.319 |
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
| compiler | fixed | 2048 | answerable_page_recall | 18 | 9 | +0.361 | [+0.210, +0.526] |
| compiler | fixed | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.379 | [+0.236, +0.534] |
| compiler | fixed | 2048 | quoted_exact_quote_recall | 18 | 9 | +0.074 | [-0.048, +0.206] |
| compiler | structural | 2048 | answerable_page_recall | 18 | 9 | +0.282 | [+0.085, +0.458] |
| compiler | structural | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.328 | [+0.151, +0.484] |
| compiler | structural | 2048 | quoted_exact_quote_recall | 18 | 9 | -0.023 | [-0.100, +0.039] |
| compiler | fixed | 4096 | answerable_page_recall | 18 | 9 | +0.247 | [+0.114, +0.376] |
| compiler | fixed | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.265 | [+0.129, +0.387] |
| compiler | fixed | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.097 | [-0.069, +0.244] |
| compiler | structural | 4096 | answerable_page_recall | 18 | 9 | +0.242 | [+0.089, +0.387] |
| compiler | structural | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.325 | [+0.210, +0.435] |
| compiler | structural | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.019 | [-0.079, +0.119] |
| compiler | fixed | 8192 | answerable_page_recall | 18 | 9 | +0.186 | [+0.068, +0.295] |
| compiler | fixed | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.205 | [+0.093, +0.307] |
| compiler | fixed | 8192 | quoted_exact_quote_recall | 18 | 9 | -0.023 | [-0.181, +0.139] |
| compiler | structural | 8192 | answerable_page_recall | 18 | 9 | +0.214 | [+0.063, +0.353] |
| compiler | structural | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.285 | [+0.152, +0.404] |
| compiler | structural | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.065 | [-0.062, +0.196] |
| compiler | fixed | 16384 | answerable_page_recall | 18 | 9 | +0.130 | [+0.032, +0.226] |
| compiler | fixed | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.149 | [+0.041, +0.252] |
| compiler | fixed | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.019 | [-0.150, +0.176] |
| compiler | structural | 16384 | answerable_page_recall | 18 | 9 | +0.168 | [+0.042, +0.308] |
| compiler | structural | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.244 | [+0.111, +0.376] |
| compiler | structural | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.079 | [-0.048, +0.202] |

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
