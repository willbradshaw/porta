"""Tests for ``render.py``: the debug-ascii rasterizer (and the SVG renderer).

The ascii grid doubles as the layout test oracle.
One character per 5-ft cell, space-separated, north at top; empty cells are
``.``. A blank line then a legend follows. Glyphs are numbers assigned by casefolded display name, then ID.
"""

import xml.etree.ElementTree as ET
from collections.abc import Callable
from copy import deepcopy
from itertools import pairwise
from pathlib import Path

import pytest

from porta.errors import RenderError
from porta.layout import block_wall_segments, solve
from porta.parser import parse
from porta.render import render_ascii, render_svg


def ascii_of(text: str) -> str:
    return render_ascii(solve(parse(text)))


# Confidently hand-derived: entrance(1)/kitchen(3)/hall(2) on an 8x12 grid.
# 'hall' is pinned on both axes (x from right-of kitchen, y from down-of
# entrance) and shares a real wall with each.
DESIGN_MANOR = (
    'room entrance "Entrance Hall" 40x20 root\n'
    'room kitchen  "Kitchen"       20x40 down-of entrance\n'
    'room hall     "Great Hall"    20x20 right-of kitchen down-of entrance'
)

DESIGN_MANOR_ASCII = """\
1 1 1 1 1 1 1 1
1 1 1 1 1 1 1 1
1 1 1 1 1 1 1 1
1 1 1 1 1 1 1 1
3 3 3 3 2 2 2 2
3 3 3 3 2 2 2 2
3 3 3 3 2 2 2 2
3 3 3 3 2 2 2 2
3 3 3 3 . . . .
3 3 3 3 . . . .
3 3 3 3 . . . .
3 3 3 3 . . . .

1=entrance  2=hall  3=kitchen"""


def test_design_manor_renders_to_expected_grid() -> None:
    assert ascii_of(DESIGN_MANOR) == DESIGN_MANOR_ASCII


def test_empty_cells_use_dots() -> None:
    # A single 10x10 room is one cell with no empties; an L of two rooms has one.
    grid = ascii_of('room a "A" 20x10 root\nroom b "B" 10x10 down-of a').split("\n\n")[
        0
    ]
    assert "." in grid


def test_glyphs_follow_names_and_reserve_later_explicit_numbers() -> None:
    source = (
        'room z "Atrium" 20x20 root\n'
        'room a "Library" 20x20 right-of z\n'
        'room m "Vault" 20x20 down-of z glyph="2"'
    )
    assert ascii_of(source).split("\n\n")[1] == "1=z  2=m  3=a"
    root = ET.fromstring(svg_of(source))
    assert [
        "  ".join(span.text or "" for span in group)
        for group in root.findall('.//{*}g[@class="key"]')
    ] == [
        "1  Atrium",
        "2  Vault",
        "3  Library",
    ]


def test_legend_is_sorted_by_glyph() -> None:
    legend = ascii_of(DESIGN_MANOR).split("\n\n")[1]
    assert legend == "1=entrance  2=hall  3=kitchen"


def test_render_is_independent_of_statement_order() -> None:
    # Same rooms, shuffled and with the root written last, render identically:
    # placement is a DAG and the labels are alphabetical, so order can't matter.
    plan = (
        'room hall "Hall" 20x20 root\n'
        'room kitchen "Kitchen" 20x20 right-of hall\n'
        'room study "Study" 20x20 down-of hall'
    )
    shuffled = (
        'room study "Study" 20x20 down-of hall\n'
        'room kitchen "Kitchen" 20x20 right-of hall\n'
        'room hall "Hall" 20x20 root'
    )
    assert ascii_of(shuffled) == ascii_of(plan)
    assert svg_of(shuffled) == svg_of(plan)


# --- the north-star manor (golden) ----------------------------------------

MANOR_ASCII = """\
.  .  .  .  .  .  .  .  .  .  .  .  .  5  5  5  5  .  .  .  .  .  .  .  .  .  .  .  .
.  .  .  .  .  .  .  .  .  .  .  .  .  5  5  5  5  .  .  .  .  .  .  .  .  .  .  .  .
.  .  .  9  9  9  9  9  9  6  6  6  6  6  6  6  6  3  3  3  3  3  3  .  .  .  .  .  .
.  .  .  9  9  9  9  9  9  6  6  6  6  6  6  6  6  3  3  3  3  3  3  .  .  .  .  .  .
16 16 16 9  9  9  9  9  9  6  6  6  6  6  6  6  6  3  3  3  3  3  3  .  .  .  .  .  .
16 16 16 9  9  9  9  9  9  6  6  6  6  6  6  6  6  3  3  3  3  3  3  .  .  .  .  .  .
16 16 16 9  9  9  9  9  9  6  6  6  6  6  6  6  6  3  3  3  3  3  3  .  .  .  .  .  .
.  .  .  9  9  9  9  9  9  6  6  6  6  6  6  6  6  3  3  3  3  3  3  .  .  .  .  .  .
.  .  .  2  2  11 11 11 11 4  4  4  4  1  1  1  1  7  7  7  7  7  7  10 10 10 .  .  .
.  .  .  2  2  11 11 11 11 4  4  4  4  1  1  1  1  7  7  7  7  7  7  10 10 10 8  8  8
.  .  .  2  2  11 11 11 11 4  4  4  4  1  1  1  1  7  7  7  7  7  7  10 10 10 8  8  8
.  .  .  2  2  11 11 11 11 4  4  4  4  1  1  1  1  7  7  7  7  7  7  10 10 10 8  8  8
.  .  .  2  2  15 15 15 15 12 13 13 .  .  .  .  .  7  7  7  7  7  7  10 10 10 .  .  .
.  .  .  2  2  15 15 15 15 12 13 13 .  .  .  .  .  14 14 14 14 14 14 .  .  .  .  .  .
.  .  .  2  2  15 15 15 15 .  .  .  .  .  .  .  .  14 14 14 14 14 14 .  .  .  .  .  .
.  .  .  2  2  15 15 15 15 .  .  .  .  .  .  .  .  14 14 14 14 14 14 .  .  .  .  .  .
.  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .  14 14 14 14 14 14 .  .  .  .  .  .

1=cloak  2=corridor  3=dining  4=entrance  5=gallery  6=hall  7=kitchen  8=larder  9=library  10=pantry  11=parlor  12=passage  13=porch  14=scullery  15=study  16=turret"""


def test_manor_example_renders_to_golden() -> None:
    source = Path("examples/manor.porta").read_text()
    assert render_ascii(solve(parse(source))) == MANOR_ASCII


# === SVG ===================================================================
#
# Geometry is drawn directly in feet (1 user unit = 1 foot); no scaling or
# y-flip (the layout's x-east/y-south coords are already SVG-native). The
# viewBox frames the bounding box plus a margin, so rooms are emitted at their
# literal (possibly negative) coordinates. Rooms are numbered (reusing the
# ascii glyph scheme) with a key below; full in-room names are deferred (#13).

SVG_NS = "http://www.w3.org/2000/svg"
MARGIN = 10  # feet of padding around the plan (matches the renderer constant)
SCALE = 10  # display scale (px per foot) applied to width/height

TWO = 'room a "A" 20x20 root\nroom b "Bee" 10x10 right-of a'


def svg_of(text: str) -> str:
    return render_svg(solve(parse(text)))


def tag(name: str) -> str:
    return f"{{{SVG_NS}}}{name}"


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
    vb_x, vb_y, vbw, vbh = (float(n) for n in view_box.split())
    # TWO's plan spans x[0,30], y[0,20]; the viewBox encloses it with at least a
    # margin on every side (it may be wider and centered to fit the key).
    assert vb_y == -MARGIN
    assert vb_x <= -MARGIN
    assert vb_x + vbw >= 30 + MARGIN
    assert vbh >= 20 + 2 * MARGIN  # extra room below for the caption + key
    # width/height are the viewBox extent scaled up for a usable default size
    # (independent rounding of each makes the relation exact only to a tolerance).
    assert float(root.get("width", "0")) == pytest.approx(vbw * SCALE, abs=0.05)
    assert float(root.get("height", "0")) == pytest.approx(vbh * SCALE, abs=0.05)


def test_has_a_white_background() -> None:
    root = ET.fromstring(svg_of(TWO))
    background = next(r for r in root.iter(tag("rect")) if not r.get("data-room"))
    assert background.get("fill") == "white"


def test_walls_do_not_cover_the_room_grid() -> None:
    root = ET.fromstring(svg_of(TWO))
    assert len(root.findall(tag("rect"))) == 1  # background only
    assert wall_lines(root)


def test_grid_has_a_line_every_five_feet_across_the_plan() -> None:
    # TWO spans x[0,30] (7 verticals) and y[0,20] (5 horizontals); door lines
    # (class="door") are excluded.
    root = ET.fromstring(svg_of(TWO))
    grid = [ln for ln in root.iter(tag("line")) if ln.get("class") is None]
    assert len(grid) == 7 + 5


def test_scale_caption_states_the_grid_size() -> None:
    texts = " ".join(
        " ".join(t.itertext()) for t in ET.fromstring(svg_of(TWO)).iter(tag("text"))
    )
    assert "5-ft squares" in texts


