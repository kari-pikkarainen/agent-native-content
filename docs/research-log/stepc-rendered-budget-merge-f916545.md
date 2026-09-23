# Rendered-evidence budget and node merging on xldev24

Date: 2026-09-23

Code commit: `f916545`. All six runs record that commit with a clean worktree.
No answer model was called: this is a retrieval-only step, as the owner chose
after the [Gate 2 failure analysis](gate2-failure-analysis.md).

Every run is pinned with `--budget-accounting rendered_evidence
--evidence-render-version evidence-render-v2`. So every arm is now charged for
its evidence tags, aliases and separators as well as its content, and the
aliases are the short `E1`, `E2` form.

| Run | Subset | Merge | Published as |
| --- | --- | --- | --- |
| C1 | `xldev24` | off | `retrieval/xldev24-rendered-mergeoff` |
| C2 | `xldev24` | on | `retrieval/xldev24-rendered-mergeon` |
| S1 | `xlfresh9-smoke` | off | `retrieval/xlfresh9-smoke-mergeoff` |
| S2 | `xlfresh9-smoke` | on | `retrieval/xlfresh9-smoke-mergeon` |
| F1 | `xldev24` factorial | off | `factorial/xldev24-factorial-rendered-mergeoff` |
| F2 | `xldev24` factorial | on | `factorial/xldev24-factorial-rendered-mergeon` |

"Merge on" means `node_merge` 64 / 128 / 256 tokens, a one-page span, and in C2
and S2 also `expanded_candidate_token_mass_multiple = 1.0`. C2 therefore changes
two things at once, and its effect is the bundle's, not merging's alone. F2
sets merging without the token-mass floor.

## 1. What the budget redefinition costs (C1 against the frozen row)

Baseline: [`xldev24-phase1-frozen`](../../results/retrieval/xldev24-phase1-frozen/report.md)
(`c7e56fa`, content-only accounting). Both runs score quotes under policy v3.
Merging is off in both, and nothing else in the configuration differs.

Page recall, answerable questions:

| Arm | 2K | 4K | 8K | 16K |
| --- | --- | --- | --- | --- |
| compiler | 0.624 → 0.553 | 0.741 → 0.738 | 0.814 → 0.806 | 0.851 → 0.836 |
| fixed | 0.291 → 0.226 | 0.458 → 0.431 | 0.653 → 0.648 | 0.790 → 0.779 |
| structural | 0.377 → 0.384 | 0.513 → 0.493 | 0.646 → 0.629 | 0.744 → 0.733 |
| long context | 0.166 → 0.089 | 0.370 → 0.197 | 0.536 → 0.380 | 0.710 → 0.581 |

- Content actually packed falls by the framing it now pays for:
  - compiler, 2,047 → 1,660 content tokens at 2K (−19%) and 14,883 → 12,986 at 16K (−13%);
  - fixed, −13% at 2K and −3% at 16K;
  - long context, −31% at 16K, where its per-item framing is heaviest.
- The compiler loses 7 points of page recall at 2K and at most 1.5 points at
  4K–16K. Fixed RAG loses 6.5 points at 2K.
- The compiler's quote recall falls 3 to 6 points at every budget.
- Against fixed RAG, the non-inferiority screen still passes at 2K, 4K and 8K,
  with the lower bound above zero at all three. **It fails at 16K** (Δ +0.056,
  lower bound −0.069). The frozen row passed there by 0.0002, so the
  redefinition is enough to tip it.
- The compiler's 2K lead over fixed RAG narrows from +0.33 only slightly:
  fixed RAG pays for framing too.

This is the honest restatement of every earlier page-recall figure.
Content-only rows overstate what fits in the prompt, and they overstate it
most for the arms that pack many small items.

## 2. What merging does (C1 against C2, compiler only)

The other three arms are **exactly** unchanged: the largest absolute
difference in any metric is 0.

| Budget | Page recall | Quote recall | Answer present |
| --- | --- | --- | --- |
| 2K | 0.553 → 0.461 (−0.092) | 0.185 → 0.278 (+0.093) | 0.444 → 0.500 |
| 4K | 0.738 → 0.709 (−0.030) | 0.292 → 0.292 | 0.500 → 0.556 |
| 8K | 0.806 → 0.861 (+0.055) | 0.319 → 0.421 (+0.102) | 0.556 → 0.556 |
| 16K | 0.836 → 0.908 (+0.072) | 0.403 → 0.463 (+0.060) | 0.611 → 0.611 |

- It is a trade at low budgets and a gain at high ones. At 2K, merged units
  are larger, so fewer pages fit. At 8K and 16K the budget is large enough
  that coherence wins on both metrics.
