# Improvement Plan: From Low-Budget Advantage to a Defensible Result

Status: revised after two review rounds on 2026-09-21. Phase 0 complete (Gate 0
passed, `30f14a1`). Phase 1 tasks 1 to 8 complete and the configuration frozen
at `c7e56fa`; Gate 1 (task 9) is next and `xlholdout6c` has not been run. Task
10 follows only if Gate 1 passes. Updated 2026-09-23.
Date: 2026-09-21
Baseline commit: `0b57eab`

Progress against this plan is recorded in `docs/research-log/`, not by editing
the tasks below, which stay as written so the plan can be read against what
was done. Where the work departed from a task, the record says so:

- Task 5's non-inferiority check is emitted on every run for both baselines,
  not fixed RAG alone, and states that no current population is confirmatory.
- Task 7 could not be done as written. Caching cross-encoder scores per query
  and node, and regression-testing rankings as unchanged, are mutually
  exclusive because the reranker is not invariant to batch composition. The
  2x latency target was not met and was ruled a documented limitation rather
  than a Gate 1 blocker. See commit `a421321`.
- Task 8's D1 to D4 ladder sets the page-neighbour radius to zero on every
  rung, so two configurations outside the spec series were added to attribute
  page neighbours and keyed joins.
- Beyond the tasks, exact quote recall was re-scored twice (policies v2 and v3)
  after an audit found the metric measuring annotation style, and the
  configuration was frozen with sibling expansion on. See
  `docs/research-log/phase1-closeout-c7e56fa.md`.

## Purpose

The compiler currently beats the best RAG baseline at 2K and 4K tokens on the
development set and the directional holdout, loses to fixed RAG at 8K and 16K
on the holdout, and has no answer-quality result. That is enough to keep the
idea alive and not enough to justify building a persistent Content IR layer.

This plan sets out how to reach one of two clean outcomes:

1. technical validation under the preregistered success criteria in
   [benchmark specification §26](../specs/benchmark.md), or
2. a documented negative result plus a reusable selection-policy library.

Both are acceptable. Prolonged ambiguity is not.

## What the evidence says today

| Signal | Source | Reading |
| --- | --- | --- |
| Compiler +22.5 pp page recall over best RAG at 2K, +16.0 pp at 4K on dev | `results/retrieval/xldev24-coverage` | Real low-budget effect on tuned data |
| Compiler +12.2 pp at 2K, +8.1 pp at 4K, −4.0 pp at 8K, −6.5 pp at 16K on holdout | `results/retrieval/xlholdout6b` | Effect survives holdout only at low budgets |
| Quote recall: compiler 0.30 vs structural 0.43 at 4K holdout | same | Page recall over-credits the compiler |
| IR trailed the best chunk unit in 7 of 8 matched comparisons; faceting + coverage packing improved 10 of 12 | `results/factorial/xldev2-content-policy` | Selection policy, not representation, drives the gain |
| IR renders 49% more tokens than raw text on gold evidence | `results/representation/xldev2-no-call` | Representation costs tokens it has not yet earned |
| Compiler query latency 4.7–5.4 s vs 1.4 s fixed RAG | holdout report | 3–4× slower |
| No answer-generation result | roadmap Gate 3 | Retrieval gains unvalidated downstream |

Diagnosis: the asset is a good deterministic selection policy. The persistent,
structure-preserving IR is the unproven part, and the current benchmark cannot
isolate it because compiler-only operators are bundled into the treatment.

Both existing holdouts are spent. `xlholdout6` rejected an earlier
configuration and `xlholdout6b` was manually inspected during the metric
audit. Any claim made after this plan changes the compiler needs a holdout
frozen before that change.

## Measurement problems that must be fixed first

The 2026-09-21 code review found defects that change absolute numbers. Most
defects are shared by every arm, but that does not make the paired deltas
safe: zero-score BM25 fill depends on how many retrieval units a document
yields, and fixed windows, structural chunks, and IR nodes yield different
counts. The paired effect must therefore be remeasured, not assumed. Until
then, no published delta or absolute figure is trustworthy.

Shared-infrastructure defects, which affect every arm equally:

