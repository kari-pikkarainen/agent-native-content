"""Evidence-page and redundancy metrics."""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation

from agent_native_content.datasets.base import BenchmarkQuestion
from agent_native_content.ir.models import IRDocument
from agent_native_content.retrieval.models import ContextItem, ContextPacket


def evaluate_context(
    question: BenchmarkQuestion,
    packet: ContextPacket,
    documents: Mapping[str, IRDocument],
) -> dict[str, object]:
    """Calculate exact page coverage and approximate text redundancy."""
    ir_id_to_dataset_id = {document.id: key for key, document in documents.items()}
    item_pages = [
        _item_pages(item, documents, ir_id_to_dataset_id) for item in packet.items
    ]
    content_verified_item_pages = [
        _content_verified_item_pages(item, documents, ir_id_to_dataset_id)
        for item in packet.items
    ]
    selected = _merge_pages(item_pages)
    content_verified_selected = _merge_pages(content_verified_item_pages)
    gold = {
        document_id: tuple(sorted(set(pages)))
        for document_id, pages in question.gold_evidence_pages.items()
    }
    matched = {
        document_id: tuple(
            sorted(set(pages).intersection(selected.get(document_id, ())))
        )
        for document_id, pages in gold.items()
    }
    gold_count = sum(len(pages) for pages in gold.values())
    matched_count = sum(len(pages) for pages in matched.values())
    recall = matched_count / gold_count if gold_count else 1.0
    full_coverage = matched_count == gold_count
    content_verified_matched = {
        document_id: tuple(
            sorted(
                set(pages).intersection(
                    content_verified_selected.get(document_id, ())
                )
            )
        )
        for document_id, pages in gold.items()
    }
    content_verified_matched_count = sum(
        len(pages) for pages in content_verified_matched.values()
    )
    content_verified_recall = (
        content_verified_matched_count / gold_count if gold_count else 1.0
    )
    quote_count, matched_quote_count, quote_recall, full_quote_coverage = (
        _quote_coverage(question, packet.items)
    )
    return {
        "selected_pages": selected,
        "gold_pages": gold,
        "matched_pages": matched,
        "evidence_page_recall": recall,
        "full_evidence_coverage": full_coverage,
        "content_verified_selected_pages": content_verified_selected,
        "content_verified_matched_pages": content_verified_matched,
        "content_verified_page_recall": content_verified_recall,
        "full_content_verified_coverage": (
            content_verified_matched_count == gold_count
        ),
        "gold_quote_count": quote_count,
        "matched_quote_count": matched_quote_count,
        "evidence_quote_recall": quote_recall,
        "full_quote_coverage": full_quote_coverage,
        "tokens_to_full_evidence": _tokens_to_full(
            packet.items,
            item_pages,
            gold,
        ),
        "redundancy": context_redundancy(packet.items),
        "gold_answer_present": gold_answer_present(question, packet.items),
        "verification_rule": question.verification_rule,
    }


# Verification rules whose gold answer is a number, compared by value.
_NUMERIC_RULES = frozenset({"numeric_tolerance", "percentage_exact"})
# A number as written in running text: digits with optional comma thousands
# separators and an optional decimal part. It must not be glued to a word
# character, a decimal point or a comma on the left, and must not continue
# into a word character or into ".<digit>" / ",<digit>" on the right, so "16"
# does not yield 6, "1,6" (a European decimal) yields nothing, and "6.5" is
# read as 6.5, not as 6. Space-separated thousands ("2 379") are deliberately
# not accepted: in a table row two adjacent numbers look the same.
_NUMBER = re.compile(
    r"(?<![\w.,])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w]|[.,]\d)"
)


