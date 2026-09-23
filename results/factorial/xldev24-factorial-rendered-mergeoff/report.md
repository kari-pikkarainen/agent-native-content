# Content-unit × selection-policy report: xldev24-factorial-rendered-mergeoff-f916545

No structural expansion, table joins, page-neighbor backfill, or answer model participates in this controlled experiment.

| Unit | Policy | Heading | Budget | Page recall | Verified recall | Full pages | Quote recall | Full quotes | Mean tokens | Redundancy | Latency (ms) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed | faceted_coverage | heading-on | 2048 | 0.403 | 0.400 | 0.250 | 0.323 | 0.292 | 1753.2 | 0.056 | 950.60 |
| fixed | faceted_coverage | heading-on | 4096 | 0.556 | 0.545 | 0.333 | 0.465 | 0.333 | 3659.0 | 0.086 | 951.84 |
| fixed | faceted_coverage | heading-on | 8192 | 0.768 | 0.746 | 0.458 | 0.486 | 0.333 | 7693.7 | 0.136 | 955.20 |
| fixed | faceted_coverage | heading-on | 16384 | 0.887 | 0.861 | 0.667 | 0.521 | 0.333 | 15726.5 | 0.195 | 962.18 |
| fixed | ranked | heading-on | 2048 | 0.419 | 0.411 | 0.250 | 0.413 | 0.333 | 1753.8 | 0.063 | 323.34 |
| fixed | ranked | heading-on | 4096 | 0.573 | 0.559 | 0.333 | 0.438 | 0.333 | 3698.3 | 0.110 | 323.15 |
| fixed | ranked | heading-on | 8192 | 0.736 | 0.726 | 0.417 | 0.500 | 0.333 | 7694.5 | 0.171 | 324.19 |
| fixed | ranked | heading-on | 16384 | 0.834 | 0.818 | 0.583 | 0.552 | 0.417 | 15727.0 | 0.240 | 325.35 |
| ir | faceted_coverage | heading-on | 2048 | 0.682 | 0.682 | 0.375 | 0.361 | 0.250 | 1650.9 | 0.063 | 973.56 |
| ir | faceted_coverage | heading-on | 4096 | 0.794 | 0.794 | 0.500 | 0.417 | 0.292 | 3354.7 | 0.088 | 984.27 |
| ir | faceted_coverage | heading-on | 8192 | 0.849 | 0.849 | 0.583 | 0.469 | 0.333 | 6482.8 | 0.130 | 999.99 |
| ir | faceted_coverage | heading-on | 16384 | 0.884 | 0.884 | 0.583 | 0.542 | 0.375 | 11625.3 | 0.176 | 1019.64 |
| ir | ranked | heading-on | 2048 | 0.615 | 0.615 | 0.292 | 0.413 | 0.333 | 1581.2 | 0.071 | 400.49 |
| ir | ranked | heading-on | 4096 | 0.695 | 0.695 | 0.333 | 0.438 | 0.333 | 3160.8 | 0.117 | 400.51 |
| ir | ranked | heading-on | 8192 | 0.782 | 0.782 | 0.458 | 0.500 | 0.333 | 6222.9 | 0.153 | 401.50 |
| ir | ranked | heading-on | 16384 | 0.843 | 0.843 | 0.500 | 0.531 | 0.375 | 11496.0 | 0.184 | 402.66 |
| structural | faceted_coverage | heading-on | 2048 | 0.513 | 0.471 | 0.292 | 0.375 | 0.333 | 1886.8 | 0.038 | 1073.55 |
| structural | faceted_coverage | heading-on | 4096 | 0.611 | 0.556 | 0.333 | 0.431 | 0.375 | 3857.3 | 0.076 | 1075.66 |
| structural | faceted_coverage | heading-on | 8192 | 0.730 | 0.646 | 0.458 | 0.465 | 0.375 | 7785.1 | 0.108 | 1081.09 |
| structural | faceted_coverage | heading-on | 16384 | 0.811 | 0.738 | 0.542 | 0.476 | 0.375 | 14636.0 | 0.141 | 1088.20 |
| structural | ranked | heading-on | 2048 | 0.536 | 0.501 | 0.292 | 0.444 | 0.375 | 1858.1 | 0.063 | 384.59 |
| structural | ranked | heading-on | 4096 | 0.618 | 0.551 | 0.333 | 0.444 | 0.375 | 3841.2 | 0.101 | 384.67 |
| structural | ranked | heading-on | 8192 | 0.722 | 0.665 | 0.417 | 0.465 | 0.375 | 7765.5 | 0.125 | 385.29 |
| structural | ranked | heading-on | 16384 | 0.799 | 0.738 | 0.542 | 0.476 | 0.375 | 14584.9 | 0.147 | 386.31 |

## Policy effect within each content unit

- fixed at 2048 (heading-on): -0.017 page recall, -0.090 quote recall.
- fixed at 4096 (heading-on): -0.018 page recall, +0.028 quote recall.
- fixed at 8192 (heading-on): +0.033 page recall, -0.014 quote recall.
- fixed at 16384 (heading-on): +0.053 page recall, -0.031 quote recall.
- structural at 2048 (heading-on): -0.023 page recall, -0.069 quote recall.
- structural at 4096 (heading-on): -0.007 page recall, -0.014 quote recall.
- structural at 8192 (heading-on): +0.008 page recall, +0.000 quote recall.
- structural at 16384 (heading-on): +0.011 page recall, +0.000 quote recall.
- ir at 2048 (heading-on): +0.067 page recall, -0.052 quote recall.
- ir at 4096 (heading-on): +0.099 page recall, -0.021 quote recall.
- ir at 8192 (heading-on): +0.068 page recall, -0.031 quote recall.
- ir at 16384 (heading-on): +0.041 page recall, +0.010 quote recall.

## IR effect under each selection policy

- ranked at 2048 (heading-on): IR vs best chunk unit (structural) is +0.079 page recall and -0.031 quote recall.
- ranked at 4096 (heading-on): IR vs best chunk unit (structural) is +0.077 page recall and -0.007 quote recall.
- ranked at 8192 (heading-on): IR vs best chunk unit (fixed) is +0.046 page recall and +0.000 quote recall.
- ranked at 16384 (heading-on): IR vs best chunk unit (fixed) is +0.009 page recall and -0.021 quote recall.
- faceted_coverage at 2048 (heading-on): IR vs best chunk unit (structural) is +0.168 page recall and -0.014 quote recall.
- faceted_coverage at 4096 (heading-on): IR vs best chunk unit (structural) is +0.183 page recall and -0.014 quote recall.
- faceted_coverage at 8192 (heading-on): IR vs best chunk unit (fixed) is +0.081 page recall and -0.017 quote recall.
- faceted_coverage at 16384 (heading-on): IR vs best chunk unit (fixed) is -0.003 page recall and +0.021 quote recall.

This experiment isolates content units from retrieval and packing policy. It does not test structural compiler operators or answer quality.
