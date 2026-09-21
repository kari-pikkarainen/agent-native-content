"""Aggregate and render evidence-only benchmark results."""

import random
import statistics
from collections.abc import Iterable, Sequence

from contextbench.evaluation.models import (
    BenchmarkSystem,
    RetrievalBenchmarkSummary,
    RetrievalEvaluationRecord,
    RetrievalPairedInterval,
    RetrievalSummaryRow,
)


def summarize(
    run_id: str,
    records: Sequence[RetrievalEvaluationRecord],
    *,
    seed: int = 20260919,
    bootstrap_resamples: int = 10_000,
) -> RetrievalBenchmarkSummary:
    rows: list[RetrievalSummaryRow] = []
    cells = sorted({(record.system, record.token_budget) for record in records})
    for system, budget in cells:
        selected = [
            record
            for record in records
            if record.system == system and record.token_budget == budget
        ]
        tokens_to_full = [
            record.tokens_to_full_evidence
            for record in selected
            if record.tokens_to_full_evidence is not None
        ]
        answerable = [record for record in selected if record.answerable]
        quoted = [record for record in selected if record.gold_quote_count > 0]
        rows.append(
            RetrievalSummaryRow(
                system=system,
                token_budget=budget,
                question_count=len(selected),
                mean_evidence_page_recall=statistics.fmean(
                    record.evidence_page_recall for record in selected
                ),
                full_evidence_coverage_rate=statistics.fmean(
                    float(record.full_evidence_coverage) for record in selected
                ),
                mean_evidence_quote_recall=statistics.fmean(
                    record.evidence_quote_recall for record in selected
                ),
                full_quote_coverage_rate=statistics.fmean(
                    float(record.full_quote_coverage) for record in selected
                ),
                mean_context_tokens=statistics.fmean(
                    record.token_count for record in selected
                ),
                median_context_tokens=statistics.median(
                    record.token_count for record in selected
                ),
                median_tokens_to_full_evidence=(
                    statistics.median(tokens_to_full) if tokens_to_full else None
                ),
                mean_redundancy=statistics.fmean(
                    record.redundancy for record in selected
                ),
                mean_retrieval_latency_ms=statistics.fmean(
                    record.retrieval_latency_ms for record in selected
                ),
                answerable_question_count=len(answerable),
                quoted_question_count=len(quoted),
                answerable_mean_evidence_page_recall=_mean_or_none(
                    record.evidence_page_recall for record in answerable
                ),
                answerable_full_evidence_coverage_rate=_mean_or_none(
                    float(record.full_evidence_coverage) for record in answerable
                ),
                answerable_mean_content_verified_page_recall=_mean_or_none(
                    record.content_verified_page_recall for record in answerable
                ),
                answerable_full_content_verified_coverage_rate=_mean_or_none(
                    float(record.full_content_verified_coverage)
                    for record in answerable
                ),
                quoted_mean_evidence_quote_recall=_mean_or_none(
                    record.evidence_quote_recall for record in quoted
                ),
                quoted_full_quote_coverage_rate=_mean_or_none(
                    float(record.full_quote_coverage) for record in quoted
                ),
            )
        )
    return RetrievalBenchmarkSummary(
        run_id=run_id,
        rows=tuple(rows),
        paired_intervals=_paired_intervals(
            records,
            seed=seed,
            bootstrap_resamples=bootstrap_resamples,
        ),
    )


def _mean_or_none(values: Iterable[float]) -> float | None:
    materialized = list(values)
    return statistics.fmean(materialized) if materialized else None


def _paired_intervals(
    records: Sequence[RetrievalEvaluationRecord],
    *,
    seed: int,
    bootstrap_resamples: int,
) -> tuple[RetrievalPairedInterval, ...]:
    intervals: list[RetrievalPairedInterval] = []
    budgets = sorted({record.token_budget for record in records})
    metrics = (
        ("answerable_page_recall", "evidence_page_recall", "answerable"),
        (
            "answerable_content_verified_page_recall",
            "content_verified_page_recall",
            "answerable",
        ),
        ("quoted_exact_quote_recall", "evidence_quote_recall", "quoted"),
    )
    for budget in budgets:
        for baseline in (BenchmarkSystem.FIXED, BenchmarkSystem.STRUCTURAL):
            for metric, field, eligibility in metrics:
                pairs = _paired_values(
                    records,
                    budget=budget,
                    baseline=baseline,
                    field=field,
                    eligibility=eligibility,
                )
                if not pairs:
                    continue
                deltas = [treatment - control for _, treatment, control in pairs]
                by_cluster: dict[tuple[str, ...], list[float]] = {}
                for cluster, treatment, control in pairs:
                    by_cluster.setdefault(cluster, []).append(treatment - control)
                bootstrap = _cluster_bootstrap(
                    by_cluster,
                    resamples=bootstrap_resamples,
                    seed=f"{seed}:{budget}:{baseline.value}:{metric}",
                )
                intervals.append(
                    RetrievalPairedInterval(
                        treatment=BenchmarkSystem.COMPILER,
                        baseline=baseline,
                        token_budget=budget,
                        metric=metric,
                        eligible_question_count=len(deltas),
                        source_cluster_count=len(by_cluster),
                        mean_delta=statistics.fmean(deltas),
                        ci95_low=_percentile(bootstrap, 0.025),
                        ci95_high=_percentile(bootstrap, 0.975),
                        bootstrap_resamples=bootstrap_resamples,
                    )
                )
    return tuple(intervals)


