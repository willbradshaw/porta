"""Tests for ``layout.py``: DAG propagation, structural validation, overlap.

Coordinates are integer feet; ``x`` increases east, ``y`` increases south
(north = up = smaller y). Each room's stored ``(x, y)`` is its top-left (NW)
corner; the root's NW corner is the origin.
"""

from pathlib import Path

import pytest

from porta.errors import LayoutError, OverlapError
from porta.layout import (
    block_wall_segments,
    door_segments,
    find_overlaps,
    open_door_segments,
    secret_door_segments,
    solve,
    stair_footprints,
)
from porta.model import Building, Room
from porta.parser import parse


def coords(text: str, room_id: str) -> tuple[int | None, int | None]:
    room = solve(parse(text)).room(room_id)
    return room.x, room.y


def placed(room_id: str, x: int, y: int, w: int, h: int) -> Room:
    return Room(id=room_id, name=room_id, width=w, height=h, x=x, y=y)


def building_of(*rooms: Room) -> Building:
    return Building(list(rooms))


# --- placement -------------------------------------------------------------


def test_root_is_placed_at_the_origin() -> None:
    assert coords('room a "A" 20x20 root', "a") == (0, 0)


@pytest.mark.parametrize(
    ("relation", "expected"),
    [
        # Anchor 'a' is 20x20 at the origin; 'b' is 10x10. Free axis align-starts.
        ("right-of", (20, 0)),  # west edge meets a's east edge; tops flush
        ("left-of", (-10, 0)),  # east edge meets a's west edge; tops flush
        ("down-of", (0, 20)),  # north edge meets a's south edge; lefts flush
        ("up-of", (0, -10)),  # south edge meets a's north edge; lefts flush
    ],
)
def test_single_relation_edge_math_and_align_start(
    relation: str, expected: tuple[int, int]
) -> None:
    text = f'room a "A" 20x20 root\nroom b "B" 10x10 {relation} a'
    assert coords(text, "b") == expected


# The design-note manor: two relations pin both axes of 'hall' directly.
DESIGN_MANOR = (
    'room entrance "Entrance Hall" 40x20 root\n'
    'room kitchen  "Kitchen"       20x40 down-of entrance\n'
    'room hall     "Great Hall"    20x20 right-of kitchen down-of entrance'
)


@pytest.mark.parametrize(
    ("room_id", "expected"),
    [
        ("entrance", (0, 0)),
        ("kitchen", (0, 20)),  # down-of entrance; left edges flush
        ("hall", (20, 20)),  # x from right-of kitchen, y from down-of entrance
    ],
)
def test_two_relations_pin_both_axes(room_id: str, expected: tuple[int, int]) -> None:
    assert coords(DESIGN_MANOR, room_id) == expected


def test_corner_touch_relation_is_rejected() -> None:
    # 'smoking' is east of the tall hall and above 'drawing'; 'up-of drawing'
    # lifts it above the hall's top, so 'right-of hall' meets the hall only at a
    # corner — no shared wall. A relation must share a wall, so this is rejected.
    text = (
        'room hall    "Hall"    20x40 root\n'
        'room drawing "Drawing" 20x20 right-of hall\n'
        'room smoking "Smoking" 20x20 right-of hall up-of drawing'
    )
    with pytest.raises(LayoutError):
        solve(parse(text))


# --- shift -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("relation", "shift", "expected"),
    [
        # Anchor 'a' is 20x20 at the origin; 'b' is 10x10. Positive shift is
        # east (for up/down-of) or south (for left/right-of). Magnitudes stay
        # small enough to keep b sharing a wall with a.
        ("up-of", 5, (5, -10)),
        ("up-of", -5, (-5, -10)),
        ("down-of", 5, (5, 20)),
        ("down-of", -5, (-5, 20)),
        ("left-of", 5, (-10, 5)),
        ("left-of", -5, (-10, -5)),
        ("right-of", 5, (20, 5)),
        ("right-of", -5, (20, -5)),
    ],
)
def test_shift_nudges_along_the_free_axis(
    relation: str, shift: int, expected: tuple[int, int]
) -> None:
    text = f'room a "A" 20x20 root\nroom b "B" 10x10 {relation} a shift={shift}'
    assert coords(text, "b") == expected


def test_shift_propagates_to_dependents() -> None:
    text = (
        'room a "A" 10x10 root\n'
        'room b "B" 10x10 up-of a shift=5\n'
        'room c "C" 10x10 up-of b'
    )
    assert coords(text, "b") == (5, -10)
    assert coords(text, "c") == (5, -20)  # c stacks on the shifted b


def test_shift_with_both_axes_constrained_raises() -> None:
    # 'up-of' shifts along x, but 'right-of' already pins x -> no free axis.
    text = 'room a "A" 20x20 root\nroom b "B" 10x10 up-of a shift=10 right-of a'
    with pytest.raises(LayoutError):
        solve(parse(text))


def test_shift_that_detaches_from_the_anchor_raises() -> None:
    # shift = the room width slides b fully off a (corner-touch, no shared wall).
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 up-of a shift=10'
    with pytest.raises(LayoutError):
        solve(parse(text))


# --- align -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("relation", "expected"),
    [
        # Anchor 'a' is 20x20; 'b' is 10x10. align=end flushes the FAR edges,
        # so b sits at a's east (up/down-of) or south (left/right-of) end.
        ("up-of", (10, -10)),
        ("down-of", (10, 20)),
        ("left-of", (-10, 10)),
        ("right-of", (20, 10)),
    ],
)
def test_align_end_flushes_the_far_edge(
    relation: str, expected: tuple[int, int]
) -> None:
    text = f'room a "A" 20x20 root\nroom b "B" 10x10 {relation} a align=end'
    assert coords(text, "b") == expected


def test_align_end_composes_with_shift() -> None:
    # align=end puts b at the east edge (x=10), then shift nudges it west by 5.
    text = 'room a "A" 20x20 root\nroom b "B" 10x10 up-of a align=end shift=-5'
    assert coords(text, "b") == (5, -10)


