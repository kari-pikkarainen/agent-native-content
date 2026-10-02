# Device-Side Preparation: Enhancement Plan

Status: proposed 2026-10-01, awaiting review
Baseline commit: `6202d0b`
Depends on: [improvement plan](2026-09-21-improvement-plan.md), whose Gate 2
left Phase 3 closed and made the tabular pilot the next research step

## Purpose

The README now states a second core idea: content should be prepared once, at
the point of capture or creation, on the device that holds the original data,
the session context, and idle capacity, so that every later consumer reuses
that work. This plan makes that idea testable in the existing codebase
without adding infrastructure.

It delivers five enhancements and one research question:

| # | Enhancement | What it makes possible |
| --- | --- | --- |
| E1 | Preparation-cost ledger | Measure the cost that is shifted and the number of queries at which preparing once breaks even |
| E2 | Producer and policy fields | Record who computed a layer, under what context, and which sensitive feature classes were enabled |
| E3 | Stable identities across versions | Let a layer be maintained continuously on the creator's device without renaming every node on each edit |
| E4 | Markdown decoder | A native authoring format with no new dependency, used as the test harness for E3 |
| E5 | XLSX decoder with formula preservation | The format the tabular pilot and the device-side claim are measured on |
| RQ5 | Break-even question | Does preparing once at creation lower cost per correct answer across many queries, and at how many queries |

The order is deliberate: measure first, then trust, then identity, then the
formats, then the experiment.

## What already fits

- The canonical IR holds source truth only; enrichment is derived, versioned,
  and rebuildable. That is the trust boundary a device-produced layer needs.
- Enrichment is deterministic, extractive, and cheap: about 81 ms for two
  documents. Every feature records generator, version, configuration,
  confidence, and source region.
- Caches, indexes, and bundles are content-addressed and verified on load, so
  nothing assumes the preparer and the consumer are the same machine.

## What does not fit

| Gap | Where | Consequence |
| --- | --- | --- |
| Ingestion starts from a rendered PDF and a heavy parser | `ingest/docling_adapter.py`, `ingest/cache.py` | Ten to twenty minutes per corpus of server work that reconstructs structure the authoring application already had |
| Identities are content hashes of the whole file | `ir/project.py:55` (`doc_{source_sha256}`) and `ir/project.py:364-368` (node ID hashes the document ID) | One edit renames every node; a continuously maintained layer cannot refer to anything |
| No preparation cost is recorded | `experiments/manifest.py` `RunManifest`, `agentdoc/models.py` bundle manifest | The cost-shifting claim cannot be measured |
| Bundles record a generator but not a producer | `agentdoc/models.py:101-116` | A consumer cannot tell a phone-side layer from a batch job, or whether people-counting was enabled |

## Constraints

1. The hash domains `contextbench-ir-v1` and `contextbench-index-chunks-v1`
   and every published node, document, and index identity stay byte-identical.
   New identity rules get a new, versioned domain and are opt-in.
2. No infrastructure: no device agents, mobile applications, sync services,
   or servers. Every enhancement is a library change, a manifest field, a
   decoder, or a measurement.
3. The canonical IR stays minimal. Anything derivable deterministically from
   source content goes in the enrichment layer, not the IR.
4. Gold benchmark data is untouched. The tabular pilot gets its own dataset
   with executable ground truth.
5. Every benchmark result stays reproducible from a config and a Git SHA, and
   every evaluation command keeps refusing a dirty worktree.
6. Tests stay offline. Fixtures are small committed files.

## Enhancements

### E1. Preparation-cost ledger

Add a `preparation` block to `RunManifest`, the factorial and generation
manifests, and the bundle manifest. Per stage (`download`, `parse`, `project`,
`enrich`, `index`) record wall milliseconds, CPU milliseconds from
`resource.getrusage`, peak resident set size, whether the stage was a cache
hit, and a host fingerprint (platform, CPU count, a salted hash of the
hostname). A cache hit records the cost stored with the cache entry at the
time it was produced, so the one-time cost travels with the artifact.

