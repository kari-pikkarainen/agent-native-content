# Device-Side Preparation: Enhancement Plan

Status: revised 2026-10-01, ready for implementation
Baseline commit: `120c796`
Depends on: [improvement plan](2026-09-21-improvement-plan.md), whose Gate 2
left Phase 3 closed and made a tabular pilot the next research step

## Purpose and decision

The README states a broader idea than document retrieval: content should be
prepared once, preferably where it is captured or created, while the producer
still has the original structure, session context, and idle capacity. Later
consumers should be able to reuse a provenance-bearing machine-readable layer
instead of reconstructing it for every query.

The current evidence does not justify building that architecture in full. The
document compiler has a narrow low-budget page-recall result, but structured
document encodings did not improve answers and used roughly twice the tokens
and latency of compact text. The next investment must therefore test the
concept on data where explicit structure has a clearer potential advantage.

**Decision:** run a minimal, preregistered tabular-data pilot before building
general producer metadata, cross-version identity, or additional native
decoders. Implement only the measurement and XLSX support needed by that
pilot. Continue with the broader device-side work only if the development
gate shows a useful accuracy, provenance, or information-efficiency signal.

This order follows the repository's founding rule: add only the smallest
implementation required to test the next research claim.

## Research questions

### Tabular representation question

> Given identical source rows, does typed and provenance-bearing tabular data
> let an answer model complete structured tasks more accurately or with fewer
> input tokens than compact CSV or plain table text?

### RQ5 — Preparation economics

> If content is prepared once at creation and reused, at how many queries does
> its cumulative cost per correct answer become lower than equivalent
> processing performed on demand?

RQ5 is measured only after the tabular development gate. A representation
that does not improve answers, provenance, or information efficiency does not
earn a broader economics exercise merely because its preparation is cacheable.

## Proposed enhancements

| # | Enhancement | What it makes possible | When |
| --- | --- | --- | --- |
| E1 | Preparation-cost ledger | Separate one-time artifact production from observed reuse and query costs | Minimum version for the pilot; generalize after the gate |
| E5 | XLSX decoder with formula preservation | Test typed cells, formulas, dependencies, and cell provenance | Minimum version for the pilot |
| E2 | Producer and feature-policy fields | Let a consumer judge who prepared a layer and which feature classes were enabled | Only after a positive development gate |
| E3 | Stable identities across versions | Maintain references as producer-owned content evolves | Only after a positive development gate |
| E4 | Markdown decoder | Exercise native authoring and cross-version identity without a heavy parser | Only with E3 |

The numbering is retained from the first draft so references to E1–E5 remain
stable. The implementation order is intentionally different.

## What already fits

- The canonical intermediate representation (IR) holds source truth only;
  enrichment is derived, versioned, and rebuildable.
- Deterministic agent-document features already retain generator, version,
  configuration, confidence, and source-region provenance.
- Caches, indexes, and bundles are content-addressed and verified on load, so
  the preparer and consumer need not be the same process or machine.
- The provider-neutral representation runner already supports controlled
  conditions, immutable artifacts, strict output parsing, and explicit cost
  reporting. The tabular runner should reuse those contracts rather than
  create a second experimental framework.

## Gaps

| Gap | Consequence |
| --- | --- |
| Ingestion starts from rendered PDF and a heavy parser | It reconstructs structure an authoring application already possessed |
| Preparation cost is not a shared manifest concept | The prepare-once claim cannot be compared with on-demand processing |
| XLSX formulas, value types, formats, and cell addresses are not represented | The proposed tabular treatment cannot be built or audited |
| Current identities derive from the complete source hash | One source edit renames the document and every node |
| Bundles record a generator but not a producer or feature policy | A consumer cannot distinguish device, batch, and service output or audit disabled sensitive features |

## Constraints

1. The published `contextbench-ir-v1` and
   `contextbench-index-chunks-v1` identity domains remain byte-identical. New
   identity behavior is opt-in and versioned.
