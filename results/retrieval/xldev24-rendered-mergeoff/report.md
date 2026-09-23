# Retrieval Decision Report: xldev24-rendered-mergeoff-f916545

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.665 | 0.333 | 0.389 | 0.292 | 1660.0 | 0.0 | 0.082 | 1368.02 |
| compiler | 4096 | 0.804 | 0.500 | 0.469 | 0.333 | 3333.3 | 422.0 | 0.119 | 1294.74 |
| compiler | 8192 | 0.855 | 0.583 | 0.490 | 0.333 | 6689.3 | 1392.0 | 0.166 | 1316.71 |
| compiler | 16384 | 0.877 | 0.583 | 0.552 | 0.375 | 12986.4 | 1392.0 | 0.234 | 2141.40 |
| fixed | 2048 | 0.419 | 0.250 | 0.413 | 0.333 | 1753.8 | 0.0 | 0.063 | 355.60 |
| fixed | 4096 | 0.573 | 0.333 | 0.438 | 0.333 | 3698.3 | 0.0 | 0.110 | 355.33 |
| fixed | 8192 | 0.736 | 0.417 | 0.500 | 0.333 | 7694.5 | 0.0 | 0.171 | 355.83 |
| fixed | 16384 | 0.834 | 0.583 | 0.552 | 0.417 | 15727.0 | 2283.5 | 0.240 | 357.16 |
| long_context | 2048 | 0.316 | 0.250 | 0.260 | 0.250 | 1224.7 | 0.0 | 0.050 | 89.56 |
| long_context | 4096 | 0.398 | 0.292 | 0.295 | 0.250 | 2657.7 | 0.0 | 0.093 | 88.46 |
| long_context | 8192 | 0.535 | 0.375 | 0.368 | 0.292 | 5593.2 | 0.0 | 0.120 | 89.31 |
| long_context | 16384 | 0.686 | 0.542 | 0.420 | 0.333 | 11010.0 | 1637.0 | 0.157 | 91.41 |
| structural | 2048 | 0.538 | 0.292 | 0.444 | 0.375 | 1861.2 | 0.0 | 0.064 | 352.65 |
| structural | 4096 | 0.620 | 0.333 | 0.444 | 0.375 | 3843.4 | 0.0 | 0.101 | 351.79 |
| structural | 8192 | 0.722 | 0.417 | 0.465 | 0.375 | 7764.6 | 0.0 | 0.125 | 352.01 |
| structural | 16384 | 0.799 | 0.542 | 0.476 | 0.375 | 14578.4 | 1583.0 | 0.147 | 352.64 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.042 full-coverage, +0.127 recall.
- 4096 tokens: compiler vs best baseline: +0.167 full-coverage, +0.184 recall.
- 8192 tokens: compiler vs best baseline: +0.167 full-coverage, +0.119 recall.
- 16384 tokens: compiler vs best baseline: +0.000 full-coverage, +0.042 recall.

## Audited metrics

Page metrics below cover only questions that are marked answerable and carry at least one annotated gold page; a question with no annotated gold page is excluded even when it is marked answerable. Quote metrics include only questions with a non-empty gold quote. Content-verified pages require the full normalized source-node text to be present in the emitted context.

Quote-match policy: **`nfkc-unified-punctuation-ordered-elision-v3`**. Quote figures are comparable only against artifacts carrying the same policy; an artifact without the field is `literal-casefold-v1`, which matched a gold quote only where it appeared verbatim after casefolding and whitespace collapse.

| System | Budget | Answerable gold-page n | Page recall | Content-verified recall | Quoted n | Exact quote recall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 18 | 0.553 | 0.548 | 18 | 0.185 |
| compiler | 4096 | 18 | 0.738 | 0.733 | 18 | 0.292 |
| compiler | 8192 | 18 | 0.806 | 0.800 | 18 | 0.319 |
| compiler | 16384 | 18 | 0.836 | 0.830 | 18 | 0.403 |
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
| compiler | fixed | 2048 | answerable_page_recall | 18 | 9 | +0.328 | [+0.171, +0.460] |
| compiler | fixed | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.333 | [+0.173, +0.467] |
| compiler | fixed | 2048 | quoted_exact_quote_recall | 18 | 9 | -0.032 | [-0.178, +0.133] |
| compiler | structural | 2048 | answerable_page_recall | 18 | 9 | +0.169 | [-0.010, +0.317] |
| compiler | structural | 2048 | answerable_content_verified_page_recall | 18 | 9 | +0.213 | [+0.044, +0.352] |
| compiler | structural | 2048 | quoted_exact_quote_recall | 18 | 9 | -0.074 | [-0.142, -0.016] |
| compiler | fixed | 4096 | answerable_page_recall | 18 | 9 | +0.307 | [+0.161, +0.434] |
| compiler | fixed | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.321 | [+0.173, +0.439] |
| compiler | fixed | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.042 | [-0.077, +0.194] |
| compiler | structural | 4096 | answerable_page_recall | 18 | 9 | +0.245 | [+0.082, +0.385] |
| compiler | structural | 4096 | answerable_content_verified_page_recall | 18 | 9 | +0.332 | [+0.211, +0.431] |
| compiler | structural | 4096 | quoted_exact_quote_recall | 18 | 9 | +0.032 | [-0.028, +0.111] |
| compiler | fixed | 8192 | answerable_page_recall | 18 | 9 | +0.158 | [+0.021, +0.272] |
| compiler | fixed | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.166 | [+0.033, +0.279] |
| compiler | fixed | 8192 | quoted_exact_quote_recall | 18 | 9 | -0.014 | [-0.179, +0.150] |
| compiler | structural | 8192 | answerable_page_recall | 18 | 9 | +0.177 | [+0.005, +0.322] |
| compiler | structural | 8192 | answerable_content_verified_page_recall | 18 | 9 | +0.248 | [+0.104, +0.372] |
| compiler | structural | 8192 | quoted_exact_quote_recall | 18 | 9 | +0.032 | [-0.071, +0.149] |
| compiler | fixed | 16384 | answerable_page_recall | 18 | 9 | +0.056 | [-0.069, +0.146] |
| compiler | fixed | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.073 | [-0.049, +0.163] |
| compiler | fixed | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.000 | [-0.105, +0.156] |
| compiler | structural | 16384 | answerable_page_recall | 18 | 9 | +0.103 | [-0.022, +0.225] |
| compiler | structural | 16384 | answerable_content_verified_page_recall | 18 | 9 | +0.179 | [+0.044, +0.301] |
| compiler | structural | 16384 | quoted_exact_quote_recall | 18 | 9 | +0.102 | [+0.000, +0.211] |

