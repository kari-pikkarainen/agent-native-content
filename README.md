# Agent-Native Content

> Persistent, structured, provenance-preserving content for AI agents.

AI systems usually break a document into loose text snippets and search those
snippets again for every question. This project tests a different approach:
parse a document once into a structured, trustworthy representation that keeps
its sections, tables, and links back to the source pages, then assemble a
small, token-budgeted evidence packet for each question. The question is
whether that preparation selects better evidence, or the same evidence in
fewer tokens, than strong conventional retrieval-augmented generation (RAG).

A second idea runs through the project: the preparation should happen once,
at the point where content is captured or created, on the device that has
the original data and spare capacity. A phone that takes a photo, a laptop on
which a document is being written, and a camera that records video all sit
idle most of the time and hold context that is lost later, such as sensor
readings, the editing history, and the full-resolution source. If those
devices write a machine-readable layer beside the content, every later
consumer, including AI agents, reuses that work instead of repeating it on a
server for every task. The current benchmark tests the document case; the
[last chapter](#beyond-documents-content-that-carries-its-own-agent-readable-layer)
sets out the broader concept.

This is a **falsification-oriented research prototype**, not a product. It is
built so that the hypothesis can be rejected, and much of the record here is
about what did not work.

## Where things stand

| Claim | Evidence |
| --- | --- |
| The compiler selects more gold-evidence **pages** than the best RAG baseline at 2K and 4K tokens. | Holds on the 24-question development set and on one run of a frozen six-question holdout. |
| It does not reliably select more **exact quoted evidence**. | On the holdout it trails fixed RAG on exact quote recall at every budget. |
| It does not yet produce better **answers**. | One preregistered answer-generation run found no benefit; its failure analysis showed the run measured abstention, not evidence quality. |
| Showing the structured representation directly to an answer model does not help. | With identical gold pages, raw text matched or beat every structured encoding at about half the tokens. |
| The persistent representation has not been shown to be the cause of the page-recall gain. | On the matched factorial, intermediate representation (IR) nodes lead on page recall but not on quote recall, and coverage packing explains much of the split. |

Development-set page recall at the frozen configuration, mean over 24
questions, with the best of the two RAG baselines beside it:

| Budget | Compiler | Best RAG |
| ---: | ---: | ---: |
| 2K | **0.718** | 0.533 |
| 4K | **0.806** | 0.634 |
| 8K | **0.860** | 0.739 |
| 16K | **0.888** | 0.843 |

Read these with the caveats on the [status page](docs/status.md): page recall
over-credits the compiler relative to exact quote recall, a later change to
charge every arm for rendered prompt overhead costs the compiler up to 7 points
at 2K, and the holdout loses to fixed RAG at 16K. The full account, every
decision, and every negative result are in [`docs/status.md`](docs/status.md),
with the compact published evidence in [`results/`](results/README.md).

**Current decision:** keep the compiler as a credible low-budget
page-selection treatment; do not claim it replaces RAG or improves answers;
pause document-format tuning; run a small tabular-data pilot next. See the
[roadmap](docs/roadmap.md).

## How it works

```text
                         prepared once per document/corpus
PDF ──▶ Docling document ──▶ canonical IR ──▶ verified local indexes
                                  │                     │
                                  └──▶ agent bundle     │
                                       HTML + JSON-LD   │
                                                        ▼
query ──▶ hybrid retrieval ──▶ query facets ──▶ structural expansion
                                                    │
                                                    ▼
answer model ◀── evidence packet ◀── exact-token coverage packing
```

The IR preserves hierarchy, heading paths,
tables, page locations, source hashes, and stable provenance. It deliberately
excludes embeddings, retrieval scores, and generated annotations: those are
replaceable derived state.

At query time the compiler retrieves IR nodes with the same local models the
RAG baselines use, expands useful document structure, optionally joins rows
across explicitly named tables, removes provenance-aware duplicates, and packs
the result without exceeding the token budget. No large language model (LLM)
takes part in retrieval or compilation.

## Compared systems

| Arm | System | Distinguishing behaviour |
| --- | --- | --- |
| A | Fixed RAG | 512-token chunks with 64-token overlap |
| B | Structural RAG | Docling `HybridChunker` chunks |
| C | Long context | Source nodes in document order; no retrieval |
| D | Context compiler | IR-node retrieval plus deterministic compilation |

Arms A, B, and D share BM25 lexical search, dense retrieval, fusion, reranking,
tokenizer, model configuration, and hard budget accounting. The treatment is
document representation and context construction, not a weakened baseline.

## Agent-ready documents: the concept and what we learned

Alongside the benchmark, the project explores a related idea: a document
that carries a machine-readable layer next to its human-readable one, so an
agent can read prepared structure directly instead of reconstructing it for
every task. The `agentize` command builds such a bundle from a PDF:

```text
source.pdf            hash-verified original (optional)
content.json          canonical Content IR
enrichments.jsonld    outline, section previews, key facts, definitions,
                      aliases, typed relationships, table schemas,
                      calculation-ready rows, quantities
agent.html            semantic HTML with the same JSON-LD embedded
manifest.json         identities, configuration, and file hashes
```

Every feature keeps its confidence and its node, item, and page provenance.
Enrichment is deterministic and extractive; no language model takes part. This
is not a new file format: HTML plus JSON-LD (JSON for Linked Data) already
carries both kinds of content, and a reader still has to choose to use the
embedded layer. See the [bundle specification](docs/specs/agent-document.md).

What the experiments showed:

- **Cheap to make, costly to show.** Two documents were enriched in about
  81 ms, reusable for every later question. But rendered into a prompt, the
  capped enriched view was 91% larger than the raw text and 28% larger than
  the IR alone.
- **No answer-quality gain when shown directly.** Given identical gold pages,
  a local 12B model answered 6 of 18 questions from raw text, 5 from IR, 5
  from enriched IR, and 6 from a query-selected feature view, at 1.9 to 2.4
  times the tokens. The feature view had the least well-supported citations.
  Under the preregistered rule, document-format tuning stopped.
- **What that leaves open.** One small model, one prompt, 18 development
  questions. The conservative default is to use the structure internally for
  selection and render compact text to the model. The next test is tabular
  data, where explicit structure has a clearer potential advantage.

Records: [no-call volume check](docs/research-log/xldev2-agent-document-no-call.md)
and [controlled representation result](docs/research-log/representation-xldev24-gemma-b3d53c0.md).

## Quick start

Requirements: Python 3.12 or newer and [`uv`](https://docs.astral.sh/uv/).

```shell
git clone https://github.com/kari-pikkarainen/agent-native-content
cd agent-native-content
uv sync --extra retrieval
uv run agent-native-content --help
uv run --frozen pytest -q
```

Run the two-question smoke experiment. The first run downloads the pinned
dataset metadata, eleven source PDFs, Docling's parser models and two small
retrieval models, then parses the PDFs; allow tens of minutes cold and about
two minutes warm.

```shell
uv run --extra retrieval agent-native-content eval-retrieval \
  --subset-file benchmarks/xl-docbench/subsets/xldev2-tables.json \
  --retrieval-corpus-subset-file benchmarks/xl-docbench/subsets/xldev24.json \
  --run-id xldev2-local
```

It prints the artifact paths as JSON on stdout. Open
`artifacts/runs/xldev2-local/report.md` for the comparison. The step-by-step
walkthrough, including ingesting your own PDF, creating an agent bundle,
running offline, and the opt-in answer-generation experiments, is in
[Getting started](docs/getting-started.md).

Every evaluation command refuses to run from a modified worktree so that a
result is always reproducible from its recorded Git SHA. Run IDs are
immutable; an existing run is never overwritten.

## Commands

| Command | Purpose |
| --- | --- |
| `dataset download` / `list` / `inspect` | Fetch and inspect the pinned XL-DocBench release |
| `ingest` | Parse one PDF into a cached, content-addressed `DoclingDocument` |
| `agentize` | Build a portable agent bundle: IR, JSON-LD features, semantic HTML |
| `eval-retrieval` | Evidence-only benchmark of all four arms at 2K, 4K, 8K, 16K |
| `eval-factorial` | Cross content units with selection policies to separate their effects |
| `eval-generation` | Answer and score questions from saved contexts; needs explicit pricing and a call ceiling |
| `eval-representation` | Compare encodings of identical gold pages with an answer model |

No default command makes a paid model call.

## Metrics

The primary retrieval metric is gold-evidence page recall at a fixed packed
token budget. Runs also record full page coverage, exact quote recall under a
recorded match policy, tokens to full evidence, packed tokens, redundancy, and
query-time latency. Generation runs record benchmark accuracy, token F1 (token
overlap), average normalized Levenshtein similarity (ANLS), citation validity
and entailment, abstention correctness, provider tokens, latency, and cost.
Definitions are in the [evaluation protocol](docs/specs/evaluation.md).

## Known limitations

- The comparison supports the complete compiler pipeline, not the IR as an
  isolated cause.
- Page recall over-credits broad page coverage; exact quote recall is less
  favourable and is treated as co-primary.
- Both holdouts are six questions and are spent; the full 100-question set has
  not been run with the frozen configuration.
- All questions are single-document with the document scope supplied.
  Cross-document routing and a second dataset are untested.
- Answer quality has been measured once, on six questions with one model, and
  was negative.
- Compiler retrieval is 2.3 to 3.9 times slower than fixed RAG.
- Experiments use English PDFs, local retrieval models, and one benchmark
  release.

The complete list with measurements is in
[`docs/status.md`](docs/status.md#known-limitations).

## Repository map

```text
src/agent_native_content/
  agentdoc/        portable document enrichment and bundles
  compiler/        query facets, joins, expansion, dedupe, and packing
  datasets/        pinned XL-DocBench adapter and source cache
  evaluation/      retrieval benchmark, metrics, reports, and stage audit
  generation/      provider-neutral answer evaluation
  ingest/          Docling conversion and verified cache
  ir/              canonical models, projection, serialization, tokenization
  representation/  controlled document-encoding experiment
  retrieval/       chunks, BM25, dense search, fusion, and reranking
benchmarks/        committed benchmark subsets
docs/              getting started, status, specs, decision records, research log
results/           compact canonical reports, summaries, and manifests
artifacts/         ignored local indexes and complete experiment outputs
data/              ignored dataset release, source PDFs, and parse cache
tests/             offline unit tests, fixtures, and release-dependent integration tests
```

## Reading guide

- To use it: [Getting started](docs/getting-started.md).
- To judge it: [Status and decision history](docs/status.md), then
  [`results/`](results/README.md).
- To understand it: [vision](docs/vision.md), [architecture](docs/architecture.md),
  then the [specifications](docs/specs/README.md).
- To reproduce or extend it: the [research log](docs/research-log/README.md)
  "start here" chain, the [improvement plan](docs/plans/2026-09-21-improvement-plan.md),
  and [CONTRIBUTING.md](CONTRIBUTING.md).

## Beyond documents: content that carries its own agent-readable layer

The document bundle above is one instance of a broader idea. Most file
formats carry two kinds of information: the content a person consumes, and
metadata for one use case, such as a camera model and GPS position in a
photo's EXIF block, or a title and bitrate in an audio file. The concept is a
third layer: pre-processed, machine-readable facts about the content itself,
computed once, stored with the file or beside it, and carrying provenance and
confidence so an agent can use them without re-deriving them for every task.

The core of the concept is where that layer is computed. The device that
captures or creates content is the best place to do it: it has the original
data at full fidelity, the sensors and session context that are gone by the
time a file reaches a server, and, most of the day, idle processors. Phones,
laptops, cameras, and recorders are rarely fully utilised, and a document
author's machine does nothing between keystrokes. Shifting part of the
processing to the point of creation spreads the cost across millions of
devices that are already paid for, keeps the richest context, and lets the
work happen once rather than on every downstream system that later needs
it. The layer must record which device and generator produced each fact so
that a consumer can decide how far to trust it.

What that layer could hold, and where it would be computed, by example:

- **Images.** Beyond camera and location: the number of people, their
  positions as regions, direction of travel, estimated speed, visible text,
  the objects present, and which pixels each claim rests on. A phone can
  compute these at capture, when it still has the burst of frames, the
  motion sensors, and the unprocessed image that a single exported JPEG has
  lost.
- **Video.** Scene and shot boundaries, on-screen text and slide changes
  aligned to the speech track, tracked objects with trajectories, and events
  with timestamp ranges, so a question about minute twelve does not require
  decoding the file. A dashcam or a phone recording video has heading and
  speed from its own sensors; writing them into the layer is cheaper and more
  accurate than inferring them later from pixels.
- **Audio.** Speaker turns, timestamps, overlaps, non-speech events, and a
  transcript whose every span points back to a time range. A recorder or a
  meeting client can produce these as the audio is captured, while it still
  knows which microphone and which participant each channel belongs to.
- **Web pages.** The content region separated from navigation and
  boilerplate, the outline, structured data for entities and relations, and
  stable anchors, which HTML plus JSON-LD can already carry today. The
  publishing system has the structured source the page was rendered from, so
  it can emit the layer at publish time instead of leaving every crawler to
  reverse-engineer the template.
- **Spreadsheets and documents.** Typed columns, units, keys, formula
  dependencies, outlines, and table schemas, where the structure is a graph
  that flat text cannot express. The author's laptop holds the live formula
  graph and the editing session and is idle between keystrokes; it can
  maintain the layer as the file is written, as this project's `agentize`
  command does after the fact for a finished PDF.
- **Logs and traces.** Event schemas, request and trace identifiers, and
  causal links between entries. The emitting service already has the
  structured event before it is flattened into a log line.

Two lessons from this repository apply directly. The pre-processed layer is
worth its cost only where the consumer cannot cheaply rebuild it from the raw
content: a count across ten thousand frames or a speed derived from video
qualifies, while restating a paragraph did not, which is what the controlled
document experiment found. And derived facts must stay separable from source
truth, with the generator, its version, its confidence, and the exact source
region recorded for each one, so that they can be discarded, rebuilt, or
challenged without touching the original.

Facts about people, such as how many there are, where they are going, and how
fast, are surveillance-grade inferences. A format that can carry them should
make them optional, record who computed them and when, and make their presence
auditable, rather than treating them like a timestamp.

Most containers already have a slot for such a layer: EXIF and XMP for
images, ID3 and Broadcast Wave chunks for audio, metadata tracks and WebVTT
for video, and JSON-LD for the web. The open problems are a shared vocabulary,
a common provenance model across media, and the evidence, which this project
has so far only for documents, that agents answer better or cheaper when the
layer is present. That evidence is the next thing to collect.

## License and citation

Agent-Native Content is available under the
[Apache License 2.0](LICENSE). Distributions must include the license and the
project's [NOTICE](NOTICE), retain applicable notices, and identify modified
files.

If the software, Content IR design, benchmark methodology, or published
results inform your work, please cite it using the metadata in
[`CITATION.cff`](CITATION.cff). Contributions are welcome under the same
license; see [CONTRIBUTING.md](CONTRIBUTING.md) for the research-integrity
rules and the Developer Certificate of Origin sign-off.