2. No device agent, mobile application, synchronization service, server, or
   hosted database is part of this plan.
3. The canonical IR contains source truth only. Formula dependencies, inferred
   units, candidate keys, and summaries are derived enrichment.
4. Gold benchmark data is untouched. The tabular pilot uses a separate,
   committed dataset with executable or committed deterministic ground truth.
5. Every measured run is reproducible from a configuration and Git SHA and
   refuses an unacknowledged dirty worktree.
6. Conditions use the same answer model, prompt contract, output limit,
   sampling settings, and scoring. No condition receives a model unavailable
   to the others.
7. Tests stay offline and fixtures stay small.
8. No untouched holdout is run until the development rule, model, renderer,
   and analysis have been frozen.

## Phase 0 — Preregister the tabular pilot

Write the experiment specification before implementing the measured runner.
It must freeze:

- the development and untouched holdout workbook IDs;
- the task generator and deterministic oracle;
- selected task families: filtering, aggregation, joins, unit conversion,
  formula tracing, and cell-level provenance;
- the exact output JSON schema and scorer;
- one answer model for the development gate;
- the three representation conditions below;
- identical-data and equal-input-token comparisons;
- response-validity, accuracy, provenance correctness, input tokens, latency,
  and cost metrics;
- the paired stopping rule and the minimum result required before E2–E4 or a
  holdout run may begin; and
- a manual audit sample for the oracle, renderers, and scorer.

The stopping rule must require a material paired improvement rather than an
aggregate tie. It should also prevent a small correctness gain bought with
unbounded representation growth from passing. Its exact threshold is frozen
after the task count and family balance are known, before any model answer is
seen.

### Conditions

All conditions contain the same authorized source rows and differ only in
representation:

1. `raw`: compact CSV or plain table text;
2. `typed`: values plus explicit column meanings, data types, units, keys, and
   null semantics; and
3. `agent_native`: the typed representation plus formula dependencies,
   explicit relationships, reusable deterministic summaries, and cell-level
   provenance.

Report two views:

- **identical data**, showing the natural token cost of each representation;
- **equal token budget**, showing what each representation can communicate in
  the same model-input allowance.

The question and prompt must not disclose the condition name. Formatting
errors remain visible through `response_valid` and are not silently repaired.

## Phase 1 — Implement the minimum pilot path

### E1-min. Preparation-cost ledger

Create one backward-compatible `PreparationCost` model and use it first in
the tabular run and bundle manifests. Record per stage:

- wall milliseconds;
- CPU milliseconds, measured as a before/after process-usage delta;
- cache status;
- the cost observed in the current run; and
- the original production cost carried by a reused artifact.

Observed reuse cost and embodied production cost are separate fields. A cache
hit must not pretend that the original parse or enrichment happened again,
and a report must not add the same embodied cost once per consuming run.

Do not claim per-stage peak resident memory from
`resource.getrusage().ru_maxrss`: it is a process-lifetime high-water mark and
cannot be differenced by stage. Record one process-level peak for the run, or
measure a stage in an isolated subprocess if a later experiment specifically
needs stage-level memory.

The environment record contains platform, architecture, logical CPU count,
Python version, and dependency identities. It does not hash the hostname. An
optional producer-supplied identifier may be recorded privately, but public
results must not expose a stable machine identifier.

Reports show:

- one-time preparation cost;
- observed reuse and mean query cost;
- total and amortized cost at 1, 10, 100, and 1,000 queries; and
- cost per correct answer once answer results exist.

Legacy manifests without the optional preparation block must continue to
validate unchanged.

### E5-min. XLSX decoder and tabular renderers

Write ADR 0004 before changing the IR. The minimum implementation:

- maps each worksheet to a section and each bounded contiguous region to a
  table;
- preserves cell address, raw value, value type, number format, and formula
  text as source truth;
- uses worksheet-and-cell references as source provenance;
- derives formula dependencies as replaceable `depends_on` enrichment;
- derives declared pilot-only schema features such as inferred units and
  candidate keys outside the canonical IR; and
