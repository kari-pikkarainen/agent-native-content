# XLHoldout6c freeze

Date: 2026-09-22

Precommit: `f6522f7`

Canonical run: `xlholdout6c-gate1-60e5836`, made once, at Gate 1, on
2026-09-23, and recorded in [the Gate 1 decision](gate1-xlholdout6c-60e5836.md).
This subset has now been spent and must not be run again or used for tuning.

## Status

Frozen. `benchmarks/xl-docbench/subsets/xlholdout6c.json` is the Gate 1
screening holdout required by Phase 0 task 8 of the
[improvement plan](../plans/2026-09-21-improvement-plan.md). It was selected
from release metadata alone. No retrieval, compilation, ingestion, indexing,
evaluation, or answer generation was performed against it, and none of its six
source documents was read.

**Amended 2026-09-22: the affirmative preflight was run and one substitution
fired.** `doc_000028`, the `finance_business` pick's source, returned HTTP 403
Forbidden. The pre-registered rule below advanced to the next candidate on a
distinct document, `adubench_single_000181` on `doc_000095`, which fetched and
verified. The other four deferred sources fetched and verified unchanged. All
six sources are now cache-verified, so the preflight deviation recorded below
is closed; page and byte totals moved from 1,239 and 101,420,487 to 1,265 and
102,483,132. No other domain changed and no selection rule was relaxed. The
substitution is recorded in full under "Executed substitution".

Two commitments travel with this file:

1. It is never tuned on. No configuration, threshold, prompt, or default may
   be chosen, adjusted, or rejected using any observation from it.
2. It is run once, at Gate 1, with the configuration already selected on
   `xldev24`.

## Selection rules

The rules are `xlholdout6b`'s, applied unchanged except for the preflight
deviation recorded below. They were derived from `xlholdout6b.json`'s
`selection_method` and verified by re-executing them: with the exclusion set
restricted to `xl10`, `xldev24`, and `xlholdout6` and seed `20260921`, the
procedure below reproduces `xlholdout6b`'s six question IDs exactly, along with
its recorded 838 source pages and 56,231,276 source bytes.

1. Candidate pool: questions in the committed `xl100` manifest.
2. Keep `task_type == "single_doc"`.
3. Keep answerable questions (`metadata.is_unanswerable` false).
4. Drop any question whose source document appears in the exclusion set below.
5. Drop any question whose source document is recorded as a PDF preflight
   failure.
6. Within each of the six domains, order the survivors by ascending source
   `page_count`, then ascending source `file_size_bytes`, then ascending
   `SHA-256("<selection_seed>:<question_id>")` in hexadecimal, and take the
   first. One question per domain, six in total.
7. Emit question IDs and `source_document_ids` in ascending domain-name order,
   which is the order used by `xlholdout6b`.

Seed: `20260922`, following the one-per-day convention of the earlier subsets.
The seed only enters the tie-break.

Strata are computed from release metadata: `source_pages` and `source_bytes`
are sums over the six distinct source documents, and `evidence_modality`
counts a question as `table_chart_or_image` when `metadata.evidence_sources`
contains `Table`, `Chart`, or `Image`, and as `text_or_no_evidence` otherwise.
That modality rule reproduces the recorded counts for `xl10`, `xlholdout6`, and
`xlholdout6b`.

## Exclusion set

Every source document used by any question in `xl10` (6 documents), `xldev24`
(11), `xlholdout6` (6), and `xlholdout6b` (6). The union is 28 distinct
documents, because `doc_000166` is shared by `xl10` and `xldev24`:

```text
doc_000001 doc_000003 doc_000008 doc_000015 doc_000025 doc_000040 doc_000056
doc_000061 doc_000072 doc_000089 doc_000097 doc_000100 doc_000102 doc_000133
doc_000134 doc_000143 doc_000147 doc_000157 doc_000166 doc_000216 doc_000220
doc_000244 doc_000253 doc_000309 doc_000310 doc_000321 doc_000330 doc_000362
```

`xl100` uses 120 distinct documents, of which 22 of the 28 excluded ones
appear, so 98 remain document-fresh before the answerability and preflight
filters. The remaining six excluded documents are used by prior subsets but
not by any `xl100` question, which is why the figure is 120 − 22 rather than
120 − 28.

## Tie-break

