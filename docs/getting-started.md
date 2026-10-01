# Getting Started

This walkthrough takes a fresh clone to a first benchmark report, then shows
the other things the command-line tool can do. Every step is offline-safe
after its first download, and nothing here makes a paid model call.

## 1. Install

Requirements: Python 3.12 or newer and [`uv`](https://docs.astral.sh/uv/).

```shell
git clone https://github.com/kari-pikkarainen/agent-native-content
cd agent-native-content
uv sync --extra retrieval
uv run agent-native-content --help
```

The `retrieval` extra installs `sentence-transformers` for the dense retriever
and the cross-encoder reranker. Without it the dataset, ingest and agentize
commands still work, and the evaluation commands refuse to start with a clear
message.

Check the environment with the offline test suite:

```shell
uv run --frozen ruff check .
uv run --frozen pytest -q
```

Unit tests use committed fixtures and never touch the network. A few
integration tests under `tests/integration/` need the downloaded dataset or
Docling's parser models; they skip themselves when those are absent.

## 2. Look at the benchmark data

The benchmark is Microsoft's XL-DocBench, pinned to one release and revision.
Download the question metadata and list a committed subset:

```shell
uv run agent-native-content dataset download xl-docbench
uv run agent-native-content dataset list xl-docbench \
  --subset-file benchmarks/xl-docbench/subsets/xldev24.json
uv run agent-native-content dataset inspect xl-docbench <question-id>
```

`inspect` prints the question, its document, the gold answer, and the gold
evidence pages and quotes. The release references publicly hosted PDFs rather
than redistributing them; the benchmark runner fetches only the PDFs its
subset needs, checks each one's size and PDF signature, and records every
failed download rather than skipping it silently. Add `--sources` to
`download` to prefetch all of them.

The subsets under `benchmarks/xl-docbench/subsets/` are committed lists of
question IDs and are never regenerated implicitly:

| Subset | Role |
| --- | --- |
| `xldev2-tables.json` | Two table-heavy questions; a mechanics check, not evidence |
| `xldev24.json` | 24-question development set used to tune the compiler |
| `xlholdout6.json`, `xlholdout6b.json`, `xlholdout6c.json` | Six-question holdouts, each run once and then retired |
| `xl100.json` | The registered 100-question evaluation set; not yet run at the frozen configuration |

## 3. Run the smoke experiment

This evaluates the two table questions while indexing the full 24-question
corpus, so retrieval statistics match the development runs:

```shell
uv run --extra retrieval agent-native-content eval-retrieval \
  --subset-file benchmarks/xl-docbench/subsets/xldev2-tables.json \
  --retrieval-corpus-subset-file benchmarks/xl-docbench/subsets/xldev24.json \
  --compiler-stage-audit \
  --run-id xldev2-local
```

What happens on a cold machine, in order:

1. The eleven source PDFs are downloaded into `data/cache/xl-docbench/`.
2. Docling's parser models are downloaded, then each PDF is parsed once into
   `data/cache/ingest/<source-sha256>/<config-sha256>/`. This is the slow
   step: expect ten to twenty minutes for eleven documents. Pass
   `--parse-workers 2` to parse uncached documents in parallel.
3. The embedding model `BAAI/bge-small-en-v1.5` and the reranker
   `cross-encoder/ms-marco-MiniLM-L-6-v2` are downloaded and pinned to a
   resolved revision.
4. Three indexes are built under `artifacts/indexes/<sha256>/`, one each for
   fixed chunks, structural chunks and intermediate representation (IR) nodes, and verified before reuse.
5. All four arms run at 2K, 4K, 8K and 16K tokens. Progress goes to stderr;
   the final artifact paths are printed as JSON on stdout.

A warm rerun with a new run ID takes about two minutes.

Open the report:

```shell
cat artifacts/runs/xldev2-local/report.md
```

The run directory contains:

| File | Contents |
| --- | --- |
| `manifest.json` | Git SHA, dirty flag, dataset and subset hashes, source and parser identities, full config, pinned model revisions, seed, question IDs |
| `retrieval.jsonl` | One record per question × system × budget with every metric |
| `contexts.jsonl` | The complete rendered evidence packet for each cell |
| `compiler-stages.jsonl` | Candidate pools at each compiler stage, from `--compiler-stage-audit` |
| `summary.json` | Aggregates by system and budget, with paired bootstrap intervals |
| `report.md` | The human-readable comparison |

Two rules apply to every evaluation command. Run IDs are immutable, so choose
a new one each time. And the command refuses to run from a modified worktree,
so that every result is reproducible from its recorded commit; pass
`--allow-dirty` to override, which stamps the manifest with `git_dirty: true`.

## 4. Run offline

Once the models and indexes are cached, force the run offline:

```shell
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  uv run --extra retrieval agent-native-content eval-retrieval \
  --subset-file benchmarks/xl-docbench/subsets/xldev2-tables.json \
  --retrieval-corpus-subset-file benchmarks/xl-docbench/subsets/xldev24.json \
  --run-id xldev2-offline
```

## 5. Parse your own PDF

```shell
uv run agent-native-content ingest path/to/document.pdf
```

This writes the authoritative serialized `DoclingDocument` and a metadata
record under `data/cache/ingest/`. The cache key is the source SHA-256 plus
the SHA-256 of the complete parser configuration, so a second run reuses the
artifact and a parser or configuration change produces a new one. Remote
inference is disabled during parsing.

## 6. Build an agent bundle

```shell
uv run agent-native-content agentize path/to/document.pdf artifacts/agent-documents/example
```

The directory contains the canonical IR (`content.json`), question-independent
agent features with provenance (`enrichments.jsonld`), a semantic HTML
rendering with the JSON-LD (JSON for Linked Data) embedded (`agent.html`), a manifest of hashes and
configuration, and optionally the hash-verified source PDF. Enrichment is
deterministic and extractive; no language model takes part. The format is
specified in [`specs/agent-document.md`](specs/agent-document.md).

## 7. Separate representation from selection policy

The primary benchmark changes representation and selection behaviour at the
same time. The factorial command crosses three content units with two
selection policies under identical models and budgets:

```shell
uv run --extra retrieval agent-native-content eval-factorial \
  --subset-file benchmarks/xl-docbench/subsets/xldev2-tables.json \
  --retrieval-corpus-subset-file benchmarks/xl-docbench/subsets/xldev24.json \
  --run-id xldev2-factorial
```

It deliberately excludes the compiler's structural expansion, table joins and
page-neighbour backfill. See [`specs/factorial.md`](specs/factorial.md).

## 8. Answer questions from saved contexts (opt-in)

Answer generation never repeats retrieval. It reads a completed run's
`contexts.jsonl`, sends each packet to one model with one prompt, and scores
the answers with the benchmark's deterministic evaluator. It requires explicit
pricing and a hard ceiling on provider calls, and refuses to start if the
requested cells exceed the ceiling.

```shell
uv sync --extra generation
uv run --extra generation agent-native-content eval-generation \
  artifacts/runs/xldev2-local \
  --subset-file benchmarks/xl-docbench/subsets/xldev2-tables.json \
  --model <model-id> \
  --input-usd-per-million <price> \
  --cached-input-usd-per-million <price> \
  --output-usd-per-million <price> \
  --max-calls 24 \
  --run-id xldev2-generation
```

To use a local server that speaks the OpenAI Responses API, such as LM Studio,
pass `--provider-base-url http://127.0.0.1:1234/v1`, set every price to `0`,
and consider `--temperature 0` and a long `--provider-timeout`. The endpoint
is recorded in the manifest and your `OPENAI_API_KEY` is never sent to it.

The companion command `eval-representation` bypasses retrieval entirely and
gives an answer model the same gold pages as raw text, as IR, as enriched IR,
and as query-selected features, to test whether the encoding itself helps. It
is resumable and takes the same provider options. Both commands are specified
in [`specs/evaluation.md`](specs/evaluation.md).

## 9. Where to go next

- What has been found so far, including the negative results:
  [`status.md`](status.md).
- The published evidence behind each claim: [`results/`](../results/README.md).
- How the pieces fit: [`architecture.md`](architecture.md).
- The research questions and kill conditions:
  [`specs/benchmark.md`](specs/benchmark.md).
- What is planned: [`roadmap.md`](roadmap.md).
- How to contribute without weakening the controls:
  [`CONTRIBUTING.md`](../CONTRIBUTING.md).