- renders the three frozen conditions from one decoded workbook.

Declare `openpyxl` directly under a `spreadsheets` optional dependency rather
than relying on Docling's transitive installation.

`openpyxl` does not calculate formulas. The pilot therefore must not treat
its cached formula values as a general calculation engine. Filtering,
aggregation, joins, and conversions use a deterministic Python oracle over
source cells; formula-tracing tasks score the parsed dependency graph. Any
expected calculated value that cannot be recomputed by that bounded oracle is
committed with the generated fixture and verified during fixture creation.

Tests require deterministic repeated decoding, preserved formula text,
correct cell provenance, correct hand-checked dependency edges, and identical
authorized rows across all three renderers. “Round-trip” means decode,
serialize, load, and compare the projected artifact; the project does not
promise to rewrite an equivalent XLSX file.

## Phase 2 — Development gate

Run only the preregistered development workbooks. Publish the manifest,
per-task records, summary, report, renderer token counts, and preparation
ledger under `results/`.

### Continue when

The frozen paired rule passes and the manual audit finds no condition-specific
oracle, prompt, or scoring advantage. Record which task families carry the
effect; a gain confined to one family narrows the claim and the holdout design.

### Stop when

- neither structured condition materially beats compact raw data;
- a correctness gain disappears under the equal-token comparison;
- provenance improvements do not translate into scored provenance tasks; or
- representation and preparation overhead violate the preregistered bound.

If the gate stops, publish the negative result and keep the existing document
default: structure may organize selection internally, while answer models see
compact text. Do not implement E2–E4 merely to complete this plan.

## Phase 3 — Trust and portable production, conditional on the gate

### E2. Producer and feature-policy fields

Extend the bundle manifest with optional `producer` and `feature_policy`
blocks while keeping schema `1.0.0` bundles readable:

```text
producer:
  kind                 device | service | batch
  application
  application_version
  producer_id          optional, supplied rather than hostname-derived
  produced_at
  capture_context      optional declared map
feature_policy:
  enabled_classes
  disabled_classes
  sensitive_classes
```

`agentize` populates the application identity and declared policy. Capture
context is absent by default and is never inferred from the host environment.
The JSON-LD export carries the blocks. No current feature describes people;
future sensitive classes require explicit enablement and tests proving they
cannot appear silently.

Acceptance: old and new bundle schemas load, the new schema round-trips, HTML
and JSON-LD expose the declared producer and policy, unknown fields remain
forbidden, and public output contains no derived machine identifier.

## Phase 4 — Native versioning, conditional on the gate

### E3. Stable identities across versions

Write ADR 0003. Keep PDF projection and every existing artifact on identity
scheme `v1`. Native decoders may opt into `agent-native-content-ir-v2`.

The v2 design separates identity from content:

- `content_id` is the SHA-256 identity of one source version;
- `lineage_id` identifies the producer-declared work across versions;
- `version` and `previous_content_id` link document versions;
- a node has a stable producer/source anchor when one exists and a separate
  normalized content hash that detects edits; and
- `previous_id` is emitted only when the producer supplies the relation or a
  deterministic matcher can establish it without ambiguity.

Do not include heading path, ordinal, page, or mutable content in a
producer-anchored stable node ID. Including heading path would contradict the
requirement that a moved section retain its identity.

For sources without native anchors, a decoder may accept the previous IR and
conservatively reuse IDs for unique, exact matches of node kind and normalized
content. Ambiguous duplicates receive new IDs rather than a silently wrong
lineage. An edited node also receives a new ID unless the producer supplies a
stable anchor; heuristic similarity alone is not provenance.

Acceptance tests cover an unchanged unique block, a moved unique section, an
ambiguous duplicated block, an edited block with and without a producer
anchor, and byte-identical v1 IDs against a committed published artifact.

### E4. Markdown decoder

Add a bounded CommonMark decoder behind the existing parser boundary. Support
headings, paragraphs, lists and items, fenced code, pipe tables, and block
quotes. Use line ranges as source references and leave page fields unset.
Declare `markdown-it-py` directly.