def test_exterior_is_stronger_and_shared_wall_is_drawn_once() -> None:
    root = ET.fromstring(svg_of(TWO))
    interior = [
        ln for ln in root.iter(tag("line")) if ln.get("class") == "wall interior"
    ]
    exterior = [
        ln for ln in root.iter(tag("line")) if ln.get("class") == "wall exterior"
    ]
    assert len(interior) == 1
    assert interior[0].get("stroke-width") == "0.5"
    assert exterior
    assert all(ln.get("stroke-width") == "0.8" for ln in exterior)
    assert (20, 0, 20, 10) in wall_lines(root)


@pytest.mark.parametrize(
    ("room_id", "glyph", "center"),
    [
        ("entrance", "1", (20.0, 10.0)),
        ("kitchen", "3", (10.0, 40.0)),
        ("hall", "2", (30.0, 30.0)),
    ],
)
def test_each_room_is_numbered_at_its_center(
    room_id: str, glyph: str, center: tuple[float, float]
) -> None:
    root = ET.fromstring(svg_of(DESIGN_MANOR))
    label = text_by_room(root, room_id)
    assert label.text == glyph
    assert (float(label.get("x", "")), float(label.get("y", ""))) == center


def test_svg_key_lists_each_room_name() -> None:
    root = ET.fromstring(svg_of(DESIGN_MANOR))
    key_text = " ".join(" ".join(t.itertext()) for t in root.iter(tag("text")))
    for name in ("Entrance Hall", "Kitchen", "Great Hall"):
        assert name in key_text


def test_key_shows_names_not_dimensions() -> None:
    key_text = " ".join(
        " ".join(t.itertext())
        for t in ET.fromstring(svg_of(DESIGN_MANOR)).iter(tag("text"))
    )
    assert "Entrance Hall" in key_text  # names are shown
    assert "ft)" not in key_text  # per-room dimensions are not


def test_unnamed_room_keys_as_just_its_glyph() -> None:
    root = ET.fromstring(svg_of('room a "" 20x30 root'))
    key_lines = [
        "  ".join(span.text or "" for span in t)
        for t in root.iter(tag("g"))
        if t.get("class") == "key"
    ]
    assert key_lines == ["1"]  # glyph only: no name, no dimensions


def test_special_characters_in_names_are_escaped() -> None:
    # Raw & or < would make the document malformed; fromstring proves escaping.
    root = ET.fromstring(svg_of('room a "Hall & Co <X>" 20x20 root'))
    key = root.find('.//{*}g[@class="key"]')
    assert key is not None
    assert " ".join(t.text or "" for t in list(key)[1:]) == "Hall & Co <X>"


def test_door_renders_as_a_door_line() -> None:
    root = ET.fromstring(svg_of('room a "A" 20x20 root\nroom b "B" 10x10 up-of a door'))
    door_lines = [ln for ln in root.iter(tag("line")) if ln.get("class") == "door"]
    assert len(door_lines) == 1
    assert door_lines[0].attrib["stroke-width"] == "1.5"
    got = tuple(float(door_lines[0].get(k, "")) for k in ("x1", "y1", "x2", "y2"))
    assert got == (0.0, 0.0, 5.0, 0.0)


def test_background_is_configurable() -> None:
    assert 'fill="white"' in svg_of('room a "A" 20x20 root')  # default
    custom = render_svg(solve(parse('room a "A" 20x20 root')), background="#f0f0f0")
    assert 'fill="#f0f0f0"' in custom


# --- open doors ------------------------------------------------------------
#
# An open door renders as a genuine gap in the wall (the adjoining rooms'
# outlines are emitted as per-edge segments with the opening cut out) with a
# dashed line across it (class="open") instead of a door mark.

OPEN_TWO = 'room a "A" 20x20 root\nroom b "Bee" 20x20 right-of a door=20 open'


def open_lines(root: ET.Element) -> list[tuple[float, ...]]:
    return [
        tuple(float(ln.get(k, "")) for k in ("x1", "y1", "x2", "y2"))
        for ln in root.iter(tag("line"))
        if ln.get("class") == "open"
    ]


def wall_lines(root: ET.Element) -> set[tuple[float, ...]]:
    return {
        tuple(float(ln.get(k, "")) for k in ("x1", "y1", "x2", "y2"))
        for ln in root.iter(tag("line"))
        if ln.get("class", "").startswith("wall ")
    }


def test_open_door_renders_as_one_dashed_line_and_no_door_mark() -> None:
    root = ET.fromstring(svg_of(OPEN_TWO))
    assert open_lines(root) == [(20.0, 0.0, 20.0, 20.0)]
    dashed = [ln for ln in root.iter(tag("line")) if ln.get("class") == "open"]
    assert dashed[0].get("stroke-dasharray") is not None
    assert [ln for ln in root.iter(tag("line")) if ln.get("class") == "door"] == []


def test_open_boundary_cuts_the_shared_wall_out_of_both_outlines() -> None:
    # The merged envelope omits the fully open shared wall.
    root = ET.fromstring(svg_of(OPEN_TWO))
    assert [r for r in root.iter(tag("rect")) if r.get("data-room")] == []
    assert wall_lines(root) == {
        (0, 0, 40, 0),
        (0, 20, 40, 20),
        (0, 0, 0, 20),
        (40, 0, 40, 20),
    }


def test_partial_opening_keeps_the_rest_of_the_wall() -> None:
    # A centered 10-ft archway: the shared edge keeps a 5-ft stub at each end.
    source = 'room a "A" 20x20 root\nroom b "Bee" 20x20 right-of a door=10 open'
    root = ET.fromstring(svg_of(source))
    assert open_lines(root) == [(20.0, 5.0, 20.0, 15.0)]
    assert {(20.0, 0.0, 20.0, 5.0), (20.0, 15.0, 20.0, 20.0)} <= wall_lines(root)


def test_rooms_away_from_the_opening_keep_their_walls() -> None:
    source = OPEN_TWO + '\nroom c "Sea" 20x20 down-of a'
    root = ET.fromstring(svg_of(source))
    assert (0, 20, 20, 20) in wall_lines(root)


def test_open_rooms_keep_their_glyphs_and_key_entries() -> None:
    root = ET.fromstring(svg_of(OPEN_TWO))
    assert text_by_room(root, "a").text == "1"
    assert text_by_room(root, "b").text == "2"
    key_lines = [
        "  ".join(span.text or "" for span in t)
        for t in root.iter(tag("g"))
        if t.get("class") == "key"
    ]
    assert key_lines == ["1  A", "2  Bee"]


def test_open_door_does_not_change_the_ascii_rendering() -> None:
    solid = 'room a "A" 20x20 root\nroom b "Bee" 20x20 right-of a'
    assert ascii_of(OPEN_TWO) == ascii_of(solid)


def test_open_and_solid_door_render_side_by_side() -> None:
    source = (
        'room a "A" 20x20 root\n'
        'room b "Bee" 20x20 right-of a door=10@0 open\n'
        "door@15 a b"
    )
    root = ET.fromstring(svg_of(source))
    assert open_lines(root) == [(20.0, 0.0, 20.0, 10.0)]
    door = [ln for ln in root.iter(tag("line")) if ln.get("class") == "door"]
    assert len(door) == 1


def test_external_open_door_cuts_the_exterior_wall() -> None:
    source = 'room a "A" 20x20 root\ndoor=10 open a outside down'
    root = ET.fromstring(svg_of(source))
    assert open_lines(root) == [(5.0, 20.0, 15.0, 20.0)]
    assert {(0.0, 20.0, 5.0, 20.0), (15.0, 20.0, 20.0, 20.0)} <= wall_lines(root)


def test_open_door_across_a_block_boundary_renders_as_a_gap() -> None:
    # 'side' opens into the block through a centered archway: one dashed line,
    # stubs on side's outline, and no solid block-outline line across the span.
    source = (
        'room main "" 20x20 root\n'
        'room wing "" 20x20 right-of main\n'
        'room side "Side" 20x20 right-of wing door=10 open\n'
        'block hall "Hall" main wing'
    )
    root = ET.fromstring(svg_of(source))
    assert open_lines(root) == [(40.0, 5.0, 40.0, 15.0)]
    assert {(40.0, 0.0, 40.0, 5.0), (40.0, 15.0, 40.0, 20.0)} <= wall_lines(root)
    outline = [
        tuple(float(ln.get(k, "")) for k in ("x1", "y1", "x2", "y2"))
        for ln in root.iter(tag("line"))
        if ln.get("stroke-linecap") == "square"
    ]
    assert (40.0, 0.0, 40.0, 20.0) not in outline


# --- secret doors ------------------------------------------------------------
#
# A secret door keeps the wall fully intact (that is the point) and draws an
# "S" marker (class="secret") centered on the door's span instead of a door
# mark.

SECRET_TWO = 'room a "A" 20x20 root\nroom b "Bee" 20x20 right-of a door=10@5 secret'


def secret_markers(root: ET.Element) -> list[tuple[float, float, str | None]]:
    return [
        (float(t.get("x", "")), float(t.get("y", "")), t.text)
        for t in root.iter(tag("text"))
        if t.get("class") == "secret"
    ]


def secret_marks(root: ET.Element) -> list[tuple[float, ...]]:
    return [
        tuple(float(ln.get(k, "")) for k in ("x1", "y1", "x2", "y2"))
        for ln in root.iter(tag("line"))
        if ln.get("class") == "secret"
    ]


