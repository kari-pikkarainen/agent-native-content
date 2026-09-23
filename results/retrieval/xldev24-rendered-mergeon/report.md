# Retrieval Decision Report: xldev24-rendered-mergeon-f916545

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.596 | 0.292 | 0.458 | 0.333 | 1811.7 | 0.0 | 0.067 | 2019.43 |
| compiler | 4096 | 0.781 | 0.458 | 0.469 | 0.333 | 3606.8 | 0.0 | 0.099 | 1992.64 |
| compiler | 8192 | 0.896 | 0.625 | 0.566 | 0.375 | 7239.0 | 2163.0 | 0.149 | 1973.29 |
| compiler | 16384 | 0.931 | 0.667 | 0.597 | 0.417 | 14633.0 | 2225.5 | 0.210 | 2058.73 |
| fixed | 2048 | 0.419 | 0.250 | 0.413 | 0.333 | 1753.8 | 0.0 | 0.063 | 344.26 |
| fixed | 4096 | 0.573 | 0.333 | 0.438 | 0.333 | 3698.3 | 0.0 | 0.110 | 344.08 |
| fixed | 8192 | 0.736 | 0.417 | 0.500 | 0.333 | 7694.5 | 0.0 | 0.171 | 344.61 |
| fixed | 16384 | 0.834 | 0.583 | 0.552 | 0.417 | 15727.0 | 2283.5 | 0.240 | 346.16 |
| long_context | 2048 | 0.316 | 0.250 | 0.260 | 0.250 | 1224.7 | 0.0 | 0.050 | 86.29 |
| long_context | 4096 | 0.398 | 0.292 | 0.295 | 0.250 | 2657.7 | 0.0 | 0.093 | 85.80 |
| long_context | 8192 | 0.535 | 0.375 | 0.368 | 0.292 | 5593.2 | 0.0 | 0.120 | 86.98 |
| long_context | 16384 | 0.686 | 0.542 | 0.420 | 0.333 | 11010.0 | 1637.0 | 0.157 | 88.44 |
| structural | 2048 | 0.538 | 0.292 | 0.444 | 0.375 | 1861.2 | 0.0 | 0.064 | 347.10 |
| structural | 4096 | 0.620 | 0.333 | 0.444 | 0.375 | 3843.4 | 0.0 | 0.101 | 346.73 |
| structural | 8192 | 0.722 | 0.417 | 0.465 | 0.375 | 7764.6 | 0.0 | 0.125 | 347.04 |
| structural | 16384 | 0.799 | 0.542 | 0.476 | 0.375 | 14578.4 | 1583.0 | 0.147 | 347.52 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.000 full-coverage, +0.057 recall.
- 4096 tokens: compiler vs best baseline: +0.125 full-coverage, +0.162 recall.
- 8192 tokens: compiler vs best baseline: +0.208 full-coverage, +0.160 recall.
- 16384 tokens: compiler vs best baseline: +0.083 full-coverage, +0.096 recall.

## Audited metrics

Page metrics below cover only questions that are marked answerable and carry at least one annotated gold page; a question with no annotated gold page is excluded even when it is marked answerable. Quote metrics include only questions with a non-empty gold quote. Content-verified pages require the full normalized source-node text to be present in the emitted context.

Quote-match policy: **`nfkc-unified-punctuation-ordered-elision-v3`**. Quote figures are comparable only against artifacts carrying the same policy; an artifact without the field is `literal-casefold-v1`, which matched a gold quote only where it appeared verbatim after casefolding and whitespace collapse.

