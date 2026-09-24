# Retrieval Decision Report: xlfresh9-smoke-mergeoff-f916545

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.712 | 0.556 | 0.611 | 0.556 | 1807.1 | 0.0 | 0.076 | 1506.19 |
| compiler | 4096 | 0.789 | 0.556 | 0.667 | 0.556 | 3562.3 | 0.0 | 0.096 | 1428.79 |
| compiler | 8192 | 0.840 | 0.556 | 0.667 | 0.556 | 7096.7 | 0.0 | 0.132 | 1491.05 |
| compiler | 16384 | 0.895 | 0.667 | 0.667 | 0.556 | 14191.4 | 0.0 | 0.191 | 1491.53 |
| fixed | 2048 | 0.646 | 0.556 | 0.611 | 0.556 | 1615.6 | 0.0 | 0.053 | 394.51 |
| fixed | 4096 | 0.720 | 0.556 | 0.611 | 0.556 | 3633.8 | 0.0 | 0.095 | 394.21 |
| fixed | 8192 | 0.742 | 0.556 | 0.611 | 0.556 | 7634.4 | 0.0 | 0.137 | 395.22 |
| fixed | 16384 | 0.802 | 0.556 | 0.667 | 0.556 | 15690.2 | 0.0 | 0.170 | 396.00 |
| long_context | 2048 | 0.598 | 0.556 | 0.556 | 0.556 | 1488.4 | 0.0 | 0.100 | 150.30 |
| long_context | 4096 | 0.587 | 0.556 | 0.556 | 0.556 | 2945.7 | 0.0 | 0.106 | 128.85 |
| long_context | 8192 | 0.639 | 0.556 | 0.556 | 0.556 | 5897.4 | 0.0 | 0.106 | 130.77 |
| long_context | 16384 | 0.664 | 0.556 | 0.556 | 0.556 | 11962.2 | 0.0 | 0.123 | 131.47 |
| structural | 2048 | 0.624 | 0.556 | 0.556 | 0.556 | 1931.6 | 0.0 | 0.071 | 428.96 |
| structural | 4096 | 0.701 | 0.556 | 0.611 | 0.556 | 3882.2 | 0.0 | 0.110 | 429.26 |
| structural | 8192 | 0.727 | 0.556 | 0.611 | 0.556 | 7818.0 | 0.0 | 0.122 | 429.27 |
| structural | 16384 | 0.837 | 0.556 | 0.778 | 0.667 | 15606.7 | 0.0 | 0.159 | 429.88 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.000 full-coverage, +0.066 recall.
- 4096 tokens: compiler vs best baseline: +0.000 full-coverage, +0.069 recall.
- 8192 tokens: compiler vs best baseline: +0.000 full-coverage, +0.098 recall.
- 16384 tokens: compiler vs best baseline: +0.111 full-coverage, +0.058 recall.

## Audited metrics

Page metrics below cover only questions that are marked answerable and carry at least one annotated gold page; a question with no annotated gold page is excluded even when it is marked answerable. Quote metrics include only questions with a non-empty gold quote. Content-verified pages require the full normalized source-node text to be present in the emitted context.

Quote-match policy: **`nfkc-unified-punctuation-ordered-elision-v3`**. Quote figures are comparable only against artifacts carrying the same policy; an artifact without the field is `literal-casefold-v1`, which matched a gold quote only where it appeared verbatim after casefolding and whitespace collapse.