| Defect | Location | Effect |
| --- | --- | --- |
| BM25 returns every chunk, including score 0.0, so RRF rewards non-matching chunks with hash-ordered sparse ranks | `src/contextbench/retrieval/sparse.py:41-58` | Sparse channel is mostly noise when few chunks match |
| Embedding and reranker models load without a pinned revision; index key records only the package version | `retrieval/embeddings.py:71`, `retrieval/rerank.py:64`, `retrieval/index.py:700-720` | A hub weight update silently mixes old corpus vectors with new query vectors |
| Manifest records the HEAD SHA but not whether the worktree was dirty | `src/contextbench/experiments/manifest.py:57-71` | Runs are not provably reproducible from config + SHA |
| Answerable-only metrics filter on the answerable flag, not on having gold pages | `src/contextbench/evaluation/reports.py:36,188` | One XL100 question scores vacuous 1.0 in every arm |
| Relaxed accuracy maps `casefold_exact_match` (822 of 1,345 questions) to substring or Levenshtein ≥ 0.8 | `src/contextbench/generation/scoring.py:68-70` | Likely more lenient than the released evaluator |
| Provider never checks response status; truncated reasoning output scores as invalid JSON with no valid-rate column | `src/contextbench/generation/providers.py:61-77` | A whole arm can silently score zero |
| One unit test reads the gitignored release | `tests/unit/test_xl_docbench.py:183` | CI on `main` has failed on the last three pushes |

Arm-asymmetric defects, which move one arm's numbers and not the others', so
they do not cancel in a paired delta at all. Found on 2026-09-22, after the
review above:

| Defect | Location | Effect |
| --- | --- | --- |
| **Fixed on this branch** (see below). Structural chunks keep heading text in `heading_path` metadata only; both channels read `retrieval_text`, which is `search_text or text`, and `search_text` is `None` on every structural chunk | `src/contextbench/retrieval/chunking.py:173-177`, `retrieval/models.py:98-100` | Only the `structural` arm is blind to heading vocabulary. `fixed` windows over every node carrying text, title and headings included (`chunking.py:78-81`), and the compiler joins the heading trail into `search_text` (`compiler/candidates.py:39-43`). Over the unit fixture `quarterly`, `report`, `results` and `methods` are indexed by `fixed` and by the compiler, and by no structural chunk |
| Compiler candidates skip list-group nodes and `content_layer == "furniture"` nodes as non-evidence | `src/contextbench/compiler/candidates.py:11,31-36` | Asymmetric the other way and smaller: the group name `Highlights` is indexed by `fixed` but by neither the compiler nor `structural` |

The first row handicaps a baseline, not the treatment, so it inflates both the
fixed and the compiler margin over structural chunks. It bears hardest on the
matched content-unit × policy factorial, the experiment meant to separate
representation from policy: "IR nodes beat structural chunks" there can partly
mean "the compiler indexes headings and the structural baseline does not".
Correcting it can only strengthen `structural`.

**Fixed on this branch.** `RetrievalConfig.heading_search_context`, default
`True`, gives structural chunks a `search_text` of their heading trail joined
above their body, as the compiler's node candidates already had. The fix is
search-only: emitted chunk `text`, token counts, budgets and provenance are
identical in both positions, and only the string the channels match against
changes. Heading context is also a crossed factorial factor
(`FactorialConfig.heading_contexts`, `eval-factorial --heading-context
on|off`), reading that one field on both heading-bearing units, so the effect
is measured rather than assumed; the fixed unit does not read it, so its rows
are constant across the factor by construction. Published numbers do not carry
across -- structural because of this fix, IR because the node-candidate id is
now derived from node text alone rather than from the indexed string, a
separate change made to keep the ablation arm-symmetric -- while the
factorial's fixed-unit rows are unaffected, so a partial rerun would mix
behaviours. A single-factor delta carries three mechanisms, not one: heading
vocabulary becoming matchable, candidate dedupe scope, and the
coverage-selection terms of `faceted_coverage` cells; all three are in the
[retrieval specification](../specs/retrieval.md).

Compiler defects, which change the treatment and are therefore fixed
separately in Phase 1 with their own before-and-after run:

| Defect | Location | Effect |
| --- | --- | --- |
| Keyed joins bump core evidence to tier 1, the same tier as page-neighbor windows | `src/contextbench/compiler/expand.py:204-217, 369` | Windows can displace direct hits at 16K |
| Facet core scores are RRF sums while table fragments carry raw reranker output | `compiler/facets.py:119-123`, `compiler/expand.py:250-253` | Fragment ordering versus core evidence is arbitrary |
| Furniture-layer items are appended after body items in the IR projection | `src/contextbench/ir/project.py:110-138` | Page headers and footers cluster into fixed windows and page-neighbor evidence |

