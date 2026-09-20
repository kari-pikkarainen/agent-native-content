# XL-DocBench Benchmark Configuration

This directory contains the committed question populations used by the
reference benchmark. Each manifest pins the dataset release and revision,
records how the population was selected, describes its intended use, and lists
question IDs in deterministic order.

## Subsets

| Manifest | Purpose | Claim status |
| --- | --- | --- |
| `xldev2-tables.json` | Two-question table failure analysis | Diagnostic |
| `xldev6-perf.json` | Cross-domain performance checks | Diagnostic |
| `xldev24.json` | Balanced compiler development and selection | Development |
| `xl10.json` | Earlier pipeline smoke/regression set | Contaminated smoke set |
| `xlholdout6.json` | First directional confirmation | Historical holdout |
| `xlholdout6b.json` | Fresh metadata-selected confirmation | Directional holdout |
| `xl100.json` | Registered full evaluation | Not yet run with selected compiler |

Subset intent is part of the experiment contract. Do not silently substitute a
diagnostic or development population for an independent evaluation set.