def test_secret_door_renders_as_a_door_mark_plus_an_s() -> None:
    # The mark shows the door's size and position; the S says it's secret.
    root = ET.fromstring(svg_of(SECRET_TWO))
    assert secret_marks(root) == [(20.0, 5.0, 20.0, 15.0)]
    mark = root.find('.//{*}line[@class="secret"]')
    marker = root.find('.//{*}text[@class="secret"]')
    assert mark is not None
    assert marker is not None
    assert mark.attrib["stroke-width"] == "1.5"
    assert marker.attrib["font-size"] == "5"
    assert secret_markers(root) == [(20.0, 10.0, "S")]  # midpoint of y[5,15]
    assert [ln for ln in root.iter(tag("line")) if ln.get("class") == "door"] == []


def test_secret_door_leaves_shared_wall_intact() -> None:
    root = ET.fromstring(svg_of(SECRET_TWO))
    assert (20, 0, 20, 20) in wall_lines(root)
    assert open_lines(root) == []


def test_secret_and_solid_door_render_side_by_side() -> None:
    source = SECRET_TWO + "\ndoor@15 a b"
    root = ET.fromstring(svg_of(source))
    assert len(secret_marks(root)) == 1
    assert len(secret_markers(root)) == 1
    door = [ln for ln in root.iter(tag("line")) if ln.get("class") == "door"]
    assert len(door) == 1


def test_external_secret_door_marks_the_exterior_wall() -> None:
    source = 'room a "A" 20x20 root\ndoor=10 secret a outside down'
    root = ET.fromstring(svg_of(source))
    assert secret_marks(root) == [(5.0, 20.0, 15.0, 20.0)]
    assert secret_markers(root) == [(10.0, 20.0, "S")]
    assert (0, 20, 20, 20) in wall_lines(root)


def test_secret_door_does_not_change_the_ascii_rendering() -> None:
    solid = 'room a "A" 20x20 root\nroom b "Bee" 20x20 right-of a'
    assert ascii_of(SECRET_TWO) == ascii_of(solid)


# --- blocks ----------------------------------------------------------------

L_BLOCK = (
    'room main "" 40x30 root\n'
    'room wing "" 20x20 down-of main\n'
    'block hall "Great Hall" main wing'
)


def test_block_members_are_not_drawn_as_separate_rects() -> None:
    root = ET.fromstring(svg_of(L_BLOCK))
    ids = {r.get("data-room") for r in root.iter(tag("rect")) if r.get("data-room")}
    assert ids == set()  # members render as one outline, not per-room rects


def test_block_draws_one_numerical_glyph() -> None:
    root = ET.fromstring(svg_of(L_BLOCK))
    block_glyphs = [t for t in root.iter(tag("text")) if t.get("data-block") == "hall"]
    assert [t.text for t in block_glyphs] == ["1"]


def test_block_outline_drops_the_internal_wall() -> None:
    segments = set(block_wall_segments(solve(parse(L_BLOCK))))
    assert (0, 30, 20, 30) not in segments  # the shared main|wing wall is gone
    assert (20, 30, 40, 30) in segments  # the exposed part of main's bottom stays


def test_block_legend_and_key_use_the_block_not_its_members() -> None:
    assert ascii_of(L_BLOCK).split("\n\n")[1] == "1=hall"
    root = ET.fromstring(svg_of(L_BLOCK))
    key_text = " ".join(" ".join(t.itertext()) for t in root.iter(tag("text")))
    assert "Great Hall" in key_text


def test_block_cells_carry_the_block_glyph_in_ascii() -> None:
    grid = ascii_of(L_BLOCK).split("\n\n")[0]
    assert "1" in grid
    assert "M" not in grid
    assert "W" not in grid


# --- display glyphs --------------------------------------------------------


@pytest.mark.parametrize("renderer", [ascii_of, svg_of], ids=["ascii", "svg"])
@pytest.mark.parametrize("count", [37, 999], ids=["past-old-pool", "three-digit-limit"])
def test_automatic_numbering_within_glyph_length_limit(
    renderer: Callable[[str], str], count: int
) -> None:
    # Construct a placed row directly so this tests rendering, not solver scaling.
    building = parse("\n".join(f'room r{i:04} "" 5x5 root' for i in range(count)))
    for i, room in enumerate(building.rooms):
        room.x, room.y = i * 5, 0
    if renderer is ascii_of:
        rendered = render_ascii(building)
        assert rendered.split("\n\n")[1].split() == [
            f"{i + 1}=r{i:04}" for i in range(count)
        ]
    else:
        root = ET.fromstring(render_svg(building))
        assert [t.text for t in root.iter(tag("text")) if t.get("data-room")] == [
            str(i + 1) for i in range(count)
        ]
        assert [
            "  ".join(span.text or "" for span in group)
            for group in root.findall('.//{*}g[@class="key"]')
        ] == [str(i + 1) for i in range(count)]


@pytest.mark.parametrize("renderer", [render_ascii, render_svg], ids=["ascii", "svg"])
@pytest.mark.parametrize(
    ("count", "explicit", "exhausted"),
    [
        pytest.param(1000, None, True, id="four-digits"),
        pytest.param(999, "999", True, id="last-number-reserved"),
        pytest.param(998, "999", False, id="last-number-reserved-at-capacity"),
        pytest.param(999, "A", False, id="custom-glyph-frees-number"),
        pytest.param(999, "", False, id="hidden-glyph-frees-number"),
    ],
)
def test_automatic_number_exhaustion(
    renderer: Callable[..., str], count: int, explicit: str | None, exhausted: bool
) -> None:
    rows = [f'room r{i:04} "" 5x5 root' for i in range(count)]
    if explicit is not None:
        rows.append(f'room fixed "" 5x5 root glyph="{explicit}"')
    building = parse("\n".join(rows))
    for i, room in enumerate(building.rooms):
        room.x, room.y = i * 5, 0
    if exhausted:
        with pytest.raises(RenderError, match="automatic numbers exhausted") as exc:
            renderer(building)
        assert exc.value.line == count
        assert f"'r{count - 1:04}'" in exc.value.message
        assert "3 characters" in exc.value.message
        assert 'nonnumeric custom glyphs or glyph=""' in exc.value.message
    else:
        assert renderer(building)


@pytest.mark.parametrize(
    ("glyph", "automatic"),
    [
        ("01", "2"),
        ("0", "1"),
        ("001", "2"),
        ("\u0661", "1"),
        ("²", "1"),
        ("+1", "1"),
        ("1a", "1"),
        ("", "1"),
    ],
    ids=[
        "leading-zero",
        "zero",
        "two-zeros",
        "unicode-decimal",
        "unicode-digit",
        "sign",
        "mixed",
        "suppressed",
    ],
)
def test_custom_number_reservation(glyph: str, automatic: str) -> None:
    source = f'room a "Auto" 5x5 root\nroom z "Z" 5x5 root glyph="{glyph}"'
    assert f"{automatic}=a" in ascii_of(source).split("\n\n")[1].split()
    root = ET.fromstring(svg_of(source))
    assert text_by_room(root, "a").text == automatic
    if glyph:
        assert text_by_room(root, "z").text == glyph


@pytest.mark.parametrize("reverse", [False, True], ids=["forward", "reverse"])
def test_name_order_handles_empty_casefolded_and_duplicate_names(reverse: bool) -> None:
    rows = [
        'room z "" 5x5 root',
        'room a "" 5x5 root',
        'room y "alpha" 5x5 root',
        'room b "ALPHA" 5x5 root',
        'room x "Straße" 5x5 root',
        'room c "STRASSE" 5x5 root',
    ]
    source = "\n".join(reversed(rows) if reverse else rows)
    assert ascii_of(source).split("\n\n")[1] == "1=a  2=z  3=b  4=y  5=c  6=x"


@pytest.mark.parametrize(
    "block_glyph", [None, "2", ""], ids=["auto", "explicit", "hidden"]
)
def test_blocks_exterior_and_components_share_numbering(
    block_glyph: str | None,
) -> None:
    modifier = "" if block_glyph is None else f' glyph="{block_glyph}"'
    source = (
        'room member "Aardvark" 5x5 root glyph="1"\n'
        'room wing "" 5x5 right-of member glyph="3"\n'
        f'block z "Beta" member wing{modifier}\n'
        'room y "Alpha" 5x5 root exterior\n'
        'room x "Gamma" 5x5 root\n'
        'room hidden "" 5x5 root glyph=""'
    )
    block_number = "2" if block_glyph is None else block_glyph
    last = "3" if block_number else "2"
    legend = f"1=y  2=z  {last}=x" if block_number else f"1=y  {last}=x"
    rendered = ascii_of(source)
    assert rendered.split("\n\n")[1] == legend
    assert rendered.splitlines()[0].split()[:2] == [block_number or "_"] * 2
    root = ET.fromstring(svg_of(source))
    assert text_by_room(root, "y").text == "1"
    assert text_by_room(root, "x").text == last
    assert [t.text for t in root.iter(tag("text")) if t.get("data-block")] == (
        [block_number] if block_number else []
    )


def test_numeric_key_interleaves_reservations_before_custom_glyphs() -> None:
    custom = ["9", "10", "100", "01", "1", "0", "Z", "Ab", "a", "\u0661"]
    source = "\n".join(
        [
            *(
                f'room r{i} "R{i}" 5x5 root glyph="{glyph}"'
                for i, glyph in enumerate(custom)
            ),
            *(f'room a{i:02} "Auto{i:02}" 5x5 root' for i in range(10)),
        ]
    )
    expected = [
        "0",
        "01",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "10",
        "11",
        "12",
        "13",
        "100",
        "Ab",
        "Z",
        "a",
        "\u0661",
    ]
    assert [
        entry.split("=")[0] for entry in ascii_of(source).split("\n\n")[1].split()
    ] == expected
    root = ET.fromstring(svg_of(source))
    assert [
        group[0].text for group in root.findall('.//{*}g[@class="key"]')
    ] == expected


