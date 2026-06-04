"""Stage 2: the debug-ascii rasterizer (and layout test oracle).

One character per 5-ft cell, space-separated, north at top; empty cells are
``.``. A blank line then a legend follows. Glyphs are mnemonic-first: the
first unused letter of the room id (uppercased), falling back to a generic
pool; ties are broken by source order.
"""

from pathlib import Path

from porta.layout import solve
from porta.parser import parse
from porta.render import render_ascii


def ascii_of(text: str) -> str:
    return render_ascii(solve(parse(text)))


# Confidently hand-derived: entrance(E)/kitchen(K)/hall(H) on a 12x12 grid.
DESIGN_MANOR = (
    'room entrance "Entrance Hall" 20x20 root\n'
    'room kitchen  "Kitchen"       20x30 left-of entrance\n'
    'room hall     "Great Hall"    40x30 up-of entrance right-of kitchen'
)

DESIGN_MANOR_ASCII = """\
. . . . H H H H H H H H
. . . . H H H H H H H H
. . . . H H H H H H H H
. . . . H H H H H H H H
. . . . H H H H H H H H
. . . . H H H H H H H H
K K K K E E E E . . . .
K K K K E E E E . . . .
K K K K E E E E . . . .
K K K K E E E E . . . .
K K K K . . . . . . . .
K K K K . . . . . . . .

E=entrance  K=kitchen  H=hall"""


def test_design_manor_renders_to_expected_grid() -> None:
    assert ascii_of(DESIGN_MANOR) == DESIGN_MANOR_ASCII


def test_empty_cells_use_dots() -> None:
    # A single 10x10 room is one cell with no empties; an L of two rooms has one.
    grid = ascii_of('room a "A" 20x10 root\nroom b "B" 10x10 down-of a').split("\n\n")[
        0
    ]
    assert "." in grid


def test_glyphs_are_mnemonic_first_with_tie_breaking() -> None:
    # kitchen -> K; kennel -> K taken -> E (second letter).
    text = (
        'room kitchen "Kitchen" 10x10 root\nroom kennel "Kennel" 10x10 right-of kitchen'
    )
    legend = ascii_of(text).split("\n\n")[1]
    assert "K=kitchen" in legend
    assert "E=kennel" in legend


def test_legend_lists_rooms_in_source_order() -> None:
    legend = ascii_of(DESIGN_MANOR).split("\n\n")[1]
    assert legend == "E=entrance  K=kitchen  H=hall"


# --- the north-star manor (golden) ----------------------------------------

MANOR_ASCII = """\
L L L L L L H H H H H H H H D D D D D D . . .
L L L L L L H H H H H H H H D D D D D D . . .
L L L L L L H H H H H H H H D D D D D D . . .
L L L L L L H H H H H H H H D D D D D D . . .
L L L L L L H H H H H H H H D D D D D D . . .
L L L L L L H H H H H H H H D D D D D D . . .
. . P P P P E E E E C C C C K K K K K K A A A
. . P P P P E E E E C C C C K K K K K K A A A
. . P P P P E E E E C C C C K K K K K K A A A
. . P P P P E E E E C C C C K K K K K K A A A
. . S S S S . . . . . . . . K K K K K K A A A
. . S S S S . . . . . . . . U U U U U U . . .
. . S S S S . . . . . . . . U U U U U U . . .
. . S S S S . . . . . . . . U U U U U U . . .
. . . . . . . . . . . . . . U U U U U U . . .

E=entrance  H=hall  L=library  D=dining  P=parlour  C=cloak  K=kitchen  A=pantry  S=study  U=scullery"""


def test_manor_example_renders_to_golden() -> None:
    source = Path("examples/manor.porta").read_text()
    assert render_ascii(solve(parse(source))) == MANOR_ASCII