Store that cost in the artifact: `IngestMetadata` gains the parse cost, the
index manifest gains the index cost, and the bundle manifest gains the enrich
cost. Each is written once when the artifact is produced.

Report: `summary.json` and `report.md` gain a resource section with total
preparation cost, mean per-query cost by arm, and amortised preparation cost
per query at 1, 10, 100, and 1,000 queries. These are descriptive; the
break-even test is RQ5.

Tests: a fake parser with known sleep records non-zero wall time; a cache hit
reproduces the stored cost rather than measuring a near-zero one; manifests
without the block still validate so published artifacts load unchanged.

### E2. Producer and policy fields

Extend the bundle manifest with two optional blocks, bumping its schema
version to `1.1.0` and keeping `1.0.0` bundles readable:

```text
producer:
  kind                 device | service | batch
  application          free text, e.g. "agent-native-content agentize"
  application_version
  host_fingerprint     same salted hash as E1
  produced_at          ISO timestamp
  capture_context      optional map, e.g. sensor fields a device supplies
feature_policy:
  enabled_classes      feature kinds the producer computed
  disabled_classes     feature kinds the producer declined to compute
  sensitive_classes    kinds that describe people and need explicit enablement
```

`agentize` fills `producer` from the running process and sets
`feature_policy` from its configuration. The JSON-LD export carries both
blocks under the existing vocabulary. No current feature kind describes
people, so `sensitive_classes` is empty today; the field exists so that a
future decoder cannot add such a class silently.

Tests: a `1.0.0` fixture bundle loads; a `1.1.0` bundle round-trips; the HTML
export renders the producer block; `extra="forbid"` still rejects unknown
keys.

### E3. Stable identities across versions

Write ADR 0003. The decision:

- A document has two identities. `content_id` is what exists today, the
  SHA-256 of the bytes. `lineage_id` is stable across versions of the same
  work: supplied by the producer when it knows it, otherwise the
  `content_id` of the first version seen. `version` is a monotonic counter
  per lineage and `previous_content_id` links versions.
- Node IDs under the new domain `agent-native-content-ir-v2` hash
  `lineage_id`, node kind, heading path, and a normalised content hash, with
  an occurrence index to separate identical siblings. Ordinal and page are
  excluded, so an untouched node keeps its ID when text moves around it; an
  edited node gets a new ID and a `previous_id` link.
- `IRDocument` gains `id_scheme` with default `"v1"`. Docling PDF projection
  keeps `v1`; native decoders use `v2`. Every manifest records the scheme.

Tests: a Markdown fixture edited in one paragraph keeps every other node ID;
a moved section keeps its IDs; a fixture projected under `v1` reproduces the
IDs recorded in a committed results manifest byte for byte, which is the
regression guard for constraint 1.

### E4. Markdown decoder

A decoder from CommonMark to IR behind the existing `DocumentParser`
protocol: headings, paragraphs, lists and items, fenced code, pipe tables,
and block quotes map to the existing node kinds; `source_item_ids` become
line ranges; `page_start` and `page_end` stay unset, which the IR already
allows. Use `markdown-it-py`, which is already in the dependency tree
through Docling, and declare it explicitly in `pyproject.toml` so the
decoder does not depend on a transitive pin. Restrict the decoder to that
block subset; determinism matters more than coverage.

`ingest` and `agentize` accept `.md`. The cache key includes the decoder
name and version exactly as it includes Docling's.

This decoder exists to test E3 and the device-side flow cheaply. It is not a
research treatment: the controlled document experiment already found no
answer-quality benefit from structured rendering of long text.

### E5. XLSX decoder with formula preservation

Write ADR 0004. The decision keeps the IR minimal:

- Each worksheet becomes a section node; each contiguous table region
  becomes a table node. `IRTable` gains optional cell-level fields: address,
  raw value, value type, number format, and formula text. These are source
  truth, because they are in the file.
- The formula dependency graph is derived, so it lives in the enrichment
  layer as `relationship` features of type `depends_on` with cell-level
  provenance, computed deterministically from the formula text. Column types,
  units inferred from number formats, and candidate keys are enrichment too.