- The 16K under-fill is gone: mean rendered evidence rises from 15,707 to
  16,373 tokens. That is the token-mass floor doing its job.
- Non-inferiority against fixed RAG now passes at all four budgets, including
  16K (lower bound +0.004). Against structural RAG it fails at 2K (lower bound
  −0.072), where it passed with merging off.
- Quote recall against structural RAG at 8K and 16K becomes positive, with the
  interval excluding zero (+0.134 [+0.036, +0.235] and +0.162
  [+0.071, +0.250]). With merging off the 2K interval against structural
  excluded zero in the other direction (−0.074 [−0.142, −0.016]); with
  merging on it includes zero.
- The shredded questions identified in the failure analysis move as expected
  at the higher budgets: `000440`, `000441` and `001102` all gain page recall
  at 8K and 16K. At 2K `000440` and `000441` lose page recall, although
  `000441` gains quote recall.
- Every per-question movement is listed by `compare.py`. At each budget 2 to 6
  of 18 quoted questions and 7 to 10 of 18 page-eligible questions move.

## 3. The fresh smoke test (S1, S2)

Nine questions, four answerable, four clusters. It is labelled
`smoke_test_not_evidence` and is reported only as a sign check.

- Merge off: compiler page recall 0.353 / 0.524 / 0.641 / 0.765 across the
  budgets, above fixed RAG and structural RAG at every one.
- Merge on: page recall is **lower at every budget**, by 0.02 to 0.05. Quote
  recall is unchanged at 0.125–0.25 (one question in eight quotes moves the
  mean by 0.125), and the other arms are unchanged.

So the merge gain seen on `xldev24` at 8K and 16K **does not appear** on
unseen documents. With four answerable questions, this is not a refutation.
But it is not a replication either, and the thresholds were chosen with the
`xldev24` shredding in view.

## 4. Factorial: IR nodes against structural chunks (F1, F2)

These are all-question means, so they are not comparable with the answerable
rows above. Heading context is on in every cell.

| Budget | IR + coverage, merge off | IR + coverage, merge on | Structural + coverage | Fixed + coverage |
| --- | --- | --- | --- | --- |
| 2K | 0.682 / 0.361 | 0.581 / 0.427 | 0.513 / 0.375 | 0.403 / 0.323 |
| 4K | 0.794 / 0.417 | 0.734 / 0.438 | 0.611 / 0.431 | 0.556 / 0.465 |
| 8K | 0.849 / 0.469 | 0.856 / 0.514 | 0.730 / 0.465 | 0.768 / 0.486 |
| 16K | 0.884 / 0.542 | 0.934 / 0.566 | 0.811 / 0.476 | 0.887 / 0.521 |

Each cell is page recall / quote recall.

- IR nodes still lead structural chunks on page recall at every budget under
  the same coverage policy, with or without merging. Under the new accounting
  the representation effect survives.
- On quote recall without merging, IR nodes trail structural at 2K and 4K and
  lead at 8K and 16K. This is the known Phase 1 pattern.
- With merging, IR nodes lead structural on quote recall at every budget, and
  lead fixed chunks + coverage at every budget except 4K.
- Under the ranked policy IR nodes also lead structural on page recall at
  every budget; those cells are in the published summary.

## Decision for the owner: freeze the merge thresholds?

**Recommendation: do not freeze merging as the default yet.** Keep it
available as an explicit option.

- On `xldev24` it buys 8K/16K page and quote recall and the 16K margin, and
  pays for them at 2K, where it loses the non-inferiority screen against
  structural RAG.
- On the fresh smoke set it lowers page recall at every budget.
- C2 bundles merging with the token-mass floor, so the two are not separated.
- The thresholds were chosen looking at the development questions that
  motivated them.

The next preregistration can name a merge configuration as the treatment
before it is run on unseen data. It can do that only after the fresh set is
larger than a smoke test, which parallel parsing is meant to make affordable.

## Known weaknesses

- 18 answerable questions in 9 clusters on `xldev24`, and 4 in 4 on the smoke
  set. Every status here is "screening", not confirmatory (the minimum is 34
  and 34).
- The merge and token-mass effects are confounded in C2 and S2.
- The comparison with the frozen row spans two commits (`c7e56fa` →
  `f916545`). What changed in between is the accounting, the renderer and code
  paths that are off by default. Merge-off identity was verified on 90 of 90
  packets when merging was added, but not across the accounting change,
  because that change is the treatment.
- Retrieval metrics only. The failure analysis showed they can misstate
  answerability; `answer_present` is a deterministic containment check, not
  an answer.
- Latency: merging adds about 650–700 ms per query at 2K–8K. The runs record
  latency, but the device (MPS) is not recorded in their manifests.
