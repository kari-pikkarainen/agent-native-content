# Retrieval Decision Report: xlholdout6b-coverage-c8066d6

No answer-generation model was used in this run.

| System | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.513 | 0.000 | 0.300 | 0.167 | 2044.3 | n/a | 0.076 | 4662.50 |
| compiler | 4096 | 0.626 | 0.167 | 0.300 | 0.167 | 4092.3 | 4095.0 | 0.108 | 4686.25 |
| compiler | 8192 | 0.815 | 0.333 | 0.439 | 0.167 | 8189.5 | 5387.0 | 0.161 | 4691.25 |
| compiler | 16384 | 0.935 | 0.500 | 0.522 | 0.333 | 16271.7 | 6510.0 | 0.229 | 5407.00 |
| fixed | 2048 | 0.390 | 0.000 | 0.189 | 0.000 | 2024.5 | n/a | 0.055 | 1401.41 |
| fixed | 4096 | 0.490 | 0.000 | 0.189 | 0.000 | 4051.8 | n/a | 0.120 | 1399.97 |
| fixed | 8192 | 0.856 | 0.500 | 0.356 | 0.167 | 8101.7 | 5067.0 | 0.169 | 1400.04 |
| fixed | 16384 | 1.000 | 1.000 | 0.522 | 0.333 | 16196.3 | 8139.0 | 0.223 | 1400.89 |
| long_context | 2048 | 0.163 | 0.000 | 0.000 | 0.000 | 2048.0 | n/a | 0.103 | 26.54 |
| long_context | 4096 | 0.250 | 0.167 | 0.000 | 0.000 | 4096.0 | 3988.0 | 0.103 | 26.22 |
| long_context | 8192 | 0.447 | 0.333 | 0.133 | 0.000 | 8192.0 | 6778.5 | 0.120 | 25.99 |
| long_context | 16384 | 0.722 | 0.667 | 0.356 | 0.167 | 16384.0 | 12047.0 | 0.152 | 102.09 |
| structural | 2048 | 0.314 | 0.000 | 0.267 | 0.167 | 2023.7 | n/a | 0.083 | 2247.26 |
| structural | 4096 | 0.546 | 0.167 | 0.433 | 0.333 | 4062.3 | 2625.0 | 0.123 | 2245.59 |
| structural | 8192 | 0.554 | 0.167 | 0.433 | 0.333 | 8153.0 | 2625.0 | 0.139 | 2246.13 |
| structural | 16384 | 0.824 | 0.500 | 0.489 | 0.333 | 16342.0 | 9585.0 | 0.170 | 2246.59 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.000 full-coverage, +0.122 recall.
- 4096 tokens: compiler vs best baseline: +0.000 full-coverage, +0.081 recall.
- 8192 tokens: compiler vs best baseline: -0.167 full-coverage, -0.040 recall.
- 16384 tokens: compiler vs best baseline: -0.500 full-coverage, -0.065 recall.

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
