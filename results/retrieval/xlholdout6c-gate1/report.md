# Retrieval Decision Report: xlholdout6c-gate1-60e5836

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.580 | 0.167 | 0.450 | 0.333 | 2047.0 | 105.0 | 0.058 | 1767.19 |
| compiler | 4096 | 0.781 | 0.500 | 0.492 | 0.333 | 4041.0 | 3455.0 | 0.076 | 1780.72 |
| compiler | 8192 | 0.818 | 0.667 | 0.575 | 0.333 | 7454.8 | 3822.0 | 0.110 | 1826.63 |
| compiler | 16384 | 0.818 | 0.667 | 0.617 | 0.500 | 13743.5 | 3822.0 | 0.167 | 6010.78 |
| fixed | 2048 | 0.493 | 0.333 | 0.558 | 0.167 | 2006.0 | 1004.0 | 0.054 | 418.97 |
| fixed | 4096 | 0.619 | 0.333 | 0.683 | 0.333 | 4016.7 | 1004.0 | 0.075 | 418.17 |
| fixed | 8192 | 0.725 | 0.333 | 0.683 | 0.333 | 8013.5 | 1004.0 | 0.112 | 418.10 |
| fixed | 16384 | 0.754 | 0.333 | 0.850 | 0.667 | 16120.2 | 1004.0 | 0.156 | 418.35 |
| long_context | 2048 | 0.248 | 0.167 | 0.108 | 0.000 | 2048.0 | 2040.0 | 0.048 | 55.38 |
| long_context | 4096 | 0.434 | 0.167 | 0.358 | 0.167 | 4096.0 | 2573.0 | 0.082 | 52.85 |
| long_context | 8192 | 0.627 | 0.333 | 0.400 | 0.167 | 8192.0 | 5376.0 | 0.098 | 53.67 |
| long_context | 16384 | 0.786 | 0.500 | 0.692 | 0.333 | 16384.0 | 8304.0 | 0.117 | 55.67 |
| structural | 2048 | 0.407 | 0.167 | 0.542 | 0.333 | 2004.7 | 356.0 | 0.028 | 382.93 |
| structural | 4096 | 0.489 | 0.167 | 0.583 | 0.333 | 4075.2 | 356.0 | 0.045 | 382.40 |
| structural | 8192 | 0.542 | 0.167 | 0.583 | 0.333 | 8148.5 | 356.0 | 0.079 | 382.48 |
| structural | 16384 | 0.728 | 0.500 | 0.625 | 0.333 | 16321.2 | 9128.0 | 0.125 | 382.72 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: -0.167 full-coverage, +0.087 recall.
- 4096 tokens: compiler vs best baseline: +0.167 full-coverage, +0.162 recall.
- 8192 tokens: compiler vs best baseline: +0.333 full-coverage, +0.093 recall.
- 16384 tokens: compiler vs best baseline: +0.167 full-coverage, +0.090 recall.

## Audited metrics

Page metrics below cover only questions that are marked answerable and carry at least one annotated gold page; a question with no annotated gold page is excluded even when it is marked answerable. Quote metrics include only questions with a non-empty gold quote. Content-verified pages require the full normalized source-node text to be present in the emitted context.

Quote-match policy: **`nfkc-unified-punctuation-ordered-elision-v3`**. Quote figures are comparable only against artifacts carrying the same policy; an artifact without the field is `literal-casefold-v1`, which matched a gold quote only where it appeared verbatim after casefolding and whitespace collapse.

| System | Budget | Answerable gold-page n | Page recall | Content-verified recall | Quoted n | Exact quote recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 6 | 0.580 | 0.580 | 6 | 0.450 |
| compiler | 4096 | 6 | 0.781 | 0.781 | 6 | 0.492 |
| compiler | 8192 | 6 | 0.818 | 0.818 | 6 | 0.575 |
| compiler | 16384 | 6 | 0.818 | 0.818 | 6 | 0.617 |
| fixed | 2048 | 6 | 0.493 | 0.493 | 6 | 0.558 |
| fixed | 4096 | 6 | 0.619 | 0.601 | 6 | 0.683 |
| fixed | 8192 | 6 | 0.725 | 0.706 | 6 | 0.683 |
| fixed | 16384 | 6 | 0.754 | 0.754 | 6 | 0.850 |
| long_context | 2048 | 6 | 0.248 | 0.248 | 6 | 0.108 |
| long_context | 4096 | 6 | 0.434 | 0.434 | 6 | 0.358 |
| long_context | 8192 | 6 | 0.627 | 0.627 | 6 | 0.400 |
| long_context | 16384 | 6 | 0.786 | 0.786 | 6 | 0.692 |
| structural | 2048 | 6 | 0.407 | 0.407 | 6 | 0.542 |
| structural | 4096 | 6 | 0.489 | 0.489 | 6 | 0.583 |
| structural | 8192 | 6 | 0.542 | 0.542 | 6 | 0.583 |
| structural | 16384 | 6 | 0.728 | 0.728 | 6 | 0.625 |

## Paired source-cluster bootstrap

Intervals are descriptive 95% paired bootstrap intervals. The sampling unit is the sorted source-document scope; 10,000 resamples are used by default.

