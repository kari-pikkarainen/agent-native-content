# Gold-Evidence Representation Report: xldev24-representation-gemma4-12b

No retrieval was used. Every evidence-bearing condition received the same annotated pages; question_only received none.
One-time enrichment: 878.60 ms (48.81 ms/question).
Question-only correct: 0; incorrect: 0; abstained: 0; invalid: 18.

## Quality

| Condition | Questions | Valid responses | Answer rate | Accuracy | Token F1 | ANLS | Citation support | Semantic accuracy | Valid answer judges | Citation entailment | Valid citation judges |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| question_only | 18 | 0.000 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | n/a | 0.000 | n/a |
| raw | 18 | 0.944 | 0.556 | 0.167 | 0.185 | 0.100 | 0.500 | 0.333 | 0.889 | 0.700 | 1.000 |
| ir | 18 | 0.722 | 0.611 | 0.111 | 0.115 | 0.090 | 0.333 | 0.278 | 1.000 | 0.455 | 0.833 |
| enriched | 18 | 0.889 | 0.667 | 0.111 | 0.152 | 0.056 | 0.500 | 0.278 | 0.900 | 0.583 | 1.000 |
| indexed | 18 | 0.944 | 0.556 | 0.056 | 0.141 | 0.090 | 0.352 | 0.333 | 1.000 | 0.200 | 0.714 |

## Answer-call efficiency (representation comparison)

| Condition | Rep. tokens | Input tokens | Output tokens | Latency (ms) | $/query | $/correct | $/semantic correct |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| question_only | 0.0 | 121.4 | 45.2 | 3272.59 | 0.000000 | n/a | n/a |
| raw | 13359.8 | 14887.9 | 86.3 | 83692.87 | 0.000000 | 0.000000 | 0.000000 |
| ir | 24031.7 | 28628.3 | 79.4 | 170951.44 | 0.000000 | 0.000000 | 0.000000 |
| enriched | 30269.1 | 36023.2 | 47.0 | 217652.72 | 0.000000 | 0.000000 | 0.000000 |
| indexed | 25642.4 | 30428.9 | 60.4 | 180675.14 | 0.000000 | 0.000000 | 0.000000 |

## All calls (answer plus judges)

| Condition | Calls | Judge calls | Input tokens | Output tokens | Latency (ms) | $/query | Judge $/query | $/correct | $/semantic correct |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| question_only | 1.00 | 0.00 | 121.4 | 45.2 | 3272.59 | 0.000000 | 0.000000 | n/a | n/a |
| raw | 2.00 | 1.00 | 15247.2 | 161.2 | 89846.46 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| ir | 1.67 | 0.67 | 28902.6 | 117.1 | 174313.90 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| enriched | 2.06 | 1.06 | 36443.6 | 125.5 | 224082.68 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| indexed | 1.89 | 0.89 | 30763.7 | 133.8 | 186413.90 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |

Skipped without gold pages: 6.
Costs use the pricing metadata frozen in the manifest.
Compare representations on answer-call efficiency. The all-calls table adds judge calls, whose number and prompt size depend on the answer (none for abstentions or question_only citations), so it measures evaluation cost, not representation cost.
Valid responses is the share of answer calls the provider completed and that parsed against the answer contract.
Answer rate is the share of cells that did not return the exact INSUFFICIENT_EVIDENCE marker. Citation entailment is over non-abstaining cells only, so it must be read with answer rate.
Valid judges is the share of judge calls that completed and parsed, over the cells that called that judge; n/a means no cell called it. An invalid judge scores zero.
Citation support is the historical citation-ID validity field; it is not semantic entailment. Accuracy, token F1 and ANLS are the deterministic relaxed metrics; semantic accuracy is the separate same-model equivalence judge.