def test_align_end_with_both_axes_constrained_raises() -> None:
    # align=end acts on x, but right-of already pins x -> no free axis.
    text = 'room a "A" 20x20 root\nroom b "B" 10x10 up-of a align=end right-of a'
    with pytest.raises(LayoutError):
        solve(parse(text))


# --- doors -----------------------------------------------------------------


def doors_of(text: str) -> list[tuple[int, int, int, int]]:
    return door_segments(solve(parse(text)))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # b (10x10) against a (20x20); shared wall is 10 ft long.
        # up-of: horizontal wall at y=0; 5-ft door centres (round down) to x[0,5].
        ('room a "A" 20x20 root\nroom b "B" 10x10 up-of a door', (0, 0, 5, 0)),
        # door=10 fills the wall.
        ('room a "A" 20x20 root\nroom b "B" 10x10 up-of a door=10', (0, 0, 10, 0)),
        # explicit offset.
        ('room a "A" 20x20 root\nroom b "B" 10x10 up-of a door=5@5', (5, 0, 10, 0)),
        # right-of: vertical wall at x=20; door spans y[0,5].
        ('room a "A" 20x20 root\nroom b "B" 10x10 right-of a door', (20, 0, 20, 5)),
    ],
)
def test_door_line_geometry(source: str, expected: tuple[int, int, int, int]) -> None:
    assert doors_of(source) == [expected]


@pytest.mark.parametrize(
    "source",
    [
        # door wider than the shared wall
        pytest.param(
            'room a "A" 10x10 root\nroom b "B" 10x10 up-of a door=20',
            id="door-wider-than-wall",
        ),
        # offset pushes the door past the wall
        pytest.param(
            'room a "A" 20x20 root\nroom b "B" 10x10 up-of a door=10@15',
            id="door-past-the-wall",
        ),
    ],
)
def test_door_that_does_not_fit_raises(source: str) -> None:
    with pytest.raises(LayoutError):
        solve(parse(source))


def test_a_shared_wall_gets_a_default_door() -> None:
    # No 'door' modifier, but the shared wall gets a default 5-ft door.
    assert doors_of('room a "A" 20x20 root\nroom b "B" 20x20 right-of a') == [
        (20, 5, 20, 10)
    ]


def test_no_door_suppresses_the_default() -> None:
    assert doors_of('room a "A" 20x20 root\nroom b "B" 20x20 right-of a no-door') == []


def test_standalone_door_between_incidental_rooms() -> None:
    # b and c are both below 'a' (not each other's anchor) but sit side by side,
    # sharing the x=20 wall; a standalone door connects them.
    text = (
        'room a "A" 40x20 root\n'
        'room b "B" 20x20 down-of a\n'
        'room c "C" 20x20 down-of a shift=20\n'
        "door b c"
    )
    assert (20, 25, 20, 30) in doors_of(text)


def test_standalone_door_between_nonadjacent_rooms_raises() -> None:
    # 'a' and 'c' only meet at a corner, so there is no wall to put a door on.
    text = (
        'room a "A" 10x10 root\n'
        'room b "B" 10x10 right-of a\n'
        'room c "C" 10x10 up-of b\n'
        "door a c"
    )
    with pytest.raises(LayoutError):
        solve(parse(text))


def test_standalone_door_to_unknown_room_raises() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 right-of a\ndoor a ghost'
    with pytest.raises(LayoutError):
        solve(parse(text))


def test_a_pair_can_have_two_doors() -> None:
    # The relation gives a default door; a standalone door adds a second on the
    # same wall -- deliberate, e.g. two openings between the rooms.
    text = 'room a "A" 20x40 root\nroom b "B" 20x40 right-of a\ndoor@30 a b'
    assert len(doors_of(text)) == 2


def test_overlapping_doors_raise() -> None:
    # Two doors on the same wall that overlap each other are a mistake.
    text = (
        'room a "A" 20x20 root\n'
        'room b "B" 20x20 right-of a no-door\n'
        "door=10@0 a b\n"
        "door@5 a b"
    )
    with pytest.raises(LayoutError):
        solve(parse(text))


# --- open doors -------------------------------------------------------------
#
# An open door is placed exactly like a solid one (same wall, fit, and overlap
# rules) but reported by open_door_segments() instead of door_segments(), so
# the renderer draws a gap in the wall rather than a door mark.


def open_doors_of(text: str) -> list[tuple[int, int, int, int]]:
    return open_door_segments(solve(parse(text)))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # the whole shared wall: b right-of a, vertical wall at x=20.
        pytest.param(
            'room a "A" 20x20 root\nroom b "B" 20x20 right-of a door=20 open',
            (20, 0, 20, 20),
            id="full-wall",
        ),
        # a centred 10-ft archway leaves solid wall either side.
        pytest.param(
            'room a "A" 20x20 root\nroom b "B" 20x20 right-of a door=10 open',
            (20, 5, 20, 15),
            id="archway-centred",
        ),
        # explicit offset pins the opening to the wall's near end.
        pytest.param(
            'room a "A" 20x20 root\nroom b "B" 20x20 right-of a door=10@0 open',
            (20, 0, 20, 10),
            id="archway-at-start",
        ),
        # horizontal wall: b up-of a, default 5-ft width still applies.
        pytest.param(
            'room a "A" 20x20 root\nroom b "B" 10x10 up-of a door open',
            (0, 0, 5, 0),
            id="default-width-up-of",
        ),
        # differently sized rooms: the opening can only span the shared interval.
        pytest.param(
            'room a "A" 20x30 root\nroom b "B" 20x20 right-of a door=20 open',
            (20, 0, 20, 20),
            id="partial-edge",
        ),
    ],
)
def test_open_door_line_geometry(
    source: str, expected: tuple[int, int, int, int]
) -> None:
    assert open_doors_of(source) == [expected]


def test_open_door_replaces_the_default_solid_door() -> None:
    # The relation's door spec is the open one; no solid door mark remains.
    text = 'room a "A" 20x20 root\nroom b "B" 20x20 right-of a door=20 open'
    assert doors_of(text) == []