| System | Budget | Answerable gold-page n | Page recall | Content-verified recall | Quoted n | Exact quote recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 18 | 0.461 | 0.456 | 18 | 0.278 |
| compiler | 4096 | 18 | 0.709 | 0.703 | 18 | 0.292 |
| compiler | 8192 | 18 | 0.861 | 0.856 | 18 | 0.421 |
| compiler | 16384 | 18 | 0.908 | 0.902 | 18 | 0.463 |
| fixed | 2048 | 18 | 0.226 | 0.215 | 18 | 0.218 |
| fixed | 4096 | 18 | 0.431 | 0.412 | 18 | 0.250 |
| fixed | 8192 | 18 | 0.648 | 0.634 | 18 | 0.333 |
| fixed | 16384 | 18 | 0.779 | 0.757 | 18 | 0.403 |
| long_context | 2048 | 18 | 0.089 | 0.089 | 18 | 0.014 |
| long_context | 4096 | 18 | 0.197 | 0.197 | 18 | 0.060 |
| long_context | 8192 | 18 | 0.380 | 0.380 | 18 | 0.157 |
| long_context | 16384 | 18 | 0.581 | 0.581 | 18 | 0.227 |
| structural | 2048 | 18 | 0.384 | 0.335 | 18 | 0.259 |
| structural | 4096 | 18 | 0.493 | 0.401 | 18 | 0.259 |
| structural | 8192 | 18 | 0.629 | 0.553 | 18 | 0.287 |
| structural | 16384 | 18 | 0.733 | 0.651 | 18 | 0.301 |

## Paired source-cluster bootstrap

Intervals are descriptive 95% paired bootstrap intervals. The sampling unit is the sorted source-document scope; 10,000 resamples are used by default.

| Treatment | Baseline | Budget | Metric | n | Clusters | Delta | 95% interval |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| compiler | fixed | 2048 | answerable_page_recall | 18 | 9 | +0.235 | [+0.114, +0.334] |
| compiler | fixed | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.240 | [+0.115, +0.343] |
| compiler | fixed | 2048 | quoted_exact_quote_recall | 18 | 9 | +0.060 | [-0.088, +0.200] |
| compiler | structural | 2048 | answerable_page_recall | 18 | 9 | +0.077 | [-0.072, +0.180] |
| compiler | structural | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.121 | [-0.012, +0.208] |
| compiler | structural | 2048 | quoted_exact_quote_recall | 18 | 9 | +0.019 | [-0.074, +0.073] |
| compiler | fixed | 4096 | answerable_page_recall | 18 | 9 | +0.277 | [+0.131, +0.404] |
| compiler | fixed | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.291 | [+0.149, +0.409] |
| compiler | fixed | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.042 | [-0.137, +0.192] |
| compiler | structural | 4096 | answerable_page_recall | 18 | 9 | +0.216 | [+0.063, +0.355] |
| compiler | structural | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.302 | [+0.180, +0.406] |
| compiler | structural | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.032 | [-0.067, +0.098] |
| compiler | fixed | 8192 | answerable_page_recall | 18 | 9 | +0.214 | [+0.082, +0.350] |
| compiler | fixed | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.221 | [+0.088, +0.360] |
| compiler | fixed | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.088 | [+0.000, +0.203] |
| compiler | structural | 8192 | answerable_page_recall | 18 | 9 | +0.232 | [+0.057, +0.392] |
| compiler | structural | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.303 | [+0.154, +0.441] |
| compiler | structural | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.134 | [+0.036, +0.235] |
| compiler | fixed | 16384 | answerable_page_recall | 18 | 9 | +0.129 | [+0.004, +0.247] |
| compiler | fixed | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.145 | [+0.018, +0.260] |
| compiler | fixed | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.060 | [-0.019, +0.188] |
| compiler | structural | 16384 | answerable_page_recall | 18 | 9 | +0.175 | [+0.025, +0.339] |
| compiler | structural | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.251 | [+0.100, +0.400] |
| compiler | structural | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.162 | [+0.071, +0.250] |

## Non-inferiority check

Margin: **-0.03** on answerable page recall. A check passes when the lower bound of the paired 95% interval is strictly above the margin. Page recall alone decides the verdict, as specified; the content-verified and quote intervals are shown beside it because page recall has moved opposite to quote recall on this benchmark, and a verdict read without them is a verdict read half-blind.

