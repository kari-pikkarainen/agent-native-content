# Documentation

Pick the entry that matches what you want to do.

## Use it

- [Getting started](getting-started.md): install, run the smoke experiment,
  read a report, parse your own PDF, build an agent bundle, run offline, and
  the opt-in answer-generation commands.

## Judge it

- [Status and decision history](status.md): the full account of what has been
  measured, what passed, what failed, and the current decision.
- [Canonical results](../results/README.md): the compact published evidence,
  with current and superseded rows kept apart.
- [Research log](research-log/README.md): every diagnostic, ablation and gate
  decision, each pinned to a commit. Its "start here" list is the
  authoritative chain.

## Understand it

- [Vision](vision.md): the broader idea beyond the current prototype.
- [Architecture](architecture.md): implemented boundaries and data flow.
- Specifications, in reading order:
  - [Benchmark and research questions](specs/benchmark.md), with its
    [original build brief](specs/history/original-build-brief.md) kept for
    the record
  - [Content IR (intermediate representation)](specs/content-ir.md)
  - [Retrieval baselines](specs/retrieval.md)
  - [Context compiler](specs/context-compiler.md)
  - [Content-unit × selection-policy factorial](specs/factorial.md)
  - [Evaluation protocol](specs/evaluation.md)
  - [Agent-ready content bundle](specs/agent-document.md)
- [Architecture decision records](adr/README.md): durable technical choices.

## Extend it

- [Roadmap](roadmap.md): the gates passed and failed, and what comes next.
- [Improvement plan](plans/2026-09-21-improvement-plan.md): the phased plan
  the gates come from, with its status.
- [Device-side preparation plan](plans/2026-10-01-device-side-preparation-plan.md):
  the enhancements that make the prepare-at-creation idea testable.
- [Contributing](../CONTRIBUTING.md): research-integrity rules, required
  checks, and the Developer Certificate of Origin.