# Explicit multi-char glyphs ("12", "1"), an automatic one (hall -> 2), and an
# unlabeled room (store, glyph="") together in one small plan.
GLYPHS = (
    'room cells "Prison Cells" 20x10 root glyph="12"\n'
    'room guard "Guard Post" 10x10 right-of cells glyph="1"\n'
    'room store "" 10x10 right-of guard glyph=""\n'
    'room hall "Hall" 40x10 down-of cells'
)

GLYPHS_ASCII = """\
12 12 12 12 1  1  _  _
12 12 12 12 1  1  _  _
2  2  2  2  2  2  2  2
2  2  2  2  2  2  2  2

1=guard  2=hall  12=cells"""


def test_explicit_glyphs_pad_the_grid_and_fill_the_legend() -> None:
    # Cells pad to the widest glyph, the unlabeled room fills with '_' and has
    # no legend entry, and the legend sorts numerically.
    assert ascii_of(GLYPHS) == GLYPHS_ASCII


def test_automatic_glyphs_avoid_explicit_ones() -> None:
    # A nonnumeric custom glyph leaves the automatic sequence starting at 1.
    text = 'room beta "" 10x10 root glyph="A"\nroom alpha "" 10x10 right-of beta'
    legend = ascii_of(text).split("\n\n")[1]
    assert "A=beta" in legend
    assert "1=alpha" in legend


def test_explicit_glyph_is_rendered_in_the_svg_room_and_key() -> None:
    root = ET.fromstring(svg_of(GLYPHS))
    assert text_by_room(root, "cells").text == "12"
    key_lines = [
        "  ".join(span.text or "" for span in t)
        for t in root.iter(tag("g"))
        if t.get("class") == "key"
    ]
    assert key_lines == ["1  Guard Post", "2  Hall", "12  Prison Cells"]


def test_unlabeled_room_keeps_its_walls_but_has_no_svg_label() -> None:
    root = ET.fromstring(svg_of(GLYPHS))
    assert wall_lines(root)
    with pytest.raises(AssertionError):
        text_by_room(root, "store")


@pytest.mark.parametrize(
    ("glyph", "expected_font"),
    [
        ("9", 6.0),  # single character: 60% of the shorter dimension
        ("123", 4.286),  # shrink wide labels to fit the room
        ("WWW", 3.0),  # wide custom labels shrink to fit
    ],
)
def test_svg_glyph_font_shrinks_to_fit_the_room_width(
    glyph: str, expected_font: float
) -> None:
    root = ET.fromstring(svg_of(f'room a "" 10x30 root glyph="{glyph}"'))
    assert float(text_by_room(root, "a").get("font-size", "")) == expected_font


def test_glyph_with_xml_specials_is_escaped() -> None:
    root = ET.fromstring(svg_of('room a "" 20x20 root glyph="A&b"'))  # parses = escaped
    assert text_by_room(root, "a").text == "A&b"


def test_block_explicit_glyph_labels_the_union() -> None:
    text = L_BLOCK.replace(
        'block hall "Great Hall"', 'block hall "Great Hall" glyph="19"'
    )
    assert ascii_of(text).split("\n\n")[1] == "19=hall"
    root = ET.fromstring(svg_of(text))
    block_glyphs = [t for t in root.iter(tag("text")) if t.get("data-block") == "hall"]
    assert [t.text for t in block_glyphs] == ["19"]


def test_unlabeled_block_draws_no_glyph_and_no_key_line() -> None:
    text = L_BLOCK.replace('block hall "Great Hall"', 'block hall "" glyph=""')
    assert ascii_of(text).split("\n\n")[1] == ""
    root = ET.fromstring(svg_of(text))
    assert [t for t in root.iter(tag("text")) if t.get("data-block")] == []


# --- stairs ----------------------------------------------------------------
#
# A 30x30 room at the origin; the default footprint is (10, 10, 10, 5) for a
# horizontal run and (10, 10, 5, 10) for a vertical one (centered, one square
# across the run, two along it). Hard sides use the wall stroke (0.5); treads
# use the thin stroke (0.25), cross the run every third of a grid square ends
# included, and narrow toward the down= end.

STAIR_ROOM = 'room hall "Hall" 30x30 root\n'

WALL = "0.5"
TREAD = "0.25"


def stair_lines(text: str, stroke: str) -> list[tuple[float, float, float, float]]:
    root = ET.fromstring(svg_of(text))
    groups = [g for g in root.iter(tag("g")) if g.get("class") == "stairs"]
    assert len(groups) == 1
    return [
        (
            float(line.get("x1", "0")),
            float(line.get("y1", "0")),
            float(line.get("x2", "0")),
            float(line.get("y2", "0")),
        )
        for line in groups[0].iter(tag("line"))
        if line.get("stroke-width") == stroke
    ]


def test_up_stairs_are_open_on_the_downhill_side() -> None:
    edges = stair_lines(STAIR_ROOM + "stairs up hall down=right", WALL)
    assert (10, 10, 20, 10) in edges  # north flank
    assert (10, 15, 20, 15) in edges  # south flank
    assert (10, 10, 10, 15) in edges  # closed far (west) end
    assert (20, 10, 20, 15) not in edges  # entrance opens at the downhill end


def test_down_stairs_are_open_at_the_top_end() -> None:
    edges = stair_lines(STAIR_ROOM + "stairs down hall down=right", WALL)
    assert (20, 10, 20, 15) in edges  # closed far (east) end
    assert (10, 10, 10, 15) not in edges  # entrance opens at the high end


def test_in_steps_are_open_at_both_ends() -> None:
    edges = stair_lines(STAIR_ROOM + "stairs in hall down=right", WALL)
    assert (10, 10, 20, 10) in edges
    assert (10, 15, 20, 15) in edges
    assert (10, 10, 10, 15) not in edges
    assert (20, 10, 20, 15) not in edges


def test_treads_narrow_toward_the_downhill_end() -> None:
    # Run is 10 ft east; treads shrink linearly from 80% of the 5 ft breadth
    # at the high (west) end to 40% at the low end, centered on y=12.5. The
    # closed west end has no tread (the hard edge draws that line); the open
    # east end gets the narrowest tread, marking the entrance.
    # Ratios apply to the visible breadth between the flank walls' inner
    # faces: 5 ft minus the 0.5 ft wall stroke = 4.5 ft. A 10-ft run has six
    # tread intervals (three per square); the closed west end has no tread.
    treads = stair_lines(STAIR_ROOM + "stairs up hall down=right", TREAD)
    assert treads == [
        (11.667, 11.075, 11.667, 13.925),  # scale 0.633
        (13.333, 11.225, 13.333, 13.775),  # scale 0.567
        (15, 11.375, 15, 13.625),  # scale 0.5
        (16.667, 11.525, 16.667, 13.475),  # scale 0.433
        (18.333, 11.675, 18.333, 13.325),  # scale 0.367
        (20, 11.825, 20, 13.175),  # scale 0.3, at the open end
    ]


def test_in_steps_have_treads_at_both_ends_never_flank_to_flank() -> None:
    treads = stair_lines(STAIR_ROOM + "stairs in hall down=right", TREAD)
    # The broadest tread (the open high end) still stops short of the
    # flanks, so it cannot be mistaken for a solid boundary.
    assert (10, 10.925, 10, 14.075) in treads  # scale 0.7 at the open high end
    assert (20, 11.825, 20, 13.175) in treads  # scale 0.3 at the open low end
    assert (10, 10, 10, 15) not in treads


def test_tread_count_scales_with_run_length() -> None:
    # Three intervals per square: a 15-ft run has nine; the closed east end
    # contributes no tread, the open west entrance does.
    treads = stair_lines(
        STAIR_ROOM + "stairs down hall down=right size=15x5 at=5,10", TREAD
    )
    assert len(treads) == 9


def test_vertical_run_treads() -> None:
    # down=up: the low end is north, so treads narrow toward smaller y; the
    # north entrance is open and gets the end tread, the south end is closed.
    treads = stair_lines(STAIR_ROOM + "stairs up hall down=up", TREAD)
    assert treads == [
        (11.825, 10, 13.175, 10),  # scale 0.3, at the open north end
        (11.675, 11.667, 13.325, 11.667),  # scale 0.367
        (11.525, 13.333, 13.475, 13.333),  # scale 0.433
        (11.375, 15, 13.625, 15),  # scale 0.5
        (11.225, 16.667, 13.775, 16.667),  # scale 0.567
        (11.075, 18.333, 13.925, 18.333),  # scale 0.633
    ]


def test_glyph_moves_off_the_stairs() -> None:
    # The centered footprint blocks the room center; the glyph settles in the
    # largest free band (below the stairs) at that band's size.
    root = ET.fromstring(svg_of(STAIR_ROOM + "stairs up hall down=right"))
    label = text_by_room(root, "hall")
    assert (label.get("x"), label.get("y")) == ("15", "22.5")
    assert label.get("font-size") == "9"


def test_glyph_settles_between_two_stairs() -> None:
    text = (
        'room landing "Landing" 20x20 root\n'
        "stairs up landing down=right at=0,0\n"
        "stairs down landing down=right at=10,15"
    )
    label = text_by_room(ET.fromstring(svg_of(text)), "landing")
    assert (label.get("x"), label.get("y")) == ("10", "10")
    assert label.get("font-size") == "6"


