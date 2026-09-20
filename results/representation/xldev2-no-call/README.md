# XLDev2 Agent-Representation Preparation Result

**Status:** no-call diagnostic  
**Questions:** two table-heavy development questions  
**External model calls:** none

This experiment prepared identical released gold-evidence pages as raw text,
canonical IR, bounded query-independent enrichment, and an indexed view over
the same reusable enrichment. A local stub returned placeholder answers, so
this result measures representation volume and preparation mechanics—not
answer quality.

| Representation | Mean local tokens |
| --- | ---: |
| Raw | 33,515.5 |
| IR | 49,940.5 |
| Bounded enriched | 64,012.0 |
| Indexed | 53,453.5 |

The indexed view uses at most 32 selected features within a 2K feature-token
budget. It is 16.5% smaller than bounded enriched and 7.1% larger than IR. All
conditions retain the same canonical source evidence.

Question-independent enrichment for both cached documents took 81.0 ms on the
development machine. This is a reusable preparation cost, not per-query model
latency.

The result does not show that agent features improve answers. That requires the
guarded provider experiment with the same answer model, prompt, pricing, and
call ceiling across conditions. The full development record is in the
[research log](../../../docs/research-log/xldev2-agent-document-no-call.md).
