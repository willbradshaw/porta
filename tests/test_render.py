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

from porta.layout import block_wall_segments, solve
from porta.parser import parse
from porta.render import render_ascii, render_svg


def ascii_of(text: str) -> str:
    return render_ascii(solve(parse(text)))


# Confidently hand-derived: entrance(E)/kitchen(K)/hall(H) on an 8x12 grid.
# 'hall' is pinned on both axes (x from right-of kitchen, y from down-of
# entrance) and shares a real wall with each.
DESIGN_MANOR = (
    'room entrance "Entrance Hall" 40x20 root\n'
    'room kitchen  "Kitchen"       20x40 down-of entrance\n'
    'room hall     "Great Hall"    20x20 right-of kitchen down-of entrance'
)

DESIGN_MANOR_ASCII = """\
E E E E E E E E
E E E E E E E E
E E E E E E E E
E E E E E E E E
K K K K H H H H
K K K K H H H H
K K K K H H H H
K K K K H H H H
K K K K . . . .
K K K K . . . .
K K K K . . . .
K K K K . . . .

E=entrance  H=hall  K=kitchen"""


def test_design_manor_renders_to_expected_grid() -> None:
    assert ascii_of(DESIGN_MANOR) == DESIGN_MANOR_ASCII


def test_empty_cells_use_dots() -> None:
    # A single 10x10 room is one cell with no empties; an L of two rooms has one.
    grid = ascii_of('room a "A" 20x10 root\nroom b "B" 10x10 down-of a').split("\n\n")[
        0
    ]
    assert "." in grid


def test_glyphs_are_mnemonic_first_with_tie_breaking() -> None:
    # Both want K; contention resolves by id order, so kennel takes K and kitchen
    # falls to its next letter, I — regardless of statement order.
    text = (
        'room kitchen "Kitchen" 10x10 root\nroom kennel "Kennel" 10x10 right-of kitchen'
    )
    legend = ascii_of(text).split("\n\n")[1]
    assert "K=kennel" in legend
    assert "I=kitchen" in legend


def test_legend_is_sorted_by_glyph() -> None:
    legend = ascii_of(DESIGN_MANOR).split("\n\n")[1]
    assert legend == "E=entrance  H=hall  K=kitchen"


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
. . . . . . . . . . . . . G G G G . . . . . . . . . . . .
. . . . . . . . . . . . . G G G G . . . . . . . . . . . .
. . . I I I I I I H H H H H H H H D D D D D D . . . . . .
. . . I I I I I I H H H H H H H H D D D D D D . . . . . .
B B B I I I I I I H H H H H H H H D D D D D D . . . . . .
B B B I I I I I I H H H H H H H H D D D D D D . . . . . .
B B B I I I I I I H H H H H H H H D D D D D D . . . . . .
. . . I I I I I I H H H H H H H H D D D D D D . . . . . .
. . . O O A A A A E E E E C C C C K K K K K K P P P . . .
. . . O O A A A A E E E E C C C C K K K K K K P P P L L L
. . . O O A A A A E E E E C C C C K K K K K K P P P L L L
. . . O O A A A A E E E E C C C C K K K K K K P P P L L L
. . . O O T T T T S R R . . . . . K K K K K K P P P . . .
. . . O O T T T T S R R . . . . . U U U U U U . . . . . .
. . . O O T T T T . . . . . . . . U U U U U U . . . . . .
. . . O O T T T T . . . . . . . . U U U U U U . . . . . .
. . . . . . . . . . . . . . . . . U U U U U U . . . . . .