def test_block_glyph_avoids_stairs_in_its_member() -> None:
    # The block glyph is drawn in 'main'; stairs there push it aside.
    text = (
        'room main "" 30x30 root\n'
        'room wing "" 10x10 down-of main\n'
        'block hall "Great Hall" main wing\n'
        "stairs up main down=right"
    )
    root = ET.fromstring(svg_of(text))
    label = next(t for t in root.iter(tag("text")) if t.get("data-block") == "hall")
    assert (label.get("x"), label.get("y")) == ("15", "22.5")


def test_ascii_omits_stairs() -> None:
    text = 'room a "A" 10x10 root'
    with_stairs = text + "\nstairs up a down=down size=5x5 at=0,0"
    assert ascii_of(with_stairs) == ascii_of(text)


# --- dividers ---------------------------------------------------------------
#
# A split chamber: 'low' (40x20 at the origin) over 'high' (40x10), one
# block; the divider marks the suppressed boundary at y=20 as a dashed
# tread-thin line (class="divider"), cut where a stair entrance meets it.

SPLIT_CHAMBER = (
    'room low "" 40x20 root\n'
    'room high "" 40x10 down-of low\n'
    'block chamber "Chamber" low high\n'
    "divider low high"
)


def divider_lines(root: ET.Element) -> list[tuple[float, ...]]:
    return [
        tuple(float(ln.get(k, "")) for k in ("x1", "y1", "x2", "y2"))
        for ln in root.iter(tag("line"))
        if ln.get("class") == "divider"
    ]


def test_divider_renders_as_one_dashed_thin_line() -> None:
    root = ET.fromstring(svg_of(SPLIT_CHAMBER))
    assert divider_lines(root) == [(0.0, 20.0, 40.0, 20.0)]
    line = next(ln for ln in root.iter(tag("line")) if ln.get("class") == "divider")
    assert line.get("stroke-dasharray") is not None
    assert line.get("stroke-width") == "0.25"


def test_divider_is_cut_at_a_stair_entrance() -> None:
    # The flight tops out on the boundary (x 15-25): the line stops either
    # side of the open end, so the symbol still reads as an 'in' flight.
    text = f"{SPLIT_CHAMBER}\nstairs in low down=up size=10x10 at=15,10"
    assert divider_lines(ET.fromstring(svg_of(text))) == [
        (0.0, 20.0, 15.0, 20.0),
        (25.0, 20.0, 40.0, 20.0),
    ]


def test_divider_only_adds_its_own_lines() -> None:
    # Every other line in the drawing (grid, outline, doors) is untouched.
    without = ET.fromstring(svg_of("\n".join(SPLIT_CHAMBER.splitlines()[:-1])))
    with_divider = ET.fromstring(svg_of(SPLIT_CHAMBER))

    def others(root: ET.Element) -> list[dict[str, str]]:
        return [
            ln.attrib for ln in root.iter(tag("line")) if ln.get("class") != "divider"
        ]

    assert others(with_divider) == others(without)


def test_divider_does_not_change_the_ascii_rendering() -> None:
    without = "\n".join(SPLIT_CHAMBER.splitlines()[:-1])
    assert ascii_of(SPLIT_CHAMBER) == ascii_of(without)


def test_ascii_renders_packed_components_with_a_gap() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 root'
    assert ascii_of(text) == ("1 1 . . 2 2\n1 1 . . 2 2\n\n1=a  2=b")


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


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            'room a "A" 30x20 root\nroom b "B" 20x30 right-of a shift=5 DOOR',
            id="relation",
        ),
        pytest.param(
            'room a "A" 30x20 root\nroom b "B" 20x30 down-of a shift=15 no-door\nDOOR a b',
            id="standalone",
        ),
        pytest.param('room a "A" 15x20 root\nDOOR a outside up', id="external"),
        pytest.param(
            'room a "A" 30x20 root\nroom b "B" 20x30 root\nlink b right-of a shift=5 DOOR',
            id="link",
        ),
    ],
)
@pytest.mark.parametrize(
    "kind", ["", " open", " secret"], ids=["solid", "open", "secret"]
)
def test_auto_door_svg_matches_explicit_full_span(source: str, kind: str) -> None:
    assert svg_of(source.replace("DOOR", f"door=?{kind}")) == svg_of(
        source.replace("DOOR", f"door=15{kind}")
    )


@pytest.mark.parametrize("blocked", [False, True], ids=["separate", "block"])
@pytest.mark.parametrize("door", ["", " no-door", " door open", " door secret"])
def test_exterior_walls_and_labels(blocked: bool, door: str) -> None:
    source = (
        'room hall "Hall" 20x20 root\n'
        f'room patio "" 30x20 exterior down-of hall{door}\n'
        'room lawn "" 20x20 exterior right-of patio\n'
    )
    if blocked:
        source += 'block garden "Garden" patio lawn'
    building = solve(parse(source))
    svg = ET.fromstring(render_svg(building))
    ns = {"s": "http://www.w3.org/2000/svg"}
    for room_id in ("patio", "lawn"):
        assert svg.findall(f'.//s:rect[@data-room="{room_id}"]', ns) == []
        assert svg.findall(f'.//s:line[@data-room="{room_id}"]', ns) == []
    walls = svg.findall('.//s:line[@class="wall exterior"]', ns)
    assert len(walls) == (5 if door == " door open" else 4)
    assert svg.findall('.//s:line[@class="wall interior"]', ns) == []
    for wall in walls:
        assert wall.attrib["stroke-width"] == "0.8"
        assert all(
            0 <= float(wall.attrib[key]) <= 20 for key in ("x1", "x2", "y1", "y2")
        )
    assert ("Garden" in render_svg(building)) == blocked
    assert "patio" in render_ascii(building) or "garden" in render_ascii(building)


@pytest.mark.parametrize(
    ("side", "expected"),
    [
        ("up", [(5, -0.25, 10, -0.25), (5, 0.25, 10, 0.25)]),
        ("down", [(5, 19.75, 10, 19.75), (5, 20.25, 10, 20.25)]),
        ("left", [(-0.25, 5, -0.25, 10), (0.25, 5, 0.25, 10)]),
        ("right", [(19.75, 5, 19.75, 10), (20.25, 5, 20.25, 10)]),
    ],
    ids=["up", "down", "left", "right"],
)
@pytest.mark.parametrize("block", [False, True], ids=["room", "block"])
@pytest.mark.parametrize("background", ["white", "#e0e0e0", "#222"])
def test_window_double_lines(
    side: str, expected: list[tuple[float, ...]], block: bool, background: str
) -> None:
    source = 'room a "" 20x20 root\n' + ('block hall "" a\n' if block else "")
    building = solve(parse(source + f"window a outside {side}"))
    root = ET.fromstring(render_svg(building, background=background))
    fills = root.findall('.//{*}line[@class="window-fill"]')
    assert len(fills) == 1
    assert fills[0].attrib["stroke"] == background
    assert fills[0].attrib["stroke-width"] == "0.5"
    marks = root.findall('.//{*}line[@class="window"]')
    assert [
        tuple(float(mark.attrib[key]) for key in ("x1", "y1", "x2", "y2"))
        for mark in marks
    ] == expected
    assert all(mark.attrib["stroke-width"] == "0.25" for mark in marks)
    assert not root.findall('.//{*}rect[@data-room="a"]')
    assert render_ascii(building) == ascii_of(source)


def test_windows_on_colored_background_golden() -> None:
    source = Path("tests/fixtures/layouts/windows.porta").read_text()
    expected = Path("tests/fixtures/windows-background.svg").read_text()
    assert render_svg(solve(parse(source)), background="#e0e0e0") == expected


@pytest.mark.parametrize(
    "glyph", ["1", "7", "0", "10", "99", "100", "WWW", "庭", "\u0301"]
)
@pytest.mark.parametrize("size", [5, 10, 100], ids=["tiny", "small", "large"])
def test_default_labels_are_proportional_and_fit(glyph: str, size: int) -> None:
    from porta.render import _text_width

    root = ET.fromstring(svg_of(f'room a "" {size}x{size} root glyph="{glyph}"'))
    label = text_by_room(root, "a")
    font = float(label.attrib["font-size"])
    assert font <= size * 0.6
    if glyph in ("1", "7", "0"):
        assert font == size * 0.6
    assert font * _text_width(glyph) <= size * 0.9 + 0.002
    assert root.attrib["font-family"] == "Palatino, Georgia, Times New Roman, serif"
    assert root.attrib["font-weight"] == "400"
    assert all(node.get("font-weight", "400") == "400" for node in root.iter())
    assert "paint-order" not in label.attrib
    assert "stroke" not in label.attrib


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            'room a "" 10x10 root\nroom b "" 10x10 root',
            "M0 0h10v10h-10z M20 0h10v10h-10z",
        ),
        (
            'room a "" 20x10 root\nroom b "" 10x10 down-of a',
            "M0 0h20v10h-20z M0 10h10v10h-10z",
        ),
        ('room a "" 10x10 exterior root', "M0 0h10v10h-10z"),
    ],
    ids=["component-gutter", "courtyard-void", "declared-outdoors"],
)
def test_grid_is_clipped_to_exact_room_union(source: str, expected: str) -> None:
    root = ET.fromstring(svg_of(source))
    grid = root.find('.//{*}g[@class="grid"]')
    clip = root.find('.//{*}clipPath[@id="plan-grid"]/{*}path')
    assert grid is not None
    assert clip is not None
    assert grid.attrib["clip-path"] == "url(#plan-grid)"
    assert clip.attrib["d"] == expected
    assert grid.attrib["stroke-width"] == "0.125"
    assert grid.attrib["stroke"] == "black"
    assert grid.attrib["opacity"] == "0.23"


