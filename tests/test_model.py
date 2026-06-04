"""Stage 1: the data model — the axis-based relation representation.

The four surface keywords (up/down/left/right-of) are stored as a ``Direction``
whose *axis* is the real internal datum, so compass/floor-axis aliases can be
added later as a pure parser-side keyword mapping with no model change.
"""

import pytest

from porta.model import Axis, Direction


@pytest.mark.parametrize(
    ("direction", "expected_axis"),
    [
        (Direction.UP, Axis.VERTICAL),
        (Direction.DOWN, Axis.VERTICAL),
        (Direction.LEFT, Axis.HORIZONTAL),
        (Direction.RIGHT, Axis.HORIZONTAL),
    ],
)
def test_direction_maps_to_expected_axis(direction: Direction, expected_axis: Axis) -> None:
    assert direction.axis is expected_axis
