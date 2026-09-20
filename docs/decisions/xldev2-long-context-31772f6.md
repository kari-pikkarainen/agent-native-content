# XLDev2 long-context baseline (`31772f6`)

## Scope

Run `xldev2-long-context-31772f6` evaluated the two committed table questions
while retaining the 24-question development subset's 11-document retrieval
corpus. This is a development diagnostic, not a holdout or thesis result. No
answer-generation model was used.

Arm C projects source-derived body nodes once, then filters to each question's
declared documents and packs them in original order. It performs no sparse or
dense search and no reranking. The projection is outside query timing.

## Directional result

At 2K, 4K, 8K, and 16K, long-context page recall was 0.236, 0.277, 0.327, and
0.605. Exact quote recall was 0.0 through 8K and 0.25 at 16K. For comparison,
the compiler's page recall was 0.261, 0.241, 0.407, and 0.598, with 0.50 quote
recall at every budget; structural retrieval reached 0.714 page recall and
0.50 quote recall at 16K.

Mean Arm C query-time packing latency was 18.8–19.8 ms, versus about 1.44–1.48
seconds for fixed/structural retrieval and 3.23–4.45 seconds for the compiler.
This confirms that source-order reading is a materially faster baseline while
also showing that its useful evidence depends strongly on source position.

## Decision

Keep Arm C in every new evidence and generation run. Do not interpret the
two-question result as answer-quality evidence or as validation/rejection of
the compiler thesis. The appropriate next comparison uses the same answer
model and prompt over saved A/B/C/D contexts, followed later by the registered
development and holdout subsets.
