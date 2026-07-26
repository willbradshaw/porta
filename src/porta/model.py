"""Data model for porta.

Plain dataclasses passed between the parser, layout engine, and renderers.
These carry no behaviour beyond holding parsed/solved state. See
``docs/room.md`` and ``docs/door.md`` for the model these structures encode.

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
class Door:
    """A door on the wall a relation's room shares with its anchor.

    ``offset`` (feet from the wall's near end) defaults to ``None``, meaning
    "centred" — the layout computes it. An ``open`` door is a doorless
    opening: placed and validated like any door, but rendered as a gap in
    the wall (dashed) instead of a door mark — a non-blocking boundary.
    """

    width: int = 5
    offset: int | None = None
    open: bool = False


@dataclass(frozen=True)
class Relation:
    """A single placement relation: this room sits ``direction`` of ``anchor``."""

    direction: Direction
    anchor: str
    line: int
    align: Align = Align.START  # free-axis alignment
    shift: int = 0  # feet to nudge along the free axis after aligning
    # Door handling on the shared wall: a real wall gets a default door unless
    # ``no_door`` suppresses it; ``door`` overrides the default width/position.
    door: Door | None = None
    no_door: bool = False


@dataclass
class Room:
    """A room: a labelled rectangle plus how it attaches to its neighbours.

    Coordinates are not held here yet; the layout engine (Stage 2) derives them.
    """

    id: str
    name: str | None
    width: int
    height: int
    # Display glyph: ``None`` = assign automatically; ``""`` = unlabeled (no
    # glyph, no key entry); anything else is drawn and keyed verbatim.
    glyph: str | None = None
    is_root: bool = False
    relations: list[Relation] = field(default_factory=list)
    line: int = 0
    # ``?`` dimensions: the layout resolves these from the anchor across the
    # parallel shared wall (``width`` / ``height`` hold 0 until then).
    auto_width: bool = False
    auto_height: bool = False
    # Filled by the layout engine (top-left corner, in feet); None until solved.
    x: int | None = None
    y: int | None = None


@dataclass(frozen=True)
class Doorway:
    """A standalone door between two adjacent rooms (any pair, not just anchors)."""

    a: str
    b: str
    door: Door
    line: int


@dataclass(frozen=True)
class ExternalDoor:
    """A door on a room's exterior ``side`` edge, opening to the outside."""

    room: str
    side: Direction
    door: Door
    line: int


@dataclass(frozen=True)
class Block:
    """A merged (possibly non-rectangular) room: a union of member rooms.

    The members are normal rooms placed by the usual relations; the block drops
    the walls they share with each other so they read as one space. The block
    carries a single glyph — explicit via ``glyph``, else derived from ``id`` —
    drawn in ``glyph_member`` (or the first member when unset), and ``name``
    (if any) labels the union in the key.
    """

    id: str
    name: str | None
    members: list[str]
    glyph_member: str | None = None
    # Display glyph, with the same semantics as :attr:`Room.glyph`.
    glyph: str | None = None
    line: int = 0


@dataclass
class Building:
    """Rooms (with id lookup) plus standalone and external doors.

    ``warnings`` collects non-fatal advisories raised while solving (e.g. a
    suppressed name or door); the CLI prints them but the run still succeeds.
    """

    rooms: list[Room] = field(default_factory=list)
    doors: list[Doorway] = field(default_factory=list)
    external_doors: list[ExternalDoor] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

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