def test_solid_doors_are_not_reported_as_open() -> None:
    text = 'room a "A" 20x20 root\nroom b "B" 20x20 right-of a'
    assert open_doors_of(text) == []


def test_standalone_open_door_between_incidental_rooms() -> None:
    # Same shape as the standalone solid-door case: b and c share the x=20 wall.
    text = (
        'room a "A" 40x20 root\n'
        'room b "B" 20x20 down-of a\n'
        'room c "C" 20x20 down-of a shift=20\n'
        "door=20@0 open b c"
    )
    assert open_doors_of(text) == [(20, 20, 20, 40)]


def test_external_open_door_geometry() -> None:
    text = 'room a "A" 20x20 root\ndoor=10 open a outside down'
    assert open_doors_of(text) == [(5, 20, 15, 20)]


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            'room a "A" 10x10 root\nroom b "B" 10x10 up-of a door=20 open',
            id="open-wider-than-wall",
        ),
        pytest.param(
            'room a "A" 20x20 root\nroom b "B" 10x10 up-of a door=10@15 open',
            id="open-past-the-wall",
        ),
        pytest.param(
            'room a "A" 10x10 root\n'
            'room b "B" 10x10 right-of a\n'
            'room c "C" 10x10 up-of b\n'
            "door open a c",
            id="open-between-nonadjacent",
        ),
    ],
)
def test_open_door_that_does_not_fit_raises(source: str) -> None:
    with pytest.raises(LayoutError):
        solve(parse(source))


def test_open_and_solid_doors_share_the_overlap_check() -> None:
    # A full-wall opening leaves no room for a separate solid door.
    text = 'room a "A" 20x20 root\nroom b "B" 20x20 right-of a door=20 open\ndoor@5 a b'
    with pytest.raises(LayoutError):
        solve(parse(text))


def test_open_door_can_coexist_with_a_solid_door_on_the_wall() -> None:
    # An archway at the wall's start plus a solid door at its end.
    text = (
        'room a "A" 20x20 root\nroom b "B" 20x20 right-of a door=10@0 open\ndoor@15 a b'
    )
    building = solve(parse(text))
    assert open_door_segments(building) == [(20, 0, 20, 10)]
    assert door_segments(building) == [(20, 15, 20, 20)]


def test_open_door_inside_a_block_is_dropped_with_a_warning() -> None:
    text = (
        'room main "" 20x20 root\n'
        'room wing "" 20x20 right-of main door=20 open\n'
        'block hall "Hall" main wing'
    )
    building = solve(parse(text))
    assert open_door_segments(building) == []
    assert any("suppressed" in warning for warning in building.warnings)


def test_open_door_across_a_block_boundary_is_cut_from_the_outline() -> None:
    # An open door between a member and a room outside the block: the block's
    # union outline omits the open span, just as a plain room's outline does.
    text = (
        'room main "" 20x20 root\n'
        'room wing "" 20x20 right-of main\n'
        'room side "Side" 20x20 right-of wing door=20 open\n'
        'block hall "Hall" main wing'
    )
    building = solve(parse(text))
    assert open_door_segments(building) == [(40, 0, 40, 20)]
    assert (40, 0, 40, 20) not in block_wall_segments(building)


def test_partial_open_door_leaves_stubs_in_the_block_outline() -> None:
    # A centred 10-ft archway into the block keeps a 5-ft stub at each end of
    # the shared wall.
    text = (
        'room main "" 20x20 root\n'
        'room wing "" 20x20 right-of main\n'
        'room side "Side" 20x20 right-of wing door=10 open\n'
        'block hall "Hall" main wing'
    )
    segments = block_wall_segments(solve(parse(text)))
    assert (40, 0, 40, 5) in segments
    assert (40, 15, 40, 20) in segments
    assert (40, 0, 40, 20) not in segments


# --- secret doors -----------------------------------------------------------
#
# A secret door is placed and validated exactly like a solid one but reported
# by secret_door_segments(), so the renderer keeps the wall intact and draws
# an "S" marker instead of a door mark.


def secret_doors_of(text: str) -> list[tuple[int, int, int, int]]:
    return secret_door_segments(solve(parse(text)))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # default 5-ft width, centred on the 10-ft shared wall.
        pytest.param(
            'room a "A" 20x20 root\nroom b "B" 10x10 up-of a door secret',
            (0, 0, 5, 0),
            id="default-width",
        ),
        # the acceptance example: explicit width and offset.
        pytest.param(
            'room store "Storeroom" 30x30 root\n'
            'room cache "Hidden Cache" 10x20 right-of store door=5@5 secret',
            (30, 5, 30, 10),
            id="explicit-width-and-offset",
        ),
        # standalone form between incidental neighbours.
        pytest.param(
            'room a "A" 40x20 root\n'
            'room b "B" 20x20 down-of a\n'
            'room c "C" 20x20 down-of a shift=20\n'
            "door secret b c",
            (20, 25, 20, 30),
            id="standalone",
        ),
        # external form: a concealed exit on an exterior wall.
        pytest.param(
            'room a "A" 20x20 root\ndoor=10 secret a outside down',
            (5, 20, 15, 20),
            id="external",
        ),
    ],
)
def test_secret_door_line_geometry(
    source: str, expected: tuple[int, int, int, int]
) -> None:
    assert secret_doors_of(source) == [expected]


def test_secret_door_replaces_the_default_solid_door() -> None:
    text = 'room a "A" 20x20 root\nroom b "B" 20x20 right-of a door secret'
    assert doors_of(text) == []
    assert open_door_segments(solve(parse(text))) == []


def test_secret_door_that_does_not_fit_raises() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 up-of a door=20 secret'
    with pytest.raises(LayoutError):
        solve(parse(text))


def test_secret_and_solid_doors_share_the_overlap_check() -> None:
    text = (
        'room a "A" 20x20 root\nroom b "B" 20x20 right-of a door=20 secret\ndoor@5 a b'
    )
    with pytest.raises(LayoutError):
        solve(parse(text))


