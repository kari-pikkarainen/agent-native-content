# Experiment: XLDev24 keyed cross-table join confirmation at `3022ce3`

Status: accepted as the selected compiler policy and promoted in compiler
version `0.5.0`.

## Confirmation run

Run `artifacts/runs/xldev24-keyed-table-joins-3022ce3` evaluates all 24
questions in `benchmarks/xl-docbench/subsets/xldev24.json` over its fixed 11-document corpus.
It uses the same retrieval models, budgets, and baseline arms as selected
control `artifacts/runs/xldev24-facets-7dd7492` and enables deterministic keyed
table joins.

The confirmation follows the successful failure-selected diagnostic recorded
in `xldev2-keyed-table-joins-e3200a6.md`. No XL100 or holdout question was
inspected.

## Aggregate comparison

| Budget | Selected control recall | Keyed-join recall | Delta | Control redundancy | Join redundancy |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2K | 0.647 | **0.651** | +0.0042 | 0.136 | 0.138 |
| 4K | 0.713 | **0.717** | +0.0042 | 0.169 | 0.174 |
| 8K | 0.791 | **0.795** | +0.0042 | 0.212 | 0.214 |
| 16K | 0.891 | **0.895** | +0.0042 | 0.298 | 0.300 |

Full-evidence coverage is unchanged at every budget:
0.333/0.333/0.417/0.667. The small aggregate recall improvement is expected:
one of 24 questions improves by 0.10 at each budget.

Against the best baseline in the confirmation run, the compiler leads mean
page recall by 0.177/0.087/0.040/0.059 at 2K/4K/8K/16K. It leads full coverage
at 2K and 16K, trails by one question at 4K and 8K, and retains higher
redundancy than both baselines.

Wall-clock compiler means are 6.2/6.0/6.3/11.2 seconds in this run. They are
higher than the earlier control run, but separate-run timing includes normal
model and machine variance. The treatment invokes its additional reranker only
for one question and three pre-collapse candidates, so these runs do not
support attributing the full timing difference to keyed joins.

## Activation and regression audit

Only `adubench_single_000703` activates keyed joining. Its page recall rises
from 0.150/0.200/0.350/0.550 to 0.250/0.300/0.450/0.650. At every budget, the
first compiler evidence item is a 93-token joined candidate containing:

- the normalized `ipsl-cm5a2-inca` key;
- an `IPSL:IPSL-CM5A2-INCA` dataset row from Table AII.10;
- `Models: IPSL-CM5A2-INCA | Main References: [blank]` from Table AII.5;
- both IR table node IDs and Docling items `#/tables/27` and `#/tables/14`.

For the other 23 questions, all 92 packed compiler cells are item-for-item and
token-count identical to the selected control. Their metric records are also
identical except for separately measured latency. Thus the confirmed gain is
isolated to the eligible reconciliation question, with no observed context or
retrieval regression elsewhere in XLDev24.

## Decision

Promote keyed table joins to the selected compiler default. The policy is
narrow, deterministic, bounded, source-derived, and reversible through
`keyed_table_join_enabled=false` or the CLI opt-out flag. It solves the exact
relational failure that independent row retrieval could not solve, improves
the eligible question at every budget, and leaves every ineligible context
unchanged.

This is not evidence of a broad gain across table questions: only one XLDev24
question activates the path. Holdout evaluation should report activation count
and results separately. The XL100 configuration must be frozen before that run;
no further tuning may use its questions.
