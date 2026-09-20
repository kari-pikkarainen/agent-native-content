# XLDev2 agent-document no-call smoke test

## Scope

The committed two-question table subset was prepared from cached source PDFs
and ingested documents. A local stub provider produced placeholder responses;
no external model was called, no answer result is meaningful, and no API cost
was incurred. The smoke test validated real released page annotations,
question-independent enrichment, context construction, and immutable artifact
publication.

The final bounded run prepared both referenced documents in 81.0 ms total on
the local test machine (40.5 ms amortized across two questions). This is a
one-time, reusable document cost, not per-query model latency.

## Representation volume

Mean local `o200k_base` tokens across the two questions were:

| Encoding | Mean tokens |
| --- | ---: |
| RAW | 33,515.5 |
| IR | 49,940.5 |
| ENRICHED, naïvely including all features | 119,732.0 |
| ENRICHED, excluding calculation rows inline | 73,675.5 |
| ENRICHED, excluding rows and capped at 128 inline features | 64,012.0 |
| INDEXED, 32 selected features within a 2K feature budget | 53,453.5 |

Calculation-ready table rows remain in the reusable JSON-LD bundle, where an
agent or tool can address them, but are not duplicated into the default answer
prompt. Inline features are selected by their fixed importance, page, and ID
order without using the question. The 128-feature cap reduces the naïve
enriched prompt by 46.5%.

The later two-stage `indexed` treatment cuts another 16.5% from the bounded
enriched prompt and is 7.1% larger than IR. It retains the same canonical source
evidence, but selects a small query-matching feature view from the reusable
document enrichment. This is a retrieval treatment rather than a pure encoding
comparison and must remain a separately reported condition.

## Decision

Keep the bounded inline policy as the initial answer experiment. It still uses
about 28% more tokens than IR and 91% more than RAW on this table-heavy slice,
so enriched documents must produce a material answer-quality or citation gain
to justify their prompt overhead. Do not interpret this smoke test as evidence
that they do; run the guarded provider experiment on the same small subset
before expanding the document set.