def _paired_values(
    records: Sequence[RetrievalEvaluationRecord],
    *,
    budget: int,
    baseline: BenchmarkSystem,
    field: str,
    eligibility: str,
) -> list[tuple[tuple[str, ...], float, float]]:
    cells = {
        (record.question_id, record.system): record
        for record in records
        if record.token_budget == budget
    }
    question_ids = sorted(
        question_id
        for question_id, system in cells
        if system == BenchmarkSystem.COMPILER
    )
    pairs: list[tuple[tuple[str, ...], float, float]] = []
    for question_id in question_ids:
        treatment = cells[(question_id, BenchmarkSystem.COMPILER)]
        control = cells.get((question_id, baseline))
        if control is None:
            continue
        if eligibility == "answerable" and not treatment.answerable:
            continue
        if eligibility == "quoted" and treatment.gold_quote_count == 0:
            continue
        cluster = treatment.document_ids or (question_id,)
        pairs.append(
            (
                tuple(sorted(cluster)),
                float(getattr(treatment, field)),
                float(getattr(control, field)),
            )
        )
    return pairs


def _cluster_bootstrap(
    by_cluster: dict[tuple[str, ...], list[float]],
    *,
    resamples: int,
    seed: str,
) -> list[float]:
    randomizer = random.Random(seed)
    clusters = sorted(by_cluster)
    samples: list[float] = []
    for _ in range(resamples):
        values = [
            value
            for _sample in range(len(clusters))
            for value in by_cluster[randomizer.choice(clusters)]
        ]
        samples.append(statistics.fmean(values))
    return sorted(samples)


def _percentile(values: Sequence[float], probability: float) -> float:
    index = round((len(values) - 1) * probability)
    return values[index]


def markdown_report(summary: RetrievalBenchmarkSummary) -> str:
    """Render a compact comparison and evidence-only decision gate."""
    lines = [
        f"# Retrieval Decision Report: {summary.run_id}",
        "",
        "No answer-generation model was used in this run.",
        "",
        "| System | Budget | Page recall | Full pages | Quote recall | "
        "Full quotes | Mean tokens | Median tokens-to-full | Redundancy | "
        "Latency (ms) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summary.rows:
        tokens_to_full = (
            f"{row.median_tokens_to_full_evidence:.1f}"
            if row.median_tokens_to_full_evidence is not None
            else "n/a"
        )
        lines.append(
            f"| {row.system.value} | {row.token_budget} | "
            f"{row.mean_evidence_page_recall:.3f} | "
            f"{row.full_evidence_coverage_rate:.3f} | "
            f"{row.mean_evidence_quote_recall:.3f} | "
            f"{row.full_quote_coverage_rate:.3f} | "
            f"{row.mean_context_tokens:.1f} | {tokens_to_full} | "
            f"{row.mean_redundancy:.3f} | "
            f"{row.mean_retrieval_latency_ms:.2f} |"
        )
    lines.extend(["", "## Evidence-only decision gate", ""])
    for budget in sorted({row.token_budget for row in summary.rows}):
        by_system = {
            row.system: row for row in summary.rows if row.token_budget == budget
        }
        compiler = by_system.get(BenchmarkSystem.COMPILER)
        structural = by_system.get(BenchmarkSystem.STRUCTURAL)
        fixed = by_system.get(BenchmarkSystem.FIXED)
        if compiler is None:
            continue
        best_baseline = max(
            (row for row in (fixed, structural) if row is not None),
            key=lambda row: (
                row.full_evidence_coverage_rate,
                row.mean_evidence_page_recall,
            ),
            default=None,
        )
        if best_baseline is None:
            continue
        coverage_delta = (
            compiler.full_evidence_coverage_rate
            - best_baseline.full_evidence_coverage_rate
        )
        recall_delta = (
            compiler.mean_evidence_page_recall - best_baseline.mean_evidence_page_recall
        )
        lines.append(
            f"- {budget} tokens: compiler vs best baseline: "
            f"{coverage_delta:+.3f} full-coverage, {recall_delta:+.3f} recall."
        )
    lines.extend(
        [
            "",
            "## Audited metrics",
            "",
            "Unanswerable questions are excluded from page metrics below. Quote "
            "metrics include only questions with a non-empty gold quote. Content-"
            "verified pages require the full normalized source-node text to be "
            "present in the emitted context.",
            "",
            "| System | Budget | Answerable n | Page recall | Content-verified "
            "recall | Quoted n | Exact quote recall |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in summary.rows:
        lines.append(
            f"| {row.system.value} | {row.token_budget} | "
            f"{row.answerable_question_count} | "
            f"{_metric(row.answerable_mean_evidence_page_recall)} | "
            f"{_metric(row.answerable_mean_content_verified_page_recall)} | "
            f"{row.quoted_question_count} | "
            f"{_metric(row.quoted_mean_evidence_quote_recall)} |"
        )
    lines.extend(
        [
            "",
            "## Paired source-cluster bootstrap",
            "",
            "Intervals are descriptive 95% paired bootstrap intervals. The "
            "sampling unit is the sorted source-document scope; 10,000 "
            "resamples are used by default.",
            "",
            "| Treatment | Baseline | Budget | Metric | n | Clusters | Delta | "
            "95% interval |",
            "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for interval in summary.paired_intervals:
        lines.append(
            f"| {interval.treatment.value} | {interval.baseline.value} | "
            f"{interval.token_budget} | {interval.metric} | "
            f"{interval.eligible_question_count} | "
            f"{interval.source_cluster_count} | {interval.mean_delta:+.3f} | "
            f"[{interval.ci95_low:+.3f}, {interval.ci95_high:+.3f}] |"
        )
    lines.extend(
        [
            "",
            "Review the recall/coverage curve before generation work. This report "
            "does not establish answer accuracy or the broader technical thesis.",
            "",
        ]
    )
    return "\n".join(lines)


def _metric(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "n/a"