**A pass is confirmatory only where one unit cannot cross the margin on its own.** That needs at least 34 eligible questions and at least 34 source clusters: below either, a delta moves by more than 0.03 when a single question flips or a single cluster is resampled away, so the interval is being tested against a threshold finer than the instrument that produced it. Every such row is reported as *screening*, and a screening pass is not evidence of non-inferiority.

| Baseline | Budget | Page delta | Page 95% interval | Status | Content-verified delta | Quote delta |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| fixed | 2048 | +0.235 | [+0.114, +0.334] | screening pass | +0.240 [+0.115, +0.343] | +0.060 [-0.088, +0.200] |
| structural | 2048 | +0.077 | [-0.072, +0.180] | screening fail | +0.121 [-0.012, +0.208] | +0.019 [-0.074, +0.073] |
| fixed | 4096 | +0.277 | [+0.131, +0.404] | screening pass | +0.291 [+0.149, +0.409] | +0.042 [-0.137, +0.192] |
| structural | 4096 | +0.216 | [+0.063, +0.355] | screening pass | +0.302 [+0.180, +0.406] | +0.032 [-0.067, +0.098] |
| fixed | 8192 | +0.214 | [+0.082, +0.350] | screening pass | +0.221 [+0.088, +0.360] | +0.088 [+0.000, +0.203] |
| structural | 8192 | +0.232 | [+0.057, +0.392] | screening pass | +0.303 [+0.154, +0.441] | +0.134 [+0.036, +0.235] |
| fixed | 16384 | +0.129 | [+0.004, +0.247] | screening pass | +0.145 [+0.018, +0.260] | +0.060 [-0.019, +0.188] |
| structural | 16384 | +0.175 | [+0.025, +0.339] | screening pass | +0.251 [+0.100, +0.400] | +0.162 [+0.071, +0.250] |

## Rendered evidence and gold-answer presence

Rendered tokens are the evidence block as the answer prompt carries it -- tags, evidence IDs, joiners and content -- and are what the budget counts unless a run chose content accounting. Answer presence asks whether the normalised gold answer is written inside a single packed item; unanswerable questions are not applicable and are excluded. It cannot see an answer the question asks to be computed, and a short number can be present by chance, so read it as a floor on retrieval failure, not as answer accuracy.

| System | Budget | Mean content tokens | Mean rendered tokens | Answer-present n | Answer present |
| --- | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 1811.7 | 2043.6 | 18 | 0.500 |
| compiler | 4096 | 3606.8 | 4090.0 | 18 | 0.556 |
| compiler | 8192 | 7239.0 | 8184.3 | 18 | 0.556 |
| compiler | 16384 | 14633.0 | 16373.3 | 18 | 0.611 |
| fixed | 2048 | 1753.8 | 1800.1 | 18 | 0.389 |
| fixed | 4096 | 3698.3 | 3794.3 | 18 | 0.500 |
| fixed | 8192 | 7694.5 | 7891.8 | 18 | 0.500 |
| fixed | 16384 | 15727.0 | 16127.2 | 18 | 0.500 |
| long_context | 2048 | 1224.7 | 2042.8 | 18 | 0.333 |
| long_context | 4096 | 2657.7 | 4090.3 | 18 | 0.389 |
| long_context | 8192 | 5593.2 | 8188.6 | 18 | 0.389 |
| long_context | 16384 | 11010.0 | 16378.6 | 18 | 0.389 |
| structural | 2048 | 1861.2 | 1958.7 | 18 | 0.500 |
| structural | 4096 | 3843.4 | 4011.1 | 18 | 0.500 |
| structural | 8192 | 7764.6 | 8096.9 | 18 | 0.500 |
| structural | 16384 | 14578.4 | 15180.2 | 18 | 0.500 |

