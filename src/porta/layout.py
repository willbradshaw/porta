"""Resolve relational placement into concrete geometry.

Topological DAG propagation: place the root at the origin, then derive every
other room's coordinates from an already-placed anchor's edge plus a relation
(align-start on the free axis). Also owns the *semantic* validations: exactly
one root, known anchors, no cycles, no disconnected rooms.

Coordinates are integer feet; ``x`` increases east, ``y`` increases south
(north = up). A room's ``(x, y)`` is its top-left (NW) corner.

Overlap detection is Stage 3; the alignment/spacing modifiers and snug-fit
validation are tracked as separate issues.
"""

from porta.errors import LayoutError, OverlapError
from porta.model import Axis, Building, Direction, Room

# An axis-aligned rectangle as (x, y, width, height) in feet.
Rect = tuple[int, int, int, int]


def solve(building: Building) -> Building:
    """Resolve every room's coordinates in place and return the building.

    Args:
        building: The parsed building (rooms with relations, no coordinates).

    Returns:
        The same building, with each room's ``x``/``y`` populated.

    Raises:
        LayoutError: On any structural problem (root count, unknown anchor,
            cycle, disconnected room, or an unsupported construct).
    """
    rooms = building.rooms
    by_id = {room.id: room for room in rooms}

    root = _find_root(rooms)
    _validate_relations(rooms, by_id)

    root.x, root.y = 0, 0
    placed: set[str] = {root.id}
    pending = [room for room in rooms if not room.is_root]

    progressed = True
    while pending and progressed:
        progressed = False
        for room in list(pending):
            if room.relations and all(rel.anchor in placed for rel in room.relations):
                _place(room, by_id)
                placed.add(room.id)
                pending.remove(room)
                progressed = True

    if pending:
        _raise_unplaceable(pending)

    overlaps = find_overlaps(building)
    if overlaps:
        first, second, rect = overlaps[0]
        raise OverlapError((first.id, second.id), rect)
    return building


def find_overlaps(building: Building) -> list[tuple[Room, Room, Rect]]:
    """Return every pair of overlapping rooms with their intersection rectangle.

    Pure: detection only, no raising. Flush-adjacent and corner-touching rooms
    (zero-area intersection) do not count. Pairs are returned in source order.

    Args:
        building: A solved building (every room has coordinates).

    Returns:
        ``(room_a, room_b, (x, y, w, h))`` triples, one per colliding pair.
    """
    rooms = building.rooms
    overlaps: list[tuple[Room, Room, Rect]] = []
    for i, first in enumerate(rooms):
        for second in rooms[i + 1 :]:
            rect = _intersection(first, second)
            if rect is not None:
                overlaps.append((first, second, rect))
    return overlaps


def _intersection(a: Room, b: Room) -> Rect | None:
    """The overlap rectangle of two placed rooms, or None if they don't overlap."""
    ax, ay, bx, by = a.x, a.y, b.x, b.y
    if ax is None or ay is None or bx is None or by is None:
        raise ValueError("find_overlaps needs a solved building")
    left = max(ax, bx)
    top = max(ay, by)
    right = min(ax + a.width, bx + b.width)
    bottom = min(ay + a.height, by + b.height)
    width, height = right - left, bottom - top
    if width > 0 and height > 0:
        return (left, top, width, height)
    return None


def _find_root(rooms: list[Room]) -> Room:
    """Return the sole root, or raise if there are zero or several."""
    roots = [room for room in rooms if room.is_root]
    if not roots:
        raise LayoutError("the building needs exactly one root room, but has none")
    if len(roots) > 1:
        ids = ", ".join(repr(room.id) for room in roots)
        raise LayoutError(
            f"the building has more than one root room ({ids})", line=roots[1].line
        )
    root = roots[0]
    if root.relations:
        raise LayoutError(
            f"root room {root.id!r} cannot also have relations", line=root.line
        )
    return root


def _validate_relations(rooms: list[Room], by_id: dict[str, Room]) -> None:
    """Check anchors exist and that no room pins the same axis twice."""
    for room in rooms:
        seen_axes: set[Axis] = set()
        for rel in room.relations:
            if rel.anchor not in by_id:
                raise LayoutError(
                    f"room {room.id!r} references unknown room {rel.anchor!r}",
                    line=rel.line,
                )
            if rel.direction.axis in seen_axes:
                raise LayoutError(
                    f"room {room.id!r} has two relations on the same "
                    f"({rel.direction.axis.value}) axis (not yet supported)",
                    line=room.line,
                )
            seen_axes.add(rel.direction.axis)


def _place(room: Room, by_id: dict[str, Room]) -> None:
    """Set ``room``'s coordinates from its (already-placed) anchors."""
    x: int | None = None
    y: int | None = None
    x_fallback: int | None = None
    y_fallback: int | None = None

    for rel in room.relations:
        anchor = by_id[rel.anchor]
        ax, ay = anchor.x, anchor.y
        assert ax is not None  # anchors are placed before dependents
        assert ay is not None
        if rel.direction is Direction.RIGHT:
            x = ax + anchor.width
            y_fallback = ay
        elif rel.direction is Direction.LEFT:
            x = ax - room.width
            y_fallback = ay
        elif rel.direction is Direction.DOWN:
            y = ay + anchor.height
            x_fallback = ax
        else:  # Direction.UP
            y = ay - room.height
            x_fallback = ax

    room.x = x if x is not None else x_fallback
    room.y = y if y is not None else y_fallback


def _raise_unplaceable(pending: list[Room]) -> None:
    """Diagnose why rooms could not be placed: disconnected vs. a cycle."""
    orphan = next((room for room in pending if not room.relations), None)
    if orphan is not None:
        raise LayoutError(
            f"room {orphan.id!r} is not connected to the root", line=orphan.line
        )
    ids = ", ".join(repr(room.id) for room in pending)
    raise LayoutError(f"dependency cycle among rooms: {ids}", line=pending[0].line)