The furniture fix also touches fixed windows. Run it as the last Phase 1
correctness change and report its effect on every arm.

## Strategy

Three approaches were considered.

**A. Policy-first.** Treat the compiler as a representation-agnostic selection
layer that can run over any chunking. Make it non-inferior to fixed RAG by
construction. Cheap, consistent with the factorial, and produces something
adoptable even if the IR thesis fails.

**B. Representation where chunking structurally fails.** Stop competing on
generic single-document page recall. Target question classes where a chunk
cannot carry the answer: whole tables with headers, keyed joins across tables,
multi-page evidence, cross-document routing, numeric computation. This is the
only path that can show the IR is causal.

**C. Token efficiency.** Render compact views from the IR (no furniture,
deduplicated heading paths, compact table rows, node-level citations) and aim
at Criterion A: 50% fewer tokens at no more than 1 point accuracy loss.
Requires answer generation to measure.

Decision: execute A, then B with C folded in. Doing B without A leaves the
compiler losing at high budgets on every slice.

The guarded generation experiment runs twice: an exploratory run on
re-baselined `xlholdout6b` contexts right after Phase 0, as an early signal
that evidence selection affects answers at all, and a confirmatory run on the
hardened policy over the fresh `xlholdout6c` holdout after Phase 1. Each run
costs about $5 and carries its own research-log entry; the original frozen
preregistration is kept unchanged as the record of what was planned.

## Phases

Each phase ends with a gate. Do not start the next phase until the gate is
recorded in `docs/research-log/`. Effort figures are rough single-developer
estimates and exclude model run time.

### Phase 0: Re-baseline the measurement

Goal: trustworthy absolute numbers, green CI, and a fresh holdout frozen before
any compiler change. Rough effort: one week.

Tasks:

1. Move `test_second_holdout_is_balanced_and_document_fresh` to
   `tests/integration/` with a skip when the release is absent, or rewrite it
   against `tests/fixtures/xl_docbench`.
2. Stop BM25 from returning zero-score chunks. Add a unit test where five
   chunks match and assert the sparse ranking has exactly five entries.
3. Pin `revision=` for the embedding and cross-encoder models. Record the
   resolved model commit hash in `RunManifest` and in the index key. Add
   `git_dirty: bool` to the manifest and refuse to publish a canonical result
   from a dirty tree.
4. Make answerable-only eligibility `gold_count > 0`. Add a test using a
   record that is answerable with no gold pages.
5. Diff `accuracy_score` against the released XL-DocBench evaluator for every
   `verification_rule`. Make the mapping match or document every deliberate
   deviation in `docs/specs/evaluation.md`.
6. Check `response.status` and `incomplete_details` in the OpenAI provider.
   Add `response_valid_rate` to generation summary rows. Record temperature
   and seed in the generation manifest.
7. Declare `numpy` in `pyproject.toml`. Update the README's "Known
   limitations" and "Next decision gate" sections to match the roadmap.
8. Freeze `benchmarks/xl-docbench/subsets/xlholdout6c.json`: six or more
   single-document questions from documents never used by `xl10`, `xldev24`,
   `xlholdout6`, or `xlholdout6b`, selected by the same rules as
   `xlholdout6b`. Commit it with a research-log note. Do not run it until
   Gate 1.
9. Rerun `xldev24` and `xlholdout6b` at the new commit and publish them under
   `results/retrieval/` as the new baseline. Mark the earlier results
   superseded in `results/README.md`.
10. Leave the
    [original generation preregistration](../research-log/xlholdout6b-generation-preregistration.md)
    untouched as the record of what was frozen. Write a new research-log
    entry that declares an exploratory generation run over the re-baselined
    `xlholdout6b` contexts with the same model, prompt, pricing, and 72-call
    ceiling, and states why the original run ID is no longer valid. Execute
    it and label every output exploratory. The confirmatory generation run is
    the `xlholdout6c` run in Phase 1.

Gate 0: CI green on `main`; new dev and holdout results published; on
`xldev24` the paired source-cluster bootstrap interval for compiler versus the
best RAG baseline excludes zero at both 2K and 4K. If the low-budget advantage
does not clear that bar after the BM25 fix, stop and write that up before
continuing. The first generation run is reported at this gate but does not
block it.

