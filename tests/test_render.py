"""Tests for ``render.py``: the debug-ascii rasterizer (and the SVG renderer).

The ascii grid doubles as the layout test oracle.
One character per 5-ft cell, space-separated, north at top; empty cells are
``.``. A blank line then a legend follows. Glyphs are mnemonic-first: the
first unused letter of the room id (uppercased), falling back to a generic
pool; ties are broken by source order.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from porta.layout import solve
from porta.parser import parse
from porta.render import render_ascii, render_svg


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


# === SVG ===================================================================
#
# Geometry is drawn directly in feet (1 user unit = 1 foot); no scaling or
# y-flip (the layout's x-east/y-south coords are already SVG-native). The
# viewBox frames the bounding box plus a margin, so rooms are emitted at their
# literal (possibly negative) coordinates. Rooms are lettered (reusing the
# ascii glyph scheme) with a key below; full in-room names are deferred (#13).

SVG_NS = "http://www.w3.org/2000/svg"
MARGIN = 10  # feet of padding around the plan (matches the renderer constant)
SCALE = 10  # display scale (px per foot) applied to width/height

TWO = 'room a "A" 20x20 root\nroom b "Bee" 10x10 right-of a'


def svg_of(text: str) -> str:
    return render_svg(solve(parse(text)))


def tag(name: str) -> str:
    return f"{{{SVG_NS}}}{name}"


def rect_by_room(root: ET.Element, room_id: str) -> ET.Element:
    for rect in root.iter(tag("rect")):
        if rect.get("data-room") == room_id:
            return rect
    raise AssertionError(f"no rect for room {room_id!r}")


def text_by_room(root: ET.Element, room_id: str) -> ET.Element:
    for text in root.iter(tag("text")):
        if text.get("data-room") == room_id:
            return text
    raise AssertionError(f"no label for room {room_id!r}")


def test_svg_output_is_well_formed_xml() -> None:
    ET.fromstring(svg_of(TWO))  # raises on malformed XML


def test_svg_root_is_svg_with_viewbox_and_matching_size() -> None:
    root = ET.fromstring(svg_of(TWO))
    assert root.tag == tag("svg")
    view_box = root.get("viewBox")
    assert view_box is not None
    min_x, min_y, vbw, vbh = (float(n) for n in view_box.split())
    # TWO spans x[0,30], y[0,20]; viewBox starts a margin up-and-left of that.
    assert (min_x, min_y) == (-MARGIN, -MARGIN)
    assert vbw == 30 + 2 * MARGIN
    assert vbh >= 20 + 2 * MARGIN  # extra room below for the caption + key
    # width/height are the viewBox extent scaled up for a usable default size.
    assert float(root.get("width", "0")) == vbw * SCALE
    assert float(root.get("height", "0")) == vbh * SCALE


def test_has_a_white_background() -> None:
    root = ET.fromstring(svg_of(TWO))
    background = next(r for r in root.iter(tag("rect")) if not r.get("data-room"))
    assert background.get("fill") == "white"


def test_room_rects_are_transparent_so_the_grid_shows_through() -> None:
    root = ET.fromstring(svg_of(TWO))
    room_rects = [r for r in root.iter(tag("rect")) if r.get("data-room")]
    assert room_rects
    assert all(r.get("fill") == "none" for r in room_rects)


def test_grid_has_a_line_every_five_feet_across_the_plan() -> None:
    # TWO spans x[0,30] (7 verticals) and y[0,20] (5 horizontals).
    root = ET.fromstring(svg_of(TWO))
    assert sum(1 for _ in root.iter(tag("line"))) == 7 + 5


def test_scale_caption_states_the_grid_size() -> None:
    texts = " ".join(t.text or "" for t in ET.fromstring(svg_of(TWO)).iter(tag("text")))
    assert "5 ft" in texts


@pytest.mark.parametrize(
    ("room_id", "expected"),
    [
        ("entrance", (0, 0, 20, 20)),
        ("hall", (0, -30, 40, 30)),
        ("library", (-30, -30, 30, 30)),
        ("pantry", (70, 0, 15, 25)),
    ],
)
def test_one_rect_per_room_at_literal_feet_coords(
    room_id: str, expected: tuple[int, int, int, int]
) -> None:
    source = Path("examples/manor.porta").read_text()
    root = ET.fromstring(render_svg(solve(parse(source))))
    rect = rect_by_room(root, room_id)
    got = tuple(int(float(rect.get(a, ""))) for a in ("x", "y", "width", "height"))
    assert got == expected


def test_svg_rect_count_matches_room_count() -> None:
    root = ET.fromstring(svg_of(DESIGN_MANOR))
    room_rects = [r for r in root.iter(tag("rect")) if r.get("data-room")]
    assert len(room_rects) == 3


@pytest.mark.parametrize(
    ("room_id", "glyph", "center"),
    [
        ("entrance", "E", (10.0, 10.0)),
        ("kitchen", "K", (-10.0, 15.0)),
        ("hall", "H", (20.0, -15.0)),
    ],
)
def test_each_room_is_lettered_at_its_centre(
    room_id: str, glyph: str, center: tuple[float, float]
) -> None:
    root = ET.fromstring(svg_of(DESIGN_MANOR))
    label = text_by_room(root, room_id)
    assert label.text == glyph
    assert (float(label.get("x", "")), float(label.get("y", ""))) == center


def test_svg_key_lists_each_room_name() -> None:
    root = ET.fromstring(svg_of(DESIGN_MANOR))
    key_text = " ".join(t.text or "" for t in root.iter(tag("text")))
    for name in ("Entrance Hall", "Kitchen", "Great Hall"):
        assert name in key_text


def test_key_includes_room_dimensions() -> None:
    key_text = " ".join(
        t.text or "" for t in ET.fromstring(svg_of(DESIGN_MANOR)).iter(tag("text"))
    )
    assert "(20x20 ft)" in key_text  # entrance
    assert "(40x30 ft)" in key_text  # hall


def test_special_characters_in_names_are_escaped() -> None:
    # Raw & or < would make the document malformed; fromstring proves escaping.
    root = ET.fromstring(svg_of('room a "Hall & Co <X>" 20x20 root'))
    texts = [t.text for t in root.iter(tag("text"))]
    assert any(t is not None and "Hall & Co <X>" in t for t in texts)


def test_manor_renders_to_golden_svg_fixture() -> None:
    source = Path("examples/manor.porta").read_text()
    expected = Path("tests/fixtures/manor.svg").read_text()
    assert render_svg(solve(parse(source))) == expected


# A corpus of small, human-reviewed layouts: each tests/fixtures/layouts/
# <case>.porta has a reviewed <case>.svg golden. Adding a case is just dropping
# in the input/golden pair.
_LAYOUT_CASES = sorted(Path("tests/fixtures/layouts").glob("*.porta"))


@pytest.mark.parametrize("porta_file", _LAYOUT_CASES, ids=lambda p: p.stem)
def test_layout_renders_to_svg_golden(porta_file: Path) -> None:
    expected = porta_file.with_suffix(".svg").read_text()
    actual = render_svg(solve(parse(porta_file.read_text())))
    assert actual == expected
