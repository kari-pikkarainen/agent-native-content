# Retrieval Baselines Specification

Milestone 4 implements benchmark Arms A and B over the same retrieval stack.
Only the chunk construction differs.

## Arms

Arm A (`fixed`) concatenates source-node text in IR ordinal order and creates
512-token windows with a 64-token overlap. Each window retains every source node
and page it contains.

Arm B (`structural`) uses Docling's `HybridChunker` with a 512-token limit,
native heading metadata, and repeated table headers. Each chunk maps back to the
Docling source item references emitted by the chunker and then to IR nodes.

Both limits and all retrieval parameters are fields of `RetrievalConfig`; tests
use smaller values only to keep fixtures compact.

### No retrieval surface indexes furniture

Running headers, footers and page numbers stay in the IR with full provenance
(`docs/specs/content-ir.md`) and are excluded from every surface a query can
reach: `fixed_chunks` for Arm A, Docling's body-only chunker traversal behind
`structural_chunks` for Arm B, `node_chunks` for the compiler, page-neighbor
windows (which are fixed windows and inherit Arm A's filter), `long_context`,
the representation runner, and the agentdoc bundle.

Until compiler 0.10.0 this held everywhere except Arm A, which is the arm the
compiler is measured against. Furniture is 5,804 nodes and 40,132 tokens across
the 28 cached documents — 1.9% of text, in strings like `'2018 l Annual
Report'` repeated once per page — so the baseline was paying budget for text
the compiler was never charged for. Correcting a source-order defect in the
same release made this larger, not smaller: with furniture interleaved in
reading order rather than appended in one block, it would have touched 2,617 of
4,895 fixed windows instead of 235.

**The rule is an allowlist: index `content_layer == "body"`.** Not "everything
except furniture". Both spellings select the same nodes today — `IRNode.content_layer`
is `Literal["body", "furniture"]`, enforced at validation, so no IR node can
hold a third value — but they diverge the moment a layer is added, and only the
allowlist fails safe. Every surface listed above now spells it that way; until
compiler 0.10.0, `fixed_chunks` and `node_chunks` used the denylist form while
the other four used the allowlist, which left this paragraph's requirement
written against two rules at once.

Any new retrieval surface must apply that rule. It is a property of the arms
being comparable, not an optimization.

## Shared retrieval pipeline

Both arms run the same deterministic stages:

1. BM25 sparse retrieval with explicit `k1`, `b`, and candidate limit.
2. Dense brute-force cosine retrieval over the same candidate corpus.
3. Reciprocal Rank Fusion with explicit `rrf_k`.
4. A shared reranker over the fused top candidates.
5. Provenance-aware token-budget packing. The budget counts the rendered
   evidence block -- tags, evidence IDs, joiners and content, as the answer
   prompt carries them -- unless a run chooses `budget_accounting="content"`.
   The definition, and why it changed, is in `docs/specs/evaluation.md`,
   "What the budget counts".

The returned `RankedEvidence` records dense, sparse, fused, and reranked scores.
Packed `ContextItem` values carry document IDs, pages, heading paths, IR node
IDs, Docling source item IDs, and an evidence ID suitable for answer citations.

### Which score may order candidates

This is normative. `RetrievalScores` has four fields and they are not
interchangeable.

**`reranked` is the only cross-class ordering key.** It is the only field
carried in one unit — cross-encoder score — for every candidate class, so it
is the only one any ordering that mixes classes may key on. Both compiler
ordering sites obey this: the candidate sort in `compiler/expand.py` and the
third element of `_coverage_key` in `compiler/pack.py`.

**`dense`, `sparse` and `fused` are class-local provenance.** They record how
a candidate reached the pool, and their units depend on the path it took.
`fused` is a reciprocal-rank-fusion sum for anything retrieved — over the
sparse and dense channels for a plain query, over rankings for a faceted one —
and a lexical overlap ratio in `0..1` for a keyed table join, which was never
retrieved at all. An RRF sum is on the order of `0.03`; the overlap ratio is
on the order of `0.4`. Comparing them across classes is meaningless. They may
break ties only inside one class, and they are published so a run can be
audited.

The facet stage must not write its RRF sum into `reranked`. It did until
compiler 0.9.0, which discarded the cross-encoder score `rerank_many` had
already computed and left faceted core evidence ordered by a number roughly a
decimal order of magnitude smaller than the raw scores that keyed joins and
table fragments carry. Every fragment then sorted above every direct hit
irrespective of relevance. Covered by
`test_faceted_core_scores_share_the_reranker_scale_with_fragments` and
`test_table_fragments_stop_displacing_faceted_core_evidence`.

#### What `reranked` holds, per class

One unit is not one meaning. Two classes are never scored on their own text:

| Candidate class | `reranked` | `fused` |
| --- | --- | --- |
| Direct retrieval, faceted, `batched` (default) | cross-encoder score from `rerank_many`, conditioned on the full query or on the facet that found it | facet RRF sum |
| Direct retrieval, faceting off, no facets, or `single_pass` | cross-encoder score against the full query | sparse+dense RRF, or facet RRF under `single_pass` |
| Keyed table join | cross-encoder score against the full query | lexical overlap ratio, `0..1` |
| Oversized-table fragment | cross-encoder score against the full query | inherited from the parent table node |
| Page-neighbor window | cross-encoder score against the full query, shrunk by `page_neighbor_score_penalty ** distance` | parent RRF × penalty |
| Sibling, list neighbor | **the anchor's `reranked`, shrunk by a penalty.** The neighbor's own text is never scored | parent RRF × penalty |

Two consequences follow and are deliberate, not defects to be silently fixed.

**Conditioning is not uniform under the batched facet strategy.**
`retrieve_faceted` keeps the first ranking that produced a candidate, and
ranking 0 is the full query, so a candidate the full query found carries a
full-query score while a candidate reached only through a facet carries that
facet's score. Same model, same unit, different conditioning. A facet is
shorter and more specific than the query it came from, so those scores tend to
read high, and nothing corrects for it; the `query_facet_full_weight` advantage
ranking 0 receives in the RRF sum is the only counterweight, and it acts on
`fused` and on rank, not on `reranked`. Making the conditioning uniform means
scoring facet-only candidates against the full query as well — a second
cross-encoder pass or a wider first one — which is a latency decision, not a
scale fix.

The caveat is narrower than it first appears, and the bound is arithmetic
rather than incidental. Facet-only candidates do arise — pool truncation, not
a failed match, is what produces them, since every facet term is also a query
term — but `retrieve_faceted` then truncates the fused union to `len(ranked)`,
and a facet-only candidate carries no `query_facet_full_weight` credit. With
the default `rrf_k` of 60, a candidate credited by a single facet at rank 1
reaches `1/61 ≈ 0.0164`, while any ranking-0 candidate reaches at least
`2/(60 + rank)`, which stays above `0.03` for any plausible rank. A facet-only
candidate therefore survives the cut only when at least two facets credit it
near rank 1 *and* the ranking-0 candidate it displaces drew no facet credit at
all. No fixture built for the 0.9.0 change produced one, so the published
compiler packets are unlikely to contain facet-conditioned scores today; that
is a bound on exposure, not a guarantee, and it will loosen if
`query_facet_limit` rises.

**Open question (2026-09-22): the structural penalties multiply.** That was
defensible while anchors carried tightly clustered RRF sums, where a 0.9 factor
moved a neighbor a predictable handful of ranks. Since 0.9.0 anchors carry
cross-encoder scores, and a fixed factor on a signed log-odds value states no
policy: `0.5` becomes `0.45` and barely moves, while `10.0` becomes `9.0` and
can still outrank many direct hits, so the displacement depends on local score
spacing. `_penalized_reranker_score` already concedes the point by
special-casing the sign so a negative score is not inverted, and still
multiplies. Task 7 of `docs/plans/2026-09-21-improvement-plan.md` caches
cross-encoder scores per (query, node), which is what would make scoring
neighbor text directly affordable; task 4 owns the resulting ordering policy.
Changing the penalty form moves packets and requires re-running the arms.

### Both channels refuse non-matches

Stage 1 returns only chunks that match at least one query term: a chunk scoring
zero under BM25 carries no lexical evidence, so giving it a rank gave it
reciprocal-rank-fusion credit ordered by chunk ID, which is a hash rather than
relevance.

Stage 2 now applies the same rule. `HybridIndex._dense_search` drops any chunk
whose similarity to the query is not strictly positive before ranking. Vectors
are L2-normalized, so the similarity is a cosine and `<= 0.0` means at or
beyond orthogonal: there is no shared direction to rank on. Previously the
stage sorted every similarity including exactly `0.0` and negative values,
truncated to the candidate limit, and broke ties by chunk ID, so a chunk with
zero similarity collected a dense rank in hash order and the full
`1 / (rrf_k + rank)` credit that rank is worth. Short queries against the
default 256-dimension hash embedding leave most chunks at similarity exactly
`0.0`, so that was the common case rather than a corner.

This was previously recorded here as a known defect held open by a research
question about empty results. That question has been decided, and the
subsections below record both the decision and the measurements it rests on.

#### It cannot fire on a benchmark run

An earlier version of this section claimed that fixing the dense channel moves
published numbers and so must precede any rerun. That claim was not measured,
and it is false. With `BAAI/bge-small-en-v1.5`, the embedder every published
run used, a non-positive similarity does not occur:

- Corpus side. All 31 cached indexes under `artifacts/indexes/` store
  384-dimension unit-normalized vectors. Their exhaustive pairwise cosines --
  3,715,675,587 distinct chunk pairs, including the three 36,294-chunk
  indexes -- contain no value at or below zero. Per-index minima run from
  `+0.1108` to `+0.5028`, and every chunk lies within 19.9 to 64.8 degrees of
  its corpus mean. The vectors occupy a narrow cone, not the whole sphere.
- Query side. The 24 `xldev24` questions, embedded at the pinned revision
  `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` with CLS pooling and L2
  normalization, scored against those stored vectors give 6,928,752
  query-chunk similarities. None is at or below zero; the minimum is `+0.1878`;
  none appears in any top-40. (The reproduction was checked against the stored
  vectors themselves, which it reproduces to approximately `5e-7` -- float32
  precision. An earlier version of this page said `6e-8`; independent
  reproduction reached `4.47e-07`, about seven times looser, which is
  consistent with float32 batch nondeterminism rather than with a disagreement
  about the vectors. The positivity conclusion is unaffected -- the smallest
  similarity involved is `+0.1878`, five orders of magnitude above the
  discrepancy -- but a reader reproducing the work will not hit `6e-8` and
  should not treat missing it as a failure. Read the agreement as float32
  precision, not as a fixed constant.)

The positivity guard on `_dense_search` is therefore inert under the production
embedder: it discards nothing on any run the benchmark has published, and so it
cannot change a published number. This narrows the guard's reach rather than
dismissing it. It is a genuine correctness change -- the code really did hand
rank credit to zero-similarity chunks, and would do so for any embedder whose
vectors are not confined to a positive cone -- but the reachable case today is
the offline `hash-256-v1` model, whose sign-bit vectors leave most chunks at
exactly `0.0` against a short query.

#### Empty retrieval is a legitimate outcome

The guard raises a policy question that only the hash model exposes. BM25
already refuses zero-score chunks; now that the dense channel also refuses
zero-similarity chunks, a query matching nothing in either channel yields no
candidates at all, where it previously yielded hash-ordered non-matches.

**The decision is that empty is correct.** A channel holding no evidence
returns nothing. That is exactly the semantics BM25 has had since its own
guard landed, and the asymmetry between the two channels was the defect, not
the emptiness. No floor is applied. Returning the top-k anyway would reinstate
precisely the hash-ordered credit the guard removes, so it is not a neutral
default; it is the old behavior under a new name. A downstream consumer that
needs a non-empty context must widen its query or its scope, not be handed
chunks the retrieval stack could not justify.

Measured on the committed fixtures, the guard empties 7 of the 20 fixture
(arm, query) pairs -- `fixed`/`metrics`, `fixed`/`growth conclusion`, and
`structural` for `quarterly report`, `metrics`, `methods`, `report highlights`
and `growth conclusion` -- and shortens the `region 42` row of the pinned
ranking table from four results to three, because only three of those chunks
carry any signal in either channel. Each of those 7 pairs previously ranked a
chunk first with sparse and dense scores both exactly `0.0`.

Consequences, audited across the consumers of `retrieve()` and `pack()`:

- `pack()` on an empty ranking yields a valid packet with zero items, zero
  tokens, and its metadata intact. `ContextPacket` permits an empty `items`
  tuple and its budget invariant holds trivially.
- Evidence-page recall for an empty context is `0.0` against annotated gold
  pages, not a vacuous `1.0`. The `1.0` branch in `evaluation/evidence.py` is
  reached only when a question annotates no gold pages at all, which is a
  property of the question and independent of retrieval.
- `tokens_to_full_evidence` is `None` for an empty context **only when the
  question annotates gold pages**, meaning full evidence was never reached, and
  the summary's median skips it. For a question with no gold pages at all,
  `_tokens_to_full` returns `0` before it looks at a single item, so an empty
  context scores a perfect `0` tokens-to-full rather than `None`. That is the
  same vacuity class as `full_evidence_coverage`, and so is `_quote_coverage`,
  which returns `1.0` and `True` for a question carrying no gold quotes. All
  three are properties of the question, not of retrieval, and an arm cannot be
  credited for them; a summary that mixes gold-less questions into these
  averages flatters every arm equally and hides an empty context entirely.
- An empty context can *raise* a metric, not only lower one.
  `insufficient_evidence_correct` is `(not question.answerable) and accuracy ==
  1.0`. An empty evidence section makes "the context does not contain enough
  information" the natural answer, so emptying retrieval pushes the model
  toward exactly the response an unanswerable question scores as correct. An
  arm that retrieves nothing can therefore post a *higher* unanswerable score
  than one that retrieves well, for no retrieval merit at all. Read that metric
  alongside the answerable accuracy and the empty-context count, never alone.
- The compiler arm does not necessarily go empty when the baselines do.
  `expand_candidates`' keyed-table-join path runs off `(query, documents)`
  rather than off `ranked`: `keyed_table_join_candidates` is called with the
  query and the document scope, not with the ranked evidence, so it can emit
  candidates for a query whose sparse and dense channels both returned nothing.
  A query that yields an empty packet on `fixed` and `structural` can yield a
  non-empty compiler packet. That is not a bug on its own -- the join is a
  different retrieval path -- but it means "empty retrieval" is not an
  arm-neutral condition, and a comparison that assumes all arms go empty
  together is wrong.
- Redundancy over zero items is `0.0` by an explicit guard, not a division by
  zero.
- Reports render an empty cell numerically; `n/a` appears only where a metric
  is genuinely undefined for every question in the cell.
- Answer generation receives a prompt with an empty evidence section. A
  grounded answer has nothing it may cite, so its citation validity and
  citation support are `0.0`. This is the existing rule for an empty citation
  list and is the intended reading: an uncited claim is ungrounded whatever
  the reason.

### Fixed defect: the structural arm could not retrieve heading vocabulary

**Status: fixed.** `RetrievalConfig.structural_heading_search_context` defaults
to `True`, and with it `structural_chunks` sets each chunk's `search_text` to
its heading trail joined above the chunk text, exactly as the compiler's
candidates already did. Setting the field to `False` reproduces the pre-fix
behaviour exactly -- `search_text` stays `None` -- so the defect can be ablated
rather than merely described. The rest of this section records what the defect
was, because **every published pre-fix structural number was measured in the
`False` state and carries it.**

**There is one field per heading-bearing unit, and they are independent.**
`structural_chunks` reads `structural_heading_search_context`;
`compiler/candidates.py` reads `compiler_node_heading_search_context`, so
`node_chunks` builds heading-bearing `search_text` only in that field's `True`
position. Both default `True`. The fixed unit reads neither.

The two were briefly one field, `heading_search_context`, so the factorial
could turn heading context off on both heading-bearing units at once and
separate "IR nodes beat structural chunks" from "IR nodes carry heading
context". That ablation has now been run, and it found the factor
**asymmetric**: heading search context costs the compiler's IR-node unit 2 to 5
points of page recall at every budget, while helping structural chunks only at
2K and 4K. The configuration that follows from it is therefore asymmetric too
-- the structural baseline keeps heading access, which it needs to be a fair
baseline, and the compiler stops paying the tax -- and one shared field made
that unreachable. Splitting makes it reachable and nothing more: **no default
moved**, and whether to adopt the asymmetric setting is for the measurement
that follows to decide.

`eval-retrieval` exposes the compiler field as
`--compiler-node-heading-search-context` and
`--no-compiler-node-heading-search-context`, defaulting on. The structural
field has no flag: one `RetrievalConfig` is shared by every arm and by the
compiler, so the asymmetric configuration is reached by turning the compiler
field off and leaving the structural baseline alone. `eval-factorial` exposes neither directly -- its `--heading-context`
factor sets both, see `docs/specs/factorial.md`.

Each field reaches the derived-index key on its own, because `RetrievalConfig`
is part of the index key payload, so a run with either one off can never reuse
an index built with it on;
`test_index_key_separates_both_heading_search_context_fields` asserts all four
combinations are distinct keys. Both the split and the rename before it rekey
every derived index; the pinned literals in
`test_index_key_is_stable_for_a_fixed_revision` were re-derived, not
re-recorded, and the field names are the whole of the difference at each step.

The fix is search-only on both units. `retrieval_text` is `search_text or
text`; the emitted chunk `text`, its `token_count`, provenance and every budget
are byte-identical in both positions of the field, and the fixed and
long-context arms are untouched. **Chunk ids do not move between the two
positions on either unit**: `compiler/candidates.py` derives the node
candidate id from `document.id`, `node.id` and `node.text` alone, and
`_chunk_from_nodes` likewise omits `search_text` from its payload. See
"Removed artifact: the factor used to permute IR candidate ids" below for why
that matters and what it used to do.

This was a separate defect from the channel-positivity work above. It was not
caused by either guard; the guards only made it visible.

Both channels read `RetrievalChunk.retrieval_text`, which is `search_text or
text`. Before the fix, `search_text` was `None` on every `fixed` and
`structural` chunk, so for those two arms the indexed string was the chunk text
alone.

- Arm A (`fixed`) builds its windows by concatenating **every** IR node that
  carries text, in ordinal order, which includes title and heading nodes. Its
  indexed vocabulary is therefore the document's full vocabulary.
- Arm B (`structural`) builds each chunk from `raw_chunk.text` as returned by
  Docling's `HybridChunker`, and keeps the chunker's headings separately as
  `heading_path` metadata. Metadata was never concatenated into anything the
  indexes read, so heading and title strings never entered `retrieval_text` and
  were invisible to BM25, to the dense embedding, and to the reranker alike.

Measured by building both indexes over the committed unit fixture, whose
document has the title `Quarterly Report`, headings `Results` and `Methods`,
and a list group named `Highlights`:

| term | source | `fixed` indexed | `structural`, field off | `structural`, field on |
|---|---|---|---|---|
| `quarterly` | title | yes | no | yes |
| `report` | title | yes | no | yes |
| `results` | heading | yes | no | yes |
| `methods` | heading | yes | no | yes |
| `highlights` | list-group name | yes | no | no |
| `measured` | code body | yes | yes | yes |

`highlights` is the one residual, and it is not a heading: it is an
`IRNodeKind.LIST` group name, which the chunker renders as its items while
dropping the name, so it never enters a heading trail. The compiler arm cannot
reach it either, for its own reason (it skips `IRNodeKind.LIST` groups as
non-evidence). It is a different, smaller gap and is not fixed here.

The consequence of the defect was arm-asymmetric and reached well past the
fixture. A benchmark question phrased in the vocabulary of a section heading --
and questions about document structure naturally are -- was retrievable by the
fixed baseline and structurally unreachable by the structural arm, whatever the
embedder. On the fixture it accounted for three of the seven empty `(arm,
query)` pairs, and one non-empty pair (`structural`/`results revenue`) survived
only on its body term. With the field on, the empty set is four pairs, every
one of them empty on both arms for genuinely absent vocabulary. Any arm
comparison run in the `False` state is biased **in favour of the fixed
baseline** by an amount that has not been measured on the benchmark subsets.

The compiler arm never shared the gap. `compiler/candidates.py` sets
`search_text` via `contextual_search_text` whenever
`compiler_node_heading_search_context` is on, which joins the node's
`heading_path` above its own text (dropping the last heading when it duplicates
the node text, so a heading node is not repeated). That helper now lives in
`retrieval/chunking.py` and is shared by both arms, so they build the same
contextual string; the import direction is `compiler` -> `retrieval`, never the
reverse. Over the fixture, the code node's `search_text` is the three lines
`Quarterly Report`, `Methods`, `print('measured')` for both arms. One further
compiler caveat, distinct from this gap: it skips `content_layer ==
"furniture"` nodes entirely.

**What this means for existing results.** Turning the field on moves every
structural number, so published structural results and the paired deltas
against them cannot be carried across the fix. A rerun must remeasure both
arms; a run that deliberately reproduces the old structural state must set
`structural_heading_search_context=False` and say so. That leaves the
compiler's node candidates alone, which is exactly why the fields are separate:
the old structural state and the old compiler state can be reproduced
independently. Adding the field, renaming it, and splitting it each change
`RetrievalConfig`, which is part of the derived-index key payload, so every
cached index rekeys across the change in either direction -- a stale index is
never reused across it.

**The field moves structural numbers by two independent mechanisms, not one.**
The first is the one described above: heading vocabulary becomes matchable. The
second is dedupe scope. `HybridIndex._unique_by_search_text` dedupes on
`retrieval_text`, and it runs on the sorted fused candidate list *before*
`rerank_limit` is applied. With the field off, two chunks whose body text is
identical under two *different* headings share a dedupe key and collapse into a
single candidate; the second is discarded along with its heading and its
provenance. With the field on the key is the heading trail above the body, so
both survive, both enter the rerank pool, and both consume a rerank slot --
which displaces whatever would otherwise have occupied it. **This operates
independently of heading-vocabulary matching: it changes results for queries
containing no heading term at all**, and it is exercised as such by
`test_heading_context_widens_candidate_dedupe_scope`. The wider scope is the
correct behaviour and is deliberate -- two passages under different headings
are different evidence with different provenance, and it puts the structural
arm on the same footing as the compiler arm, whose candidates have always
carried heading-bearing `search_text`. It is recorded here because an ablation
toggling this one field measures **heading matching plus dedupe scope
together**, and attributing the whole of the resulting delta to matching would
be wrong. Separating the two requires a second ablation that varies the dedupe
key independently of what is indexed; none has been run. The same caveat
applies to the compiler's node candidates now that they read the field: a
single-factor delta there also carries both mechanisms, because
`_unique_by_search_text` reads `retrieval_text` for every unit alike.

**Third mechanism: the factor reaches the packing objective, not only
retrieval.** `compiler/pack.py:124` derives the coverage terms of every
candidate from `candidate.chunk.retrieval_text` and `compiler/pack.py:128`
derives its table references from the same string; both sit in the `prepared`
comprehension that begins at `compiler/pack.py:120`. `retrieval_text` is
`search_text or text`. Turning the factor off therefore removes
heading vocabulary from the *selection objective* of every
`FACETED_COVERAGE` cell on the two heading-bearing units, not merely from what
the indexes match: a heading term in the query stops earning `new_terms`
credit, and coverage picks different evidence for the same ranked pool. This
is a **policy-side** effect of a factor that exists to isolate representation,
and the two cannot be separated through this one field. It is an intrinsic
consequence of `retrieval_text` being the single string the compiler reads
downstream, not an artifact: any candidate whose indexed string differs from
its body genuinely is different evidence to a coverage objective phrased over
indexed terms. The `RANKED` policy never touches `retrieval_text` during
packing, so it does not carry this mechanism. The generated factorial report
mitigates the confusion by printing only `RANKED` cells in its
heading-context bullets, so the printed contrast is clean; the faceted rows of
the summary table are not, and must be read with this in mind.

#### Removed artifact: the factor used to permute IR candidate ids

The node candidate id payload used to embed the *indexed* string --
`search_text` when the factor was on and `node.text` when it was off -- so
toggling the factor permuted every IR chunk id. Chunk ids are deterministic
tie-break sort keys in at least eight places (`retrieval/index.py` at the
candidate, fusion, dedupe, rerank and packing sorts; the fused ordering in
`compiler/facets.py`; and the coverage key in `compiler/pack.py`), so the
permutation changed ranking order, and through order at a fixed budget it
changed which evidence was packed. This is demonstrable with content and
config held fixed: substituting only the heading-on ids into an otherwise
heading-off candidate set reorders the returned top five -- one of four probe
queries on the committed compiler fixture, and independent verification
observed it on three of four of its own probe queries, there also pulling a
page-2 chunk into a previously all-page-1 result. The size of the effect
depends on how often scores tie; that it exists at all is the problem.

The structural unit never had this: `_chunk_from_nodes` builds its id from the
arm, document, ordinal, text and source refs, and has never read
`search_text`. So an IR heading-on/off delta silently carried an
id-permutation effect that the structural delta did not -- **arm-asymmetric
contamination of exactly the IR-versus-structural comparison the factor exists
to enable.** That is why it was an artifact rather than a consequence: it did
not follow from what the factor represents, it followed from an incidental
choice about what went into a hash, and one unit made that choice while the
other did not.

It is now removed. `node_chunks` derives the id from `document.id`, `node.id`
and `node.text` alone, and the payload marker moved from `compiler-node-v2` to
`compiler-node-v3` so that ids produced by the old derivation and the new one
cannot be confused: without a bump the heading-off position would have kept
its old ids unchanged while the heading-on position silently adopted them,
making two differently-derived candidate sets share a namespace. Cache
isolation never depended on the id: each position gets its own
`RetrievalConfig`, which is part of the derived-index key payload, so no
cached index is reused across the factor either way. The property is pinned by
`test_node_candidate_ids_are_identical_across_heading_context` and, at the
factorial-index level, by
`test_heading_context_keeps_ir_chunk_ids_identical_across_positions`.

Changing the derivation moved default-configuration IR numbers, because the
ids it changed are tie-breaks. Over the committed fixtures: all fourteen IR
chunk ids changed while no other chunk field did; IR retrieval returned the
same candidate *set* on every probe query but a different order on three of
six; and compiler evidence ids changed everywhere, because the evidence id
payload embeds the chunk id. Every factorial metric on the committed corpora
was unchanged, and the structural and fixed units were byte-identical. Larger
corpora may move metrics; published IR numbers do not carry across this
change.

**What the packed set did, stated by budget rather than by count.** Packed
content moved on two of the six probe queries, and the packed *set* -- not
merely its order -- changed over contiguous budget bands rather than at a
single budget. On the committed compiler fixture with
`candidate_limit=20, rerank_limit=10`, the query `"target"` packed `Target
revenue increased.` under the old ids and `Context before target.` under the
new ones at **every budget from 7 to 13 tokens**, budgets 8 and 12 included;
from 14 tokens up the same multiset was packed in a different order. The query
`"revenue table"` changed its packed set at budgets **32-34 and 49-69**, where
the heading node `Results` takes the place of `Measurements were audited.`,
and moved order only at 35-48 and from 70 up. The other four probe queries
packed byte-identical content at every budget from 1 to 120. An earlier
statement here that the set changed "at one tight budget" was an artifact of a
sparse budget grid and understated the effect.

**Sparse and dense scores are unchanged; fused values are not.** The channel
scores are functions of text alone, so every sparse score, every dense score
and every reranker score is identical across the two derivations. The fused
value is not a score over text: `retrieval/index.py:317-328` sums
`1 / (rrf_k + rank)` over the per-channel ranks, and `retrieval/index.py:576`
assigns those ranks with the key `(-score, chunk.id)`. Changing an id
therefore re-partitions the ranks *inside* a score tie and changes the fused
sum. On the compiler fixture with the query `"target"`, where all three body
sentences carry the same sparse score, ranks 2 and 3 moved from
`0.03225806451612903` (`2/62`) and `0.031746031746031744` (`2/63`) to
`0.03200204813108039` for both -- `1/62 + 1/63`, the tie-averaged value that
follows from one candidate taking sparse rank 2 with dense rank 3 and the
other the reverse. On `"revenue table"` a fused value likewise moves from
`1/71` to `1/70`. This is a downstream consequence of the id tie-break, not a
change in scoring logic, and **no metric consumes the fused value**: it is a
class-local ordering key and a recorded diagnostic. Since compiler 0.9.0 it is
read at four ordering sites, every one of them comparing candidates within a
single class, per "Which score may order candidates" above: the candidate sort
in `retrieval/index.py:330`, the reranker tie-break in `retrieval/index.py:380`
and `:425`, and the page-neighbor sort in `compiler/expand.py:445`. It is also
part of the rerank cache key at `retrieval/index.py:718`, so a moved fused
value costs a cache miss rather than a changed result. Two other fields follow
it: `retrieve` seeds `RetrievalScores.reranked` with the fused value at
`retrieval/index.py:356`, so that seed moves until a reranker overwrites it,
and the structural penalties at `compiler/expand.py:429` and `:727` scale it.
The compiler's main candidate sort no longer reads it; before 0.9.0 it did,
which is what this paragraph used to record as `compiler/expand.py:293`.
Any earlier statement that retrieval scores were unchanged is false as
written; it holds for the sparse, dense and reranked scores only.

**Blast radius beyond the retrieval arm.** The field is read wherever
`structural_chunks` or `node_chunks` is called with an unpinned
`RetrievalConfig`. That includes `evaluation/factorial.py`, which builds the
`ContentUnit.STRUCTURAL` and `ContentUnit.IR` indexes with no pin, so the
default changes the factorial's structural-unit and IR-unit cells alike.
Published **factorial** structural-unit results, and the unit and policy
comparisons drawn from them, carry the old behaviour exactly as the retrieval
arm's numbers do and cannot be carried across either. The factorial crosses the
factor explicitly as `FactorialConfig.heading_contexts`, which sets **both**
fields from one position so the ablation stays arm-symmetric; see
`docs/specs/factorial.md`.

**Compiler table fragments are protected by an explicit pin, not
automatically.** `compiler/expand.py` builds oversized-table fragments with
`structural_chunks` and pins `structural_heading_search_context=False` at that
one call site. That pin is the whole of the isolation: remove it and table
fragment reranker scores move, and the expanded candidate also keeps a stale
`search_text` -- the heading trail above the *un-rendered* fragment body --
which shadows the rendered `text` for every downstream reader of
`retrieval_text`, including the coverage and table-reference terms in
`compiler/pack.py`. The pin is covered by
`test_table_fragments_pin_structural_heading_search_context_off`. It is a
separate concern from the compiler's node candidates, which read their own
`compiler_node_heading_search_context`: the pin stays in place whatever either
field is set to, so a change moves what the node index matches on and never
what a rendered table fragment carries. Any new `structural_chunks` call site
inside the compiler needs the same pin.

### How much the sparse defect cost each arm

The share of the sparse channel that was noise was measured before the fix,
and it is not the same share in every arm: 6 of 35 sparse ranks were unearned
on the ranking corpus, 15 of 30 on the fixed retrieval fixture, and 15 of 20
on the structural one, where five queries matched no chunk at all and their
whole sparse channel was noise. The arms therefore did not pay equally for the
defect, which is why a rerun has to remeasure the paired deltas rather than
carry the published ones over. These counts come from the committed fixture
corpora, which are small: they establish that the effect differs by arm, not
how large it is on the benchmark subsets.

## Models

The default `hash-256-v1` embedding and `lexical-overlap-v1` reranker are
deterministic, local fallbacks for tests and smoke runs. They avoid model
downloads and make repeated fixture runs byte-stable.

Benchmark runs can select SentenceTransformers models by setting
`RetrievalConfig.embedding_model` and `reranker_model` to model names and
installing the optional dependency. A model name alone names a moving Hugging
Face branch, so a hub-backed model must also be given a pinned revision
(`--embedding-revision` / `--reranker-revision`); loading one without a
revision fails rather than resolving whatever `main` points at.

```shell
uv sync --extra retrieval
```

The revision is not part of `RetrievalConfig`, so a programmatic caller
constructs the adapters itself and passes them to `HybridIndex.build`:

```python
from contextbench.retrieval import (
    RetrievalConfig,
    SentenceTransformerCrossEncoderReranker,
    SentenceTransformerEmbeddingModel,
)

config = RetrievalConfig(
    embedding_model="BAAI/bge-small-en-v1.5",
    reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
)
embedder = SentenceTransformerEmbeddingModel(
    config.embedding_model,
    revision="5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
)
reranker = SentenceTransformerCrossEncoderReranker(
    config.reranker_model,
    revision="233902d25c440f23af6f7d6e94d2946bac0bee0a",
)
```

Each revision must be the commit its own model ID resolved to; both adapters
refuse an empty or missing revision.

The same selected model configuration must be used for Arms A and B. Model
loading is lazy; importing the retrieval package does not make network calls.

## Derived index artifacts

`HybridIndex.build(..., artifacts_root=Path("artifacts"))` writes:

```text
artifacts/indexes/<content-and-config-sha256>/index.json
```

The key includes the arm, IR document IDs, chunk IDs, retrieval configuration,
resolved embedding, reranker, and tokenizer identities and implementation
versions, and the pinned embedding and reranker model revisions. The serialized
artifact includes the same provenance plus canonical chunks and vectors, so a
changed implementation, or the same model ID repinned to different weights,
selects a different derived index path.

Adding the revisions to the key invalidated the existing cache. All 31
indexes under `artifacts/indexes/` were written before the pin, record the two
hub models without a revision, and are now unreachable by key: they must be
rebuilt. That is cache invalidation, not a change in results, but it means the
next run pays full index construction for every arm rather than reusing a warm
cache.

Benchmark evaluation may build a single index per arm over all subset source
documents. `retrieve(..., document_ids=...)` and `pack(..., document_ids=...)`
filter both sparse and dense candidates before fusion and reranking, preventing
evidence from outside a question's declared document scope.

## API

```python
from contextbench.retrieval import HybridIndex, RetrievalArm, RetrievalConfig

index = HybridIndex.build(
    [ir_document],
    arm=RetrievalArm.STRUCTURAL,
    config=RetrievalConfig(),
    source_documents={ir_document.id: docling_document},
    artifacts_root=Path("artifacts"),
    # Omit both to get the offline `hash-256-v1` and `lexical-overlap-v1`
    # fallbacks; hub-backed models are passed in already pinned, as above.
    embedder=embedder,
    reranker=reranker,
)
ranked = index.retrieve("Which region grew?")
packet = index.pack("Which region grew?", token_budget=2048)
```

The packer rejects any output that exceeds the supplied budget as the run
accounts it: the rendered evidence block by default, packed content under
`budget_accounting="content"`. Each packet records both counts. No LLM call is
made by either baseline.