def gold_answer_present(
    question: BenchmarkQuestion,
    items: Sequence[ContextItem],
) -> bool | None:
    """Whether the normalised gold answer occurs in a packed item's content.

    A deterministic, retrieval-only proxy for "the context contains the
    answer". No model is involved and nothing is inferred.

    * **Not applicable** (``None``) for an unanswerable question, and for a
      gold answer that is empty or boolean. Not-applicable is never counted as
      a hit or a miss.
    * **Numeric rules** (``numeric_tolerance``, ``percentage_exact``): the gold
      value must equal, as a decimal, some number written in an item. Comma
      thousands separators, trailing zeros and a trailing percent sign are
      tolerated: ``2379`` matches ``2,379`` and ``2379.0``; ``100`` matches
      ``100%``. The rule's own tolerance is *not* applied -- presence asks
      whether the value is written down, not whether an answer near it would
      be scored correct.
    * **Everything else**: the gold answer, normalised with the quote
      normaliser, must occur in an item bounded by non-word characters, so
      ``FIST`` does not match ``FISTULA``.

    The match must fall inside a **single item's content**. The framing is
    never searched, and items are not concatenated, because a join could
    manufacture a match across two unrelated fragments -- the shredded packets
    in ``docs/research-log/gate2-failure-analysis.md`` are exactly where that
    would happen.

    Blind spots, stated so the number is not over-read:

    * **Computed answers are invisible.** An answer the question asks to be
      *derived* -- a sum, a difference, a count -- need not be written
      anywhere. ``adubench_single_000331``'s gold answer 2379 appears in no
      context of any arm, so the metric scores it absent however good the
      evidence.
    * **Short numbers are present by chance.** A gold answer of ``6`` is very
      likely written somewhere in any page-sized packet -- a page number, a
      list index, a table cell. A hit on a small integer is weak evidence.
    * **Presence is not sufficiency.** The value can be present in the wrong
      role, for example as a different year or another row's count.
    """
    if not question.answerable:
        return None
    gold = question.gold_answer
    if gold is None or isinstance(gold, bool):
        return None
    text = str(gold).strip()
    if not text:
        return None
    contents = [_normalize_quote_text(item.content) for item in items]
    if question.verification_rule in _NUMERIC_RULES:
        value = _decimal(text.rstrip("%").strip())
        if value is not None:
            return any(
                _decimal(match.group(0)) == value
                for content in contents
                for match in _NUMBER.finditer(content)
            )
    needle = _normalize_quote_text(text)
    pattern = re.compile(rf"(?<!\w){re.escape(needle)}(?!\w)")
    return any(pattern.search(content) for content in contents)


def _decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None


def _quote_coverage(
    question: BenchmarkQuestion,
    items: Sequence[ContextItem],
) -> tuple[int, int, float, bool]:
    quotes = tuple(
        _normalize_quote_text(item.quote)
        for evidence in question.gold_evidence
        for item in evidence.items
        if item.quote and item.quote.strip()
    )
    if not quotes:
        return 0, 0, 1.0, True
    context = _normalize_quote_text("\n".join(item.content for item in items))
    matched = sum(_quote_matches(quote, context) for quote in quotes)
    return len(quotes), matched, matched / len(quotes), matched == len(quotes)


def _normalize_text(value: str) -> str:
    """Casefold and collapse whitespace.

    Used by the content-verified page path, which compares an IR node's text
    against the emitted item that carries it. Both sides come from the same
    parse, so there is nothing to reconcile and this must stay as it is:
    widening it would move content-verified page recall, which is a different
    metric measuring a different thing.
    """
    return " ".join(value.casefold().split())


# Bumped when the comparison changes, and recorded in every summary, so an
# artifact says how its quote figures were produced. An artifact without the
# field predates it and is v1 by definition.
#
# v3 corrects v2's handling of a quote whose elision marker is leading or
# trailing, and rejects a marker-only quote outright; see ``_quote_matches``.
# A v2 artifact and a v3 artifact can disagree on those quotes and nowhere
# else. v2 artifacts exist and are published, so the name had to change.
QUOTE_MATCH_POLICY = "nfkc-unified-punctuation-ordered-elision-v3"

