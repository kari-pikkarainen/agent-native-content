"""The compiler ablation ladder required by benchmark specification section 25.

Section 25 names four variants -- D1 no structural expansion, D2 headings
only, D3 headings plus sibling expansion, D4 headings plus siblings plus table
preservation -- and says why they exist: "This prevents attributing
improvements vaguely to 'the IR.'" The spec gives the names and not the field
settings, so the settings are fixed here, as data, and checked by a test. A
reader of a published ablation can then see what was run without
reconstructing it from shell history.

Each entry is a set of overrides applied to ``CompilerConfig``. Anything not
named keeps its shipped default, so these describe the expansion ladder and
nothing else.

Two decisions the spec does not make, recorded with their alternatives.

**"Sibling expansion" in D3 includes list-item grouping.** ``_list_neighbors``
and ``_paragraph_siblings`` in ``compiler/expand.py`` both resolve candidates
through the same ``_siblings`` helper: this is one adjacency mechanism with
two entry points, and the ladder is about mechanisms. The reading is also
forced at the bottom of the ladder -- D1 is "no structural expansion", and
leaving adjacent list items grouped would contradict that in plain terms --
and once off at D1 it has to come back somewhere, which can only be the
sibling step.

The alternative reading is defensible and is recorded because the two switches
have different shipped status: ``include_previous_sibling`` and
``include_next_sibling`` ship **off** while ``group_adjacent_list_items``
ships **on**, so "turn on sibling expansion" means a change from the shipped
configuration for the first two and no change for the third. A reader who took
"sibling expansion" to mean the paragraph switches alone would produce a
D1-to-D3 ladder in which list items are always grouped. If that variant is
ever run it should be labelled distinctly rather than called D3.

**Keyed joins, page neighbours and query faceting.** Section 25's ladder stops
at table preservation, so the two later operators -- keyed table joins and
page-neighbour windows -- are off throughout D1 to D4 and appear only in the
shipped configuration. Query faceting is left at its default everywhere,
including D1: it is a retrieval-stage operator, not structural expansion, and
switching it off in D1 would confound the thing the ladder exists to isolate.

``SHIPPED`` is not a spec ablation. It is the configuration the benchmark
actually runs, included because none of D1 to D4 is, and a reader comparing
the ladder against a published headline number would otherwise be comparing
against something unlisted.
"""

from collections.abc import Mapping
from types import MappingProxyType

_NO_EXPANSION: dict[str, object] = {
    "include_heading_context": False,
    "include_previous_sibling": False,
    "include_next_sibling": False,
    "group_adjacent_list_items": False,
    "preserve_tables": False,
    "keyed_table_join_enabled": False,
    "page_neighbor_radius": 0,
}

D1: Mapping[str, object] = MappingProxyType(dict(_NO_EXPANSION))
D2: Mapping[str, object] = MappingProxyType(
    {**_NO_EXPANSION, "include_heading_context": True}
)
D3: Mapping[str, object] = MappingProxyType(
    {
        **D2,
        "include_previous_sibling": True,
        "include_next_sibling": True,
        "group_adjacent_list_items": True,
    }
)
D4: Mapping[str, object] = MappingProxyType({**D3, "preserve_tables": True})
# Empty: the shipped configuration is ``CompilerConfig()`` with nothing
# overridden. Naming it keeps the ladder's endpoint explicit.
SHIPPED: Mapping[str, object] = MappingProxyType({})

COMPILER_ABLATIONS: Mapping[str, Mapping[str, object]] = MappingProxyType(
    {"D1": D1, "D2": D2, "D3": D3, "D4": D4, "SHIPPED": SHIPPED}
)

# The command-line option each overridable field is reached by, so the mapping
# above can be turned into an ``eval-retrieval`` invocation mechanically.
ABLATION_CLI_OPTIONS: Mapping[str, str] = MappingProxyType(
    {
        "include_heading_context": "--compiler-heading-context",
        "include_previous_sibling": "--compiler-previous-sibling",
        "include_next_sibling": "--compiler-next-sibling",
        "group_adjacent_list_items": "--compiler-group-adjacent-list-items",
        "preserve_tables": "--compiler-preserve-tables",
        "keyed_table_join_enabled": "--compiler-keyed-table-joins",
        "page_neighbor_radius": "--compiler-page-neighbor-radius",
    }
)


def ablation_command_line(name: str) -> tuple[str, ...]:
    """Render one ablation as the options that select it.

    Boolean fields use the ``--x/--no-x`` form the CLI already uses; the
    page-neighbour radius is an integer and takes a value. Only fields the
    ablation names are emitted, so everything else is visibly left at its
    default.
    """
    overrides = COMPILER_ABLATIONS[name]
    options: list[str] = []
    for field, option in ABLATION_CLI_OPTIONS.items():
        if field not in overrides:
            continue
        value = overrides[field]
        if isinstance(value, bool):
            options.append(option if value else option.replace("--", "--no-", 1))
        else:
            options.extend((option, str(value)))
    return tuple(options)
