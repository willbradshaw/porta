"""Stage 2: the layout engine — DAG propagation and structural validation.

Coordinates are integer feet; ``x`` increases east, ``y`` increases south
(north = up = smaller y). Each room's stored ``(x, y)`` is its top-left (NW)
corner; the root's NW corner is the origin.
"""

import pytest

from porta.errors import LayoutError
from porta.layout import solve
from porta.parser import parse


def coords(text: str, room_id: str) -> tuple[int | None, int | None]:
    room = solve(parse(text)).room(room_id)
    return room.x, room.y


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
    'room entrance "Entrance Hall" 20x20 root\n'
    'room kitchen  "Kitchen"       20x30 left-of entrance\n'
    'room hall     "Great Hall"    40x30 up-of entrance right-of kitchen'
)


@pytest.mark.parametrize(
    ("room_id", "expected"),
    [
        ("entrance", (0, 0)),
        ("kitchen", (-20, 0)),  # left-of entrance; tops flush
        ("hall", (0, -30)),  # y from up-of entrance, x from right-of kitchen
    ],
)
def test_two_relations_pin_both_axes(room_id: str, expected: tuple[int, int]) -> None:
    assert coords(DESIGN_MANOR, room_id) == expected


def test_align_start_propagates_to_create_a_gap() -> None:
    # 'smoking' is east of the tall hall and north of 'drawing'; because
    # 'drawing' align-started to hall's top, 'smoking' rises above the hall's
    # roofline, leaving the south-east corner empty (the spec's §2.4 surprise).
    text = (
        'room hall    "Hall"    20x40 root\n'
        'room drawing "Drawing" 20x20 right-of hall\n'
        'room smoking "Smoking" 20x20 right-of hall up-of drawing'
    )
    assert coords(text, "drawing") == (20, 0)
    assert coords(text, "smoking") == (20, -20)


# --- structural validation -------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        pytest.param('room a "A" 10x10', id="no-root"),
        pytest.param('room a "A" 10x10 root\nroom b "B" 10x10 root', id="two-roots"),
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
        pytest.param('room r "R" 10x10 root\nroom a "A" 10x10', id="disconnected"),
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