# Dash, apostrophe, quotation and space variants collapse to one spelling
# each. These are typographic renderings of the same character: a PDF
# extractor and a human annotator routinely disagree about which one a
# document contains, and that disagreement is not evidence about retrieval.
#
# What each could wrongly make match, stated rather than waved past:
#   dashes      -- an en-dash range "1914-18" and a hyphenated compound
#                  become indistinguishable. Both are the same characters to a
#                  reader; no gold quote in the set turns on the difference.
#   apostrophes -- a typographic apostrophe and a prime symbol merge, so a
#                  measurement in feet ("6'") could match a possessive. Only
#                  inside an otherwise-identical span, so the risk is remote.
#   quotes      -- an opening and a closing double quote become the same, so
#                  nested quotation could match with its nesting inverted.
#   spaces      -- a non-breaking space merges with a normal one, which is the
#                  point; it cannot make different words match.
#   invisibles  -- soft hyphens and zero-width joiners are deleted, which can
#                  join a line-broken word. That is the intent; it can also
#                  join two words a document deliberately kept apart, which no
#                  observed quote does.
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_APOSTROPHES = dict.fromkeys(map(ord, "‘’‚‛′ʼ"), "'")
_QUOTATIONS = dict.fromkeys(map(ord, "“”„‟″"), '"')
_SPACES = dict.fromkeys(
    map(ord, "       "), " "
)
_INVISIBLES = dict.fromkeys(map(ord, "​‌‍﻿­"), None)
_QUOTE_TRANSLATION = {
    **_DASHES,
    **_APOSTROPHES,
    **_QUOTATIONS,
    **_SPACES,
    **_INVISIBLES,
}
# An elision marker, either spelling. Normalised to one so that fragment
# splitting does not depend on which the annotator typed. It is deliberately
# *not* deleted: a quote that elides is a quote about non-contiguous text, and
# deleting the marker would silently assert contiguity the annotator denied.
_ELLIPSIS_SPLIT = re.compile(r"\s*\.\s*\.\s*\.\s*")


def _normalize_quote_text(value: str) -> str:
    """Normalise both sides of a gold-quote comparison, identically.

    Deliberately narrow. The comparison exists to decide whether a retrieved
    context contains a passage, and every rule here reconciles a difference in
    how the same characters were *rendered* -- by NFKC compatibility folding,
    or by the variant tables above -- never a difference in what was written.

    Stripping punctuation generally was measured and rejected. It raises
    apparent matches from 19 to 27 of 46 on the development set, but the
    recoveries are not typographic: three are quotes whose trailing ellipsis
    the stripping deletes, one is an annotator writing a colon where the
    document has a line break, one is a table read as prose with its column
    separators removed, and one is a quote carrying punctuation from the
    citation list around it. Those are annotation differences, and counting
    them would make the metric agree with the annotator rather than measure
    the retrieval.
    """
    folded = unicodedata.normalize("NFKC", value)
    folded = folded.replace("…", "...")
    folded = folded.translate(_QUOTE_TRANSLATION)
    return " ".join(folded.casefold().split())


def _quote_fragments(normalized_quote: str) -> tuple[str, ...]:
    """Split a normalised quote on its elision markers."""
    parts = (part.strip() for part in _ELLIPSIS_SPLIT.split(normalized_quote))
    return tuple(fragment for fragment in parts if fragment)


def _quote_matches(normalized_quote: str, normalized_context: str) -> bool:
    """Decide whether a context contains a gold quote.

    A quote without an elision must appear contiguously, exactly as before.

    A quote *with* one is a claim about several passages, and no contiguous
    search can ever satisfy it: as shipped, every elided quote scored zero in
    every arm at every budget, so the metric was reporting the annotator's
    punctuation rather than anything a retriever did. Such a quote is matched
    when all of its fragments are present **and in order**, each after the
    previous one.

    Order is required rather than mere presence. "All fragments somewhere"
    can be satisfied by a context that assembles the pieces from unrelated
    parts of a document, which is precisely the false positive this metric
    cannot afford. The cost is real and is accepted: a packet whose items
    happen to emit the fragments out of document order will not match, so this
    under-reports rather than over-reports.

    The branch is on whether the quote *contains a marker*, not on how many
    fragments it yields. v2 branched on the fragment count, so a quote with a
    leading or trailing ellipsis -- one fragment -- fell through to the
    contiguous test with its ``...`` still attached and could never match,
    contradicting the rule stated above. v3 applies that rule to it.

    A quote made of markers alone has no fragments and never matches. It names
    no text, so there is nothing a retriever could have found; treating it as
    satisfied would score it present in every context. Under v2 it was not
    rejected on principle either: it fell through to ``"..." in context`` and
    matched any context that itself contained an ellipsis.
    """
    if not _ELLIPSIS_SPLIT.search(normalized_quote):
        return normalized_quote in normalized_context
    fragments = _quote_fragments(normalized_quote)
    if not fragments:
        return False
    position = 0
    for fragment in fragments:
        found = normalized_context.find(fragment, position)
        if found < 0:
            return False
        position = found + len(fragment)
    return True


