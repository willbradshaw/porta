"""Tests for ``render.py``: the debug-ascii rasterizer (and the SVG renderer).

The ascii grid doubles as the layout test oracle.
One character per 5-ft cell, space-separated, north at top; empty cells are
``.``. A blank line then a legend follows. Glyphs are mnemonic-first: the
first unused letter of the room id (uppercased), falling back to a generic
pool; ties are broken by source order.
"""

import xml.etree.ElementTree as ET
from collections.abc import Callable
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
    assert key_lines == ["A"]  # glyph only: no name, no dimensions


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
    # A centred 10-ft archway: the shared edge keeps a 5-ft stub at each end.
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
    assert text_by_room(root, "a").text == "A"
    assert text_by_room(root, "b").text == "B"
    key_lines = [
        "  ".join(span.text or "" for span in t)
        for t in root.iter(tag("g"))
        if t.get("class") == "key"
    ]
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
    assert {(0.0, 20.0, 5.0, 20.0), (15.0, 20.0, 20.0, 20.0)} <= wall_lines(root)


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
    key_text = " ".join(" ".join(t.itertext()) for t in root.iter(tag("text")))
    assert "Great Hall" in key_text


def test_block_cells_carry_the_block_glyph_in_ascii() -> None:
    grid = ascii_of(L_BLOCK).split("\n\n")[0]
    assert "H" in grid
    assert "M" not in grid
    assert "W" not in grid


# --- display glyphs --------------------------------------------------------


@pytest.mark.parametrize("renderer", [ascii_of, svg_of], ids=["ascii", "svg"])
@pytest.mark.parametrize(
    ("extra", "capacity"),
    [
        pytest.param("", 36, id="rooms"),
        pytest.param('room fixed "" 5x5 root glyph="A"', 35, id="reserved-letter"),
        pytest.param('room fixed "" 5x5 root glyph="0"', 35, id="reserved-digit"),
        pytest.param('room fixed "" 5x5 root glyph="12"', 36, id="multi-character"),
        pytest.param('room fixed "" 5x5 root glyph=""', 36, id="unlabeled-room"),
        pytest.param(L_BLOCK, 35, id="automatic-block"),
        pytest.param(
            L_BLOCK.replace('block hall "Great Hall"', 'block hall "" glyph="A"'),
            35,
            id="reserved-block",
        ),
        pytest.param(
            L_BLOCK.replace('block hall "Great Hall"', 'block hall "" glyph="12"'),
            36,
            id="multi-character-block",
        ),
        pytest.param(
            L_BLOCK.replace('block hall "Great Hall"', 'block hall "" glyph=""'),
            36,
            id="unlabeled-block",
        ),
    ],
)
@pytest.mark.parametrize("offset", [-1, 0, 1], ids=["below", "at", "over"])
def test_automatic_glyph_capacity(
    renderer: Callable[[str], str], extra: str, capacity: int, offset: int
) -> None:
    source = "\n".join(
        [extra, *(f'room r{i} "" 5x5 root' for i in range(capacity + offset))]
    )
    if offset <= 0:
        rendered = renderer(source)
        assert rendered == renderer(source)
        if renderer is ascii_of:
            glyphs = [
                entry.split("=")[0] for entry in rendered.split("\n\n")[1].split()
            ]
        else:
            glyphs = [
                node.text or ""
                for node in ET.fromstring(rendered).iter(tag("text"))
                if node.get("data-room") or node.get("data-block")
            ]
        labeled_extra = bool(extra) and 'glyph=""' not in extra
        assert len(glyphs) == capacity + offset + labeled_extra
        assert len(set(glyphs)) == len(glyphs)
    else:
        with pytest.raises(ValueError, match="automatic glyphs exhausted") as exc:
            renderer(source)
        message = str(exc.value)
        assert "automatic glyphs exhausted for 'r" in message
        assert "36 used" in message
        assert "unique multi-character glyphs" in message
        assert 'glyph=""' in message
        assert "ascii" not in message.lower()
        assert "svg" not in message.lower()


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
    key_lines = [
        "  ".join(span.text or "" for span in t)
        for t in root.iter(tag("g"))
        if t.get("class") == "key"
    ]
    assert key_lines == ["1  Guard Post", "H  Hall", "12  Prison Cells"]


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
    assert fills[0].attrib["stroke"] == "white"
    assert fills[0].attrib["stroke-width"] == "0.5"
    marks = root.findall('.//{*}line[@class="window"]')
    assert [
        tuple(float(mark.attrib[key]) for key in ("x1", "y1", "x2", "y2"))
        for mark in marks
    ] == expected
    assert all(mark.attrib["stroke-width"] == "0.25" for mark in marks)
    assert not root.findall('.//{*}rect[@data-room="a"]')
    assert render_ascii(building) == ascii_of(source)


def test_windows_on_coloured_background_golden() -> None:
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
    assert grid.attrib["stroke"] == "#c4c4c4"


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
    from porta.render import _KEY_FONT_FT
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
    assert float(rows[-1].attrib["y"]) + _KEY_FONT_FT < top + height


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
    monkeypatch.setattr(render, "choose_layout", lambda *args: choice)
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