| System | Budget | Answerable gold-page n | Page recall | Content-verified recall | Quoted n | Exact quote recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 4 | 0.353 | 0.353 | 4 | 0.125 |
| compiler | 4096 | 4 | 0.524 | 0.524 | 4 | 0.250 |
| compiler | 8192 | 4 | 0.641 | 0.641 | 4 | 0.250 |
| compiler | 16384 | 4 | 0.765 | 0.765 | 4 | 0.250 |
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
| compiler | fixed | 2048 | answerable_page_recall | 4 | 4 | +0.149 | [-0.033, +0.341] |
| compiler | fixed | 2048 | answerable_content_verified_page_recall | 4 | 4 | +0.168 | [-0.033, +0.360] |
| compiler | fixed | 2048 | quoted_exact_quote_recall | 4 | 4 | +0.000 | [-0.375, +0.375] |
| compiler | structural | 2048 | answerable_page_recall | 4 | 4 | +0.198 | [+0.106, +0.349] |
| compiler | structural | 2048 | answerable_content_verified_page_recall | 4 | 4 | +0.198 | [+0.106, +0.349] |
| compiler | structural | 2048 | quoted_exact_quote_recall | 4 | 4 | +0.125 | [+0.000, +0.375] |
| compiler | fixed | 4096 | answerable_page_recall | 4 | 4 | +0.155 | [+0.113, +0.202] |
| compiler | fixed | 4096 | answerable_content_verified_page_recall | 4 | 4 | +0.224 | [+0.165, +0.281] |
| compiler | fixed | 4096 | quoted_exact_quote_recall | 4 | 4 | +0.125 | [+0.000, +0.375] |
| compiler | structural | 4096 | answerable_page_recall | 4 | 4 | +0.196 | [+0.113, +0.264] |
| compiler | structural | 4096 | answerable_content_verified_page_recall | 4 | 4 | +0.235 | [+0.208, +0.270] |
| compiler | structural | 4096 | quoted_exact_quote_recall | 4 | 4 | +0.125 | [+0.000, +0.375] |
| compiler | fixed | 8192 | answerable_page_recall | 4 | 4 | +0.221 | [+0.121, +0.321] |
| compiler | fixed | 8192 | answerable_content_verified_page_recall | 4 | 4 | +0.290 | [+0.190, +0.363] |
| compiler | fixed | 8192 | quoted_exact_quote_recall | 4 | 4 | +0.125 | [+0.000, +0.375] |
| compiler | structural | 8192 | answerable_page_recall | 4 | 4 | +0.255 | [+0.083, +0.371] |
| compiler | structural | 8192 | answerable_content_verified_page_recall | 4 | 4 | +0.332 | [+0.297, +0.377] |
| compiler | structural | 8192 | quoted_exact_quote_recall | 4 | 4 | +0.125 | [+0.000, +0.375] |
| compiler | fixed | 16384 | answerable_page_recall | 4 | 4 | +0.210 | [+0.113, +0.369] |
| compiler | fixed | 16384 | answerable_content_verified_page_recall | 4 | 4 | +0.274 | [+0.171, +0.383] |
| compiler | fixed | 16384 | quoted_exact_quote_recall | 4 | 4 | +0.000 | [+0.000, +0.000] |
| compiler | structural | 16384 | answerable_page_recall | 4 | 4 | +0.131 | [-0.065, +0.286] |
| compiler | structural | 16384 | answerable_content_verified_page_recall | 4 | 4 | +0.208 | [+0.148, +0.288] |
| compiler | structural | 16384 | quoted_exact_quote_recall | 4 | 4 | -0.250 | [-0.500, +0.000] |

## Non-inferiority check

Margin: **-0.03** on answerable page recall. A check passes when the lower bound of the paired 95% interval is strictly above the margin. Page recall alone decides the verdict, as specified; the content-verified and quote intervals are shown beside it because page recall has moved opposite to quote recall on this benchmark, and a verdict read without them is a verdict read half-blind.

**A pass is confirmatory only where one unit cannot cross the margin on its own.** That needs at least 34 eligible questions and at least 34 source clusters: below either, a delta moves by more than 0.03 when a single question flips or a single cluster is resampled away, so the interval is being tested against a threshold finer than the instrument that produced it. Every such row is reported as *screening*, and a screening pass is not evidence of non-inferiority.

| Baseline | Budget | Page delta | Page 95% interval | Status | Content-verified delta | Quote delta |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| fixed | 2048 | +0.149 | [-0.033, +0.341] | screening fail | +0.168 [-0.033, +0.360] | +0.000 [-0.375, +0.375] |
| structural | 2048 | +0.198 | [+0.106, +0.349] | screening pass | +0.198 [+0.106, +0.349] | +0.125 [+0.000, +0.375] |
| fixed | 4096 | +0.155 | [+0.113, +0.202] | screening pass | +0.224 [+0.165, +0.281] | +0.125 [+0.000, +0.375] |
| structural | 4096 | +0.196 | [+0.113, +0.264] | screening pass | +0.235 [+0.208, +0.270] | +0.125 [+0.000, +0.375] |
| fixed | 8192 | +0.221 | [+0.121, +0.321] | screening pass | +0.290 [+0.190, +0.363] | +0.125 [+0.000, +0.375] |
| structural | 8192 | +0.255 | [+0.083, +0.371] | screening pass | +0.332 [+0.297, +0.377] | +0.125 [+0.000, +0.375] |
| fixed | 16384 | +0.210 | [+0.113, +0.369] | screening pass | +0.274 [+0.171, +0.383] | +0.000 [+0.000, +0.000] |
| structural | 16384 | +0.131 | [-0.065, +0.286] | screening fail | +0.208 [+0.148, +0.288] | -0.250 [-0.500, +0.000] |

## Rendered evidence and gold-answer presence

Rendered tokens are the evidence block as the answer prompt carries it -- tags, evidence IDs, joiners and content -- and are what the budget counts unless a run chose content accounting. Answer presence asks whether the normalised gold answer is written inside a single packed item; unanswerable questions are not applicable and are excluded. It cannot see an answer the question asks to be computed, and a short number can be present by chance, so read it as a floor on retrieval failure, not as answer accuracy.

| System | Budget | Mean content tokens | Mean rendered tokens | Answer-present n | Answer present |
| --- | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 1807.1 | 2041.4 | 4 | 0.250 |
| compiler | 4096 | 3562.3 | 4091.7 | 4 | 0.500 |
| compiler | 8192 | 7096.7 | 8184.3 | 4 | 0.500 |
| compiler | 16384 | 14191.4 | 16349.6 | 4 | 0.500 |
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
