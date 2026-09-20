# Retrieval Decision Report: xldev24-coverage-packing-87df330

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.727 | 0.417 | 0.354 | 0.292 | 2046.5 | 0.0 | 0.086 | 4291.82 |
| compiler | 4096 | 0.791 | 0.458 | 0.389 | 0.333 | 3923.7 | 0.0 | 0.123 | 4147.67 |
| compiler | 8192 | 0.864 | 0.583 | 0.476 | 0.375 | 7507.4 | 1226.0 | 0.191 | 4171.21 |
| compiler | 16384 | 0.922 | 0.667 | 0.517 | 0.417 | 16292.3 | 1688.5 | 0.290 | 6004.62 |
| fixed | 2048 | 0.474 | 0.292 | 0.326 | 0.292 | 2013.9 | 0.0 | 0.085 | 1646.84 |
| fixed | 4096 | 0.631 | 0.375 | 0.340 | 0.292 | 4031.2 | 0.0 | 0.126 | 1644.81 |
| fixed | 8192 | 0.755 | 0.458 | 0.465 | 0.375 | 8035.3 | 0.0 | 0.185 | 1644.69 |
| fixed | 16384 | 0.836 | 0.625 | 0.476 | 0.375 | 16168.1 | 2542.0 | 0.240 | 1645.92 |
| long_context | 2048 | 0.425 | 0.292 | 0.260 | 0.250 | 2048.0 | 0.0 | 0.084 | 79.92 |
| long_context | 4096 | 0.559 | 0.375 | 0.326 | 0.250 | 4096.0 | 0.0 | 0.098 | 78.43 |
| long_context | 8192 | 0.652 | 0.375 | 0.378 | 0.292 | 8192.0 | 0.0 | 0.130 | 78.80 |
| long_context | 16384 | 0.749 | 0.583 | 0.434 | 0.292 | 15981.8 | 2985.5 | 0.171 | 79.35 |
| structural | 2048 | 0.502 | 0.250 | 0.333 | 0.333 | 2027.8 | 0.0 | 0.063 | 1915.21 |
| structural | 4096 | 0.624 | 0.333 | 0.358 | 0.333 | 4077.6 | 0.0 | 0.091 | 1914.90 |
| structural | 8192 | 0.745 | 0.458 | 0.399 | 0.375 | 8156.2 | 0.0 | 0.126 | 1914.93 |
| structural | 16384 | 0.810 | 0.542 | 0.431 | 0.375 | 15398.5 | 2128.0 | 0.151 | 1914.86 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.125 full-coverage, +0.253 recall.
- 4096 tokens: compiler vs best baseline: +0.083 full-coverage, +0.160 recall.
- 8192 tokens: compiler vs best baseline: +0.125 full-coverage, +0.109 recall.
- 16384 tokens: compiler vs best baseline: +0.042 full-coverage, +0.086 recall.

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