## Non-inferiority check

Margin: **-0.03** on answerable page recall. A check passes when the lower bound of the paired 95% interval is strictly above the margin. Page recall alone decides the verdict, as specified; the content-verified and quote intervals are shown beside it because page recall has moved opposite to quote recall on this benchmark, and a verdict read without them is a verdict read half-blind.

**A pass is confirmatory only where one unit cannot cross the margin on its own.** That needs at least 34 eligible questions and at least 34 source clusters: below either, a delta moves by more than 0.03 when a single question flips or a single cluster is resampled away, so the interval is being tested against a threshold finer than the instrument that produced it. Every such row is reported as *screening*, and a screening pass is not evidence of non-inferiority.

| Baseline | Budget | Page delta | Page 95% interval | Status | Content-verified delta | Quote delta |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| fixed | 2048 | +0.328 | [+0.171, +0.460] | screening pass | +0.333 [+0.173, +0.467] | -0.032 [-0.178, +0.133] |
| structural | 2048 | +0.169 | [-0.010, +0.317] | screening pass | +0.213 [+0.044, +0.352] | -0.074 [-0.142, -0.016] |
| fixed | 4096 | +0.307 | [+0.161, +0.434] | screening pass | +0.321 [+0.173, +0.439] | +0.042 [-0.077, +0.194] |
| structural | 4096 | +0.245 | [+0.082, +0.385] | screening pass | +0.332 [+0.211, +0.431] | +0.032 [-0.028, +0.111] |
| fixed | 8192 | +0.158 | [+0.021, +0.272] | screening pass | +0.166 [+0.033, +0.279] | -0.014 [-0.179, +0.150] |
| structural | 8192 | +0.177 | [+0.005, +0.322] | screening pass | +0.248 [+0.104, +0.372] | +0.032 [-0.071, +0.149] |
| fixed | 16384 | +0.056 | [-0.069, +0.146] | screening fail | +0.073 [-0.049, +0.163] | +0.000 [-0.105, +0.156] |
| structural | 16384 | +0.103 | [-0.022, +0.225] | screening pass | +0.179 [+0.044, +0.301] | +0.102 [+0.000, +0.211] |

## Rendered evidence and gold-answer presence

Rendered tokens are the evidence block as the answer prompt carries it -- tags, evidence IDs, joiners and content -- and are what the budget counts unless a run chose content accounting. Answer presence asks whether the normalised gold answer is written inside a single packed item; unanswerable questions are not applicable and are excluded. It cannot see an answer the question asks to be computed, and a short number can be present by chance, so read it as a floor on retrieval failure, not as answer accuracy.

| System | Budget | Mean content tokens | Mean rendered tokens | Answer-present n | Answer present |
| --- | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 1660.0 | 2042.8 | 18 | 0.444 |
| compiler | 4096 | 3333.3 | 4090.7 | 18 | 0.500 |
| compiler | 8192 | 6689.3 | 8184.8 | 18 | 0.556 |
| compiler | 16384 | 12986.4 | 15707.0 | 18 | 0.611 |
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
| compiler | 2048 | casefold_exact_match | 15 | 6 | 0.400 |
| compiler | 2048 | numeric_tolerance | 2 | 2 | 1.000 |
| compiler | 2048 | percentage_exact | 1 | 0 | 0.000 |
| compiler | 4096 | casefold_exact_match | 15 | 7 | 0.467 |
| compiler | 4096 | numeric_tolerance | 2 | 2 | 1.000 |
| compiler | 4096 | percentage_exact | 1 | 0 | 0.000 |
| compiler | 8192 | casefold_exact_match | 15 | 8 | 0.533 |
| compiler | 8192 | numeric_tolerance | 2 | 2 | 1.000 |
| compiler | 8192 | percentage_exact | 1 | 0 | 0.000 |
| compiler | 16384 | casefold_exact_match | 15 | 9 | 0.600 |
| compiler | 16384 | numeric_tolerance | 2 | 2 | 1.000 |
| compiler | 16384 | percentage_exact | 1 | 0 | 0.000 |
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
