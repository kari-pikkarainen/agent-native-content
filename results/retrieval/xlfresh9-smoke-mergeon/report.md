# Retrieval Decision Report: xlfresh9-smoke-mergeon-f916545

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.695 | 0.556 | 0.611 | 0.556 | 1860.7 | 0.0 | 0.062 | 1977.88 |
| compiler | 4096 | 0.780 | 0.556 | 0.667 | 0.556 | 3700.7 | 0.0 | 0.084 | 1709.03 |
| compiler | 8192 | 0.819 | 0.556 | 0.667 | 0.556 | 7356.0 | 0.0 | 0.110 | 1743.27 |
| compiler | 16384 | 0.884 | 0.667 | 0.667 | 0.556 | 14853.2 | 0.0 | 0.161 | 1753.93 |
| fixed | 2048 | 0.646 | 0.556 | 0.611 | 0.556 | 1615.6 | 0.0 | 0.053 | 402.06 |
| fixed | 4096 | 0.720 | 0.556 | 0.611 | 0.556 | 3633.8 | 0.0 | 0.095 | 401.73 |
| fixed | 8192 | 0.742 | 0.556 | 0.611 | 0.556 | 7634.4 | 0.0 | 0.137 | 402.42 |
| fixed | 16384 | 0.802 | 0.556 | 0.667 | 0.556 | 15690.2 | 0.0 | 0.170 | 403.93 |
| long_context | 2048 | 0.598 | 0.556 | 0.556 | 0.556 | 1488.4 | 0.0 | 0.100 | 127.08 |
| long_context | 4096 | 0.587 | 0.556 | 0.556 | 0.556 | 2945.7 | 0.0 | 0.106 | 127.04 |
| long_context | 8192 | 0.639 | 0.556 | 0.556 | 0.556 | 5897.4 | 0.0 | 0.106 | 127.00 |
| long_context | 16384 | 0.664 | 0.556 | 0.556 | 0.556 | 11962.2 | 0.0 | 0.123 | 127.96 |
| structural | 2048 | 0.624 | 0.556 | 0.556 | 0.556 | 1931.6 | 0.0 | 0.071 | 425.19 |
| structural | 4096 | 0.701 | 0.556 | 0.611 | 0.556 | 3882.2 | 0.0 | 0.110 | 424.65 |
| structural | 8192 | 0.727 | 0.556 | 0.611 | 0.556 | 7818.0 | 0.0 | 0.122 | 424.68 |
| structural | 16384 | 0.837 | 0.556 | 0.778 | 0.667 | 15606.7 | 0.0 | 0.159 | 425.23 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.000 full-coverage, +0.049 recall.
- 4096 tokens: compiler vs best baseline: +0.000 full-coverage, +0.060 recall.
- 8192 tokens: compiler vs best baseline: +0.000 full-coverage, +0.077 recall.
- 16384 tokens: compiler vs best baseline: +0.111 full-coverage, +0.047 recall.

## Audited metrics

Page metrics below cover only questions that are marked answerable and carry at least one annotated gold page; a question with no annotated gold page is excluded even when it is marked answerable. Quote metrics include only questions with a non-empty gold quote. Content-verified pages require the full normalized source-node text to be present in the emitted context.

Quote-match policy: **`nfkc-unified-punctuation-ordered-elision-v3`**. Quote figures are comparable only against artifacts carrying the same policy; an artifact without the field is `literal-casefold-v1`, which matched a gold quote only where it appeared verbatim after casefolding and whitespace collapse.

| System | Budget | Answerable gold-page n | Page recall | Content-verified recall | Quoted n | Exact quote recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 4 | 0.314 | 0.314 | 4 | 0.125 |
| compiler | 4096 | 4 | 0.505 | 0.505 | 4 | 0.250 |
| compiler | 8192 | 4 | 0.594 | 0.594 | 4 | 0.250 |
| compiler | 16384 | 4 | 0.740 | 0.740 | 4 | 0.250 |
| fixed | 2048 | 4 | 0.204 | 0.185 | 4 | 0.125 |
| fixed | 4096 | 4 | 0.370 | 0.300 | 4 | 0.125 |
| fixed | 8192 | 4 | 0.420 | 0.350 | 4 | 0.125 |
| fixed | 16384 | 4 | 0.554 | 0.491 | 4 | 0.250 |
| long_context | 2048 | 4 | 0.096 | 0.096 | 4 | 0.000 |
| long_context | 4096 | 4 | 0.071 | 0.071 | 4 | 0.000 |
| long_context | 8192 | 4 | 0.187 | 0.187 | 4 | 0.000 |
| long_context | 16384 | 4 | 0.245 | 0.245 | 4 | 0.000 |
| structural | 2048 | 4 | 0.154 | 0.154 | 4 | 0.000 |
| structural | 4096 | 4 | 0.328 | 0.290 | 4 | 0.125 |
| structural | 8192 | 4 | 0.386 | 0.309 | 4 | 0.125 |
| structural | 16384 | 4 | 0.634 | 0.557 | 4 | 0.500 |