def test_secret_door_can_coexist_with_a_solid_door_on_the_wall() -> None:
    text = (
        'room a "A" 20x20 root\n'
        'room b "B" 20x20 right-of a door=5@0 secret\n'
        "door@10 a b"
    )
    building = solve(parse(text))
    assert secret_door_segments(building) == [(20, 0, 20, 5)]
    assert door_segments(building) == [(20, 10, 20, 15)]


def test_secret_door_inside_a_block_is_dropped_with_a_warning() -> None:
    text = (
        'room main "" 20x20 root\n'
        'room wing "" 20x20 right-of main door secret\n'
        'block hall "Hall" main wing'
    )
    building = solve(parse(text))
    assert secret_door_segments(building) == []
    assert any("suppressed" in warning for warning in building.warnings)


# --- auto dimensions (?) ---------------------------------------------------


def dims(text: str, room_id: str) -> tuple[int, int]:
    room = solve(parse(text)).room(room_id)
    return room.width, room.height


def test_auto_height_matches_a_left_right_anchor() -> None:
    # right-of shares a vertical wall, so '?' height = the anchor's height.
    text = 'room a "A" 30x25 root\nroom b "B" 20x? right-of a'
    assert dims(text, "b") == (20, 25)


def test_auto_width_matches_an_up_down_anchor() -> None:
    # up-of shares a horizontal wall, so '?' width = the anchor's width.
    text = 'room a "A" 40x20 root\nroom b "B" ?x15 up-of a'
    assert dims(text, "b") == (40, 15)


def test_auto_both_dims_from_two_perpendicular_anchors() -> None:
    # right-of x sizes height, down-of y sizes width; r fills the corner under y
    # and right of x's lower half -> 10x10 at (20,10), reaching x's bottom (20).
    text = (
        'room x "X" 20x20 root\n'
        'room y "Y" 10x10 right-of x\n'
        'room r "R" ?x? right-of x down-of y'
    )
    assert dims(text, "r") == (10, 10)
    assert coords(text, "r") == (20, 10)


def test_auto_dim_chains_through_an_auto_anchor() -> None:
    # c matches b's height, which itself matched a's height -> resolved in order.
    text = (
        'room a "A" 30x25 root\nroom b "B" 20x? right-of a\nroom c "C" 15x? right-of b'
    )
    assert dims(text, "c") == (15, 25)


def test_auto_height_shrinks_by_a_shift() -> None:
    # shift fixes b's top 10 ft down a (20..30 stays 0..30); '?' fills to a's bottom.
    text = 'room a "A" 20x30 root\nroom b "B" 10x? right-of a shift=10'
    assert dims(text, "b") == (10, 20)
    assert coords(text, "b") == (20, 10)


def test_auto_fills_the_wall_below_a_neighbour() -> None:
    # c is dropped below b by down-of b, then '?' fills the rest of a's east wall.
    text = (
        'room a "A" 20x40 root\n'
        'room b "B" 20x10 right-of a\n'
        'room c "C" 10x? right-of a down-of b'
    )
    assert dims(text, "c") == (10, 30)
    assert coords(text, "c") == (20, 10)


def test_auto_up_of_fills_toward_the_near_side() -> None:
    # up-of b fixes r's BOTTOM at b's top; '?' fills upward to a's top.
    text = (
        'room a "A" 10x30 root\n'
        'room b "B" 10x10 right-of a align=end\n'
        'room r "R" 10x? right-of a up-of b'
    )
    assert dims(text, "r") == (10, 20)
    assert coords(text, "r") == (10, 0)


def test_auto_with_align_end_matches_the_anchor() -> None:
    # align=end fixes the far edge at the anchor's far edge; '?' fills the wall.
    text = 'room a "A" 20x30 root\nroom b "B" 10x? right-of a align=end'
    assert dims(text, "b") == (10, 30)
    assert coords(text, "b") == (20, 0)


@pytest.mark.parametrize(
    "source",
    [
        # '?' width needs an up/down relation; b only has a left/right one.
        pytest.param(
            'room a "A" 20x20 root\nroom b "B" ?x10 right-of a',
            id="auto-width-no-updown-relation",
        ),
        # '?' height needs a left/right relation; b only has an up/down one.
        pytest.param(
            'room a "A" 20x20 root\nroom b "B" 10x? down-of a',
            id="auto-height-no-leftright-relation",
        ),
        # the root has no anchor to size against.
        pytest.param('room a "A" ?x20 root', id="auto-on-root"),
        # shift slides the fixed edge to a's far edge -> nothing left to fill.
        pytest.param(
            'room a "A" 10x10 root\nroom b "B" 10x? right-of a shift=10',
            id="auto-non-positive-span",
        ),
    ],
)
def test_unresolvable_auto_dim_raises(source: str) -> None:
    with pytest.raises(LayoutError):
        solve(parse(source))


# --- same-axis: snug-fit & same-direction ----------------------------------

# 'c' fills the 10-ft gap between b (x[0,20]) and d (x[30,50]), both below a.
SNUG = (
    'room a "A" 40x20 root\n'
    'room b "B" 20x20 down-of a\n'
    'room d "D" 20x20 down-of a shift=30\n'
    'room c "C" {dims} right-of b left-of d'
)


def test_opposite_relations_snug_fit_explicit() -> None:
    assert dims(SNUG.format(dims="10x20"), "c") == (10, 20)
    assert coords(SNUG.format(dims="10x20"), "c") == (20, 20)


def test_opposite_relations_snug_fit_auto_width() -> None:
    # '?' on the doubly-pinned axis solves to the gap.
    assert dims(SNUG.format(dims="?x20"), "c") == (10, 20)
    # ?x? also resolves height via match-anchor (first-wins to b) -> 10x20.
    assert dims(SNUG.format(dims="?x?"), "c") == (10, 20)


def test_snug_fit_size_mismatch_raises() -> None:
    # 15 != the 10-ft gap between the anchors.
    with pytest.raises(LayoutError):
        solve(parse(SNUG.format(dims="15x20")))


