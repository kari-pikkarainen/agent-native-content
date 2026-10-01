# Contributing to Agent-Native Content

Agent-Native Content is a falsification-oriented research project. Contributions
should make the central hypothesis easier to test, extend the content model in
a source-grounded way, or improve reproducibility without weakening controls.

## Start here

1. Work through [Getting started](docs/getting-started.md), then read the
   [vision](docs/vision.md), [architecture](docs/architecture.md), and
   [evaluation protocol](docs/specs/evaluation.md).
2. Open an issue before a large schema, benchmark, or architecture change.
3. Keep changes focused and include tests for behavioral changes.
4. Run the required checks before submitting a pull request.

```shell
uv sync --extra retrieval
uv run --frozen ruff check .
uv run --frozen pytest -q
```

Tests must remain offline and use committed fixtures or verified local caches.

Unless explicitly stated otherwise, contributions submitted for inclusion are
licensed under the project's [Apache License 2.0](LICENSE), as described in
Section 5 of that license.

## Developer Certificate of Origin

Every commit in a pull request must carry a `Signed-off-by` line certifying the
[Developer Certificate of Origin 1.1](DCO). This confirms that the contributor
has the right to submit the work under the project's license; it is not a
copyright assignment or a contributor license agreement.

Create the sign-off with Git's `-s` option:

```shell
git commit -s -m "Describe the change"
```

Use your real name and an email address you are comfortable recording in the
public Git history. Maintainers may ask contributors to amend commits that lack
the sign-off.

## Research integrity

- Never change released gold labels or question answers.
- Do not tune on a holdout and continue describing it as independent.
- Keep models, prompts, and scoring comparable across benchmark arms.
- Record the dataset population, Git SHA, configuration, and model identities.
- Preserve source provenance and enforce configured token budgets exactly.
- Label diagnostics, development results, ablations, and holdouts explicitly.
- Report regressions and negative results alongside improvements.

## Adding a content format

A decoder must retain immutable source identity, stable node identity,
structure, ordering, and location-level provenance. Derived summaries,
embeddings, and agent features belong outside the canonical intermediate representation (IR). Include a small
fixture and round-trip or provenance tests.

## Publishing results

Generated runs belong under ignored `artifacts/` paths. Propose a result for
`results/` only when it supports a public project claim. Publish compact
reports, summaries, and manifests; do not commit source documents, embeddings,
indexes, or rendered contexts that reproduce source material.
