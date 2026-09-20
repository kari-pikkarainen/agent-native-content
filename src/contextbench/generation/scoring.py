"""Deterministic XL-DocBench-compatible answer scoring."""

import re

from contextbench.datasets.base import BenchmarkQuestion


def normalize_answer(text: str) -> str:
    """Normalize a short benchmark answer."""
    normalized = text.strip().lower()
    for prefix in ("the answer is", "answer:", "answer is"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
    normalized = re.sub(r"[^\w\s\.\-\%]", "", normalized)
    normalized = re.sub(r"\b(a|an|the)\b", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def answer_type(question: BenchmarkQuestion) -> str:
    """Map released format/rule metadata to the native evaluator type."""
    if not question.answerable or question.answer_format == "None":
        return "unanswerable"
    if question.verification_rule == "choice_exact_match":
        return "single_choice"
    if question.verification_rule == "percentage_exact":
        return "percentage"
    if question.answer_format in {"Int", "Float"} or any(
        marker in question.verification_rule for marker in ("numeric", "tolerance")
    ):
        return "numeric"
    if question.answer_format in {"Bool", "Boolean"}:
        return "boolean"
    return "entity"


def accuracy_score(prediction: str, gold: str, kind: str) -> float:
    """Compute the benchmark's relaxed rule-based accuracy."""
    prediction_norm = normalize_answer(prediction)
    gold_norm = normalize_answer(gold)
    if kind == "unanswerable":
        phrases = (
            "not answerable",
            "unanswerable",
            "cannot be determined",
            "cannot be answered",
            "not enough information",
            "insufficient_evidence",
        )
        return float(any(phrase in prediction_norm for phrase in phrases))
    if kind == "boolean":
        prediction_bool = _parse_boolean(prediction)
        gold_bool = _parse_boolean(gold)
        return float(prediction_bool is not None and prediction_bool == gold_bool)
    if kind in {"numeric", "percentage"}:
        prediction_number = _extract_number(prediction)
        gold_number = _extract_number(gold)
        if prediction_number is None or gold_number is None:
            return 0.0
        if gold_number == 0:
            return float(abs(prediction_number) < 1e-6)
        return float(abs(prediction_number - gold_number) / abs(gold_number) <= 0.05)
    if kind == "single_choice":
        prediction_option = re.search(r"\b([A-D])\b", prediction.strip().upper())
        gold_option = re.search(r"\b([A-D])\b", gold.strip().upper())
        if prediction_option is None or gold_option is None:
            return 0.0
        return float(prediction_option.group(1) == gold_option.group(1))
    if gold_norm and gold_norm in prediction_norm:
        return 1.0
    return float(normalized_levenshtein_similarity(prediction_norm, gold_norm) >= 0.8)


def token_f1_score(prediction: str, gold: str) -> float:
    """Compute bag-of-token F1 using the benchmark normalization."""
    prediction_tokens = set(normalize_answer(prediction).split())
    gold_tokens = set(normalize_answer(gold).split())
    if not gold_tokens:
        return float(not prediction_tokens)
    if not prediction_tokens:
        return 0.0
    overlap = len(prediction_tokens & gold_tokens)
    if not overlap:
        return 0.0
    precision = overlap / len(prediction_tokens)
    recall = overlap / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


def anls_score(prediction: str, gold: str, *, threshold: float = 0.5) -> float:
    """Return average normalized Levenshtein similarity with cutoff."""
    similarity = normalized_levenshtein_similarity(prediction, gold)
    return similarity if similarity >= threshold else 0.0


def normalized_levenshtein_similarity(left: str, right: str) -> float:
    left = left.strip().lower()
    right = right.strip().lower()
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return 1.0 - _levenshtein_distance(left, right) / max(len(left), len(right))


def _levenshtein_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        return _levenshtein_distance(right, left)
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left):
        current = [left_index + 1]
        for right_index, right_char in enumerate(right):
            current.append(
                min(
                    current[right_index] + 1,
                    previous[right_index + 1] + 1,
                    previous[right_index] + int(left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def _parse_boolean(text: str) -> bool | None:
    tokens = set(normalize_answer(text).split())
    positive = bool(tokens & {"yes", "true", "correct"})
    negative = bool(tokens & {"no", "false", "incorrect"})
    if positive == negative:
        return None
    return positive


def _extract_number(text: str) -> float | None:
    compact = text.replace(" ", "")
    power = re.search(
        r"(?P<base>[-+]?(?:\d+(?:\.\d+)?|\.\d+))\^(?P<exponent>[-+]?\d+)",
        compact,
    )
    if power:
        try:
            return float(power.group("base")) ** int(power.group("exponent"))
        except (OverflowError, ValueError):
            return None
    fraction = re.search(
        r"(?P<numerator>[-+]?(?:\d+(?:\.\d+)?|\.\d+))/"
        r"(?P<denominator>[-+]?(?:\d+(?:\.\d+)?|\.\d+))",
        compact,
    )
    if fraction:
        denominator = float(fraction.group("denominator"))
        if denominator == 0:
            return None
        return float(fraction.group("numerator")) / denominator
    match = re.search(
        r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?|\.\d+)"
        r"(?:[eE][-+]?\d+)?",
        compact,
    )
    if not match:
        return None
    token = match.group()
    if "," in token and "." not in token:
        integer, fractional = token.split(",", maxsplit=1)
        token = (
            f"{integer}.{fractional}"
            if len(fractional) <= 2
            else token.replace(",", "")
        )
    else:
        token = token.replace(",", "")
    try:
        return float(token)
    except ValueError:
        return None
