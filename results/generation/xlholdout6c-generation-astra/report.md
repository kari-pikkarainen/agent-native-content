# Generation Decision Report: xlholdout6c-generation-astra

Retrieval contexts: `xlholdout6c-gate1-60e5836`

| System | Budget | Valid responses | Valid judges | Accuracy | Token F1 | ANLS | Citation valid | Gold-page align | Citation entail | Citation present | Input tokens | Output tokens | Latency (ms) | $/query | $/correct |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| compiler | 2048 | 1.000 | 1.000 | 0.167 | 0.128 | 0.000 | 0.333 | 0.208 | 0.333 | 0.333 | 6278.8 | 77.5 | 3233.23 | 0.066663 | 0.399980 |
| compiler | 4096 | 1.000 | 1.000 | 0.167 | 0.111 | 0.113 | 0.333 | 0.222 | 0.333 | 0.333 | 11656.7 | 77.5 | 3737.80 | 0.120442 | 0.722650 |
| fixed | 2048 | 1.000 | 1.000 | 0.333 | 0.195 | 0.000 | 0.667 | 0.583 | 0.500 | 0.667 | 3052.3 | 145.5 | 5992.43 | 0.037798 | 0.113395 |
| fixed | 4096 | 1.000 | 1.000 | 0.333 | 0.196 | 0.000 | 0.500 | 0.361 | 0.333 | 0.500 | 5149.5 | 110.0 | 4639.61 | 0.056995 | 0.170985 |
| structural | 2048 | 1.000 | 1.000 | 0.167 | 0.159 | 0.000 | 0.333 | 0.278 | 0.333 | 0.333 | 2719.8 | 73.2 | 3639.64 | 0.030857 | 0.185140 |
| structural | 4096 | 1.000 | 1.000 | 0.167 | 0.118 | 0.113 | 0.333 | 0.222 | 0.333 | 0.333 | 5078.5 | 69.7 | 3208.44 | 0.054268 | 0.325610 |

Costs use the pricing metadata frozen in this run's manifest.
Valid responses is the share of cells the provider completed and that parsed against the answer contract; a low rate means the arm's scores measure failed calls, not answer quality.
Valid judges is the same check for the citation-entailment judge call, over the cells that called it; n/a means no cell in the row called the judge, which is not a judge failure. A truncated judge can still emit parseable JSON, so citation entailment can only be read alongside this rate.
Gold-page alignment is the historical `citation_support` field; it is not semantic entailment. Citation entailment is reported only when the optional same-model judge is enabled.