def test_same_direction_colinear_borders_both() -> None:
    # a and b are stacked with a common left edge; c is left of both and spans
    # them, so it borders each (and gets a default door to each).
    text = (
        'room a "A" 20x10 root\n'
        'room b "B" 20x10 down-of a\n'
        'room c "C" 10x20 left-of a left-of b'
    )
    assert coords(text, "c") == (-10, 0)
    assert dims(text, "c") == (10, 20)
    # doors: a<->b (down-of), c<->a, c<->b.
    assert len(doors_of(text)) == 3


def test_same_direction_explicit_too_short_raises() -> None:
    # An explicit size too short to span both anchors is non-flush with b.
    text = (
        'room a "A" 20x10 root\n'
        'room b "B" 20x10 down-of a\n'
        'room c "C" 10x10 left-of a left-of b'
    )
    with pytest.raises(LayoutError):
        solve(parse(text))


def test_same_direction_auto_spans_the_union() -> None:
    # a (10 tall) over b (20 tall), colinear left edges; '?' height spans BOTH
    # (the union, 30) and the near edge moves to the union's top.
    text = (
        'room a "A" 20x10 root\n'
        'room b "B" 20x20 down-of a\n'
        'room c "C" 10x? left-of a left-of b'
    )
    assert dims(text, "c") == (10, 30)
    assert coords(text, "c") == (-10, 0)
    assert len(doors_of(text)) == 3  # a<->b, c<->a, c<->b


def test_horizontal_union_spans_side_by_side_anchors() -> None:
    # a and b sit side by side, colinear tops; c above both with '?' width unions
    # them horizontally (20) and its near edge moves to the union's left.
    text = (
        'room a "A" 10x20 root\n'
        'room b "B" 10x20 right-of a\n'
        'room c "C" ?x10 up-of a up-of b'
    )
    assert dims(text, "c") == (20, 10)
    assert coords(text, "c") == (0, -10)


def test_corridor_pattern_is_fully_derived() -> None:
    # The manor corridor in miniature: width match-anchors the library overhang
    # (10), height unions the two stacked rooms (40), top pinned by down-of.
    text = (
        'room lib "L" 30x10 root\n'
        'room a "A" 20x20 down-of lib shift=10\n'
        'room b "B" 20x20 down-of a\n'
        'room cor "C" ?x? down-of lib left-of a left-of b'
    )
    assert dims(text, "cor") == (10, 40)
    assert coords(text, "cor") == (0, 10)


def test_same_direction_not_aligned_raises() -> None:
    # b is shifted, so its left edge no longer lines up with a's -> the two
    # left-of relations disagree on where to put c.
    text = (
        'room a "A" 20x10 root\n'
        'room b "B" 10x10 down-of a shift=5\n'
        'room c "C" 10x20 left-of a left-of b'
    )
    with pytest.raises(LayoutError):
        solve(parse(text))


# --- external doors --------------------------------------------------------


@pytest.mark.parametrize(
    ("side", "expected"),
    [
        # a 20x20 root; default 5-ft door centres (round down) to offset 5.
        ("down", (5, 20, 10, 20)),
        ("up", (5, 0, 10, 0)),
        ("left", (0, 5, 0, 10)),
        ("right", (20, 5, 20, 10)),
    ],
)
def test_external_door_geometry(side: str, expected: tuple[int, int, int, int]) -> None:
    text = f'room a "A" 20x20 root\ndoor a outside {side}'
    assert doors_of(text) == [expected]


def test_external_door_into_a_neighbour_raises() -> None:
    # b is flush below a, so a's down edge is interior there, not exterior.
    text = 'room a "A" 20x20 root\nroom b "B" 20x20 down-of a\ndoor a outside down'
    with pytest.raises(LayoutError):
        solve(parse(text))


def test_external_door_on_the_exterior_part_is_fine() -> None:
    # b covers only the right of a's bottom edge; the door sits on the open left.
    # (no-door on the relation so only the external door is in the list.)
    text = (
        'room a "A" 20x20 root\n'
        'room b "B" 20x20 down-of a shift=10 no-door\n'
        "door=5@0 a outside down"
    )
    assert doors_of(text) == [(0, 20, 5, 20)]


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            'room a "A" 10x10 root\ndoor=20 a outside down', id="wider-than-edge"
        ),
        pytest.param(
            'room a "A" 10x10 root\ndoor ghost outside down', id="unknown-room"
        ),
    ],
)
def test_invalid_external_door_raises(source: str) -> None:
    with pytest.raises(LayoutError):
        solve(parse(source))


# --- structural validation -------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        pytest.param('room a "A" 10x10', id="no-root"),
        pytest.param(
            'room a "A" 10x10 root\n'
            'room c "C" 10x10 root\n'
            'room b "B" 10x10 right-of a left-of c',
            id="two-roots-in-one-component",
        ),
        pytest.param(
            'room a "A" 10x10 root up-of b\nroom b "B" 10x10 down-of a',
            id="root-with-relations",
        ),
        pytest.param(
            'room a "A" 10x10 root\nroom b "B" 10x10 right-of ghost',
            id="unknown-anchor",
        ),
        pytest.param(
            'room r "R" 10x10 root\nroom a "A" 10x10 up-of b\nroom b "B" 10x10 up-of a',
            id="cycle",
        ),
        pytest.param(
            'room r "R" 10x10 root\nroom a "A" 10x10', id="rootless-component"
        ),
        pytest.param(
            'room a "A" 10x10 root\n'
            'room c "C" 10x10 right-of a\n'
            'room b "B" 10x10 left-of a right-of c',
            id="same-axis-over-constraint",
        ),
    ],
)
def test_layout_validation_raises(text: str) -> None:
    with pytest.raises(LayoutError):
        solve(parse(text))


def test_unknown_anchor_error_points_at_the_relation_line() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 right-of ghost'
    with pytest.raises(LayoutError) as exc:
        solve(parse(text))
    assert exc.value.line == 2


# --- disconnected components -----------------------------------------------


def test_two_isolated_roots_pack_into_a_row_with_a_gap() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 root'
    building = solve(parse(text))
    assert (building.room("a").x, building.room("a").y) == (0, 0)
    assert (building.room("b").x, building.room("b").y) == (20, 0)