### Phase 1: Correctness, then a hardened selection policy

Goal: the compiler is never worse than fixed RAG at any budget, and its cost
is bounded. Rough effort: two to three weeks.

Tasks:

1. Fix the join tier bump so page-neighbor windows always rank after core
   evidence. Add a test that combines joins and page neighbors at 16K.
2. Normalize facet and fragment scores onto one scale before ordering. Add a
   test with a faceted query and an oversized table.
3. Exclude furniture-layer items from fixed windows, structural chunks, and
   page-neighbor evidence, or assign them source-order ordinals. Add an IR
   test with a furniture item in the body tree. Rerun `xldev24` after tasks
   1 to 3 and record the before-and-after deltas for every arm.
4. Budget-adaptive packing: coverage-pack until every facet is covered or no
   candidate adds a new page, then backfill the remaining budget in plain
   reranked order from the same candidate pool. Expose it as a packing
   strategy; keep `coverage` and `ranked` as ablation controls.
5. Add a non-inferiority check to the evaluation report: for each budget,
   the compiler's paired delta against fixed RAG with its bootstrap interval
   and a prespecified non-inferiority margin of −3 pp page recall. The check
   passes only when the interval's lower bound is above the margin. Report it
   on every run, but treat it as confirmatory only on a population large
   enough to reach that bound.
6. Run the content-unit × policy factorial on the full `xldev24` set with the
   corrected code. Record the representation effect, policy effect, and
   interaction.
7. Cache cross-encoder scores per (query, node) across facets and budgets.
   Reduce the compiler rerank pool by token mass so it matches the baselines
   in scored tokens, not in unit count. Target: compiler latency at most twice
   fixed RAG on the development machine. Regression-test rankings against the
   Phase 0 artifacts before and after caching.
8. Run the D1 to D4 ablations required by benchmark specification §25 on
   `xldev24`: no expansion, headings only, headings + siblings, headings +
   siblings + tables.
9. Run `xlholdout6c` once, with the selected configuration, and publish it.
10. Write and freeze a new preregistration for the confirmatory generation
    run over the `xlholdout6c` contexts at 2K and 4K, using the same model,
    prompt, pricing, and call ceiling as the original, then execute it.

Gate 1 is a screening check, not a non-inferiority result. Six holdout
questions cannot bound a loss margin. It passes when, on `xlholdout6c`, the
compiler's paired point estimate against fixed RAG is positive at 2K and 4K
and its interval at 8K and 16K does not lie entirely below the −3 pp margin.
A confirmatory non-inferiority test at every budget is deferred to the larger
Phase 3 population. Factorial verdict recorded: if faceted fixed or structural
chunks match IR nodes under the same policy, the IR is not a retrieval
treatment. That is a result, not a failure; record it and continue with the
policy as the treatment.

### Phase 2: Decide whether answers improve

Goal: learn whether better evidence selection produces better answers. Rough
effort: one week of analysis; run time and spend are set by the
preregistrations.

Tasks:

1. Analyse both guarded generation runs together: relaxed accuracy,
   same-model citation entailment, abstention correctness, dollars per
   correct answer, and per-question failures.
2. Promote exact quote recall and content-verified page recall to co-primary
   retrieval metrics in `docs/specs/evaluation.md` and in every report.
3. Extend generation to `xldev24` at 2K and 4K only if either six-question
   run shows a directional answer or citation benefit. Preregister the
   extension before running it.

Gate 2: decision rule from the preregistration. Directional accuracy or
citation-entailment benefit at 2K or 4K, or comparable quality at lower cost,
opens Phase 3. Otherwise pause algorithm work and run the per-question failure
analysis first.

### Phase 3: Test the representation where it should matter

Goal: a causal test of the IR on questions where flat chunks cannot carry the
evidence, followed by the robustness checks the specification requires before
validation. Rough effort: four to six weeks plus run time; the second model
tier and long-context comparison add paid runs that need their own
preregistered spend envelopes.

Tasks:

1. Freeze a stratified population from the untouched XL-DocBench remainder:
   table questions, multi-page evidence, cross-document questions, and
   numeric-computation questions. Record selection rules, minimum sample
   sizes, and the analysis plan in `docs/research-log/` before any run.
2. Check T²-RAGBench availability, licence, and source-document access. If
   usable, implement the adapter behind the existing `BenchmarkQuestion`
   interface with cached fixtures and no network in tests. If not, record
   the reason and choose a substitute table-and-text benchmark before
   proceeding.
