"""Aggregate and render evidence-only benchmark results."""

import statistics
from collections.abc import Sequence

from contextbench.evaluation.models import (
    BenchmarkSystem,
    RetrievalBenchmarkSummary,
    RetrievalEvaluationRecord,
    RetrievalSummaryRow,
)


def summarize(
    run_id: str,
    records: Sequence[RetrievalEvaluationRecord],
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
            )
        )
    return RetrievalBenchmarkSummary(run_id=run_id, rows=tuple(rows))


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
            "Review the recall/coverage curve before generation work. This report "
            "does not establish answer accuracy or the broader technical thesis.",
            "",
        ]
    )
    return "\n".join(lines)