def test_second_component_is_translated_whole_and_top_aligned() -> None:
    # Component 1 spans x 0..30, y 0..20; component 2 internally has d
    # protruding above c (negative y), so its bounding box top is at -20.
    # Packing puts its box at x = 30 + 10 (the gap), top aligned with y = 0.
    text = (
        'room a "A" 20x20 root\n'
        'room b "B" 10x10 right-of a\n'
        'room c "C" 30x30 root\n'
        'room d "D" 10x20 up-of c'
    )
    building = solve(parse(text))
    assert (building.room("a").x, building.room("a").y) == (0, 0)
    assert (building.room("b").x, building.room("b").y) == (20, 0)
    assert (building.room("c").x, building.room("c").y) == (40, 20)
    assert (building.room("d").x, building.room("d").y) == (40, 0)


def test_components_pack_in_first_appearance_order() -> None:
    # 'tail' opens the file (a forward reference to 'head'), so its
    # component packs before 'solo' — order follows first appearance.
    text = (
        'room tail "T" 10x10 right-of head\n'
        'room head "H" 10x10 root\n'
        'room solo "S" 10x10 root'
    )
    building = solve(parse(text))
    assert (building.room("head").x, building.room("head").y) == (0, 0)
    assert (building.room("tail").x, building.room("tail").y) == (10, 0)
    assert (building.room("solo").x, building.room("solo").y) == (30, 0)


def test_rootless_component_error_names_a_room_in_it() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 10x10\nroom c "C" 10x10 right-of b'
    with pytest.raises(LayoutError) as exc:
        solve(parse(text))
    assert "'b'" in exc.value.message
    assert "no root" in exc.value.message
    assert exc.value.line == 2


def test_two_roots_in_one_component_error_lists_both() -> None:
    text = (
        'room a "A" 10x10 root\n'
        'room c "C" 10x10 root\n'
        'room b "B" 10x10 right-of a left-of c'
    )
    with pytest.raises(LayoutError) as exc:
        solve(parse(text))
    assert "'a'" in exc.value.message
    assert "'c'" in exc.value.message
    assert exc.value.line == 2


def test_no_root_anywhere_keeps_the_building_level_message() -> None:
    with pytest.raises(LayoutError) as exc:
        solve(parse('room a "A" 10x10'))
    assert "building" in exc.value.message
    assert exc.value.line is None


def test_overlap_inside_a_later_component_is_still_detected() -> None:
    text = (
        'room a "A" 10x10 root\n'
        'room b "B" 20x20 root\n'
        'room c "C" 20x20 right-of b\n'
        'room d "D" 20x20 right-of b'
    )
    with pytest.raises(OverlapError):
        solve(parse(text))


def test_door_between_components_shares_no_wall() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 root\ndoor a b'
    with pytest.raises(LayoutError) as exc:
        solve(parse(text))
    assert "share no wall" in exc.value.message


# --- component links -------------------------------------------------------


def test_link_translates_the_whole_subject_component() -> None:
    # 'c' is placed down-of 'b' exactly as a relation would place it, and 'd'
    # rides along with its component.
    text = (
        'room a "A" 20x20 root\n'
        'room b "B" 10x10 down-of a\n'
        'room c "C" 10x10 root\n'
        'room d "D" 10x10 right-of c\n'
        "link c down-of b"
    )
    building = solve(parse(text))
    assert (building.room("c").x, building.room("c").y) == (0, 30)
    assert (building.room("d").x, building.room("d").y) == (10, 30)


def test_link_align_and_shift_act_on_the_free_axis() -> None:
    text = (
        'room a "A" 30x10 root\n'
        'room c "C" 10x10 root\n'
        "link c down-of a align=end shift=-5"
    )
    building = solve(parse(text))
    assert (building.room("c").x, building.room("c").y) == (15, 10)


def test_links_chain_across_three_components() -> None:
    text = (
        'room a "A" 10x10 root\n'
        'room b "B" 10x10 root\n'
        'room c "C" 10x10 root\n'
        "link b right-of a\n"
        "link c right-of b"
    )
    building = solve(parse(text))
    assert (building.room("b").x, building.room("b").y) == (10, 0)
    assert (building.room("c").x, building.room("c").y) == (20, 0)


def test_consistent_link_cycle_is_fine() -> None:
    # The two links state the same constraint from both ends. Each link still
    # carries its own default door, so one must say no-door (overlapping
    # doors are an error, as everywhere else).
    text = (
        'room a "A" 10x10 root\n'
        'room b "B" 10x10 root\n'
        "link b right-of a\n"
        "link a left-of b no-door"
    )
    building = solve(parse(text))
    assert (building.room("b").x, building.room("b").y) == (10, 0)
    assert doors_of(text) == [(10, 0, 10, 5)]


def test_contradictory_links_raise() -> None:
    text = (
        'room a "A" 10x10 root\n'
        'room b "B" 10x10 root\n'
        "link b right-of a\n"
        "link b down-of a"
    )
    with pytest.raises(LayoutError) as exc:
        solve(parse(text))
    assert "contradict" in exc.value.message


def test_first_component_keeps_literal_coordinates_when_linked() -> None:
    # The subject appears first, so its component anchors the group and the
    # *anchor* component is the one translated (into negative x here).
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 root\nlink a right-of b'
    building = solve(parse(text))
    assert (building.room("a").x, building.room("a").y) == (0, 0)
    assert (building.room("b").x, building.room("b").y) == (-10, 0)


def test_link_within_one_component_raises() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 right-of a\nlink b right-of a'
    with pytest.raises(LayoutError) as exc:
        solve(parse(text))
    assert "same component" in exc.value.message


def test_link_to_unknown_room_raises() -> None:
    text = 'room a "A" 10x10 root\nlink a right-of ghost'
    with pytest.raises(LayoutError) as exc:
        solve(parse(text))
    assert "'ghost'" in exc.value.message


def test_link_needs_a_shared_wall_after_placement() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 root\nlink b right-of a shift=20'
    with pytest.raises(LayoutError) as exc:
        solve(parse(text))
    assert "wall" in exc.value.message


def test_link_gets_a_default_door_on_the_shared_wall() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 root\nlink b right-of a'
    assert doors_of(text) == [(10, 0, 10, 5)]


