# Content-unit × selection-policy report: xldev2-factorial-8c8e044

No structural expansion, table joins, page-neighbor backfill, or answer model participates in this controlled experiment.

| Unit | Policy | Budget | Page recall | Full pages | Quote recall | Full quotes | Mean tokens | Redundancy | Latency (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed | faceted_coverage | 2048 | 0.373 | 0.000 | 0.000 | 0.000 | 2042.0 | 0.053 | 993.69 |
| fixed | faceted_coverage | 4096 | 0.373 | 0.000 | 0.000 | 0.000 | 4081.0 | 0.120 | 993.80 |
| fixed | faceted_coverage | 8192 | 0.609 | 0.000 | 0.000 | 0.000 | 8158.5 | 0.176 | 998.16 |
| fixed | faceted_coverage | 16384 | 0.750 | 0.500 | 0.000 | 0.000 | 16288.5 | 0.267 | 999.78 |
| fixed | ranked | 2048 | 0.145 | 0.000 | 0.000 | 0.000 | 2040.5 | 0.074 | 590.78 |
| fixed | ranked | 4096 | 0.145 | 0.000 | 0.000 | 0.000 | 4082.5 | 0.125 | 589.76 |
| fixed | ranked | 8192 | 0.473 | 0.000 | 0.000 | 0.000 | 8154.0 | 0.207 | 589.12 |
| fixed | ranked | 16384 | 0.614 | 0.000 | 0.000 | 0.000 | 16291.5 | 0.284 | 589.64 |
| ir | faceted_coverage | 2048 | 0.302 | 0.000 | 0.000 | 0.000 | 2048.0 | 0.049 | 963.55 |
| ir | faceted_coverage | 4096 | 0.418 | 0.000 | 0.000 | 0.000 | 4096.0 | 0.077 | 964.06 |
| ir | faceted_coverage | 8192 | 0.584 | 0.000 | 0.000 | 0.000 | 8192.0 | 0.197 | 969.03 |
| ir | faceted_coverage | 16384 | 0.755 | 0.000 | 0.000 | 0.000 | 16383.5 | 0.243 | 976.78 |
| ir | ranked | 2048 | 0.211 | 0.000 | 0.000 | 0.000 | 2048.0 | 0.052 | 402.82 |
| ir | ranked | 4096 | 0.236 | 0.000 | 0.000 | 0.000 | 4095.5 | 0.072 | 402.63 |
| ir | ranked | 8192 | 0.357 | 0.000 | 0.000 | 0.000 | 8192.0 | 0.162 | 403.13 |
| ir | ranked | 16384 | 0.593 | 0.000 | 0.000 | 0.000 | 16384.0 | 0.239 | 403.27 |
| structural | faceted_coverage | 2048 | 0.145 | 0.000 | 0.500 | 0.500 | 2008.5 | 0.036 | 1068.97 |
| structural | faceted_coverage | 4096 | 0.266 | 0.000 | 0.500 | 0.500 | 4029.0 | 0.116 | 1068.02 |
| structural | faceted_coverage | 8192 | 0.755 | 0.000 | 0.500 | 0.500 | 8080.5 | 0.167 | 1069.79 |
| structural | faceted_coverage | 16384 | 0.805 | 0.000 | 0.500 | 0.500 | 16159.5 | 0.231 | 1071.49 |
| structural | ranked | 2048 | 0.236 | 0.000 | 0.000 | 0.000 | 2017.5 | 0.113 | 361.85 |
| structural | ranked | 4096 | 0.332 | 0.000 | 0.000 | 0.000 | 4081.5 | 0.145 | 361.62 |
| structural | ranked | 8192 | 0.527 | 0.000 | 0.500 | 0.500 | 8102.5 | 0.199 | 361.39 |
| structural | ranked | 16384 | 0.714 | 0.000 | 0.500 | 0.500 | 16277.0 | 0.240 | 361.42 |

## Policy effect within each content unit

- fixed at 2048: +0.227 page recall, +0.000 quote recall.
- fixed at 4096: +0.227 page recall, +0.000 quote recall.
- fixed at 8192: +0.136 page recall, +0.000 quote recall.
- fixed at 16384: +0.136 page recall, +0.000 quote recall.
- structural at 2048: -0.091 page recall, +0.500 quote recall.
- structural at 4096: -0.066 page recall, +0.500 quote recall.
- structural at 8192: +0.227 page recall, +0.000 quote recall.
- structural at 16384: +0.091 page recall, +0.000 quote recall.
- ir at 2048: +0.091 page recall, +0.000 quote recall.
- ir at 4096: +0.182 page recall, +0.000 quote recall.
- ir at 8192: +0.227 page recall, +0.000 quote recall.
- ir at 16384: +0.161 page recall, +0.000 quote recall.

## IR effect under each selection policy

- ranked at 2048: IR vs best chunk unit (structural) is -0.025 page recall and +0.000 quote recall.
- ranked at 4096: IR vs best chunk unit (structural) is -0.095 page recall and +0.000 quote recall.
- ranked at 8192: IR vs best chunk unit (structural) is -0.170 page recall and -0.500 quote recall.
- ranked at 16384: IR vs best chunk unit (structural) is -0.120 page recall and -0.500 quote recall.
- faceted_coverage at 2048: IR vs best chunk unit (fixed) is -0.070 page recall and +0.000 quote recall.
- faceted_coverage at 4096: IR vs best chunk unit (fixed) is +0.045 page recall and +0.000 quote recall.
- faceted_coverage at 8192: IR vs best chunk unit (structural) is -0.170 page recall and -0.500 quote recall.
- faceted_coverage at 16384: IR vs best chunk unit (structural) is -0.050 page recall and -0.500 quote recall.

This experiment isolates content units from retrieval and packing policy. It does not test structural compiler operators or answer quality.
