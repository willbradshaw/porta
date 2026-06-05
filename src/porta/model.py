"""Data model for porta.

Plain dataclasses passed between the parser, layout engine, and renderers.
These carry no behaviour beyond holding parsed/solved state. See
``docs/design.md`` for the placement model these structures encode.

Relations are stored axis-first: a :class:`Direction` knows its :class:`Axis`,
so the four surface keywords (and any future compass or floor-axis aliases)
are just a parser-side keyword mapping with no change to the model.
"""

from dataclasses import dataclass, field
from enum import Enum


class Axis(Enum):
    """The two in-plane axes a relation can pin."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class Direction(Enum):
    """A relational placement direction, keyed by its surface keyword."""

    UP = "up-of"
    DOWN = "down-of"
    LEFT = "left-of"
    RIGHT = "right-of"

    @property
    def axis(self) -> Axis:
        """The axis this direction pins (vertical for up/down, else horizontal)."""
        if self in (Direction.UP, Direction.DOWN):
            return Axis.VERTICAL
        return Axis.HORIZONTAL


class Align(Enum):
    """Free-axis alignment of a room against its anchor (default ``START``)."""

    START = "start"  # near edges flush
    END = "end"  # far edges flush


@dataclass(frozen=True)
class Relation:
    """A single placement relation: this room sits ``direction`` of ``anchor``."""

    direction: Direction
    anchor: str
    line: int
    align: Align = Align.START  # free-axis alignment
    shift: int = 0  # feet to nudge along the free axis after aligning


@dataclass
class Room:
    """A room: a labelled rectangle plus how it attaches to its neighbours.

    Coordinates are not held here yet; the layout engine (Stage 2) derives them.
    """

    id: str
    name: str
    width: int
    height: int
    is_root: bool = False
    relations: list[Relation] = field(default_factory=list)
    line: int = 0
    # Filled by the layout engine (top-left corner, in feet); None until solved.
    x: int | None = None
    y: int | None = None


@dataclass
class Building:
    """An ordered collection of rooms with id lookup."""

    rooms: list[Room] = field(default_factory=list)

    def room(self, room_id: str) -> Room:
        """Return the room with ``room_id``.

        Args:
            room_id: The id to look up.

        Returns:
            The matching :class:`Room`.

        Raises:
            KeyError: If no room has that id.
        """
        for room in self.rooms:
            if room.id == room_id:
                return room
        raise KeyError(room_id)