@pytest.mark.parametrize(
    ("count", "width"),
    [(0, 20), (1, 5), (10, 150), (11, 150), (42, 150), (42, 20)],
    ids=["empty", "tiny", "short", "medium", "large", "narrow"],
)
def test_key_columns_preserve_order_and_readable_size(count: int, width: int) -> None:
    from porta.render import _key_layout

    entries = [(str(i), f"Room {i}") for i in range(count)]
    layout = _key_layout(entries, width)
    assert [e.glyph for e in layout.entries] == [e[0] for e in entries]
    assert len({e.x for e in layout.entries}) <= count
    for entry in layout.entries:
        assert 0 < entry.y < layout.height
        assert 0 < entry.x <= layout.width


@pytest.mark.parametrize(
    "name",
    ["Élodie\u2019s bibliothèque — northern archive", "W" * 40, "庭園" * 20],
    ids=["word-boundaries", "unbroken-token", "wide-unicode"],
)
def test_wrapped_key_names_keep_hanging_alignment_and_space(name: str) -> None:
    from porta.style import DEFAULT_STYLE
    from porta.text_metrics import text_bounds

    source = f'room a "{name}" 20x20 root glyph="100"\nroom b "Next" 20x20 down-of a'
    root = ET.fromstring(svg_of(source))
    keys = root.findall('.//{*}g[@class="key"]')
    wrapped = next(key for key in keys if key[0].text == "100")
    rows = list(wrapped)[1:]
    assert len(rows) > 1
    assert "".join(row.text or "" for row in rows).replace(" ", "") == name.replace(
        " ", ""
    )
    positions = [float(row.attrib["x"]) + text_bounds(row.text or "").x for row in rows]
    assert max(positions) - min(positions) < 0.002
    _, top, _, height = map(float, root.attrib["viewBox"].split())
    assert float(rows[-1].attrib["y"]) + DEFAULT_STYLE["key"]["font_ft"] < top + height


def test_wrapped_entries_reserve_height_and_reduce_columns() -> None:
    from porta.render import _key_layout

    entries = [(str(i), "W" * 40) for i in range(42)]
    layout = _key_layout(entries, 140)
    assert len({entry.x for entry in layout.entries}) == 2
    for previous, current in zip(layout.entries, layout.entries[1:], strict=False):
        if previous.x == current.x:
            assert current.y - previous.y >= len(previous.names) * 4


def test_scale_bar_survives_no_key() -> None:
    root = ET.fromstring(svg_of('room a "" 10x10 root glyph=""'))
    assert root.findall('.//{*}g[@class="key"]') == []
    scale = root.find('.//{*}g[@class="scale"]')
    assert scale is not None
    assert [mark.text for mark in scale.iter(tag("text"))] == [
        "0",
        "10",
        "20 ft",
        "5-ft squares",
    ]
    assert len(scale.findall(tag("rect"))) == 2


def test_key_and_scale_share_five_foot_type() -> None:
    root = ET.fromstring(svg_of(TWO))
    groups = [g for g in root.iter(tag("g")) if g.get("class") in ("key", "scale")]
    assert groups
    assert all(g.attrib["font-size"] == "5" for g in groups)


