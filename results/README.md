# Canonical Results

This directory contains the compact result set supporting the project's current
public claims. Complete generated runs remain under ignored `artifacts/`
directories because they can contain large indexes and rendered source context.

## Published results

| Result | Status | Main conclusion |
| --- | --- | --- |
| [XLDev2 content-unit × policy factorial](factorial/xldev2-content-policy/report.md) | Diagnostic | Selection policy explains more of the page-recall effect than IR nodes on two table-heavy questions. |
| [XLDev24 coverage packing](retrieval/xldev24-coverage/report.md) | Development | Compiler page recall and full coverage beat both RAG baselines at every tested budget. |
| [XLHoldout6](retrieval/xlholdout6/report.md) | Historical holdout | The preceding compiler configuration mostly failed to reproduce its development advantage. |
| [XLHoldout6b](retrieval/xlholdout6b/report.md) | Directional holdout | Compiler leads at 2K and 4K; fixed RAG leads at 8K and 16K. |
| [XLDev2 agent representation](representation/xldev2-no-call/README.md) | No-call diagnostic | Indexed enrichment reduces prompt growth, but answer-quality value remains untested. |

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