- Bounding boxes are not applicable; `source_item_ids` are cell addresses.

Dependency: `openpyxl`, already present transitively through Docling, declared
explicitly under a new optional extra `spreadsheets`. Tests use small
committed workbooks with formulas across sheets.

The tabular pilot's three conditions map onto this: compact CSV text is
`raw`, the typed schema is `ir`, and the agent-native representation with
formula dependencies and provenance is `enriched`. The pilot's tasks
(filtering, aggregation, joins, unit conversion, formula tracing, provenance)
get executable ground truth computed from the workbook itself.

### RQ5. Break-even question

Add to the evaluation protocol:

> Does preparing content once at creation, then reusing it across many
> queries, lower the total cost per correct answer compared with processing
> on demand, and at how many queries does it break even?

Measurement: total preparation cost from E1, mean per-query cost by arm, and
an on-demand baseline that parses and enriches inside the query path with
caches disabled. Break-even is the number of queries at which cumulative
prepared cost falls below cumulative on-demand cost. Report it per corpus
and per format. Preregister the first run, on `xldev24` and on the pilot
workbooks, before executing it. The founding benchmark specification stays
as written; the question is recorded in `docs/specs/evaluation.md` and the
roadmap.

## Phases and gates

| Phase | Scope | Rough effort | Gate |
| --- | --- | --- | --- |
| A | E1 ledger; record the principle in `docs/vision.md`, `docs/roadmap.md`, and `docs/specs/evaluation.md` | One week | Every manifest kind carries the block; a rerun of the smoke experiment reports amortised cost; published artifacts load unchanged |
| B | E2 producer and policy fields | Two to three days | `1.0.0` and `1.1.0` bundles both load; `agentize` output carries both blocks |
| C | ADR 0003; E3 identities; E4 Markdown decoder | Two weeks | Edit tests pass; `v1` regression guard reproduces committed IDs; `ingest` and `agentize` accept Markdown |
| D | ADR 0004; E5 XLSX decoder, IR cell fields, dependency enrichment | Two to three weeks | Fixture workbooks round-trip; formulas preserved verbatim; dependency graph matches hand-computed truth |
| E | RQ5 preregistration and first run; tabular pilot preregistration | One week plus run time | Break-even reported for `xldev24` and the pilot workbooks; pilot frozen before any measured run |

Do not start a phase before the previous gate is recorded in
`docs/research-log/`. Phases A and B can run in parallel with the tabular
pilot's task design, which is separate work.

## Non-goals

- Device agents, mobile applications, background services, or any sync
  mechanism. The device-side claim is tested by producing bundles on one
  machine and consuming them on another, not by shipping software to phones.
- Abstractive or model-generated enrichment. Everything remains deterministic.
- People-describing features. E2 reserves the policy vocabulary; nothing in
  this plan computes a count, a trajectory, or a speed.
- Audio, video, and image decoders. They are decoder work for a later plan
  once E3 and E5 show the identity and trust model holds.
- Re-running any spent holdout.

## Risks

| Risk | Mitigation |
| --- | --- |
| `v2` identities leak into a `v1` artifact and change a published ID | `id_scheme` is explicit, defaults to `v1`, and the regression guard compares against committed manifests |
| Cell-level fields bloat the IR for large workbooks | Fields are optional; region detection bounds table size; the pilot workbooks are small by design |
| Host fingerprint identifies a person's machine | Hostname is salted and hashed; the salt is per-repository and not committed |
| The on-demand baseline for RQ5 is unfair to one side | Both sides use the same parser, enrichment, and models; only caching differs, and the configuration is recorded |
| Markdown parser edge cases produce nondeterministic trees | Bounded CommonMark subset, fixture corpus with golden IR, determinism test over repeated runs |
| The tabular pilot stalls on task design | Phases A to D do not depend on it; Phase E waits |

## Acceptance

The plan is complete when the five enhancements are merged with their tests,
ADRs 0003 and 0004 are recorded, the research log holds one entry per gate,
and the first preregistered RQ5 run is published under `results/` with its
break-even figure for at least one document corpus and one workbook set.