def test_link_no_door_suppresses_the_door() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 10x10 root\nlink b right-of a no-door'
    assert doors_of(text) == []


def test_link_open_door_is_an_opening() -> None:
    text = (
        'room a "A" 10x10 root\nroom b "B" 10x10 root\nlink b right-of a door=10 open'
    )
    building = solve(parse(text))
    assert open_door_segments(building) == [(10, 0, 10, 10)]
    assert door_segments(building) == []


def test_unlinked_components_pack_around_the_linked_group() -> None:
    text = (
        'room a "A" 10x10 root\n'
        'room b "B" 10x10 root\n'
        'room c "C" 10x10 root\n'
        "link b down-of a"
    )
    building = solve(parse(text))
    assert (building.room("a").x, building.room("a").y) == (0, 0)
    assert (building.room("b").x, building.room("b").y) == (0, 10)
    assert (building.room("c").x, building.room("c").y) == (20, 0)


def test_overlap_caused_by_a_link_is_detected() -> None:
    text = (
        'room a "A" 20x20 root\n'
        'room b "B" 10x10 down-of a\n'
        'room c "C" 10x10 root\n'
        'room d "D" 10x10 left-of c\n'
        "link c right-of b"
    )
    with pytest.raises(OverlapError):
        solve(parse(text))


# --- stairs ----------------------------------------------------------------


def footprints(text: str) -> list[tuple[int, int, int, int]]:
    return [rect for _, rect in stair_footprints(solve(parse(text)))]


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        # A 30x30 room at the origin. Default footprint is one grid square
        # across the run and two along it, centred (rounded down to the grid).
        pytest.param("stairs up hall down=right", (10, 10, 10, 5), id="run-east"),
        pytest.param("stairs down hall down=up", (10, 10, 5, 10), id="run-north"),
        # Explicit size and position, measured from the room's NW corner.
        pytest.param(
            "stairs in hall down=left size=15x5 at=10,5",
            (10, 5, 15, 5),
            id="explicit-size-and-at",
        ),
        # at= may butt the footprint against the far walls.
        pytest.param(
            "stairs up hall down=down size=5x10 at=25,20",
            (25, 20, 5, 10),
            id="flush-far-corner",
        ),
    ],
)
def test_stair_footprint_geometry(
    statement: str, expected: tuple[int, int, int, int]
) -> None:
    text = f'room hall "Hall" 30x30 root\n{statement}'
    assert footprints(text) == [expected]


def test_stair_footprint_is_room_relative() -> None:
    # The room sits away from the origin; the footprint follows it.
    text = (
        'room a "A" 10x10 root\n'
        'room hall "Hall" 20x20 right-of a\n'
        "stairs up hall down=right"
    )
    assert footprints(text) == [(15, 5, 10, 5)]


def test_two_stairs_may_share_a_room() -> None:
    text = (
        'room landing "Landing" 20x20 root\n'
        "stairs up landing down=left at=0,0\n"
        "stairs down landing down=right at=10,15"
    )
    assert footprints(text) == [(0, 0, 10, 5), (10, 15, 10, 5)]


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            'room hall "Hall" 20x20 root\nstairs up ghost down=up',
            id="unknown-room",
        ),
        pytest.param(
            'room hall "Hall" 5x5 root\nstairs up hall down=right',
            id="default-footprint-too-wide",
        ),
        pytest.param(
            'room hall "Hall" 20x20 root\nstairs up hall down=up size=25x5',
            id="explicit-size-too-wide",
        ),
        pytest.param(
            'room hall "Hall" 20x20 root\nstairs up hall down=right at=15,0',
            id="at-pushes-past-the-wall",
        ),
        pytest.param(
            'room landing "Landing" 20x20 root\n'
            "stairs up landing down=left at=0,0\n"
            "stairs down landing down=right at=5,0",
            id="overlapping-footprints",
        ),
    ],
)
def test_invalid_stairs_raise(source: str) -> None:
    with pytest.raises(LayoutError):
        solve(parse(source))


def test_stairs_that_do_not_fit_report_the_room() -> None:
    text = 'room hall "Hall" 5x5 root\nstairs up hall down=right'
    with pytest.raises(LayoutError) as exc:
        solve(parse(text))
    assert "'hall'" in exc.value.message
    assert exc.value.line == 2


# --- overlap detection -----------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "expected_rect"),
    [
        pytest.param(
            placed("a", 0, 0, 20, 20),
            placed("b", 10, 10, 20, 20),
            (10, 10, 10, 10),
            id="partial-corner-overlap",
        ),
        pytest.param(
            placed("a", 0, 0, 40, 40),
            placed("b", 10, 10, 10, 10),
            (10, 10, 10, 10),
            id="b-fully-contained-in-a",
        ),
        pytest.param(
            placed("a", 0, 0, 20, 40),
            placed("b", 10, 0, 20, 40),
            (10, 0, 10, 40),
            id="half-overlap",
        ),
    ],
)
def test_find_overlaps_reports_intersection_rectangle(
    a: Room, b: Room, expected_rect: tuple[int, int, int, int]
) -> None:
    overlaps = find_overlaps(building_of(a, b))
    assert len(overlaps) == 1
    first, second, rect = overlaps[0]
    assert (first.id, second.id) == ("a", "b")
    assert rect == expected_rect


@pytest.mark.parametrize(
    ("a", "b"),
    [
        pytest.param(
            placed("a", 0, 0, 20, 20),
            placed("b", 20, 0, 20, 20),
            id="flush-shared-vertical-edge",
        ),
        pytest.param(
            placed("a", 0, 0, 20, 20),
            placed("b", 0, 20, 20, 20),
            id="flush-shared-horizontal-edge",
        ),
        pytest.param(
            placed("a", 0, 0, 20, 20),
            placed("b", 20, 20, 20, 20),
            id="corner-touching-only",
        ),
        pytest.param(
            placed("a", 0, 0, 20, 20),
            placed("b", 100, 100, 20, 20),
            id="fully-disjoint",
        ),
    ],
)
def test_flush_and_touching_rooms_do_not_overlap(a: Room, b: Room) -> None:
    assert find_overlaps(building_of(a, b)) == []