Markdown is the inexpensive harness for the v2 identity contract; it is not a
new answer-quality treatment. `ingest` and `agentize` accept `.md`, cache keys
include decoder identity, and fixtures exercise edits, moves, and ambiguous
duplicates against the rules above.

## Phase 5 — Holdout and RQ5, conditional on the gate

Freeze the winning development configuration before running the untouched
tabular holdout. No renderer, prompt, oracle, task, or threshold changes are
allowed afterward.

For RQ5, compare:

- prepared once, then reused with caches enabled; and
- the same decoder, enrichment, renderers, and answer model run on demand with
  caches disabled.

Report cumulative wall time, CPU time, model tokens, dollars, correctness, and
cost per correct answer. Break-even is the smallest query count at which the
prepared path's cumulative cost per correct answer is lower. Report no
break-even when the prepared representation does not preserve at least the
preregistered answer-quality floor.

The document corpus may receive a descriptive prepare-once measurement, but
the spent document holdouts are never rerun and that measurement cannot revive
the rejected document-rendering claim.

## Gates and rough effort

| Phase | Scope | Rough effort | Gate |
| --- | --- | --- | --- |
| 0 | Pilot dataset, oracle, conditions, metrics, stopping rule | 2–4 days | Preregistration committed before model answers |
| 1 | E1-min, ADR 0004, E5-min, renderers and offline tests | 1–2 weeks | Fixtures decode deterministically; costs and tokens are recorded; conditions use identical source rows |
| 2 | Development run and audit | Run time plus 2–3 days | Frozen paired rule decides stop or continue |
| 3 | E2 producer and policy metadata | 2–3 days, only after pass | Old/new bundles load and public output has no machine fingerprint |
| 4 | ADR 0003, E3 identity, E4 Markdown | About 2 weeks, only after pass | Move/edit/ambiguity tests and v1 regression guard pass |
| 5 | Untouched holdout and RQ5 | About 1 week plus run time | Holdout result and break-even or no-break-even result published |

Every completed gate receives a dated research-log entry. A stopped gate does
not automatically authorize the next phase.

## Non-goals

- Device applications, background services, synchronization, authentication,
  or hosted infrastructure.
- LLM-generated enrichment. Pilot structure and features are deterministic.
- People-describing features. E2 reserves an auditable policy mechanism but
  this plan computes no count, location, trajectory, or speed of a person.
- Image, audio, or video decoders.
- Re-running a spent holdout.
- Claiming cross-device savings from a same-machine cache benchmark. The first
  RQ5 run tests prepare-once reuse; cross-device portability requires a
  separately declared transfer and verification test.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| The pilot becomes an XLSX platform before producing evidence | Phase 1 implements only frozen task and renderer needs; the development gate precedes all generalization |
| Conditions contain different source facts | One decoded workbook and an authorized-row manifest feed every renderer; tests compare the row and cell sets |
| Formula results are mistaken for spreadsheet-engine output | Use a bounded deterministic oracle; score dependency tracing separately; disclose unsupported formulas |
| Resource figures appear more precise than their measurement | Separate observed and embodied cost; do not report per-stage `ru_maxrss` |
| v2 identity changes a published v1 artifact | v2 is opt-in and a committed regression guard checks published v1 IDs byte for byte |
| A move changes identity through its heading path | Heading paths are excluded from producer-anchored IDs; anchorless reuse is conservative and tested |
| Machine fingerprints leak into public bundles | Do not derive identity from hostname; any producer ID is explicit and optional |
| Development tuning consumes the holdout | Holdout IDs are frozen and untouched until the complete winning configuration is committed |

## Acceptance

The immediate plan is complete at the Phase 2 decision: a preregistered
tabular development result is published and honestly stops or authorizes the
conditional work. The broader enhancement program is complete only if that
gate passes and E2–E4, the untouched tabular holdout, and RQ5 are subsequently
implemented, tested, recorded, and published.
