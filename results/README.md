# Canonical Results

This directory contains the compact result set supporting the project's current
public claims. Complete generated runs remain under ignored `artifacts/`
directories because they can contain large indexes and rendered source context.

## Published results

| Result | Status | Main conclusion |
| --- | --- | --- |
| [XLDev24 re-baseline](retrieval/xldev24-rebaseline/report.md) | Development, current | Compiler leads both RAG baselines at every budget; the paired interval excludes zero at 2K and 4K, which is Gate 0's criterion. |
| [XLHoldout6b re-baseline](retrieval/xlholdout6b-rebaseline/report.md) | Directional holdout, current | Compiler leads fixed RAG at 2K and 4K and **loses to it at 16K**, with that interval excluding zero. It leads structural at 2K and 16K. |
| [XLDev24 content-unit × policy × heading factorial](factorial/xldev24-content-policy-heading/report.md) | Development, current | On page recall IR nodes beat the best chunk unit in 8 of 8 matched cells; on quote recall in only 3 of 8. Heading search context costs the IR unit 2 to 5 points and helps structural only at low budgets. |
| [XLHoldout6b metric audit](retrieval/xlholdout6b-metric-audit/report.md) | Diagnostic | The low-budget page effect survives stricter accounting, but manual inspection confirms retrieval metrics can misstate answerability. |
| [XLDev2 agent representation](representation/xldev2-no-call/README.md) | No-call diagnostic | Indexed enrichment reduces prompt growth, but answer-quality value remains untested. |
| [XLDev2 content-unit × policy factorial](factorial/xldev2-content-policy/report.md) | **Superseded** | Selection policy explains more of the page-recall effect than IR nodes on two table-heavy questions. |
| [XLDev24 coverage packing](retrieval/xldev24-coverage/report.md) | **Superseded** | Compiler page recall and full coverage beat both RAG baselines at every tested budget. |
| [XLHoldout6](retrieval/xlholdout6/report.md) | **Superseded**, historical holdout | The preceding compiler configuration mostly failed to reproduce its development advantage. |
| [XLHoldout6b](retrieval/xlholdout6b/report.md) | **Superseded** | Compiler leads at 2K and 4K; fixed RAG leads at 8K and 16K. |

### What supersedes the four marked rows

They were measured before the 2026-09-21 review's defects were fixed, so their
absolute figures and their paired deltas are not comparable with the current
rows and must not be quoted alongside them. Every one of them was produced
with BM25 returning hash-ordered zero-score chunks into rank fusion, with the
dense channel doing the same, with embedding and reranker weights unpinned,
and with the structural arm unable to retrieve on its own heading vocabulary.
None of their manifests records whether the worktree was dirty.

The XLDev2 factorial is superseded by evidence rather than by defect as well:
it drew on two table-heavy questions, and the current factorial runs the same
matched design over all 24 development questions, where its central finding
reverses.

The current rows carry the provenance the superseded ones cannot: a recorded
`git_dirty`, and both model weights pinned to a resolved commit.

A conclusion in a superseded row may still hold. None of them has been
re-tested except where a current row states otherwise.

## Result status vocabulary

- **Diagnostic:** mechanism or pipeline check; not evidence for a general claim.
- **Development:** used to choose or tune the treatment.
- **Holdout:** selected before evaluation and not used for tuning.
- **Ablation:** controlled comparison of one implementation choice.
- **Superseded:** retained for history but replaced by a later configuration.

Each published retrieval directory includes the generated `report.md`,
`summary.json`, `manifest.json`, and source-text-free per-question
`retrieval.jsonl`. Runs with a stage audit also publish
`compiler-stages.jsonl`. The manifest binds the result to the Git commit,
dataset revision, subset hash, source hashes, models, tokenizer, and full
configuration. Publication intentionally omits source PDFs, rendered contexts,
indexes, and embeddings.

Each holdout is only six questions, so both remain directional. No published
retrieval run used an answer-generation model, and the full XL100 has not been
run with the selected compiler.
