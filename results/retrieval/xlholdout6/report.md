# Retrieval Decision Report: xlholdout6-faceted-fcca4d0

No answer-generation model was used in this run.

| System | Budget | Page recall | Full coverage | Mean tokens | Median tokens-to-full | Redundancy | Latency (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 0.230 | 0.000 | 2046.3 | n/a | 0.120 | 4251.46 |
| compiler | 4096 | 0.395 | 0.000 | 4092.8 | n/a | 0.170 | 4014.82 |
| compiler | 8192 | 0.488 | 0.000 | 8190.7 | n/a | 0.194 | 4014.38 |
| compiler | 16384 | 0.697 | 0.167 | 16379.7 | 10818.0 | 0.228 | 4015.46 |
| fixed | 2048 | 0.264 | 0.000 | 2022.8 | n/a | 0.104 | 1148.26 |
| fixed | 4096 | 0.390 | 0.000 | 4048.0 | n/a | 0.146 | 1147.29 |
| fixed | 8192 | 0.522 | 0.000 | 8104.7 | n/a | 0.212 | 1147.40 |
| fixed | 16384 | 0.735 | 0.167 | 16196.2 | 13448.0 | 0.239 | 1147.35 |
| structural | 2048 | 0.251 | 0.000 | 2028.5 | n/a | 0.096 | 1474.97 |
| structural | 4096 | 0.332 | 0.000 | 4087.7 | n/a | 0.110 | 1474.26 |
| structural | 8192 | 0.578 | 0.000 | 8184.7 | n/a | 0.164 | 1474.31 |
| structural | 16384 | 0.767 | 0.333 | 16327.0 | 14680.5 | 0.186 | 1474.38 |

## Evidence-only decision gate

- 2048 tokens: compiler vs best baseline: +0.000 full-coverage, -0.034 recall.
- 4096 tokens: compiler vs best baseline: +0.000 full-coverage, +0.005 recall.
- 8192 tokens: compiler vs best baseline: +0.000 full-coverage, -0.090 recall.
- 16384 tokens: compiler vs best baseline: -0.167 full-coverage, -0.070 recall.

Review the recall/coverage curve before generation work. This report does not establish answer accuracy or the broader technical thesis.
