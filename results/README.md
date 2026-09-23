# Canonical Results

This directory contains the compact result set supporting the project's current
public claims. Complete generated runs remain under ignored `artifacts/`
directories because they can contain large indexes and rendered source context.

## Published results

| Result | Status | Main conclusion |
| --- | --- | --- |
| [XLDev24 at the frozen Phase 1 configuration](retrieval/xldev24-phase1-frozen/report.md) | **Development, current — the Gate 1 reference** | Siblings on, page neighbours on, quote policy v3. Page recall leads both baselines at every budget, excluding zero at 2K and 4K against both. The non-inferiority margin holds at 8 of 8 cells, by 0.0002 against fixed RAG at 16K. The 2K exact-quote deficit against structural chunks no longer excludes zero. |
| [Freeze decision: siblings × page neighbours](retrieval/xldev24-freeze-sibON-nbON/report.md) | Ablation, current | Four cells, keyed joins on, quote policy v2. Siblings carry the quote gain (+0.019 mean); page neighbours add +0.002 but are what keep the 16K margin. Other cells: [sib off/nb off](retrieval/xldev24-freeze-sibOFF-nbOFF/report.md), [sib off/nb on](retrieval/xldev24-freeze-sibOFF-nbON/report.md), [sib on/nb off](retrieval/xldev24-freeze-sibON-nbOFF/report.md). |
| [XLDev24 re-baseline](retrieval/xldev24-rebaseline/report.md) | Development, **superseded for absolute figures** | Compiler leads both RAG baselines at every budget; the paired interval excludes zero at 2K and 4K, which is Gate 0's criterion. |
| [XLHoldout6b re-baseline](retrieval/xlholdout6b-rebaseline/report.md) | Directional holdout, current | Compiler leads fixed RAG at 2K and 4K and **loses to it at 16K**, with that interval excluding zero. It leads structural at 2K and 16K. |
| [XLDev24 content-unit × policy × heading factorial](factorial/xldev24-content-policy-heading/report.md) | Development, current | On page recall IR nodes beat the best chunk unit in 8 of 8 matched cells; on quote recall in only 3 of 8. Heading search context costs the IR unit 2 to 5 points and helps structural only at low budgets. |
| [XLDev24 after Phase 1 correctness fixes](retrieval/xldev24-phase1-fixes/report.md) | Development, **superseded by the frozen configuration** | Three correctness fixes, measured per arm. Gate 0's page-recall criterion still holds at 2K and 4K. The compiler's exact-quote advantage over fixed RAG includes zero at every budget, and against structural chunks at 2K it is negative with an interval excluding zero. |
| [XLDev24 content-unit × policy factorial, corrected](factorial/xldev24-content-policy-corrected/report.md) | Development, current | IR nodes beat the better chunk unit on page recall in 7 of 8 matched cells and on quote recall in 2 of 8. Faceted coverage buys page recall and costs quote recall for **every** content unit, replicating the packing-policy finding through an independent design. The IR page advantage is larger under coverage than under ranked, so representation and policy are not separable. |
| [XLDev24 expansion ablations D1–D4](retrieval/xldev24-ablation-D1/report.md) | Ablation, current | The spec's expansion ladder. D1 with no expansion has the best page recall at 4K and 8K, so structural expansion does not produce the page advantage. Table preservation moves 1 of 96 packets and no metric. Keyed joins are the largest quote-recall contributor and rest on one question. The shipped config is not the best rung. |
| [XLDev24 packing-policy comparison](retrieval/xldev24-packing-adaptive/report.md) | Ablation, current | Three packing policies. Budget-adaptive packing **rejected** under the preregistered rule (A1 and A2 fail). Page recall falls and quote recall rises monotonically as coverage is withdrawn, and the 2K quote deficit against structural chunks disappears entirely without coverage — so coverage packing is the source of both the page advantage and the quote deficit. [ranked arm](retrieval/xldev24-packing-ranked/report.md). |
| [XLDev24 compiler heading-free ablation](retrieval/xldev24-compiler-headingfree/report.md) | Ablation, current | Removing heading context from compiler node search improves page recall at every budget (+0.016 to +0.036) but quote recall splits by budget. Rejected under the joint-metric rule; the quote effect rests on two of eighteen questions and is not resolved by this subset. |
| [XLHoldout6b metric audit](retrieval/xlholdout6b-metric-audit/report.md) | Diagnostic | The low-budget page effect survives stricter accounting, but manual inspection confirms retrieval metrics can misstate answerability. |
| [XLDev2 agent representation](representation/xldev2-no-call/README.md) | No-call diagnostic | Indexed enrichment reduces prompt growth, but answer-quality value remains untested. |
| [XLDev2 content-unit × policy factorial](factorial/xldev2-content-policy/report.md) | **Superseded** | Selection policy explains more of the page-recall effect than IR nodes on two table-heavy questions. |
| [XLDev24 coverage packing](retrieval/xldev24-coverage/report.md) | **Superseded** | Compiler page recall and full coverage beat both RAG baselines at every tested budget. |
| [XLHoldout6](retrieval/xlholdout6/report.md) | **Superseded**, historical holdout | The preceding compiler configuration mostly failed to reproduce its development advantage. |
| [XLHoldout6b](retrieval/xlholdout6b/report.md) | **Superseded** | Compiler leads at 2K and 4K; fixed RAG leads at 8K and 16K. |

### Quote-recall figures are scored under different policies

Exact quote recall was re-scored twice during Phase 1, and only the comparison
changed, never the gold data. Every summary records the policy it was scored
under in `quote_match_policy`; an artifact without the field was scored under
`literal-casefold-v1`.

- `literal-casefold-v1`: every row published before `08acd28`.
- `nfkc-unified-punctuation-ordered-elision-v2`: the four freeze-decision cells.
- `nfkc-unified-punctuation-ordered-elision-v3`: the frozen configuration.

Quote figures under different policies are not comparable. Page recall,
content-verified recall and every other metric are unaffected by the policy.

### What the Phase 1 fixes superseded

The Gate 0 development row is marked superseded **for its absolute figures
only**. Its gate decision stands: the criterion it was judged on is still met
by the Phase 1 row above. But three correctness fixes moved every arm except
structural, so its per-arm numbers are not comparable with the current row and
must not be quoted beside them.

The holdout rows were not re-run. `xlholdout6b-rebaseline` predates the same
three fixes, so it too is stale in absolute terms; it is left unmarked because
re-running a holdout to keep a table tidy would spend it. `xlholdout6c` stays
frozen until Gate 1.

The three fixes were: keyed joins no longer gate core evidence out of a
packet; every candidate class is ordered on one scale; and IR ordinals follow
source order with furniture excluded from every retrieval surface. Only the
third moved the numbers materially, and it moved the fixed baseline hardest.
See [the Phase 1 record](../docs/research-log/phase1-correctness-fixes-9110e70.md).

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