## Paired source-cluster bootstrap

Intervals are descriptive 95% paired bootstrap intervals. The sampling unit is the sorted source-document scope; 10,000 resamples are used by default.

| Treatment | Baseline | Budget | Metric | n | Clusters | Delta | 95% interval |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| compiler | fixed | 2048 | answerable_page_recall | 4 | 4 | +0.110 | [-0.094, +0.314] |
| compiler | fixed | 2048 | answerable_content_verified_page_recall | 4 | 4 | +0.129 | [-0.056, +0.321] |
| compiler | fixed | 2048 | quoted_exact_quote_recall | 4 | 4 | +0.000 | [-0.375, +0.375] |
| compiler | structural | 2048 | answerable_page_recall | 4 | 4 | +0.160 | [+0.028, +0.346] |
| compiler | structural | 2048 | answerable_content_verified_page_recall | 4 | 4 | +0.160 | [+0.028, +0.346] |
| compiler | structural | 2048 | quoted_exact_quote_recall | 4 | 4 | +0.125 | [+0.000, +0.375] |
| compiler | fixed | 4096 | answerable_page_recall | 4 | 4 | +0.136 | [+0.088, +0.192] |
| compiler | fixed | 4096 | answerable_content_verified_page_recall | 4 | 4 | +0.205 | [+0.148, +0.263] |
| compiler | fixed | 4096 | quoted_exact_quote_recall | 4 | 4 | +0.125 | [+0.000, +0.375] |
| compiler | structural | 4096 | answerable_page_recall | 4 | 4 | +0.177 | [+0.056, +0.264] |
| compiler | structural | 4096 | answerable_content_verified_page_recall | 4 | 4 | +0.215 | [+0.171, +0.264] |
| compiler | structural | 4096 | quoted_exact_quote_recall | 4 | 4 | +0.125 | [+0.000, +0.375] |
| compiler | fixed | 8192 | answerable_page_recall | 4 | 4 | +0.174 | [+0.121, +0.226] |
| compiler | fixed | 8192 | answerable_content_verified_page_recall | 4 | 4 | +0.243 | [+0.182, +0.304] |
| compiler | fixed | 8192 | quoted_exact_quote_recall | 4 | 4 | +0.125 | [+0.000, +0.375] |
| compiler | structural | 8192 | answerable_page_recall | 4 | 4 | +0.208 | [+0.014, +0.356] |
| compiler | structural | 8192 | answerable_content_verified_page_recall | 4 | 4 | +0.285 | [+0.226, +0.358] |
| compiler | structural | 8192 | quoted_exact_quote_recall | 4 | 4 | +0.125 | [+0.000, +0.375] |
| compiler | fixed | 16384 | answerable_page_recall | 4 | 4 | +0.185 | [+0.038, +0.369] |
| compiler | fixed | 16384 | answerable_content_verified_page_recall | 4 | 4 | +0.249 | [+0.121, +0.376] |
| compiler | fixed | 16384 | quoted_exact_quote_recall | 4 | 4 | +0.000 | [+0.000, +0.000] |
| compiler | structural | 16384 | answerable_page_recall | 4 | 4 | +0.106 | [-0.080, +0.275] |
| compiler | structural | 16384 | answerable_content_verified_page_recall | 4 | 4 | +0.183 | [+0.113, +0.286] |
| compiler | structural | 16384 | quoted_exact_quote_recall | 4 | 4 | -0.250 | [-0.500, +0.000] |

## Non-inferiority check

Margin: **-0.03** on answerable page recall. A check passes when the lower bound of the paired 95% interval is strictly above the margin. Page recall alone decides the verdict, as specified; the content-verified and quote intervals are shown beside it because page recall has moved opposite to quote recall on this benchmark, and a verdict read without them is a verdict read half-blind.

**A pass is confirmatory only where one unit cannot cross the margin on its own.** That needs at least 34 eligible questions and at least 34 source clusters: below either, a delta moves by more than 0.03 when a single question flips or a single cluster is resampled away, so the interval is being tested against a threshold finer than the instrument that produced it. Every such row is reported as *screening*, and a screening pass is not evidence of non-inferiority.