def context_redundancy(items: Sequence[ContextItem], *, ngram_size: int = 4) -> float:
    """Estimate duplicated token share using repeated cross-item word n-grams."""
    total_tokens = 0
    duplicate_positions = 0
    seen_ngrams: set[tuple[str, ...]] = set()
    for item in items:
        terms = re.findall(r"[\w]+", item.content.casefold())
        total_tokens += len(terms)
        duplicated: set[int] = set()
        current: list[tuple[str, ...]] = []
        for start in range(max(len(terms) - ngram_size + 1, 0)):
            ngram = tuple(terms[start : start + ngram_size])
            current.append(ngram)
            if ngram in seen_ngrams:
                duplicated.update(range(start, start + ngram_size))
        duplicate_positions += len(duplicated)
        seen_ngrams.update(current)
    return duplicate_positions / total_tokens if total_tokens else 0.0


def _item_pages(
    item: ContextItem,
    documents: Mapping[str, IRDocument],
    ir_id_to_dataset_id: Mapping[str, str],
) -> dict[str, tuple[int, ...]]:
    dataset_id = ir_id_to_dataset_id[item.document_id]
    document = documents[dataset_id]
    pages = {
        box.page_no
        for node_id in item.source_node_ids
        for box in document.node_by_id[node_id].bounding_boxes
    }
    if not pages and item.page_start is not None and item.page_end is not None:
        pages.update(range(item.page_start, item.page_end + 1))
    return {dataset_id: tuple(sorted(pages))}


def _content_verified_item_pages(
    item: ContextItem,
    documents: Mapping[str, IRDocument],
    ir_id_to_dataset_id: Mapping[str, str],
) -> dict[str, tuple[int, ...]]:
    """Credit pages only when each referenced node's full text is emitted."""
    dataset_id = ir_id_to_dataset_id[item.document_id]
    document = documents[dataset_id]
    normalized_content = _normalize_text(item.content)
    pages: set[int] = set()
    for node_id in item.source_node_ids:
        node = document.node_by_id[node_id]
        node_text = _normalize_text(node.text)
        if not node_text or node_text not in normalized_content:
            continue
        node_pages = {box.page_no for box in node.bounding_boxes}
        if not node_pages and node.page_start is not None and node.page_end is not None:
            node_pages.update(range(node.page_start, node.page_end + 1))
        pages.update(node_pages)
    return {dataset_id: tuple(sorted(pages))}


def _merge_pages(
    values: Sequence[Mapping[str, tuple[int, ...]]],
) -> dict[str, tuple[int, ...]]:
    merged: dict[str, set[int]] = {}
    for value in values:
        for document_id, pages in value.items():
            merged.setdefault(document_id, set()).update(pages)
    return {
        document_id: tuple(sorted(pages))
        for document_id, pages in sorted(merged.items())
    }


def _tokens_to_full(
    items: Sequence[ContextItem],
    item_pages: Sequence[Mapping[str, tuple[int, ...]]],
    gold: Mapping[str, tuple[int, ...]],
) -> int | None:
    remaining = {
        (document_id, page) for document_id, pages in gold.items() for page in pages
    }
    if not remaining:
        return 0
    tokens = 0
    for item, pages_by_document in zip(items, item_pages, strict=True):
        tokens += item.token_count
        for document_id, pages in pages_by_document.items():
            remaining.difference_update((document_id, page) for page in pages)
        if not remaining:
            return tokens
    return None
