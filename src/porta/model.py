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
    A ``secret`` door is concealed: the wall renders intact with an "S"
    marker over the door's span. A door is at most one of the two.
    """

    width: int = 5
    offset: int | None = None
    open: bool = False
    secret: bool = False


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


class StairSense(Enum):
    """Where a flight of stairs leads, relative to the floor being drawn."""

    UP = "up"  # leaves this floor upward
    DOWN = "down"  # leaves this floor downward
    IN = "in"  # a level change within the floor (e.g. steps up to a dais)


@dataclass(frozen=True)
class Stairs:
    """A flight of stairs drawn inside a room.

    ``down`` is the plan direction that leads downward on the flight — the
    direction the rendered treads narrow toward. The open (entrance) sides
    derive from it and the sense: ``UP`` opens toward ``down``, ``DOWN``
    opens away from it, ``IN`` opens at both ends of the run.
    """

    room: str
    sense: StairSense
    down: Direction
    size: tuple[int, int] | None = None  # (w, h) in feet; None = default
    at: tuple[int, int] | None = (
        None  # offset from the room's NW corner; None = centred
    )
    line: int = 0


@dataclass(frozen=True)
class Divider:
    """A dashed dividing line along the boundary of two same-block members.

    A block suppresses the wall between its members; a divider draws that
    boundary back in as a thin dashed line. Spans where a stair entrance
    meets the boundary are left out, so a flight through the divider keeps
    its open end (see :func:`~porta.layout.divider_segments`).
    """

    a: str
    b: str
    line: int = 0


@dataclass(frozen=True)
class Link:
    """A cross-component join: a relation that reaches between components.

    Places the whole component containing ``room`` so that ``room`` sits in
    ``relation`` to the anchor room (which lives in another component) —
    flush, wall-shared, and with the usual align/shift and door handling.
    Only the component's translation is affected; its internal geometry,
    root, and relations are untouched.
    """

    room: str
    relation: Relation
    line: int


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
    links: list[Link] = field(default_factory=list)
    stairs: list[Stairs] = field(default_factory=list)
    dividers: list[Divider] = field(default_factory=list)
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
