"""The one canonical rendering of packed evidence, and what it costs.

The answer prompt shows evidence to a model as

    <evidence id="{evidence_id}">
    {content}
    </evidence>

with items joined by a blank line. Before this module that rendering lived only
in the generation runner, while every packer counted content tokens alone, so
the budget never saw the framing. On a poorly parsed document the compiler
packed 500 items at a median of 6 tokens: 3,772 packed tokens at a nominal 4K
budget became a 28,954-token prompt (``docs/research-log/gate2-failure-analysis.md``).

Generation and budget accounting both call this module, so they cannot drift.

Only the variable, system-dependent part is rendered here: the evidence tags,
the IDs, the joiners and the content. The question and the fixed system
instructions are identical across arms and are not part of the evidence
budget.
"""

from collections.abc import Iterable, Sequence
from typing import Literal, Protocol

EVIDENCE_JOINER = "\n\n"

BudgetAccounting = Literal["rendered_evidence", "content"]
# The owner's decision: the budget counts the rendered evidence block. Content
# accounting stays reachable so a re-baseline can measure the change.
DEFAULT_BUDGET_ACCOUNTING: BudgetAccounting = "rendered_evidence"

# How an item's label is written inside ``id="..."``. Nothing else about the
# rendering differs between versions.
#
# * ``evidence-render-v1``: the full 73-character evidence ID. This is the
#   format every run before the alias change used, including the published
#   Gate 2 generation run, which must stay reproducible. Measured under
#   ``o200k_base`` it costs a median of 50 tokens of framing per item, of which
#   the ID is about 39: hex digits tokenise badly.
# * ``evidence-render-v2``: a positional alias, ``E1``, ``E2``, ... in packet
#   order. Every record, citation and metric still carries the full,
#   provenance-bearing evidence ID; the alias exists only in the rendered text
#   and is mapped back before anything is scored.
EvidenceRenderVersion = Literal["evidence-render-v1", "evidence-render-v2"]
EVIDENCE_RENDER_V1: EvidenceRenderVersion = "evidence-render-v1"
EVIDENCE_RENDER_V2: EvidenceRenderVersion = "evidence-render-v2"
# The owner's decision: new runs render aliases.
DEFAULT_EVIDENCE_RENDER_VERSION: EvidenceRenderVersion = EVIDENCE_RENDER_V2


class _Counter(Protocol):
    def count(self, text: str) -> int: ...


def evidence_label(
    evidence_id: str,
    index: int,
    version: EvidenceRenderVersion,
) -> str:
    """The label an item is shown under at zero-based ``index`` in its packet."""
    if version == EVIDENCE_RENDER_V1:
        return evidence_id
    return f"E{index + 1}"


def evidence_labels(
    evidence_ids: Sequence[str],
    version: EvidenceRenderVersion,
) -> dict[str, str]:
    """Map each rendered label back to the full evidence ID it stands for."""
    return {
        evidence_label(evidence_id, index, version): evidence_id
        for index, evidence_id in enumerate(evidence_ids)
    }


def render_evidence_item(label: str, content: str) -> str:
    """Render one packed item, under whatever label its version assigns."""
    return f'<evidence id="{label}">\n{content}\n</evidence>'


def render_evidence_block(
    items: Iterable[tuple[str, str]],
    *,
    version: EvidenceRenderVersion,
) -> str:
    """Render ``(evidence_id, content)`` pairs as the prompt's evidence block.

    Labels are assigned by position, so the block is a function of the items
    *in order*; that is what makes a v2 alias cost depend on its slot.
    """
    return EVIDENCE_JOINER.join(
        render_evidence_item(evidence_label(evidence_id, index, version), content)
        for index, (evidence_id, content) in enumerate(items)
    )