| Treatment | Baseline | Budget | Metric | n | Clusters | Delta | 95% interval |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| compiler | fixed | 2048 | answerable_page_recall | 6 | 6 | +0.087 | [-0.106, +0.246] |
| compiler | fixed | 2048 | answerable_content_verified_page_recall | 6 | 6 | +0.087 | [-0.101, +0.246] |
| compiler | fixed | 2048 | quoted_exact_quote_recall | 6 | 6 | -0.108 | [-0.358, +0.167] |
| compiler | structural | 2048 | answerable_page_recall | 6 | 6 | +0.173 | [+0.042, +0.332] |
| compiler | structural | 2048 | answerable_content_verified_page_recall | 6 | 6 | +0.173 | [+0.042, +0.332] |
| compiler | structural | 2048 | quoted_exact_quote_recall | 6 | 6 | -0.092 | [-0.292, +0.067] |
| compiler | fixed | 4096 | answerable_page_recall | 6 | 6 | +0.162 | [-0.007, +0.325] |
| compiler | fixed | 4096 | answerable_content_verified_page_recall | 6 | 6 | +0.180 | [+0.009, +0.352] |
| compiler | fixed | 4096 | quoted_exact_quote_recall | 6 | 6 | -0.192 | [-0.358, -0.042] |
| compiler | structural | 4096 | answerable_page_recall | 6 | 6 | +0.292 | [+0.148, +0.432] |
| compiler | structural | 4096 | answerable_content_verified_page_recall | 6 | 6 | +0.292 | [+0.148, +0.432] |
| compiler | structural | 4096 | quoted_exact_quote_recall | 6 | 6 | -0.092 | [-0.292, +0.067] |
| compiler | fixed | 8192 | answerable_page_recall | 6 | 6 | +0.093 | [-0.069, +0.246] |
| compiler | fixed | 8192 | answerable_content_verified_page_recall | 6 | 6 | +0.112 | [-0.069, +0.288] |
| compiler | fixed | 8192 | quoted_exact_quote_recall | 6 | 6 | -0.108 | [-0.317, +0.083] |
| compiler | structural | 8192 | answerable_page_recall | 6 | 6 | +0.276 | [+0.133, +0.403] |
| compiler | structural | 8192 | answerable_content_verified_page_recall | 6 | 6 | +0.276 | [+0.140, +0.403] |
| compiler | structural | 8192 | quoted_exact_quote_recall | 6 | 6 | -0.008 | [-0.217, +0.158] |
| compiler | fixed | 16384 | answerable_page_recall | 6 | 6 | +0.064 | [-0.083, +0.190] |
| compiler | fixed | 16384 | answerable_content_verified_page_recall | 6 | 6 | +0.064 | [-0.083, +0.194] |
| compiler | fixed | 16384 | quoted_exact_quote_recall | 6 | 6 | -0.233 | [-0.417, -0.067] |
| compiler | structural | 16384 | answerable_page_recall | 6 | 6 | +0.090 | [+0.000, +0.224] |
| compiler | structural | 16384 | answerable_content_verified_page_recall | 6 | 6 | +0.090 | [+0.000, +0.224] |
| compiler | structural | 16384 | quoted_exact_quote_recall | 6 | 6 | -0.008 | [-0.217, +0.158] |

## Non-inferiority check

Margin: **-0.03** on answerable page recall. A check passes when the lower bound of the paired 95% interval is strictly above the margin. Page recall alone decides the verdict, as specified; the content-verified and quote intervals are shown beside it because page recall has moved opposite to quote recall on this benchmark, and a verdict read without them is a verdict read half-blind.

**A pass is confirmatory only where one unit cannot cross the margin on its own.** That needs at least 34 eligible questions and at least 34 source clusters: below either, a delta moves by more than 0.03 when a single question flips or a single cluster is resampled away, so the interval is being tested against a threshold finer than the instrument that produced it. Every such row is reported as *screening*, and a screening pass is not evidence of non-inferiority.

| Baseline | Budget | Page delta | Page 95% interval | Status | Content-verified delta | Quote delta |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| fixed | 2048 | +0.087 | [-0.106, +0.246] | screening fail | +0.087 [-0.101, +0.246] | -0.108 [-0.358, +0.167] |
| structural | 2048 | +0.173 | [+0.042, +0.332] | screening pass | +0.173 [+0.042, +0.332] | -0.092 [-0.292, +0.067] |
| fixed | 4096 | +0.162 | [-0.007, +0.325] | screening pass | +0.180 [+0.009, +0.352] | -0.192 [-0.358, -0.042] |
| structural | 4096 | +0.292 | [+0.148, +0.432] | screening pass | +0.292 [+0.148, +0.432] | -0.092 [-0.292, +0.067] |
| fixed | 8192 | +0.093 | [-0.069, +0.246] | screening fail | +0.112 [-0.069, +0.288] | -0.108 [-0.317, +0.083] |
| structural | 8192 | +0.276 | [+0.133, +0.403] | screening pass | +0.276 [+0.140, +0.403] | -0.008 [-0.217, +0.158] |
| fixed | 16384 | +0.064 | [-0.083, +0.190] | screening fail | +0.064 [-0.083, +0.194] | -0.233 [-0.417, -0.067] |
| structural | 16384 | +0.090 | [+0.000, +0.224] | screening pass | +0.090 [+0.000, +0.224] | -0.008 [-0.217, +0.158] |

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