Ties are broken on ascending `SHA-256("20260922:" + question_id)`, never by
sampling. The tie-break decided exactly one domain. In
`technical_engineering`, `adubench_single_001346` and `adubench_single_000687`
share the same source document `doc_000363`, so their page and byte keys are
identical; the digests are `38918363c56f...` and `b4950c99d51e...`, and the
lower digest selects `adubench_single_001346`.

## Selected questions

| Domain | Question | Document | Pages | Bytes | Modality |
| --- | --- | --- | ---: | ---: | --- |
| finance_business | `adubench_single_000741` | `doc_000028` | 135 | 4,482,102 | text |
| legal_regulation | `adubench_single_001173` | `doc_000257` | 150 | 1,782,770 | text |
| medical_clinical | `adubench_single_000826` | `doc_000067` | 110 | 1,154,633 | text |
| narrative_literature | `adubench_single_000331` | `doc_000168` | 550 | 62,005,852 | text |
| scientific_academic | `adubench_single_000255` | `doc_000127` | 118 | 28,678,548 | text |
| technical_engineering | `adubench_single_001346` | `doc_000363` | 176 | 3,316,582 | chart |

Totals: 6 questions, 6 distinct documents, 1,239 pages, 101,420,487 bytes.
All six are answerable single-document questions. None of the six documents
appears in `xl10`, `xldev24`, `xlholdout6`, or `xlholdout6b`.

## Deviation: the affirmative preflight is deferred

`xlholdout6b` selected only from sources that had passed a fetch-and-verify
preflight. Selection here was performed offline, so the negative half of that
filter was applied from the recorded failure ledgers
(`data/cache/xl-docbench/failures.jsonl` and
`data/cache/xl-docbench/documents/failures.jsonl`), but the positive half was
not: only `doc_000067` is present and SHA-256-verified in the local source
cache. The other five pinned sources are preflight-deferred.

Those ledgers are under `data/cache/`, which `.gitignore` excludes, and they
are network-derived, so rule 5 is not reproducible from the repository alone.
It is recorded here instead, because it decides two of the six picks: without
it `finance_business` selects `adubench_single_000572` on `doc_000288` (105
pages) rather than `doc_000028` (135), and `legal_regulation` selects
`adubench_single_000245` on `doc_000124` (96 pages) rather than `doc_000257`
(150). The ledgers hold 22 distinct documents, every one a
`DocumentDownloadError`:

```text
doc_000016 doc_000045 doc_000057 doc_000086 doc_000099 doc_000101 doc_000115
doc_000124 doc_000125 doc_000126 doc_000136 doc_000165 doc_000172 doc_000177
doc_000200 doc_000240 doc_000288 doc_000290 doc_000312 doc_000323 doc_000328
doc_000356
```

Five of those 22 would otherwise have been eligible, carrying six questions
between them. An earlier revision of this log recorded three; that figure was
wrong and could not be reconciled against any reading of the rule. The
predicate is: present in `xl100`, `task_type == "single_doc"`, answerable, and
on a document absent from the 28-document exclusion set.

| Question | Document |
| --- | --- |
| `adubench_single_000095` | `doc_000045` |
| `adubench_single_000245` | `doc_000124` |
| `adubench_single_000249` | `doc_000125` |
| `adubench_single_000572` | `doc_000288` |
| `adubench_single_001243` | `doc_000288` |
| `adubench_single_001283` | `doc_000312` |

Requiring a cache-verified source instead would not have produced a balanced
set: no document-fresh, answerable `finance_business` candidate in `xl100` is
cached, so that rule yields five domains, not six. The balance rule was kept
and the preflight rule was weakened, not the reverse.

To keep the freeze meaningful, the contingency is pre-registered here and in
the manifest rather than decided later. If a pinned source fails preflight
before the Gate 1 run, substitute the next candidate in the same domain's
deterministic order **that sits on a distinct document which itself passes
preflight**, repeating until one does, and record every substitution in this
log.

The distinct-document requirement is load-bearing rather than pedantic: the
plain next candidate is not always on a different source. In
`technical_engineering` the next candidate by the frozen order is
`adubench_single_000687`, which sits on `doc_000363` — the same document as
the pinned question — so if that source fails, that substitute fails with it.
The chains below therefore list one question per distinct document, and an
earlier revision of this log listed `adubench_single_000687` as
`technical_engineering`'s first fallback, which would not have been
executable.