| Baseline | Budget | Page delta | Page 95% interval | Status | Content-verified delta | Quote delta |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| fixed | 2048 | +0.110 | [-0.094, +0.314] | screening fail | +0.129 [-0.056, +0.321] | +0.000 [-0.375, +0.375] |
| structural | 2048 | +0.160 | [+0.028, +0.346] | screening pass | +0.160 [+0.028, +0.346] | +0.125 [+0.000, +0.375] |
| fixed | 4096 | +0.136 | [+0.088, +0.192] | screening pass | +0.205 [+0.148, +0.263] | +0.125 [+0.000, +0.375] |
| structural | 4096 | +0.177 | [+0.056, +0.264] | screening pass | +0.215 [+0.171, +0.264] | +0.125 [+0.000, +0.375] |
| fixed | 8192 | +0.174 | [+0.121, +0.226] | screening pass | +0.243 [+0.182, +0.304] | +0.125 [+0.000, +0.375] |
| structural | 8192 | +0.208 | [+0.014, +0.356] | screening pass | +0.285 [+0.226, +0.358] | +0.125 [+0.000, +0.375] |
| fixed | 16384 | +0.185 | [+0.038, +0.369] | screening pass | +0.249 [+0.121, +0.376] | +0.000 [+0.000, +0.000] |
| structural | 16384 | +0.106 | [-0.080, +0.275] | screening fail | +0.183 [+0.113, +0.286] | -0.250 [-0.500, +0.000] |

## Rendered evidence and gold-answer presence

Rendered tokens are the evidence block as the answer prompt carries it -- tags, evidence IDs, joiners and content -- and are what the budget counts unless a run chose content accounting. Answer presence asks whether the normalised gold answer is written inside a single packed item; unanswerable questions are not applicable and are excluded. It cannot see an answer the question asks to be computed, and a short number can be present by chance, so read it as a floor on retrieval failure, not as answer accuracy.

| System | Budget | Mean content tokens | Mean rendered tokens | Answer-present n | Answer present |
| --- | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 1860.7 | 2041.7 | 4 | 0.250 |
| compiler | 4096 | 3700.7 | 4090.4 | 4 | 0.500 |
| compiler | 8192 | 7356.0 | 8182.2 | 4 | 0.500 |
| compiler | 16384 | 14853.2 | 16374.9 | 4 | 0.500 |
| fixed | 2048 | 1615.6 | 1657.0 | 4 | 0.250 |
| fixed | 4096 | 3633.8 | 3726.9 | 4 | 0.250 |
| fixed | 8192 | 7634.4 | 7829.6 | 4 | 0.250 |
| fixed | 16384 | 15690.2 | 16091.4 | 4 | 0.500 |
| long_context | 2048 | 1488.4 | 2044.6 | 4 | 0.000 |
| long_context | 4096 | 2945.7 | 4091.4 | 4 | 0.250 |
| long_context | 8192 | 5897.4 | 8185.0 | 4 | 0.250 |
| long_context | 16384 | 11962.2 | 16378.7 | 4 | 0.250 |
| structural | 2048 | 1931.6 | 2029.9 | 4 | 0.000 |
| structural | 4096 | 3882.2 | 4073.7 | 4 | 0.250 |
| structural | 8192 | 7818.0 | 8167.1 | 4 | 0.250 |
| structural | 16384 | 15606.7 | 16368.1 | 4 | 0.750 |

| System | Budget | Verification rule | n | Present | Rate |
| --- | ---: | --- | ---: | ---: | ---: |
| compiler | 2048 | casefold_exact_match | 4 | 1 | 0.250 |
| compiler | 4096 | casefold_exact_match | 4 | 2 | 0.500 |
| compiler | 8192 | casefold_exact_match | 4 | 2 | 0.500 |
| compiler | 16384 | casefold_exact_match | 4 | 2 | 0.500 |
| fixed | 2048 | casefold_exact_match | 4 | 1 | 0.250 |
| fixed | 4096 | casefold_exact_match | 4 | 1 | 0.250 |
| fixed | 8192 | casefold_exact_match | 4 | 1 | 0.250 |
| fixed | 16384 | casefold_exact_match | 4 | 2 | 0.500 |
| long_context | 2048 | casefold_exact_match | 4 | 0 | 0.000 |
| long_context | 4096 | casefold_exact_match | 4 | 1 | 0.250 |
| long_context | 8192 | casefold_exact_match | 4 | 1 | 0.250 |
| long_context | 16384 | casefold_exact_match | 4 | 1 | 0.250 |
| structural | 2048 | casefold_exact_match | 4 | 0 | 0.000 |
| structural | 4096 | casefold_exact_match | 4 | 1 | 0.250 |
| structural | 8192 | casefold_exact_match | 4 | 1 | 0.250 |
| structural | 16384 | casefold_exact_match | 4 | 3 | 0.750 |

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
