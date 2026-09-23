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


class _Counter(Protocol):
    def count(self, text: str) -> int: ...


def render_evidence_item(evidence_id: str, content: str) -> str:
    """Render one packed item exactly as the answer prompt shows it."""
    return f'<evidence id="{evidence_id}">\n{content}\n</evidence>'


def render_evidence_block(items: Iterable[tuple[str, str]]) -> str:
    """Render ``(evidence_id, content)`` pairs as the prompt's evidence block."""
    return EVIDENCE_JOINER.join(
        render_evidence_item(evidence_id, content) for evidence_id, content in items
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
    """

    def __init__(
        self,
        token_budget: int,
        tokenizer: _Counter,
        accounting: BudgetAccounting = DEFAULT_BUDGET_ACCOUNTING,
    ) -> None:
        self.token_budget = token_budget
        self.tokenizer = tokenizer
        self.accounting = accounting
        # Sum of count(item + JOINER) for every accepted item.
        self._charged = 0

    def item_costs(self, evidence_id: str, content: str) -> tuple[int, int]:
        """Return ``(cost if last, cost if followed by another item)``."""
        if self.accounting == "content":
            count = self.tokenizer.count(content)
            return count, count
        rendered = render_evidence_item(evidence_id, content)
        return (
            self.tokenizer.count(rendered),
            self.tokenizer.count(rendered + EVIDENCE_JOINER),
        )

    def fits(self, costs: tuple[int, int]) -> bool:
        """Whether an item can be added as the block's last item."""
        return self._charged + costs[0] <= self.token_budget

    def add(self, costs: tuple[int, int]) -> None:
        self._charged += costs[1]

    @property
    def remaining(self) -> int:
        """Budget left for a further item's last-position cost."""
        return self.token_budget - self._charged


_REPRESENTATIVE_EVIDENCE_ID = "evidence_" + (
    "3f2a9c1d7e5b8046a1c3e9f7d2b5a8c4e6f1a3d9b7c5e2f8a4d6b1c9e7f3a5d2"
)


def evidence_item_overhead(
    tokenizer: _Counter,
    accounting: BudgetAccounting,
) -> int:
    """Tokens one item's framing adds, for sizing content before it is packed.

    Used where content is cut to fit the budget before any evidence ID exists
    -- oversized-table fragments -- so a fragment sized to the whole budget in
    content tokens is not left unable to fit once it is framed. The ID used is
    a representative 64-hex-digit SHA-256; a real ID can tokenise a few tokens
    differently, so this sizes content, and the packer, not this estimate,
    enforces the budget.
    """
    if accounting == "content":
        return 0
    return tokenizer.count(render_evidence_item(_REPRESENTATIVE_EVIDENCE_ID, ""))


def verified_count(
    items: Sequence[tuple[str, str]],
    tokenizer: _Counter,
    accounting: BudgetAccounting,
) -> int:
    """Count a finished packet exactly as the budget defines it."""
    if accounting == "content":
        return sum(tokenizer.count(content) for _evidence_id, content in items)
    if not items:
        return 0
    return tokenizer.count(render_evidence_block(items))
