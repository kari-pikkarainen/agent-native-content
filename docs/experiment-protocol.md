# Experiment Protocol

The benchmark protocol will define dataset revisions, deterministic subsets,
shared model settings, token budgets, seeds, metrics, immutable output
artifacts, and decision gates.

The protocol will be completed before benchmark results are inspected. Until
then, the authoritative requirements are in
[`benchmark-spec.md`](benchmark-spec.md).

## Development dataset

Milestone 1 pins the conservative XL-DocBench release as follows:

- dataset: `microsoft/XL-DocBench`
- release: `xldocbench_strict_1345_v1`
- revision: `72954bd70ffffe230f08b57c57fa9274ec14d7ea`
- evidence pages: one-based PDF/release indices

The development subset is the explicit ordered list in
`configs/subsets/xl100.json`. It contains 100 questions balanced across all six
domains, including 80 single-document and 20 cross-document questions. The
selection includes zero-, one-, and multi-page evidence cases and both textual
and table/visual evidence. Benchmark commands load this list and never
regenerate it implicitly.
