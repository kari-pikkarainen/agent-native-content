# Content-unit × selection-policy report: xldev24-factorial-6cc7fd9

No structural expansion, table joins, page-neighbor backfill, or answer model participates in this controlled experiment.

| Unit | Policy | Heading | Budget | Page recall | Verified recall | Full pages | Quote recall | Full quotes | Mean tokens | Redundancy | Latency (ms) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed | faceted_coverage | heading-on | 2048 | 0.430 | 0.428 | 0.250 | 0.292 | 0.292 | 2018.4 | 0.059 | 932.91 |
| fixed | faceted_coverage | heading-on | 4096 | 0.585 | 0.571 | 0.333 | 0.424 | 0.333 | 4034.7 | 0.091 | 933.20 |
| fixed | faceted_coverage | heading-on | 8192 | 0.778 | 0.756 | 0.458 | 0.444 | 0.333 | 8043.5 | 0.140 | 934.83 |
| fixed | faceted_coverage | heading-on | 16384 | 0.887 | 0.861 | 0.667 | 0.465 | 0.333 | 16130.2 | 0.198 | 937.54 |
| fixed | ranked | heading-on | 2048 | 0.468 | 0.454 | 0.292 | 0.347 | 0.333 | 2015.3 | 0.077 | 311.52 |
| fixed | ranked | heading-on | 4096 | 0.594 | 0.583 | 0.333 | 0.361 | 0.333 | 4035.1 | 0.115 | 310.66 |
| fixed | ranked | heading-on | 8192 | 0.739 | 0.726 | 0.417 | 0.465 | 0.375 | 8044.4 | 0.177 | 310.70 |
| fixed | ranked | heading-on | 16384 | 0.843 | 0.826 | 0.583 | 0.476 | 0.375 | 16136.9 | 0.241 | 310.80 |
| ir | faceted_coverage | heading-on | 2048 | 0.711 | 0.711 | 0.375 | 0.326 | 0.250 | 2047.6 | 0.068 | 949.95 |
| ir | faceted_coverage | heading-on | 4096 | 0.807 | 0.807 | 0.542 | 0.361 | 0.292 | 3907.9 | 0.095 | 957.16 |
| ir | faceted_coverage | heading-on | 8192 | 0.860 | 0.860 | 0.583 | 0.424 | 0.333 | 7152.3 | 0.136 | 972.26 |
| ir | faceted_coverage | heading-on | 16384 | 0.884 | 0.884 | 0.583 | 0.476 | 0.375 | 12265.6 | 0.182 | 984.10 |
| ir | ranked | heading-on | 2048 | 0.655 | 0.655 | 0.333 | 0.392 | 0.333 | 2047.5 | 0.089 | 401.71 |
| ir | ranked | heading-on | 4096 | 0.724 | 0.724 | 0.333 | 0.413 | 0.333 | 3930.0 | 0.128 | 401.47 |
| ir | ranked | heading-on | 8192 | 0.791 | 0.791 | 0.500 | 0.444 | 0.333 | 7155.5 | 0.158 | 401.71 |
| ir | ranked | heading-on | 16384 | 0.860 | 0.860 | 0.542 | 0.465 | 0.375 | 12382.5 | 0.188 | 402.12 |
| structural | faceted_coverage | heading-on | 2048 | 0.554 | 0.511 | 0.333 | 0.344 | 0.333 | 2030.2 | 0.037 | 1076.65 |
| structural | faceted_coverage | heading-on | 4096 | 0.622 | 0.565 | 0.333 | 0.385 | 0.375 | 4059.3 | 0.078 | 1078.13 |
| structural | faceted_coverage | heading-on | 8192 | 0.755 | 0.674 | 0.500 | 0.399 | 0.375 | 8132.4 | 0.110 | 1080.96 |
| structural | faceted_coverage | heading-on | 16384 | 0.811 | 0.738 | 0.542 | 0.410 | 0.375 | 15100.1 | 0.143 | 1085.71 |
| structural | ranked | heading-on | 2048 | 0.531 | 0.494 | 0.292 | 0.399 | 0.375 | 2032.1 | 0.067 | 366.62 |
| structural | ranked | heading-on | 4096 | 0.634 | 0.568 | 0.333 | 0.399 | 0.375 | 4059.8 | 0.102 | 366.18 |
| structural | ranked | heading-on | 8192 | 0.734 | 0.677 | 0.458 | 0.399 | 0.375 | 8154.4 | 0.129 | 366.26 |
| structural | ranked | heading-on | 16384 | 0.808 | 0.747 | 0.542 | 0.431 | 0.375 | 15071.8 | 0.150 | 366.51 |

## Policy effect within each content unit

- fixed at 2048 (heading-on): -0.038 page recall, -0.056 quote recall.
- fixed at 4096 (heading-on): -0.008 page recall, +0.062 quote recall.
- fixed at 8192 (heading-on): +0.039 page recall, -0.021 quote recall.
- fixed at 16384 (heading-on): +0.045 page recall, -0.010 quote recall.
- structural at 2048 (heading-on): +0.023 page recall, -0.056 quote recall.
- structural at 4096 (heading-on): -0.013 page recall, -0.014 quote recall.
- structural at 8192 (heading-on): +0.020 page recall, +0.000 quote recall.
- structural at 16384 (heading-on): +0.003 page recall, -0.021 quote recall.
- ir at 2048 (heading-on): +0.056 page recall, -0.066 quote recall.
- ir at 4096 (heading-on): +0.083 page recall, -0.052 quote recall.
- ir at 8192 (heading-on): +0.069 page recall, -0.021 quote recall.
- ir at 16384 (heading-on): +0.023 page recall, +0.010 quote recall.

## IR effect under each selection policy

- ranked at 2048 (heading-on): IR vs best chunk unit (structural) is +0.124 page recall and -0.007 quote recall.
- ranked at 4096 (heading-on): IR vs best chunk unit (structural) is +0.090 page recall and +0.014 quote recall.
- ranked at 8192 (heading-on): IR vs best chunk unit (fixed) is +0.052 page recall and -0.021 quote recall.
- ranked at 16384 (heading-on): IR vs best chunk unit (fixed) is +0.018 page recall and -0.010 quote recall.
- faceted_coverage at 2048 (heading-on): IR vs best chunk unit (structural) is +0.157 page recall and -0.017 quote recall.
- faceted_coverage at 4096 (heading-on): IR vs best chunk unit (structural) is +0.185 page recall and -0.024 quote recall.
- faceted_coverage at 8192 (heading-on): IR vs best chunk unit (fixed) is +0.082 page recall and -0.021 quote recall.
- faceted_coverage at 16384 (heading-on): IR vs best chunk unit (fixed) is -0.003 page recall and +0.010 quote recall.

This experiment isolates content units from retrieval and packing policy. It does not test structural compiler operators or answer quality.