@pytest.mark.parametrize("columns", [1, 2])
def test_visible_key_bounds_are_centered_despite_font_bearings(
    columns: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from porta import render
    from porta.key_layout import candidates
    from porta.text_metrics import TextBounds

    building = solve(parse('room a "" 100x80 root glyph="1"'))
    entries = [("1", "Short"), ("100", "Wide"), ("Ab", "Other")]
    metrics = {
        "1": TextBounds(0.4, -4, 2, 5),
        "100": TextBounds(-0.2, -4, 7, 5),
        "Ab": TextBounds(0.1, -4, 6, 5),
        "Short": TextBounds(0.3, -4, 13, 5),
        "Wide": TextBounds(-0.4, -4, 50, 5),
        "Other": TextBounds(0.7, -4, 20, 5),
        "0": TextBounds(0.2, -4, 2, 5),
        "10": TextBounds(-0.1, -4, 4, 5),
        "20 ft": TextBounds(0.3, -4, 10, 5),
        "5-ft squares": TextBounds(0.6, -4, 30, 5),
    }
    choice = candidates(entries, 100, metrics, wrap=False)[columns - 1]
    monkeypatch.setattr(render, "choose_layout", lambda *args, **kwargs: choice)
    monkeypatch.setattr(render, "text_bounds", lambda text, size=5: metrics[text])
    root = ET.fromstring(render.render_svg(building))
    boxes = [
        (
            float(text.attrib["x"]) + metrics[text.text or ""].x,
            metrics[text.text or ""].width,
        )
        for group in root.findall('.//{*}g[@class="key"]')
        for text in group
    ]
    left = min(x for x, _ in boxes)
    right = max(x + width for x, width in boxes)
    assert (left + right) / 2 == pytest.approx(50, abs=0.002)
    assert right - left == pytest.approx(choice.width, abs=0.002)
    caption = next(
        t
        for t in root.findall('.//{*}g[@class="scale"]/{*}text')
        if t.text == "5-ft squares"
    )
    assert caption is not None
    assert float(caption.attrib["x"]) + 0.6 + 30 / 2 == pytest.approx(50, abs=0.002)


@pytest.mark.parametrize(
    "source",
    [
        'room a "Store" 5x5 root',
        'room a "" 10x10 root glyph=""',
        'room a "Hall" 30x20 root\nroom b "Wing" 20x30 left-of a shift=-10',
    ],
    ids=["tiny", "no-key", "negative-coordinates"],
)
def test_scale_bar_geometry_and_furniture_bounds(source: str) -> None:
    from porta.text_metrics import text_bounds

    building = solve(parse(source))
    root = ET.fromstring(render_svg(building))
    scale = root.find('.//{*}g[@class="scale"]')
    assert scale is not None
    segments = scale.findall(tag("rect"))
    assert [s.attrib["fill"] for s in segments] == ["black", "white"]
    assert [float(s.attrib["width"]) for s in segments] == [10, 10]
    start = float(segments[0].attrib["x"])
    assert float(segments[1].attrib["x"]) == start + 10
    placed = [(r, r.x, r.y) for r in building.rooms]
    assert all(x is not None and y is not None for _, x, y in placed)
    left = min(x for _, x, _ in placed if x is not None)
    right = max(x + r.width for r, x, _ in placed if x is not None)
    bottom = max(y + r.height for r, _, y in placed if y is not None)
    assert start + 10 == (left + right) / 2
    assert (
        float(segments[0].attrib["y"]) + float(segments[0].attrib["height"])
        == bottom + 12
    )
    texts = scale.findall(tag("text"))
    assert [t.text for t in texts] == ["0", "10", "20 ft", "5-ft squares"]
    for text, expected in zip(texts[:3], [start, start + 10, start + 20], strict=True):
        bounds = text_bounds(text.text or "")
        assert float(text.attrib["x"]) + bounds.x + bounds.width / 2 == pytest.approx(
            expected, abs=0.001
        )
    vx, vy, vw, vh = map(float, root.attrib["viewBox"].split())
    for text in texts:
        bounds = text_bounds(text.text or "")
        x, y = float(text.attrib["x"]), float(text.attrib["y"])
        assert vx <= x + bounds.x <= x + bounds.x + bounds.width <= vx + vw
        assert vy <= y + bounds.y <= y + bounds.y + bounds.height <= vy + vh
        assert y + bounds.y > bottom
    caption_y = float(texts[-1].attrib["y"])
    keys = root.findall('.//{*}g[@class="key"]/{*}text')
    if keys:
        assert min(float(t.attrib["y"]) for t in keys) - caption_y == 12


def test_renderer_uses_resolved_defaults(monkeypatch: pytest.MonkeyPatch) -> None:

    from porta import render
    from porta.style import DEFAULT_STYLE

    building = solve(parse(TWO))
    original = render_svg(building)
    style = deepcopy(DEFAULT_STYLE)
    style["page"]["background"] = "#fff8e7"
    style["typography"]["text_color"] = "#654321"
    style["page"]["line_color"] = "#332211"
    style["typography"]["font_family"] = '"Example Serif", serif'
    style["grid"]["spacing_ft"] = 10
    style["scale_bar"]["length_ft"] = 40
    style["key"]["font_ft"] = 7
    style["key"]["identifier_gap_ft"] = 4
    style["key"]["column_gap_ft"] = 9
    style["page"]["display_scale"] = 12
    with monkeypatch.context() as patched:
        patched.setattr(render, "DEFAULT_STYLE", style)
        custom = ET.fromstring(render_svg(building))
    assert custom.attrib["font-family"] == '"Example Serif", serif'
    backdrop = custom.find(tag("rect"))
    assert backdrop is not None
    assert backdrop.attrib["fill"] == "#fff8e7"
    for text in custom.findall(".//{*}text[@data-room]"):
        assert text.attrib["fill"] == "#654321"
    scale = custom.find('.//{*}g[@class="scale"]')
    assert scale is not None
    assert scale.attrib["font-size"] == "7"
    assert [t.text for t in scale.findall(tag("text"))] == [
        "0",
        "20",
        "40 ft",
        "10-ft squares",
    ]
    assert [float(r.attrib["width"]) for r in scale.findall(tag("rect"))] == [20, 20]
    assert [float(r.attrib["height"]) for r in scale.findall(tag("rect"))] == [2.1, 2.1]
    assert [float(r.attrib["stroke-width"]) for r in scale.findall(tag("rect"))] == [
        0.28,
        0.28,
    ]
    grid = custom.find('.//{*}g[@class="grid"]')
    assert grid is not None
    assert len(grid.findall(tag("line"))) == 7  # 4 verticals + 3 horizontals
    before = ET.fromstring(original)
    assert wall_lines(custom) == wall_lines(before)
    assert render_svg(building) == original
    monkeypatch.setattr(render, "DEFAULT_STYLE", style)
    overridden = ET.fromstring(render_svg(building, background="white"))
    background = overridden.find(tag("rect"))
    assert background is not None
    assert background.attrib["fill"] == "white"


@pytest.mark.parametrize("font_size", [3, 8])
def test_key_metrics_follow_default_size(
    font_size: int, monkeypatch: pytest.MonkeyPatch
) -> None:

    from porta import render
    from porta.style import DEFAULT_STYLE
    from porta.text_metrics import text_bounds

    style = deepcopy(DEFAULT_STYLE)
    style["key"]["font_ft"] = font_size
    style["key"]["identifier_gap_ft"] = 4
    style["key"]["column_gap_ft"] = 11
    source = 'room a "A long room name that needs wrapping" 10x10 root glyph="100"'
    monkeypatch.setattr(render, "DEFAULT_STYLE", style)
    root = ET.fromstring(render_svg(solve(parse(source))))
    key = root.find('.//{*}g[@class="key"]')
    assert key is not None
    assert float(key.attrib["font-size"]) == font_size
    glyph, *rows = list(key)
    glyph_bounds = text_bounds(glyph.text or "", font_size)
    glyph_right = float(glyph.attrib["x"]) + glyph_bounds.x + glyph_bounds.width
    for row in rows:
        bounds = text_bounds(row.text or "", font_size)
        assert float(row.attrib["x"]) + bounds.x - glyph_right == pytest.approx(
            4, abs=0.002
        )
    for first, second in pairwise(rows):
        assert float(second.attrib["y"]) - float(first.attrib["y"]) == pytest.approx(
            style["key"]["line_spacing_ft"], abs=0.002
        )


@pytest.mark.parametrize("background_override", [None, "#ddd"])
@pytest.mark.parametrize("fixture", ["windows-outdoor-auto", "secret-door"])
def test_symbols_share_style_colors(
    fixture: str, background_override: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:

    from porta import render
    from porta.style import DEFAULT_STYLE

    source = Path(f"tests/fixtures/layouts/{fixture}.porta").read_text()
    style = deepcopy(DEFAULT_STYLE)
    style["page"]["line_color"] = "#123456"
    style["page"]["background"] = "#ffeedd"
    monkeypatch.setattr(render, "DEFAULT_STYLE", style)
    root = ET.fromstring(
        render_svg(solve(parse(source)), background=background_override)
    )
    backdrop = background_override or style["page"]["background"]
    for mark in root.findall('.//{*}line[@class="window-fill"]'):
        assert mark.attrib["stroke"] == backdrop
    for kind in ("door", "secret", "open", "window"):
        for mark in root.findall(f'.//{{*}}line[@class="{kind}"]'):
            assert mark.attrib["stroke"] == "#123456"
    for marker in root.findall('.//{*}text[@class="secret"]'):
        assert marker.attrib["stroke"] == backdrop
        assert marker.get("fill", root.attrib["fill"]) == "#123456"
    halves = root.findall('.//{*}g[@class="scale"]/{*}rect')
    assert [half.attrib["fill"] for half in halves] == ["#123456", backdrop]


def test_grid_uses_shared_color_with_group_opacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    from porta import render
    from porta.style import DEFAULT_STYLE

    style = deepcopy(DEFAULT_STYLE)
    style["page"]["line_color"] = "#332211"
    style["grid"]["opacity"] = 0.4
    monkeypatch.setattr(render, "DEFAULT_STYLE", style)
    root = ET.fromstring(render_svg(solve(parse(TWO))))
    grid = root.find('.//{*}g[@class="grid"]')
    assert grid is not None
    assert grid.attrib["stroke"] == "#332211"
    assert grid.attrib["opacity"] == "0.4"
    # Composite the grid as a group so intersections do not become darker.
    assert all("opacity" not in line.attrib for line in grid)
    assert "opacity" not in root.attrib


def test_supplied_style_is_local_to_one_render(tmp_path: Path) -> None:
    from porta.style import load_style

    path = tmp_path / "style.json"
    path.write_text(
        '{"page": {"background": "#fff8e7", "line_color": "#332211"}, "key": {"font_ft": 6}, "scale_bar": {"length_ft": 40}}'
    )
    style = load_style(path)
    building = solve(parse(TWO))
    original = render_svg(building)
    root = ET.fromstring(render_svg(building, style=style))
    scale = root.find('.//{*}g[@class="scale"]')
    assert scale is not None
    assert scale.attrib["font-size"] == "6"
    assert [text.text for text in scale.findall(tag("text"))][:3] == [
        "0",
        "20",
        "40 ft",
    ]
    assert root.attrib["fill"] == "#332211"
    assert render_svg(building) == original
    overridden = ET.fromstring(render_svg(building, style=style, background="white"))
    background = overridden.find(tag("rect"))
    assert background is not None
    assert background.attrib["fill"] == "white"
    assert style["page"]["background"] == "#fff8e7"


@pytest.mark.parametrize("font_size", [3, 8], ids=["small-key", "large-key"])
def test_custom_styles_preserve_numeric_assignments_and_key_order(
    tmp_path: Path, font_size: int
) -> None:
    from porta.style import load_style

    style_path = tmp_path / "style.json"
    style_path.write_text(
        '{"labels": {"ratio": 0.4, "fit": 0.7}, '
        f'"key": {{"font_ft": {font_size}, "line_spacing_ft": 12}}, '
        '"typography": {"text_color": "#123456"}}'
    )
    source = (
        'room z "Atrium" 20x20 root\n'
        'room a "Library" 20x20 right-of z\n'
        'room m "Vault" 20x20 down-of z glyph="2"'
    )
    building = solve(parse(source))
    root = ET.fromstring(render_svg(building, style=load_style(style_path)))
    assert {rid: text_by_room(root, rid).text for rid in ("z", "m", "a")} == {
        "z": "1",
        "m": "2",
        "a": "3",
    }
    keys = root.findall('.//{*}g[@class="key"]')
    assert [key[0].text for key in keys] == ["1", "2", "3"]
    assert all(key.attrib["font-size"] == str(font_size) for key in keys)
    assert ascii_of(source).split("\n\n")[1] == "1=z  2=m  3=a"


@pytest.mark.parametrize(
    ("source", "legend"),
    [
        pytest.param(
            'room z "Atrium" 5x5 root\nroom a "Vault" 5x5 root',
            "A=a  Z=z",
            id="id-order-not-name-order",
        ),
        pytest.param(
            'room kitchen "A" 5x5 root\nroom kennel "Z" 5x5 root',
            "I=kitchen  K=kennel",
            id="id-contention",
        ),
        pytest.param(
            'room hall "Hall" 5x5 root\nroom z "Z" 5x5 root glyph="H"',
            "A=hall  H=z",
            id="reserve-later-explicit",
        ),
        pytest.param(
            'room a "" 5x5 root glyph="A"\nroom a-a "" 5x5 root',
            "A=a  B=a-a",
            id="fallback-skips-punctuation",
        ),
        pytest.param(
            'room a "" 5x5 root glyph="A"\nroom a1 "" 5x5 root',
            "1=a1  A=a",
            id="id-digit-and-numeric-key-order",
        ),
        pytest.param(
            'room main "" 5x5 root glyph="H"\n'
            'block hall "Hall" main\nroom z "" 5x5 root exterior',
            "H=hall  Z=z",
            id="members-suppressed-exterior-component",
        ),
        pytest.param(
            'room main "" 5x5 root\nblock hall "" main glyph="12"\n'
            'room a "" 5x5 root glyph=""\nroom z "" 5x5 root',
            "12=hall  Z=z",
            id="explicit-block-and-hidden-room",
        ),
    ],
)
def test_mnemonic_assignments_match_in_svg_and_ascii(source: str, legend: str) -> None:
    from porta.style import DEFAULT_STYLE

    style = deepcopy(DEFAULT_STYLE)
    style["labels"]["scheme"] = "mnemonic"
    for text in (source, "\n".join(reversed(source.splitlines()))):
        building = solve(parse(text))
        assert render_ascii(building, style=style).split("\n\n")[1] == legend
        root = ET.fromstring(render_svg(building, style=style))
        expected = dict(entry.split("=")[::-1] for entry in legend.split())
        assert {
            node.get("data-room") or node.get("data-block"): node.text
            for node in root.iter(tag("text"))
            if node.get("data-room") or node.get("data-block")
        } == expected
        assert [key[0].text for key in root.findall('.//{*}g[@class="key"]')] == list(
            expected.values()
        )
        assert render_ascii(building) == ascii_of(text)
        assert render_svg(building) == svg_of(text)


@pytest.mark.parametrize("renderer", [render_ascii, render_svg], ids=["ascii", "svg"])
@pytest.mark.parametrize("count", [36, 37], ids=["full", "exhausted"])
def test_mnemonic_pool_capacity(renderer: Callable[..., str], count: int) -> None:
    from porta.style import DEFAULT_STYLE

    style = deepcopy(DEFAULT_STYLE)
    style["labels"]["scheme"] = "mnemonic"
    building = solve(
        parse("\n".join(f'room r{i:02} "" 5x5 root' for i in range(count)))
    )
    if count == 36:
        assert renderer(building, style=style)
    else:
        with pytest.raises(RenderError, match="mnemonic glyphs exhausted") as exc:
            renderer(building, style=style)
        assert exc.value.line == 37
        assert 'labels.scheme="numeric"' in exc.value.message
        assert renderer(building)


@pytest.mark.parametrize(
    ("start", "reserved", "expected"),
    [
        pytest.param(10, "11", {"z": "10", "a": "12", "m": "11"}, id="skip-reserved"),
        pytest.param(
            10, "5", {"z": "10", "a": "11", "m": "5"}, id="explicit-below-start"
        ),
        pytest.param(
            10,
            "010",
            {"z": "11", "a": "12", "m": "010"},
            id="reserved-start-leading-zero",
        ),
        pytest.param(
            998, "0", {"z": "998", "a": "999", "m": "0"}, id="last-two-numbers"
        ),
    ],
)
def test_numeric_start_preserves_reservations_and_key_order(
    start: int, reserved: str, expected: dict[str, str]
) -> None:
    from porta.style import DEFAULT_STYLE

    style = deepcopy(DEFAULT_STYLE)
    style["labels"]["start"] = start
    source = (
        'room z "Atrium" 20x20 root\n'
        'room a "Library" 20x20 right-of z\n'
        f'room m "Vault" 20x20 down-of z glyph="{reserved}"'
    )
    building = solve(parse(source))
    entries = sorted(expected.items(), key=lambda item: int(item[1]))
    assert render_ascii(building, style=style).split("\n\n")[1] == "  ".join(
        f"{glyph}={eid}" for eid, glyph in entries
    )
    root = ET.fromstring(render_svg(building, style=style))
    assert {eid: text_by_room(root, eid).text for eid in expected} == expected
    assert [key[0].text for key in root.findall('.//{*}g[@class="key"]')] == [
        glyph for _, glyph in entries
    ]
    assert render_ascii(building) == ascii_of(source)
    assert DEFAULT_STYLE["labels"]["start"] == 1


@pytest.mark.parametrize("renderer", [render_ascii, render_svg], ids=["ascii", "svg"])
@pytest.mark.parametrize(
    ("start", "source", "exhausted"),
    [
        pytest.param(999, 'room a "" 5x5 root', False, id="last-number"),
        pytest.param(
            999, 'room a "" 5x5 root\nroom b "" 5x5 root', True, id="no-wraparound"
        ),
        pytest.param(
            999,
            'room a "" 5x5 root\nroom b "" 5x5 root glyph="999"',
            True,
            id="last-number-reserved",
        ),
        pytest.param(
            999,
            'room a "" 5x5 root glyph=""\nroom b "" 5x5 root',
            False,
            id="hidden-frees-last-number",
        ),
    ],
)
def test_start_near_numeric_limit(
    renderer: Callable[..., str], start: int, source: str, exhausted: bool
) -> None:
    from porta.style import DEFAULT_STYLE

    style = deepcopy(DEFAULT_STYLE)
    style["labels"]["start"] = start
    building = solve(parse(source))
    if exhausted:
        with pytest.raises(RenderError, match=r"lower labels\.start"):
            renderer(building, style=style)
    else:
        assert "999" in renderer(building, style=style)


def test_numeric_start_is_shared_by_blocks_and_components() -> None:
    from porta.style import DEFAULT_STYLE

    style = deepcopy(DEFAULT_STYLE)
    style["labels"]["start"] = 10
    building = solve(
        parse(
            'room member "" 5x5 root glyph="10"\n'
            'block b "Beta" member\n'
            'room a "Alpha" 5x5 root exterior\n'
            'room c "Charlie" 5x5 root\n'
            'room hidden "" 5x5 root glyph=""'
        )
    )
    assert render_ascii(building, style=style).split("\n\n")[1] == "10=a  11=b  12=c"
    root = ET.fromstring(render_svg(building, style=style))
    label = root.find('.//{*}text[@data-block="b"]')
    assert label is not None
    assert label.text == "11"
    assert text_by_room(root, "a").text == "10"
    assert text_by_room(root, "c").text == "12"


@pytest.mark.parametrize("key_visible", [False, True], ids=["no-key", "key"])
@pytest.mark.parametrize("scale_visible", [False, True], ids=["no-scale", "scale"])
@pytest.mark.parametrize("grid_visible", [False, True], ids=["no-grid", "grid"])
@pytest.mark.parametrize("glyph", ["", ' glyph=""'], ids=["labeled", "unlabeled"])
def test_optional_presentation_visibility(
    key_visible: bool, scale_visible: bool, grid_visible: bool, glyph: str
) -> None:
    from porta.style import DEFAULT_STYLE
    from porta.text_metrics import text_bounds

    building = solve(parse(f'room a "Hall" 5x5 root{glyph}'))
    before = deepcopy(building)
    default = ET.fromstring(render_svg(building))
    style = deepcopy(DEFAULT_STYLE)
    for group, visible in [
        ("key", key_visible),
        ("scale_bar", scale_visible),
        ("grid", grid_visible),
    ]:
        style[group]["visible"] = visible
    root = ET.fromstring(render_svg(building, style=style))
    assert building == before
    assert render_ascii(building, style=style) == render_ascii(building)
    assert bool(root.findall('.//{*}g[@class="key"]')) == (key_visible and not glyph)
    assert bool(root.findall('.//{*}g[@class="scale"]')) == scale_visible
    assert bool(root.findall('.//{*}g[@class="grid"]')) == grid_visible
    assert ("5-ft squares" in "".join(root.itertext())) == (
        scale_visible and grid_visible
    )
    # All map elements, including in-room labels, retain exact coordinates.
    for selector in (".//*[@data-room]", './/*[@class="wall exterior"]'):
        assert [(e.attrib, e.text) for e in root.findall(selector)] == [
            (e.attrib, e.text) for e in default.findall(selector)
        ]
    x, y, width, height = map(float, root.attrib["viewBox"].split())
    for element in root.findall(".//{*}g"):
        if element.get("class") not in ("key", "scale"):
            continue
        for text in element.findall("{*}text"):
            bounds = text_bounds(text.text or "", 5)
            left = float(text.attrib["x"]) + bounds.x
            top = float(text.attrib["y"]) + bounds.y
            assert x <= left
            assert left + bounds.width <= x + width + 0.001
            assert y <= top
            assert top + bounds.height <= y + height + 0.001
    if scale_visible:
        halves = root.findall('.//{*}g[@class="scale"]/{*}rect')
        assert sum(float(r.attrib["width"]) for r in halves) == 20
    if not key_visible and not scale_visible:
        assert (x, y, width, height) == (-10, -10, 25, 25)


@pytest.mark.parametrize(
    "columns", [1, 2, 3, 100], ids=["one", "two", "three", "capped"]
)
@pytest.mark.parametrize("width", [5, 100], ids=["narrow", "wide"])
def test_requested_key_columns_fit_without_changing_order(
    columns: int, width: int
) -> None:
    from porta.render import _key_layout
    from porta.style import DEFAULT_STYLE
    from porta.text_metrics import text_bounds

    entries = [
        ("1", "ExtraordinarilyLongUnbrokenName"),
        ("2", "The Great Dining Hall"),
        ("3", "Library"),
    ]
    style = deepcopy(DEFAULT_STYLE)
    style["key"]["columns"] = columns
    layout = _key_layout(entries, width, style)
    assert len({e.x for e in layout.entries}) == min(columns, len(entries))
    assert [e.glyph for e in layout.entries] == ["1", "2", "3"]
    for entry, (_, name) in zip(layout.entries, entries, strict=True):
        assert "".join(entry.names).replace(" ", "") == name.replace(" ", "")
        assert entry.x - text_bounds(entry.glyph, 5).width >= -0.001
        assert (
            entry.x + 2 + max(text_bounds(row, 5).width for row in entry.names)
            <= layout.width + 0.001
        )
        assert entry.y + (len(entry.names) - 1) * 8 <= layout.height
    building = solve(parse(DESIGN_MANOR))
    assert render_ascii(building, style=style) == render_ascii(building)
    root = ET.fromstring(render_svg(building, style=style))
    assert [e[0].text for e in root.findall('.//{*}g[@class="key"]')] == ["1", "2", "3"]


@pytest.mark.parametrize(
    ("name", "overrides"),
    [
        ("grid-off-columns", {"grid": {"visible": False}, "key": {"columns": 2}}),
        ("scale-only", {"key": {"visible": False}}),
        ("key-only", {"scale_bar": {"visible": False}, "key": {"columns": 1}}),
    ],
    ids=["grid-off-columns", "scale-only", "key-only"],
)
def test_presentation_goldens(
    name: str, overrides: dict[str, dict[str, bool | int]]
) -> None:
    from porta.style import DEFAULT_STYLE

    building = solve(
        parse(
            'room a "Extraordinarily Long Gallery" 15x10 root\n'
            'room b "The Great Dining Hall" 15x10 down-of a\n'
            'room c "Library" 15x10 down-of b'
        )
    )
    style = deepcopy(DEFAULT_STYLE)
    for group, values in overrides.items():
        style[group].update(values)
    expected = Path(f"tests/fixtures/presentation/{name}.svg").read_text()
    assert render_svg(building, style=style) + "\n" == expected