| System | Budget | Verification rule | n | Present | Rate |
| --- | ---: | --- | ---: | ---: | ---: |
| compiler | 2048 | casefold_exact_match | 15 | 7 | 0.467 |
| compiler | 2048 | numeric_tolerance | 2 | 2 | 1.000 |
| compiler | 2048 | percentage_exact | 1 | 0 | 0.000 |
| compiler | 4096 | casefold_exact_match | 15 | 8 | 0.533 |
| compiler | 4096 | numeric_tolerance | 2 | 2 | 1.000 |
| compiler | 4096 | percentage_exact | 1 | 0 | 0.000 |
| compiler | 8192 | casefold_exact_match | 15 | 8 | 0.533 |
| compiler | 8192 | numeric_tolerance | 2 | 2 | 1.000 |
| compiler | 8192 | percentage_exact | 1 | 0 | 0.000 |
| compiler | 16384 | casefold_exact_match | 15 | 8 | 0.533 |
| compiler | 16384 | numeric_tolerance | 2 | 2 | 1.000 |
| compiler | 16384 | percentage_exact | 1 | 1 | 1.000 |
| fixed | 2048 | casefold_exact_match | 15 | 6 | 0.400 |
| fixed | 2048 | numeric_tolerance | 2 | 1 | 0.500 |
| fixed | 2048 | percentage_exact | 1 | 0 | 0.000 |
| fixed | 4096 | casefold_exact_match | 15 | 7 | 0.467 |
| fixed | 4096 | numeric_tolerance | 2 | 2 | 1.000 |
| fixed | 4096 | percentage_exact | 1 | 0 | 0.000 |
| fixed | 8192 | casefold_exact_match | 15 | 7 | 0.467 |
| fixed | 8192 | numeric_tolerance | 2 | 2 | 1.000 |
| fixed | 8192 | percentage_exact | 1 | 0 | 0.000 |
| fixed | 16384 | casefold_exact_match | 15 | 7 | 0.467 |
| fixed | 16384 | numeric_tolerance | 2 | 2 | 1.000 |
| fixed | 16384 | percentage_exact | 1 | 0 | 0.000 |
| long_context | 2048 | casefold_exact_match | 15 | 4 | 0.267 |
| long_context | 2048 | numeric_tolerance | 2 | 2 | 1.000 |
| long_context | 2048 | percentage_exact | 1 | 0 | 0.000 |
| long_context | 4096 | casefold_exact_match | 15 | 5 | 0.333 |
| long_context | 4096 | numeric_tolerance | 2 | 2 | 1.000 |
| long_context | 4096 | percentage_exact | 1 | 0 | 0.000 |
| long_context | 8192 | casefold_exact_match | 15 | 5 | 0.333 |
| long_context | 8192 | numeric_tolerance | 2 | 2 | 1.000 |
| long_context | 8192 | percentage_exact | 1 | 0 | 0.000 |
| long_context | 16384 | casefold_exact_match | 15 | 5 | 0.333 |
| long_context | 16384 | numeric_tolerance | 2 | 2 | 1.000 |
| long_context | 16384 | percentage_exact | 1 | 0 | 0.000 |
| structural | 2048 | casefold_exact_match | 15 | 7 | 0.467 |
| structural | 2048 | numeric_tolerance | 2 | 2 | 1.000 |
| structural | 2048 | percentage_exact | 1 | 0 | 0.000 |
| structural | 4096 | casefold_exact_match | 15 | 7 | 0.467 |
| structural | 4096 | numeric_tolerance | 2 | 2 | 1.000 |
| structural | 4096 | percentage_exact | 1 | 0 | 0.000 |
| structural | 8192 | casefold_exact_match | 15 | 7 | 0.467 |
| structural | 8192 | numeric_tolerance | 2 | 2 | 1.000 |
| structural | 8192 | percentage_exact | 1 | 0 | 0.000 |
| structural | 16384 | casefold_exact_match | 15 | 7 | 0.467 |
| structural | 16384 | numeric_tolerance | 2 | 2 | 1.000 |
| structural | 16384 | percentage_exact | 1 | 0 | 0.000 |

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