If a domain's chain is exhausted, **run Gate 1 on the remaining domains and
report the set as five-domain**, recording which domain was dropped and why.
Do not substitute across domains, re-draw, or relax a selection rule after
results are visible. `narrative_literature` is the shallowest chain at two
distinct documents, so it is the most likely to exhaust.

The frozen orders are:

- finance_business: `adubench_single_000741`, `adubench_single_000181`,
  `adubench_single_000045`, `adubench_single_000360`
- legal_regulation: `adubench_single_001173`, `adubench_single_000757`,
  `adubench_single_000103`, `adubench_single_000038`
- medical_clinical: `adubench_single_000826`, `adubench_single_000184`,
  `adubench_single_001267`, `adubench_single_001215`
- narrative_literature: `adubench_single_000331`, `adubench_single_000256`
- scientific_academic: `adubench_single_000255`, `adubench_single_000113`,
  `adubench_single_000630`, `adubench_single_001199`
- technical_engineering: `adubench_single_001346`, `adubench_single_000846`,
  `adubench_single_000130`, `adubench_single_001202`

Each entry sits on a distinct document. Chain depths, counted in distinct
documents: finance_business 4, legal_regulation 7, medical_clinical 8,
narrative_literature 2, scientific_academic 7, technical_engineering 9.

## Executed substitution, 2026-09-22

The affirmative preflight was run with
`contextbench dataset download xl-docbench --sources --document-id ...` over
the five deferred sources. One failed:

| Document | Domain | Outcome |
| --- | --- | --- |
| `doc_000028` | finance_business | **HTTP 403 Forbidden** |
| `doc_000127` | scientific_academic | fetched, SHA-256 `82acd6f852d5c509…` |
| `doc_000168` | narrative_literature | fetched, SHA-256 `a72a61acb1215aac…` |
| `doc_000257` | legal_regulation | fetched, SHA-256 `7fada798bc7c018c…` |
| `doc_000363` | technical_engineering | fetched, SHA-256 `e159db17c5de3e07…` |

Applying the rule above, `finance_business` advanced to the next candidate on
a distinct document: `adubench_single_000181` on `doc_000095`, 161 pages. It
was preflighted on its own and fetched, SHA-256 `cd2658668b1754fa…`, so the
chain stopped at one step. The frozen order for that domain is unchanged; the
substitution consumed its first fallback, leaving three.

Resulting changes, all mechanical consequences of the swap:

- `question_ids[0]`: `adubench_single_000741` → `adubench_single_000181`
- `source_document_ids[0]`: `doc_000028` → `doc_000095`
- `source_pages`: 1,239 → 1,265
- `source_bytes`: 101,420,487 → 102,483,132
- `evidence_modality` unchanged: both questions carry `["Text"]` evidence

`doc_000028`'s failure is now recorded in `data/cache/xl-docbench/failures.jsonl`,
so re-running rule 5 against the current ledgers excludes it and re-derives the
amended set directly.

This is the contingency working as designed rather than a re-selection: the
substitute was fixed in writing before the preflight ran, and the failure was
observed afterwards. Nothing about the result influenced the choice, because no
result exists.

## Known weaknesses

- Five of six questions have text-only gold evidence, against three of six on
  `xlholdout6b`. Modality was never a selection constraint in either subset;
  it is an outcome of minimizing pages and bytes. Gate 1 therefore says little
  about table, chart, and image evidence, and no table or figure claim may
  rest on it.
- The set costs 1,239 pages and about 101 MB to ingest, against 838 pages for
  `xlholdout6b`. `doc_000168` alone is 550 pages and 62 MB.
- `narrative_literature` had only two eligible candidates, so its fallback
  chain is two distinct documents deep and is the first that could exhaust.
- The reproduction check against `xlholdout6b` validates less than it may
  appear to. It exercises rules 1 to 4, 6 and 7, but not the affirmative
  preflight, which is inert on `xlholdout6b` because every domain winner
  there was cache-verified anyway, and not the tie-break, because no tie
  fired on `xlholdout6b`. Both are active here: the preflight is deferred on
  five of six sources, and the tie-break decided `technical_engineering`.
  Those two rules rest on their stated definitions and on the digests
  recorded above, not on the reproduction.
- Six questions cannot bound a loss margin. Gate 1 is a screening check, as
  the improvement plan already states.
