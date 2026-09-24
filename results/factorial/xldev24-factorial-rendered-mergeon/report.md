# Content-unit × selection-policy report: xldev24-factorial-rendered-mergeon-f916545

No structural expansion, table joins, page-neighbor backfill, or answer model participates in this controlled experiment.

| Unit | Policy | Heading | Budget | Page recall | Verified recall | Full pages | Quote recall | Full quotes | Mean tokens | Redundancy | Latency (ms) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed | faceted_coverage | heading-on | 2048 | 0.403 | 0.400 | 0.250 | 0.323 | 0.292 | 1753.2 | 0.056 | 905.36 |
| fixed | faceted_coverage | heading-on | 4096 | 0.556 | 0.545 | 0.333 | 0.465 | 0.333 | 3659.0 | 0.086 | 905.70 |
| fixed | faceted_coverage | heading-on | 8192 | 0.768 | 0.746 | 0.458 | 0.486 | 0.333 | 7693.7 | 0.136 | 908.80 |
| fixed | faceted_coverage | heading-on | 16384 | 0.887 | 0.861 | 0.667 | 0.521 | 0.333 | 15726.5 | 0.195 | 915.33 |
| fixed | ranked | heading-on | 2048 | 0.419 | 0.411 | 0.250 | 0.413 | 0.333 | 1753.8 | 0.063 | 316.10 |
| fixed | ranked | heading-on | 4096 | 0.573 | 0.559 | 0.333 | 0.438 | 0.333 | 3698.3 | 0.110 | 315.78 |
| fixed | ranked | heading-on | 8192 | 0.736 | 0.726 | 0.417 | 0.500 | 0.333 | 7694.5 | 0.171 | 316.35 |
| fixed | ranked | heading-on | 16384 | 0.834 | 0.818 | 0.583 | 0.552 | 0.417 | 15727.0 | 0.240 | 317.91 |
| ir | faceted_coverage | heading-on | 2048 | 0.581 | 0.581 | 0.292 | 0.427 | 0.292 | 1846.0 | 0.051 | 1143.67 |
| ir | faceted_coverage | heading-on | 4096 | 0.734 | 0.734 | 0.458 | 0.438 | 0.292 | 3700.8 | 0.083 | 1150.81 |
| ir | faceted_coverage | heading-on | 8192 | 0.856 | 0.856 | 0.583 | 0.514 | 0.333 | 7454.3 | 0.133 | 1163.10 |
| ir | faceted_coverage | heading-on | 16384 | 0.934 | 0.934 | 0.708 | 0.566 | 0.375 | 14712.0 | 0.177 | 1182.41 |
| ir | ranked | heading-on | 2048 | 0.583 | 0.583 | 0.333 | 0.448 | 0.333 | 1793.3 | 0.076 | 433.06 |
| ir | ranked | heading-on | 4096 | 0.640 | 0.640 | 0.333 | 0.469 | 0.333 | 3649.8 | 0.115 | 432.76 |
| ir | ranked | heading-on | 8192 | 0.762 | 0.762 | 0.458 | 0.521 | 0.375 | 7345.0 | 0.151 | 433.41 |
| ir | ranked | heading-on | 16384 | 0.872 | 0.872 | 0.583 | 0.552 | 0.417 | 14606.5 | 0.193 | 434.81 |
| structural | faceted_coverage | heading-on | 2048 | 0.513 | 0.471 | 0.292 | 0.375 | 0.333 | 1886.8 | 0.038 | 1055.47 |
| structural | faceted_coverage | heading-on | 4096 | 0.611 | 0.556 | 0.333 | 0.431 | 0.375 | 3857.3 | 0.076 | 1057.24 |
| structural | faceted_coverage | heading-on | 8192 | 0.730 | 0.646 | 0.458 | 0.465 | 0.375 | 7785.1 | 0.108 | 1061.31 |
| structural | faceted_coverage | heading-on | 16384 | 0.811 | 0.738 | 0.542 | 0.476 | 0.375 | 14636.0 | 0.141 | 1068.43 |
| structural | ranked | heading-on | 2048 | 0.536 | 0.501 | 0.292 | 0.444 | 0.375 | 1858.1 | 0.063 | 363.58 |
| structural | ranked | heading-on | 4096 | 0.618 | 0.551 | 0.333 | 0.444 | 0.375 | 3841.2 | 0.101 | 363.73 |
| structural | ranked | heading-on | 8192 | 0.722 | 0.665 | 0.417 | 0.465 | 0.375 | 7765.5 | 0.125 | 364.23 |
| structural | ranked | heading-on | 16384 | 0.799 | 0.738 | 0.542 | 0.476 | 0.375 | 14584.9 | 0.147 | 365.33 |

## Policy effect within each content unit

- fixed at 2048 (heading-on): -0.017 page recall, -0.090 quote recall.
- fixed at 4096 (heading-on): -0.018 page recall, +0.028 quote recall.
- fixed at 8192 (heading-on): +0.033 page recall, -0.014 quote recall.
- fixed at 16384 (heading-on): +0.053 page recall, -0.031 quote recall.
- structural at 2048 (heading-on): -0.023 page recall, -0.069 quote recall.
- structural at 4096 (heading-on): -0.007 page recall, -0.014 quote recall.
- structural at 8192 (heading-on): +0.008 page recall, +0.000 quote recall.
- structural at 16384 (heading-on): +0.011 page recall, +0.000 quote recall.
- ir at 2048 (heading-on): -0.002 page recall, -0.021 quote recall.
- ir at 4096 (heading-on): +0.094 page recall, -0.031 quote recall.
- ir at 8192 (heading-on): +0.094 page recall, -0.007 quote recall.
- ir at 16384 (heading-on): +0.062 page recall, +0.014 quote recall.

## IR effect under each selection policy

- ranked at 2048 (heading-on): IR vs best chunk unit (structural) is +0.047 page recall and +0.003 quote recall.
- ranked at 4096 (heading-on): IR vs best chunk unit (structural) is +0.022 page recall and +0.024 quote recall.
- ranked at 8192 (heading-on): IR vs best chunk unit (fixed) is +0.026 page recall and +0.021 quote recall.
- ranked at 16384 (heading-on): IR vs best chunk unit (fixed) is +0.038 page recall and +0.000 quote recall.
- faceted_coverage at 2048 (heading-on): IR vs best chunk unit (structural) is +0.068 page recall and +0.052 quote recall.
- faceted_coverage at 4096 (heading-on): IR vs best chunk unit (structural) is +0.123 page recall and +0.007 quote recall.
- faceted_coverage at 8192 (heading-on): IR vs best chunk unit (fixed) is +0.087 page recall and +0.028 quote recall.
- faceted_coverage at 16384 (heading-on): IR vs best chunk unit (fixed) is +0.047 page recall and +0.045 quote recall.

This experiment isolates content units from retrieval and packing policy. It does not test structural compiler operators or answer quality.