3. Compact rendering (approach C): drop furniture, deduplicate heading paths
   within a packet, render table rows compactly, cite at node level. Measure
   tokens and quote recall on the Phase 1 contexts before and after.
4. Run all four arms plus the D1 to D4 ablations on the stratified population
   and on the second benchmark at 2K, 4K, 8K, and 16K. Apply the Phase 1
   non-inferiority check at every budget; this population is the confirmatory
   test, so the −3 pp margin must be cleared by the interval's lower bound.
5. Repeat the matched content-unit × selection-policy factorial on the
   stratified population. Full-arm comparisons there confound representation
   with policy in the same way the primary benchmark does; only the matched
   factorial attributes a structured-question gain to IR nodes.
6. Run the RAW versus IR gold-evidence generation experiment on the same
   population with the Phase 2 model. This is the retrieval-free
   representation check and stands independently of task 5.
7. Robustness checks required by benchmark specification Milestone 8 before
   any validation claim:
   - repeat the guarded generation run on the stratified population with a
     second, stronger answer-model tier under a fresh preregistration; and
   - run a realistic long-context comparison that gives the same answer model
     the full relevant documents at 64K or 128K where they fit, and compare
     accuracy, citation support, total input cost, and latency against the
     compiler at its best budget.

Gate 3: the IR must show a large effect on the structured slice (Criterion B
or C in benchmark specification §26) with parity elsewhere, the matched
factorial must attribute that effect to IR nodes rather than to policy alone,
the gold-evidence experiment must show the IR communicates the same evidence
at equal or lower cost, and the effect must persist under the second model
tier. If long context wins on accuracy at acceptable cost and latency, the
second kill condition in benchmark specification §29 applies. Small average
gains do not pass.

### Phase 4: Decide

Two outcomes, both publishable:

- **Validated.** Gates 1 to 3 pass, including the confirmatory
  non-inferiority test, the second answer-model tier, and the long-context
  comparison. Write the final comparison report distinguishing development,
  holdout, cross-dataset, and model-tier results as required by benchmark
  specification §44, then plan the persistent IR and compiler as a product
  layer. If the robustness checks are skipped for cost reasons, the claim
  must be narrowed to the tested model and budgets and the specification
  amended to say so.
- **Not validated.** Any gate fails. Publish the negative result with the
  same rigour, and package the faceting plus coverage-aware packing policy as
  a standalone library that runs over ordinary chunked RAG.

## Non-goals

- No LLM query planner, LLM enrichment, or knowledge graph to rescue weak
  results. Benchmark specification §41 forbids it.
- No product features: web UI, hosted database, multi-tenancy, or
  distributed workers.
- No tuning on `xlholdout6c` or the stratified population after they are
  frozen. Each is run once with the configuration selected on `xldev24`.
- No new benchmark arms beyond the four specified. New packing strategies are
  compiler configurations, not arms.

## Risks

| Risk | Mitigation |
| --- | --- |
| BM25 fix removes the low-budget advantage | Gate 0 stops the plan and records the result |
| Paid generation runs consume budget without a usable answer | Frozen preregistration, hard call ceiling, response-valid rate |
| Fresh holdout is too small to distinguish outcomes | Gate 1 is stated on interval bounds, not point estimates; Phase 3 adds a larger preregistered population |
| Stratified population is too small to distinguish outcomes | Preregister minimum sample sizes and paired intervals before selection |
| T²-RAGBench is unavailable or unlicensed for this use | Phase 3 task 2 checks first and names a substitute |
| Latency work changes rankings | Regression-test rankings against Phase 0 artifacts before and after caching |
| Furniture fix changes baseline arms as well as the compiler | Reported per arm as its own before-and-after delta in Phase 1 |
| Shared BM25 fix shifts arms unequally because their unit counts differ | Paired deltas are remeasured at Gate 0, never carried over from the old runs |
| Second model tier and long-context runs are expensive | Each gets its own frozen preregistration and call ceiling; they run only after Gate 2 passes |
| Re-baselined `xlholdout6b` generation run is mistaken for the preregistered one | Original preregistration kept unchanged; the re-baselined run is labelled exploratory in its research-log entry and results index |

## Acceptance

The plan is complete when a research-log entry for each gate exists, the
final report is published under `results/`, and the README's current-status
section makes exactly one of the two Phase 4 claims.
