"""Release-dependent tests for the XL-DocBench holdout subsets.

These tests read the XL-DocBench release under ``data/raw/xl-docbench``, which
is not committed to the repository. They are skipped when the release is
absent so the unit suite stays runnable from a bare checkout.
"""

from pathlib import Path

import pytest

from contextbench.datasets.subsets import load_subset
from contextbench.datasets.xl_docbench import XLDocBenchDataset

RELEASE = Path(__file__).resolve().parents[2] / "data" / "raw" / "xl-docbench"

pytestmark = pytest.mark.skipif(
    not (RELEASE / "manifest.json").is_file(),
    reason="XL-DocBench release not present",
)


def _subset(name: str) -> Path:
    """Resolve a committed subset file relative to the repository root."""
    return RELEASE.parents[2] / "benchmarks" / "xl-docbench" / "subsets" / name


def test_second_holdout_is_balanced_and_document_fresh() -> None:
    dataset = XLDocBenchDataset(RELEASE)
    xl100 = load_subset(_subset("xl100.json"))
    second = load_subset(_subset("xlholdout6b.json"))
    prior = [
        load_subset(_subset("xl10.json")),
        load_subset(_subset("xldev24.json")),
        load_subset(_subset("xlholdout6.json")),
    ]
    prior_documents = {
        document_id
        for subset in prior
        for question_id in subset.question_ids
        for document_id in dataset.get_question(question_id).document_ids
    }
    second_documents = {
        document_id
        for question_id in second.question_ids
        for document_id in dataset.get_question(question_id).document_ids
    }

    assert len(second.question_ids) == 6
    assert set(second.question_ids).issubset(xl100.question_ids)
    assert second.strata["purpose"] == "second_directional_holdout_not_final_claims"
    assert second.strata["domains"] == {
        "finance_business": 1,
        "legal_regulation": 1,
        "medical_clinical": 1,
        "narrative_literature": 1,
        "scientific_academic": 1,
        "technical_engineering": 1,
    }
    assert second_documents.isdisjoint(prior_documents)
    assert second_documents == set(second.strata["source_document_ids"])
    assert second.strata["source_pages"] == 838


def test_third_holdout_is_balanced_and_document_fresh() -> None:
    dataset = XLDocBenchDataset(RELEASE)
    xl100 = load_subset(_subset("xl100.json"))
    third = load_subset(_subset("xlholdout6c.json"))
    prior = [
        load_subset(_subset("xl10.json")),
        load_subset(_subset("xldev24.json")),
        load_subset(_subset("xlholdout6.json")),
        load_subset(_subset("xlholdout6b.json")),
    ]
    prior_documents = {
        document_id
        for subset in prior
        for question_id in subset.question_ids
        for document_id in dataset.get_question(question_id).document_ids
    }
    questions = [
        dataset.get_question(question_id) for question_id in third.question_ids
    ]
    third_documents = {
        document_id for question in questions for document_id in question.document_ids
    }

    # The question ids are the freeze. Everything else here describes them, so
    # pin them literally: without this a swap within a document -- the same
    # document, the same modality, the same page and byte totals -- would pass
    # every other assertion in this test.
    assert tuple(third.question_ids) == (
        "adubench_single_000181",
        "adubench_single_001173",
        "adubench_single_000826",
        "adubench_single_000331",
        "adubench_single_000255",
        "adubench_single_001346",
    )
    assert len(third.question_ids) == 6
    assert set(third.question_ids).issubset(xl100.question_ids)
    assert third.strata["purpose"] == "gate1_screening_holdout_not_final_claims"
    assert third.strata["evidence_modality"] == {
        "table_chart_or_image": 1,
        "text_or_no_evidence": 5,
    }
    assert third.strata["source_documents"] == 6
    assert third.strata["domains"] == {
        "finance_business": 1,
        "legal_regulation": 1,
        "medical_clinical": 1,
        "narrative_literature": 1,
        "scientific_academic": 1,
        "technical_engineering": 1,
    }
    assert all(question.task_type == "single_doc" for question in questions)
    assert all(question.answerable for question in questions)
    assert len(prior_documents) == 28
    assert third_documents.isdisjoint(prior_documents)
    assert third_documents == set(third.strata["source_document_ids"])
    assert len(third.strata["source_document_ids"]) == 6
    documents = [
        dataset.get_document(document_id)
        for document_id in third.strata["source_document_ids"]
    ]
    assert [document.domain for document in documents] == [
        "finance_business",
        "legal_regulation",
        "medical_clinical",
        "narrative_literature",
        "scientific_academic",
        "technical_engineering",
    ]
    assert third.strata["source_pages"] == sum(
        document.page_count for document in documents
    )
    assert third.strata["source_bytes"] == sum(
        document.file_size_bytes for document in documents
    )
    assert third.strata["source_pages"] == 1265
    assert third.strata["source_bytes"] == 102483132