def test_find_overlaps_finds_every_colliding_pair() -> None:
    # Three mutually overlapping rooms -> all three pairs.
    overlaps = find_overlaps(
        building_of(
            placed("a", 0, 0, 30, 30),
            placed("b", 10, 10, 30, 30),
            placed("c", 20, 20, 30, 30),
        )
    )
    pairs = {(first.id, second.id) for first, second, _ in overlaps}
    assert pairs == {("a", "b"), ("a", "c"), ("b", "c")}


def test_solved_manor_has_no_overlaps() -> None:
    source = Path("examples/manor.porta").read_text()
    assert find_overlaps(solve(parse(source))) == []


# 'd' loops back over the root 'a' via the b->c->d chain.
OVERLAPPING = (
    'room a "A" 40x20 root\n'
    'room b "B" 20x20 down-of a\n'
    'room c "C" 20x20 right-of b\n'
    'room d "D" 20x40 up-of c'
)


def test_solve_raises_overlap_error_with_rooms_and_rectangle() -> None:
    # Read the collision off the real solve path: 'a' (root) and 'd' overlap
    # on (20, 0, 20, 20). The error carries this structurally for the CLI.
    with pytest.raises(OverlapError) as exc:
        solve(parse(OVERLAPPING))
    assert exc.value.rooms == ("a", "d")
    assert exc.value.rect == (20, 0, 20, 20)


# --- blocks ----------------------------------------------------------------

TWO_ADJACENT = 'room a "" 20x20 root\nroom b "" 20x20 right-of a'


def test_block_drops_the_internal_default_door() -> None:
    assert len(door_segments(solve(parse(TWO_ADJACENT)))) == 1  # the default door
    blocked = solve(parse(TWO_ADJACENT + '\nblock h "Hall" a b'))
    assert door_segments(blocked) == []  # internal wall: door dropped


def test_valid_block_solves_without_warnings() -> None:
    src = 'room a "" 20x20 root\nroom b "" 20x20 down-of a\nblock h "H" a b'
    building = solve(parse(src))
    assert building.warnings == []


def test_member_name_is_suppressed_with_a_warning() -> None:
    building = solve(parse('room a "Kept" 20x20 root\nblock h "Hall" a'))
    assert any("suppressed" in w and "'a'" in w for w in building.warnings)


def test_explicit_internal_door_is_dropped_with_a_warning() -> None:
    src = 'room a "" 20x20 root\nroom b "" 20x20 right-of a door=10\nblock h "H" a b'
    building = solve(parse(src))
    assert door_segments(building) == []
    assert any("explicit door" in w for w in building.warnings)


def test_standalone_internal_door_is_dropped_with_a_warning() -> None:
    src = 'room a "" 20x20 root\nroom b "" 20x20 right-of a\nblock h "H" a b\ndoor a b'
    building = solve(parse(src))
    assert door_segments(building) == []
    assert any("same block" in w for w in building.warnings)


def test_block_keeps_doors_to_rooms_outside_it() -> None:
    # 'c' is outside the block; its wall with member 'b' still gets a door.
    src = (
        'room a "" 20x20 root\nroom b "" 20x20 right-of a\n'
        'room c "" 20x20 right-of b\nblock h "H" a b'
    )
    assert len(door_segments(solve(parse(src)))) == 1  # only the b|c door survives


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            'room a "" 20x20 root\nblock h "H" a nonesuch', id="unknown-member"
        ),
        pytest.param(
            'room a "" 20x20 root\nroom b "" 20x20 right-of a\nblock h "H" a glyph=b',
            id="glyph-not-a-member",
        ),
        pytest.param(
            'room a "" 20x20 root\nroom b "" 20x20 right-of a\n'
            'room c "" 20x20 right-of b\nblock h "H" a c',
            id="non-contiguous",
        ),
        pytest.param(
            'room a "" 20x20 root\nroom b "" 20x20 right-of a\n'
            'block h "H" a b\nblock g "G" a',
            id="room-in-two-blocks",
        ),
    ],
)
def test_invalid_block_layout_raises(source: str) -> None:
    with pytest.raises(LayoutError):
        solve(parse(source))


# --- display glyphs ---------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            'room a "" 20x20 root glyph="9"\nroom b "" 20x20 right-of a glyph="9"',
            id="room-room",
        ),
        pytest.param(
            'room a "" 20x20 root glyph="9"\nroom b "" 20x20 right-of a\n'
            'block h "" glyph="9" b',
            id="room-block",
        ),
        pytest.param(
            'room a "" 20x20 root\nroom b "" 20x20 right-of a\n'
            'room c "" 20x20 right-of b\n'
            'block h "" glyph="9" a\nblock g "" glyph="9" c',
            id="block-block",
        ),
    ],
)
def test_duplicate_explicit_glyph_raises(source: str) -> None:
    with pytest.raises(LayoutError, match="glyph '9' is used by both"):
        solve(parse(source))


def test_duplicate_glyph_error_reports_the_second_line() -> None:
    src = 'room a "" 20x20 root glyph="9"\nroom b "" 20x20 right-of a glyph="9"'
    with pytest.raises(LayoutError) as exc:
        solve(parse(src))
    assert exc.value.line == 2


def test_unlabeled_rooms_do_not_collide() -> None:
    # glyph="" labels nothing, so any number of them may coexist.
    src = 'room a "" 20x20 root glyph=""\nroom b "" 20x20 right-of a glyph=""'
    assert solve(parse(src)).warnings == []


def test_member_glyph_is_suppressed_with_a_warning_not_an_error() -> None:
    # The member's glyph is inert, so it neither collides with the identical
    # room glyph outside the block nor shows up anywhere; it just warns.
    src = (
        'room a "" 20x20 root glyph="9"\n'
        'room b "" 20x20 right-of a glyph="9"\n'
        'block h "" b'
    )
    building = solve(parse(src))
    assert any("glyph '9' is suppressed" in w and "'b'" in w for w in building.warnings)