class EvidenceBudget:
    """Exact, incremental accounting of a rendered evidence block.

    A packer asks ``fits`` before adding an item and calls ``add`` when it
    does. The cost of the block is kept exact without re-tokenising it on
    every step, by splitting it where tokenisation cannot merge across the
    split:

        count(block) = sum(count(item_i + JOINER) for all but the last item)
                       + count(last item)

    Every item after the first begins with ``<evidence``, and every joiner
    follows an item's closing ``</evidence>``. Under ``o200k_base`` the
    pre-tokeniser emits ``>`` plus trailing newlines as one pre-token and
    ``<evidence`` as the next, and BPE never merges across pre-tokens, so the
    sum is exact. It is exact for any whitespace tokenizer too. Because a
    tokenizer this module has not seen could break that assumption, the
    caller verifies the finished block with ``verified_count`` and a packet
    that does not fit is refused rather than emitted.

    In ``content`` mode the framing costs nothing and each item costs its
    content count, which reproduces the accounting every packer used before.

    Under ``evidence-render-v2`` an item's label is its position, so its cost
    depends on the slot it would take: ``E9`` and ``E10`` need not cost the
    same. The budget tracks how many items it has accepted and prices each
    candidate at the next slot -- the one it would actually occupy, since a
    rejected candidate takes no slot. The split argument above is unaffected:
    the alias sits between ``<evidence id="`` and ``">``, and the joiner split
    is still after ``</evidence>``.
    """

    def __init__(
        self,
        token_budget: int,
        tokenizer: _Counter,
        accounting: BudgetAccounting = DEFAULT_BUDGET_ACCOUNTING,
        version: EvidenceRenderVersion = DEFAULT_EVIDENCE_RENDER_VERSION,
    ) -> None:
        self.token_budget = token_budget
        self.tokenizer = tokenizer
        self.accounting = accounting
        self.version = version
        # Sum of count(item + JOINER) for every accepted item.
        self._charged = 0
        self._slots = 0
        self._adjustments: dict[int, tuple[int, int]] = {}

    def item_costs(self, evidence_id: str, content: str) -> tuple[int, int]:
        """Return ``(cost if last, cost if followed)`` at the next free slot."""
        return self.item_costs_at(evidence_id, content, self._slots)

    def item_costs_at(
        self,
        evidence_id: str,
        content: str,
        slot: int,
    ) -> tuple[int, int]:
        """Return an item's two costs if it occupied zero-based ``slot``."""
        if self.accounting == "content":
            count = self.tokenizer.count(content)
            return count, count
        rendered = render_evidence_item(
            evidence_label(evidence_id, slot, self.version), content
        )
        return (
            self.tokenizer.count(rendered),
            self.tokenizer.count(rendered + EVIDENCE_JOINER),
        )

    def slot_adjustment(self, slot: int) -> tuple[int, int]:
        """How much more an item costs at ``slot`` than at slot 0.

        Lets a selector price every candidate once, at slot 0, and adjust by
        slot instead of re-tokenising the whole pool at every step. It is exact
        whenever the label's cost does not interact with the content around it,
        which holds for ``o200k_base`` -- the alias is its own pre-tokens,
        fenced by ``="`` and ``">`` -- and for whitespace and character
        tokenizers. The emission loop still prices each item exactly at its
        real slot, and the finished block is verified, so an approximation
        here could only make the selector choose slightly differently, never
        overrun the budget.
        """
        if self.accounting == "content" or self.version == EVIDENCE_RENDER_V1:
            return 0, 0
        if slot not in self._adjustments:
            probe = "x"
            base = self.item_costs_at(_PROBE_EVIDENCE_ID, probe, 0)
            here = self.item_costs_at(_PROBE_EVIDENCE_ID, probe, slot)
            self._adjustments[slot] = (here[0] - base[0], here[1] - base[1])
        return self._adjustments[slot]

    def fits(self, costs: tuple[int, int]) -> bool:
        """Whether an item can be added as the block's last item."""
        return self._charged + costs[0] <= self.token_budget

    def add(self, costs: tuple[int, int]) -> None:
        self._charged += costs[1]
        self._slots += 1

    @property
    def slots(self) -> int:
        """How many items have been accepted, i.e. the next item's slot."""
        return self._slots

    @property
    def remaining(self) -> int:
        """Budget left for a further item's last-position cost."""
        return self.token_budget - self._charged


_REPRESENTATIVE_EVIDENCE_ID = "evidence_" + (
    "3f2a9c1d7e5b8046a1c3e9f7d2b5a8c4e6f1a3d9b7c5e2f8a4d6b1c9e7f3a5d2"
)
_PROBE_EVIDENCE_ID = _REPRESENTATIVE_EVIDENCE_ID


def evidence_item_overhead(
    tokenizer: _Counter,
    accounting: BudgetAccounting,
    version: EvidenceRenderVersion = DEFAULT_EVIDENCE_RENDER_VERSION,
) -> int:
    """Tokens one item's framing adds, for sizing content before it is packed.

    Used where content is cut to fit the budget before any evidence ID exists
    -- oversized-table fragments -- so a fragment sized to the whole budget in
    content tokens is not left unable to fit once it is framed. Under v1 the
    ID used is a representative 64-hex-digit SHA-256, which can tokenise a few
    tokens differently from a real one; under v2 it is the first alias. Either
    way this sizes content, and the packer, not this estimate, enforces the
    budget.
    """
    if accounting == "content":
        return 0
    label = evidence_label(_REPRESENTATIVE_EVIDENCE_ID, 0, version)
    return tokenizer.count(render_evidence_item(label, ""))


def verified_count(
    items: Sequence[tuple[str, str]],
    tokenizer: _Counter,
    accounting: BudgetAccounting,
    version: EvidenceRenderVersion = DEFAULT_EVIDENCE_RENDER_VERSION,
) -> int:
    """Count a finished packet exactly as the budget defines it."""
    if accounting == "content":
        return sum(tokenizer.count(content) for _evidence_id, content in items)
    if not items:
        return 0
    return tokenizer.count(render_evidence_block(items, version=version))