A=parlour  B=turret  C=cloak  D=dining  E=entrance  G=gallery  H=hall  I=library  K=kitchen  L=larder  O=corridor  P=pantry  R=porch  S=passage  T=study  U=scullery"""


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
    vb_x, vb_y, vbw, vbh = (float(n) for n in view_box.split())
    # TWO's plan spans x[0,30], y[0,20]; the viewBox encloses it with at least a
    # margin on every side (it may be wider and centred to fit the key).
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


def test_room_rects_are_transparent_so_the_grid_shows_through() -> None:
    root = ET.fromstring(svg_of(TWO))
    room_rects = [r for r in root.iter(tag("rect")) if r.get("data-room")]
    assert room_rects
    assert all(r.get("fill") == "none" for r in room_rects)


def test_grid_has_a_line_every_five_feet_across_the_plan() -> None:
    # TWO spans x[0,30] (7 verticals) and y[0,20] (5 horizontals); door lines
    # (class="door") are excluded.
    root = ET.fromstring(svg_of(TWO))
    grid = [ln for ln in root.iter(tag("line")) if ln.get("class") != "door"]
    assert len(grid) == 7 + 5


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
        ("entrance", "E", (20.0, 10.0)),
        ("kitchen", "K", (10.0, 40.0)),
        ("hall", "H", (30.0, 30.0)),
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


def test_key_shows_names_not_dimensions() -> None:
    key_text = " ".join(
        t.text or "" for t in ET.fromstring(svg_of(DESIGN_MANOR)).iter(tag("text"))
    )
    assert "Entrance Hall" in key_text  # names are shown
    assert "ft)" not in key_text  # per-room dimensions are not


def test_unnamed_room_keys_as_just_its_glyph() -> None:
    root = ET.fromstring(svg_of('room a "" 20x30 root'))
    key_lines = [t.text for t in root.iter(tag("text")) if t.get("class") == "key"]
    assert key_lines == ["A"]  # glyph only: no name, no dimensions


def test_special_characters_in_names_are_escaped() -> None:
    # Raw & or < would make the document malformed; fromstring proves escaping.
    root = ET.fromstring(svg_of('room a "Hall & Co <X>" 20x20 root'))
    texts = [t.text for t in root.iter(tag("text"))]
    assert any(t is not None and "Hall & Co <X>" in t for t in texts)


def test_door_renders_as_a_door_line() -> None:
    root = ET.fromstring(svg_of('room a "A" 20x20 root\nroom b "B" 10x10 up-of a door'))
    door_lines = [ln for ln in root.iter(tag("line")) if ln.get("class") == "door"]
    assert len(door_lines) == 1
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


def walls_by_room(root: ET.Element, room_id: str) -> set[tuple[float, ...]]:
    return {
        tuple(float(ln.get(k, "")) for k in ("x1", "y1", "x2", "y2"))
        for ln in root.iter(tag("line"))
        if ln.get("data-room") == room_id
    }


def test_open_door_renders_as_one_dashed_line_and_no_door_mark() -> None:
    root = ET.fromstring(svg_of(OPEN_TWO))
    assert open_lines(root) == [(20.0, 0.0, 20.0, 20.0)]
    dashed = [ln for ln in root.iter(tag("line")) if ln.get("class") == "open"]
    assert dashed[0].get("stroke-dasharray") is not None
    assert [ln for ln in root.iter(tag("line")) if ln.get("class") == "door"] == []


def test_open_boundary_cuts_the_shared_wall_out_of_both_outlines() -> None:
    # Neither room is a plain rect any more; each outline omits the open span.
    root = ET.fromstring(svg_of(OPEN_TWO))
    assert [r for r in root.iter(tag("rect")) if r.get("data-room")] == []
    assert walls_by_room(root, "a") == {
        (0.0, 0.0, 20.0, 0.0),  # top
        (0.0, 20.0, 20.0, 20.0),  # bottom
        (0.0, 0.0, 0.0, 20.0),  # left; the right edge is fully open
    }
    assert walls_by_room(root, "b") == {
        (20.0, 0.0, 40.0, 0.0),
        (20.0, 20.0, 40.0, 20.0),
        (40.0, 0.0, 40.0, 20.0),
    }


def test_partial_opening_keeps_the_rest_of_the_wall() -> None:
    # A centred 10-ft archway: the shared edge keeps a 5-ft stub at each end.
    source = 'room a "A" 20x20 root\nroom b "Bee" 20x20 right-of a door=10 open'
    root = ET.fromstring(svg_of(source))
    assert open_lines(root) == [(20.0, 5.0, 20.0, 15.0)]
    assert {(20.0, 0.0, 20.0, 5.0), (20.0, 15.0, 20.0, 20.0)} <= walls_by_room(
        root, "a"
    )


def test_rooms_away_from_the_opening_keep_their_plain_rects() -> None:
    source = OPEN_TWO + '\nroom c "Sea" 20x20 down-of a'
    root = ET.fromstring(svg_of(source))
    assert rect_by_room(root, "c") is not None


def test_open_rooms_keep_their_glyphs_and_key_entries() -> None:
    root = ET.fromstring(svg_of(OPEN_TWO))
    assert text_by_room(root, "a").text == "A"
    assert text_by_room(root, "b").text == "B"
    key_lines = [t.text for t in root.iter(tag("text")) if t.get("class") == "key"]
    assert key_lines == ["A  A", "B  Bee"]


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
    assert {(0.0, 20.0, 5.0, 20.0), (15.0, 20.0, 20.0, 20.0)} <= walls_by_room(
        root, "a"
    )


def test_open_door_across_a_block_boundary_renders_as_a_gap() -> None:
    # 'side' opens into the block through a centred archway: one dashed line,
    # stubs on side's outline, and no solid block-outline line across the span.
    source = (
        'room main "" 20x20 root\n'
        'room wing "" 20x20 right-of main\n'
        'room side "Side" 20x20 right-of wing door=10 open\n'
        'block hall "Hall" main wing'
    )
    root = ET.fromstring(svg_of(source))
    assert open_lines(root) == [(40.0, 5.0, 40.0, 15.0)]
    assert {(40.0, 0.0, 40.0, 5.0), (40.0, 15.0, 40.0, 20.0)} <= walls_by_room(
        root, "side"
    )
    outline = [
        tuple(float(ln.get(k, "")) for k in ("x1", "y1", "x2", "y2"))
        for ln in root.iter(tag("line"))
        if ln.get("stroke-linecap") == "square"
    ]
    assert (40.0, 0.0, 40.0, 20.0) not in outline


# --- secret doors ------------------------------------------------------------
#
# A secret door keeps the wall fully intact (that is the point) and draws an
# "S" marker (class="secret") centred on the door's span instead of a door
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
    assert secret_markers(root) == [(20.0, 10.0, "S")]  # midpoint of y[5,15]
    assert [ln for ln in root.iter(tag("line")) if ln.get("class") == "door"] == []


def test_secret_door_leaves_both_room_rects_intact() -> None:
    root = ET.fromstring(svg_of(SECRET_TWO))
    assert rect_by_room(root, "a") is not None
    assert rect_by_room(root, "b") is not None
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
    assert rect_by_room(root, "a") is not None


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


def test_block_draws_one_glyph_from_the_block_id() -> None:
    root = ET.fromstring(svg_of(L_BLOCK))
    block_glyphs = [t for t in root.iter(tag("text")) if t.get("data-block") == "hall"]
    assert [t.text for t in block_glyphs] == ["H"]


def test_block_outline_drops_the_internal_wall() -> None:
    segments = set(block_wall_segments(solve(parse(L_BLOCK))))
    assert (0, 30, 20, 30) not in segments  # the shared main|wing wall is gone
    assert (20, 30, 40, 30) in segments  # the exposed part of main's bottom stays


def test_block_legend_and_key_use_the_block_not_its_members() -> None:
    assert ascii_of(L_BLOCK).split("\n\n")[1] == "H=hall"
    root = ET.fromstring(svg_of(L_BLOCK))
    key_text = " ".join(t.text or "" for t in root.iter(tag("text")))
    assert "Great Hall" in key_text


def test_block_cells_carry_the_block_glyph_in_ascii() -> None:
    grid = ascii_of(L_BLOCK).split("\n\n")[0]
    assert "H" in grid
    assert "M" not in grid
    assert "W" not in grid


# --- display glyphs --------------------------------------------------------

# Explicit multi-char glyphs ("12", "1"), an automatic one (hall -> H), and an
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
H  H  H  H  H  H  H  H
H  H  H  H  H  H  H  H

1=guard  H=hall  12=cells"""


