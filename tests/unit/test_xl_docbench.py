"""Tests for the XL-DocBench normalized adapter."""

from pathlib import Path

import pytest

from contextbench.datasets.base import DatasetIntegrityError
from contextbench.datasets.subsets import load_subset
from contextbench.datasets.xl_docbench import XLDocBenchDataset

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.fixture
def dataset() -> XLDocBenchDataset:
    return XLDocBenchDataset(FIXTURES / "xl_docbench", verify_release=False)


def test_iteration_is_sorted_and_repeatable(dataset: XLDocBenchDataset) -> None:
    first = [question.id for question in dataset.iter_questions()]
    second = [question.id for question in dataset.iter_questions()]

    assert first == [
        "adubench_cross_fixture_001",
        "adubench_single_fixture_002",
    ]
    assert second == first


def test_normalizes_single_document_evidence(dataset: XLDocBenchDataset) -> None:
    question = dataset.get_question("adubench_single_fixture_002")

    assert question.document_ids == ("doc_fixture_001",)
    assert question.gold_answer == "alpha"
    assert question.answerable is True
    assert question.gold_evidence_pages == {"doc_fixture_001": (3,)}
    assert question.gold_evidence[0].items[0].mentioned_elements == ("Table 1",)


def test_normalizes_unanswerable_cross_document_question(
    dataset: XLDocBenchDataset,
) -> None:
    question = dataset.get_question("adubench_cross_fixture_001")

    assert question.document_ids == ("doc_fixture_002", "doc_fixture_003")
    assert question.answerable is False
    assert question.gold_evidence == ()


def test_subset_preserves_committed_order(dataset: XLDocBenchDataset) -> None:
    subset = load_subset(FIXTURES / "xl_fixture_subset.json")

    first = [question.id for question in dataset.iter_subset(subset)]
    second = [question.id for question in dataset.iter_subset(subset)]

    assert first == [
        "adubench_single_fixture_002",
        "adubench_cross_fixture_001",
    ]
    assert second == first


def test_subset_rejects_unknown_question(dataset: XLDocBenchDataset) -> None:
    subset = load_subset(FIXTURES / "xl_fixture_subset.json").model_copy(
        update={"question_ids": ("missing",)}
    )

    with pytest.raises(DatasetIntegrityError, match="unknown question"):
        list(dataset.iter_subset(subset))


def test_committed_xl100_is_unique_and_fixed_size() -> None:
    subset = load_subset(Path("configs/subsets/xl100.json"))

    assert len(subset.question_ids) == 100
    assert len(set(subset.question_ids)) == 100
    assert sum(subset.strata["domains"].values()) == 100


def test_committed_xl10_is_an_explicit_xl100_smoke_subset() -> None:
    xl100 = load_subset(Path("configs/subsets/xl100.json"))
    xl10 = load_subset(Path("configs/subsets/xl10.json"))

    assert len(xl10.question_ids) == 10
    assert len(set(xl10.question_ids)) == 10
    assert set(xl10.question_ids).issubset(xl100.question_ids)
    assert sum(xl10.strata["domains"].values()) == 10
    assert xl10.strata["source_documents"] == 6
    assert xl10.strata["source_pages"] == 718


def test_committed_xldev24_is_balanced_and_disjoint_from_xl100() -> None:
    xl100 = load_subset(Path("configs/subsets/xl100.json"))
    xldev24 = load_subset(Path("configs/subsets/xldev24.json"))

    assert len(xldev24.question_ids) == 24
    assert len(set(xldev24.question_ids)) == 24
    assert set(xldev24.question_ids).isdisjoint(xl100.question_ids)
    assert xldev24.strata["domains"] == {
        "finance_business": 4,
        "legal_regulation": 4,
        "medical_clinical": 4,
        "narrative_literature": 4,
        "scientific_academic": 4,
        "technical_engineering": 4,
    }
    assert xldev24.strata["task_type"] == {
        "single_doc": 24,
        "cross_doc": 0,
    }
    assert xldev24.strata["answerability"] == {
        "answerable": 18,
        "unanswerable": 6,
    }
    assert xldev24.strata["evidence_modality"] == {
        "table_chart_or_image": 6,
        "text_or_no_evidence": 18,
    }
    assert xldev24.strata["source_documents"] == 11
