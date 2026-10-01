"""Deterministic XL-DocBench-compatible answer scoring.

This module *targets* the released XL-DocBench deterministic evaluator. The
released evaluator has never been executed or read here: the pinned release on
disk carries only ``manifest.json`` and ``data/*.jsonl``. The manifest names
evaluator artifacts (``release_files.per_question_scores``,
``release_files.score_summary``, ``score_evaluator_sha256``) that are not
downloaded, and no evaluator code is vendored in this repository. The mapping
below is therefore **unverified** against the reference implementation.

Known deviations and unverified assumptions are enumerated in
``docs/specs/evaluation.md`` under "Released rule mapping and deviations".
Do not change a predicate here without updating that table: these functions
produce published benchmark numbers.
"""

import re

from agent_native_content.datasets.base import BenchmarkQuestion

RELEASED_VERIFICATION_RULES = frozenset(
    {
        "casefold_exact_match",
        "choice_exact_match",
        "exact_match",
        "numeric_tolerance",
        "percentage_exact",
    }
)
"""Every ``answer.verification_rule`` observed in release ``xldocbench_strict_1345_v1``.

Counts over the 1345 released rows: ``casefold_exact_match`` 822,
``numeric_tolerance`` 276, ``exact_match`` 188, ``percentage_exact`` 43,
``choice_exact_match`` 16.

This constant documents the closed set :func:`answer_type` was written against.
It is deliberately *not* consulted at runtime: :func:`answer_type` must keep
scoring whatever a future release hands it rather than raising mid-benchmark.

The test suite only asserts that this constant and a literal table in
``tests/unit/test_generation.py`` name the same rules. Both are literals in
this repository: no test reads a ``verification_rule`` from the release, and
none can, since ``data/raw/**`` is git-ignored and unit tests must not read
``data/**``. A rule first appearing in a future release is therefore unreviewed
*and* undetected, and may take a wrong path silently -- notably any rule
containing ``"tolerance"`` or ``"numeric"``, which is routed to the numeric path
by substring test.
"""

NUMERIC_RELATIVE_TOLERANCE = 0.05
"""Relative tolerance applied to the ``numeric`` and ``percentage`` paths.

**This value has no source in the release.** Every released ``answer`` object
contains exactly ``format``, ``value``, and ``verification_rule`` -- there is no
per-question tolerance parameter, and the reference evaluator's tolerance is
unknown. 5% is a local assumption, pending an evaluator fetch.
"""


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
    """Map released format/rule metadata to the native evaluator type.

    Over release ``xldocbench_strict_1345_v1`` this yields entity 822,
    numeric 276, unanswerable 188, percentage 43, single_choice 16.

    The unanswerable guard runs **first**, before any rule dispatch. All 188
    ``exact_match`` rows carry ``format == "None"`` and
    ``metadata.is_unanswerable == true``, so ``exact_match`` never reaches the
    relaxed entity path; the entity path is reached only by the 822
    ``casefold_exact_match`` rows.

    The ``boolean`` branch is dead for this release: no released row has a
    ``Bool`` format. It is retained for datasets that do.

    Numeric routing uses a **substring** test on the rule name, so an unseen
    rule containing ``"numeric"`` or ``"tolerance"`` would silently take the
    numeric path. See :data:`RELEASED_VERIFICATION_RULES`.
    """
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
    """Compute the benchmark's relaxed rule-based accuracy.

    Relaxed relative to the released rule names, in ways that are unverified
    against the reference evaluator:

    - ``unanswerable`` is a phrase-substring test over a hardcoded phrase list,
      not a structured abstention check. Any answer containing one of those
      phrases scores 1.0 regardless of the rest of its content.
    - ``numeric`` and ``percentage`` share one relative tolerance
      (:data:`NUMERIC_RELATIVE_TOLERANCE`), despite the released rule being
      named ``percentage_exact``.
    - ``entity`` (the fallback, reached by ``casefold_exact_match``) accepts a
      *non-empty* gold-in-prediction substring hit *or* a Levenshtein ratio
      >= 0.8, which is laxer than a casefolded exact match. An empty normalized
      gold skips the substring branch and is decided by Levenshtein alone.
    - ``single_choice`` compares the **first** standalone ``A``-``D`` token of
      the raw uppercased prediction with that of the gold, so surrounding prose
      can produce both false negatives and false positives, and an option
      letter beyond ``D`` scores 0.0.
    - ``numeric`` and ``percentage`` compare whatever :func:`_extract_number`
      finds: the first number *anywhere* in the text, with magnitude words and
      ``%`` dropped.
    - An unrecognized ``kind`` falls through to the entity path.

    See "Released rule mapping and deviations" in ``docs/specs/evaluation.md``.
    """
    prediction_norm = normalize_answer(prediction)
    gold_norm = normalize_answer(gold)
    if kind == "unanswerable":
        # Substring match, not structured abstention: a prediction that asserts
        # an answer *and* contains one of these phrases still scores 1.0.
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
        relative_error = abs(prediction_number - gold_number) / abs(gold_number)
        return float(relative_error <= NUMERIC_RELATIVE_TOLERANCE)
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