def test_explicit_glyphs_pad_the_grid_and_fill_the_legend() -> None:
    # Cells pad to the widest glyph, the unlabeled room fills with '_' and has
    # no legend entry, and the legend sorts shortest-glyph-first.
    assert ascii_of(GLYPHS) == GLYPHS_ASCII


def test_automatic_glyphs_avoid_explicit_ones() -> None:
    # 'beta' claims A explicitly, so 'alpha' falls through to its next letter.
    text = 'room beta "" 10x10 root glyph="A"\nroom alpha "" 10x10 right-of beta'
    legend = ascii_of(text).split("\n\n")[1]
    assert "A=beta" in legend
    assert "L=alpha" in legend


def test_explicit_glyph_is_rendered_in_the_svg_room_and_key() -> None:
    root = ET.fromstring(svg_of(GLYPHS))
    assert text_by_room(root, "cells").text == "12"
    key_lines = [t.text for t in root.iter(tag("text")) if t.get("class") == "key"]
    assert key_lines == ["1  Guard Post", "H  Hall", "12  Prison Cells"]


def test_unlabeled_room_keeps_its_rect_but_has_no_svg_label() -> None:
    root = ET.fromstring(svg_of(GLYPHS))
    assert rect_by_room(root, "store") is not None
    with pytest.raises(AssertionError):
        text_by_room(root, "store")


@pytest.mark.parametrize(
    ("glyph", "expected_font"),
    [
        ("9", 6.0),  # single char: the usual 0.6 x shorter side
        ("123", 5.0),  # three chars overflow a 10-ft-wide room: shrink to fit
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
# horizontal run and (10, 10, 5, 10) for a vertical one (centred, one square
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
    # at the high (west) end to 40% at the low end, centred on y=12.5. The
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
    # The centred footprint blocks the room centre; the glyph settles in the
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
    assert ascii_of(text) == ("A A . . B B\nA A . . B B\n\nA=a  B=b")


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
