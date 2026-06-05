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
from porta.model import (
    Align,
    Axis,
    Building,
    Direction,
    Door,
    Doorway,
    ExternalDoor,
    Relation,
    Room,
)

_GRID_FT = 5
# An axis-aligned rectangle as (x, y, width, height) in feet.
Rect = tuple[int, int, int, int]
# A line segment as (x1, y1, x2, y2) in feet.
Segment = tuple[int, int, int, int]


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
    if root.auto_width or root.auto_height:
        raise LayoutError(
            f"root {root.id!r} cannot use '?' (no anchor to size against)",
            line=root.line,
        )

    root.x, root.y = 0, 0
    placed: set[str] = {root.id}
    pending = [room for room in rooms if not room.is_root]

    progressed = True
    while pending and progressed:
        progressed = False
        for room in list(pending):
            if room.relations and all(rel.anchor in placed for rel in room.relations):
                _resolve_auto_dims(room, by_id)
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

    door_segments(building)  # validates every door (raises on a bad one)
    return building


def _resolve_auto_dims(room: Room, by_id: dict[str, Room]) -> None:
    """Resolve a room's ``?`` dimensions to fill the sizing anchor's wall.

    Called in topological order, so each anchor's own dimensions are already
    resolved. A ``?`` extends the room from whichever edge its placement has
    fixed to the sizing anchor's matching edge, across the parallel shared wall
    (``up/down-of`` sizes the *width*, ``left/right-of`` the *height*).
    """
    if room.auto_width:
        room.width = _auto_extent(room, by_id, Axis.HORIZONTAL)
    if room.auto_height:
        room.height = _auto_extent(room, by_id, Axis.VERTICAL)


def _auto_extent(room: Room, by_id: dict[str, Room], dim_axis: Axis) -> int:
    """Resolve a ``?`` on ``dim_axis``: the snug-fit gap if pinned on both sides,
    else the span from the room's fixed edge to the sizing anchor's edge."""
    if dim_axis is Axis.HORIZONTAL:
        dim_name, hint = "width", "up-of/down-of"
    else:
        dim_name, hint = "height", "left-of/right-of"
    gap = _opposite_gap(room, by_id, dim_axis)
    if gap is not None:  # axis pinned on both sides -> fill the gap (snug-fit)
        if gap <= 0:
            raise LayoutError(
                f"room {room.id!r}: '?' {dim_name} resolves to {gap} ft "
                f"(its anchors overlap or are reversed)",
                line=room.line,
            )
        return gap
    union = _union_bbox(room, by_id, dim_axis)
    if union is not None:  # several sizing walls -> span all of them
        return union[1] - union[0]
    sizing = _sizing_relation(room, _perp(dim_axis), dim_name, hint)
    anchor = by_id[sizing.anchor]
    a_lo = _axis_lo(anchor, dim_axis)
    a_hi = a_lo + _axis_dim(anchor, dim_axis)
    fixed, is_far = _fixed_edge(room, by_id, dim_axis, sizing)
    # Fill from the fixed edge to the anchor's opposite edge.
    extent = (fixed - a_lo) if is_far else (a_hi - fixed)
    if extent <= 0:
        raise LayoutError(
            f"room {room.id!r}: '?' {dim_name} resolves to {extent} ft "
            f"(it does not reach across {anchor.id!r})",
            line=room.line,
        )
    return extent


def _fixed_edge(
    room: Room, by_id: dict[str, Room], dim_axis: Axis, sizing: Relation
) -> tuple[int, bool]:
    """The room edge placement nails on ``dim_axis``: ``(coordinate, is_far_edge)``.

    Always a constant (from anchor positions), never the room's own size — which
    is why a ``?`` is never circular.
    """
    for rel in room.relations:
        if rel.direction.axis is dim_axis:  # this relation positions the room here
            anchor = by_id[rel.anchor]
            lo = _axis_lo(anchor, dim_axis)
            if rel.direction in (Direction.DOWN, Direction.RIGHT):
                return lo + _axis_dim(anchor, dim_axis), False  # near edge at far side
            return lo, True  # up/left-of: far edge at the anchor's near side
    anchor = by_id[sizing.anchor]
    lo = _axis_lo(anchor, dim_axis)
    if sizing.align is Align.END:
        return lo + _axis_dim(anchor, dim_axis) + sizing.shift, True
    return lo + sizing.shift, False


def _sizing_relation(room: Room, axis: Axis, dim: str, hint: str) -> Relation:
    """The sole relation whose shared wall is parallel to ``dim`` (else error)."""
    matches = [rel for rel in room.relations if rel.direction.axis is axis]
    if not matches:
        raise LayoutError(
            f"room {room.id!r}: '?' {dim} needs a {hint} relation to size against",
            line=room.line,
        )
    return matches[0]


def _perp(axis: Axis) -> Axis:
    return Axis.VERTICAL if axis is Axis.HORIZONTAL else Axis.HORIZONTAL


def _axis_lo(room: Room, axis: Axis) -> int:
    value = room.x if axis is Axis.HORIZONTAL else room.y
    assert value is not None
    return value


def _axis_dim(room: Room, axis: Axis) -> int:
    return room.width if axis is Axis.HORIZONTAL else room.height


def _axis_hi(room: Room, axis: Axis) -> int:
    return _axis_lo(room, axis) + _axis_dim(room, axis)


def _opposite_gap(room: Room, by_id: dict[str, Room], axis: Axis) -> int | None:
    """Gap between the anchors when ``axis`` is pinned on both sides, else None.

    The positive direction (``right/down-of``) fixes the room's near edge at its
    anchor's far edge; the negative (``left/up-of``) fixes the far edge at its
    anchor's near edge. The room must exactly fill the space between them.
    """
    near = far = None
    for rel in room.relations:
        if rel.direction.axis is not axis:
            continue
        anchor = by_id[rel.anchor]
        if rel.direction in (Direction.RIGHT, Direction.DOWN):
            near = _axis_lo(anchor, axis) + _axis_dim(anchor, axis)
        else:
            far = _axis_lo(anchor, axis)
    if near is None or far is None:
        return None
    return far - near


def _union_bbox(
    room: Room, by_id: dict[str, Room], axis: Axis
) -> tuple[int, int] | None:
    """The ``(near, far)`` a union ``?`` spans on ``axis``, or None if not a union.

    A union applies when ``axis`` carries the room's auto dimension, has no
    relation of its own (it is free), and is sized by *several* walls on the
    perpendicular axis (a same-direction pair, or an opposite pair on the other
    axis). The ``?`` then spans the bounding box of all those anchors — driving
    both the size and, via :func:`_free_axis_position`, the near-edge position.
    """
    auto = room.auto_width if axis is Axis.HORIZONTAL else room.auto_height
    if not auto or any(rel.direction.axis is axis for rel in room.relations):
        return None
    sizing = [rel for rel in room.relations if rel.direction.axis is _perp(axis)]
    if len(sizing) < 2:
        return None
    near = min(_axis_lo(by_id[rel.anchor], axis) for rel in sizing)
    far = max(_axis_hi(by_id[rel.anchor], axis) for rel in sizing)
    return near, far


def door_segments(building: Building) -> list[Segment]:
    """Return the door line ``(x1, y1, x2, y2)`` for every door in the building.

    Doors are on by default: a relation with a real shared wall gets a default
    door unless ``no_door`` suppresses it; an explicit ``door`` overrides its
    width/position. Validates each door (raising on an explicit door that has no
    wall or doesn't fit). Assumes a solved building.
    """
    by_id = {room.id: room for room in building.rooms}
    segments: list[Segment] = []
    for room in building.rooms:
        for rel in room.relations:
            if rel.no_door:
                continue
            segment = _relation_door(room, by_id[rel.anchor], rel)
            if segment is not None:
                segments.append(segment)
    for doorway in building.doors:
        segments.append(_doorway_door(doorway, by_id))
    for external in building.external_doors:
        segments.append(_external_door_line(external, by_id, building.rooms))
    _check_door_overlaps(segments)
    return segments


def _external_door_line(
    external: ExternalDoor, by_id: dict[str, Room], rooms: list[Room]
) -> Segment:
    """Door line on a room's exterior ``side`` edge; validates fit and that the
    span is genuinely exterior (no room flush on the other side)."""
    room = by_id.get(external.room)
    if room is None:
        raise LayoutError(
            f"external door references unknown room {external.room!r}",
            line=external.line,
        )
    horizontal, coord, lo, length = _edge(room, external.side)
    segment = _door_on_wall(
        external.door, horizontal, coord, lo, length, external.room, external.line
    )
    span = (segment[0], segment[2]) if horizontal else (segment[1], segment[3])
    for other in rooms:
        if other.id != room.id and _flush_outside(room, external.side, other, span):
            raise LayoutError(
                f"external door on {room.id!r} ({external.side.value}) is not "
                f"exterior: {other.id!r} is on the other side",
                line=external.line,
            )
    return segment


def _edge(room: Room, side: Direction) -> _Wall:
    """The room's ``side`` edge as (horizontal?, fixed coord, near end, length)."""
    rx, ry = _axis_lo(room, Axis.HORIZONTAL), _axis_lo(room, Axis.VERTICAL)
    if side is Direction.UP:
        return True, ry, rx, room.width
    if side is Direction.DOWN:
        return True, ry + room.height, rx, room.width
    if side is Direction.LEFT:
        return False, rx, ry, room.height
    return False, rx + room.width, ry, room.height  # RIGHT


def _flush_outside(
    room: Room, side: Direction, other: Room, span: tuple[int, int]
) -> bool:
    """Whether ``other`` sits flush against ``room``'s ``side`` over ``span``."""
    wall = _perp(side.axis)
    lo, hi = max(span[0], _axis_lo(other, wall)), min(span[1], _axis_hi(other, wall))
    if hi <= lo:  # no overlap along the wall
        return False
    if side is Direction.UP:
        return _axis_hi(other, Axis.VERTICAL) == _axis_lo(room, Axis.VERTICAL)
    if side is Direction.DOWN:
        return _axis_lo(other, Axis.VERTICAL) == _axis_hi(room, Axis.VERTICAL)
    if side is Direction.LEFT:
        return _axis_hi(other, Axis.HORIZONTAL) == _axis_lo(room, Axis.HORIZONTAL)
    return _axis_lo(other, Axis.HORIZONTAL) == _axis_hi(room, Axis.HORIZONTAL)  # RIGHT


def _check_door_overlaps(segments: list[Segment]) -> None:
    """Raise if two doors occupy overlapping space on the same wall line.

    Two doors between the same rooms are fine (e.g. a pair of openings); two
    that *overlap* are almost certainly a mistake.
    """
    for i, first in enumerate(segments):
        for second in segments[i + 1 :]:
            if _doors_overlap(first, second):
                raise LayoutError(f"two doors overlap: {first} and {second}")


def _doors_overlap(a: Segment, b: Segment) -> bool:
    """Whether two door segments share interior space on a common wall line."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    if ay1 == ay2 and by1 == by2 and ay1 == by1:  # both horizontal, same y
        return min(ax2, bx2) > max(ax1, bx1)
    if ax1 == ax2 and bx1 == bx2 and ax1 == bx1:  # both vertical, same x
        return min(ay2, by2) > max(ay1, by1)
    return False


# A wall as (horizontal?, fixed coordinate, near-end, length) in feet.
_Wall = tuple[bool, int, int, int]


def _relation_door(room: Room, anchor: Room, rel: Relation) -> Segment | None:
    """Door line on the wall ``room`` shares with its ``anchor`` (None if no door).

    A real shared wall gets a default 5-ft door; ``rel.door`` overrides it. An
    *explicit* door on a relation with no wall (or too big to fit) raises; a
    *default* door is simply absent when there is no wall (a coordinate-pin).
    """
    horizontal, coord, lo, length = _relation_wall(room, anchor, rel)
    if length <= 0:
        if rel.door is not None:
            raise LayoutError(
                f"door on room {room.id!r}: it shares no wall with {anchor.id!r}",
                line=rel.line,
            )
        return None  # default door needs a real wall
    door = rel.door if rel.door is not None else Door()
    return _door_on_wall(door, horizontal, coord, lo, length, room.id, rel.line)


def _doorway_door(doorway: Doorway, by_id: dict[str, Room]) -> Segment:
    """Door line for a standalone ``door a b`` between two adjacent rooms."""
    for room_id in (doorway.a, doorway.b):
        if room_id not in by_id:
            raise LayoutError(
                f"door references unknown room {room_id!r}", line=doorway.line
            )
    wall = _shared_wall(by_id[doorway.a], by_id[doorway.b])
    if wall is None:
        raise LayoutError(
            f"door: rooms {doorway.a!r} and {doorway.b!r} share no wall",
            line=doorway.line,
        )
    horizontal, coord, lo, length = wall
    return _door_on_wall(
        doorway.door, horizontal, coord, lo, length, doorway.a, doorway.line
    )


def _relation_wall(room: Room, anchor: Room, rel: Relation) -> _Wall:
    """The wall a relation puts ``room`` against (length <= 0 means corner-touch)."""
    rx, ry = room.x, room.y
    ax, ay = anchor.x, anchor.y
    assert rx is not None
    assert ry is not None
    assert ax is not None
    assert ay is not None
    if _free_axis(rel.direction) is Axis.HORIZONTAL:
        lo = max(rx, ax)
        length = min(rx + room.width, ax + anchor.width) - lo
        coord = ry + room.height if rel.direction is Direction.UP else ry
        return True, coord, lo, length
    lo = max(ry, ay)
    length = min(ry + room.height, ay + anchor.height) - lo
    coord = rx + room.width if rel.direction is Direction.LEFT else rx
    return False, coord, lo, length


def _shared_wall(a: Room, b: Room) -> _Wall | None:
    """The wall two adjacent rooms share, or None if they are not wall-adjacent."""
    ax, ay = a.x, a.y
    bx, by = b.x, b.y
    assert ax is not None
    assert ay is not None
    assert bx is not None
    assert by is not None
    if ax + a.width == bx or bx + b.width == ax:  # vertical shared edge
        lo, hi = max(ay, by), min(ay + a.height, by + b.height)
        if hi > lo:
            coord = ax + a.width if ax + a.width == bx else ax
            return False, coord, lo, hi - lo
    if ay + a.height == by or by + b.height == ay:  # horizontal shared edge
        lo, hi = max(ax, bx), min(ax + a.width, bx + b.width)
        if hi > lo:
            coord = ay + a.height if ay + a.height == by else ay
            return True, coord, lo, hi - lo
    return None


def _door_on_wall(
    door: Door,
    horizontal: bool,
    coord: int,
    lo: int,
    length: int,
    label: str,
    line: int,
) -> Segment:
    """Place ``door`` on a wall segment of ``length``; raise if it doesn't fit."""
    if door.width > length:
        raise LayoutError(
            f"door on {label!r} ({door.width} ft) is wider than the wall ({length} ft)",
            line=line,
        )
    offset = (
        door.offset
        if door.offset is not None
        else ((length - door.width) // (2 * _GRID_FT)) * _GRID_FT
    )
    if offset < 0 or offset + door.width > length:
        raise LayoutError(
            f"door on {label!r} does not fit the wall "
            f"(offset {offset} + width {door.width} > {length} ft)",
            line=line,
        )
    start, end = lo + offset, lo + offset + door.width
    if horizontal:
        return (start, coord, end, coord)
    return (coord, start, coord, end)


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
    """Check anchors exist and that align/shift act on a genuinely free axis.

    Two relations on the *same* axis are allowed now (snug-fit / colinear); the
    geometric agreement is checked during placement.
    """
    for room in rooms:
        axes = {rel.direction.axis for rel in room.relations}
        for rel in room.relations:
            if rel.anchor not in by_id:
                raise LayoutError(
                    f"room {room.id!r} references unknown room {rel.anchor!r}",
                    line=rel.line,
                )
            modifies_free_axis = rel.shift != 0 or rel.align is not Align.START
            if modifies_free_axis and _free_axis(rel.direction) in axes:
                raise LayoutError(
                    f"room {room.id!r} cannot align/shift: both axes are constrained",
                    line=rel.line,
                )


def _free_axis(direction: Direction) -> Axis:
    """The axis a relation leaves free (the one align/shift act on)."""
    if direction.axis is Axis.VERTICAL:
        return Axis.HORIZONTAL
    return Axis.VERTICAL


def _aligned(anchor_lo: int, anchor_dim: int, room_dim: int, align: Align) -> int:
    """Free-axis base coordinate: near edge (START) or far edge (END) flush."""
    if align is Align.END:
        return anchor_lo + anchor_dim - room_dim
    return anchor_lo


def _place(room: Room, by_id: dict[str, Room]) -> None:
    """Set ``room``'s coordinates from its (already-placed) anchors."""
    rx = _axis_position(room, by_id, Axis.HORIZONTAL)
    ry = _axis_position(room, by_id, Axis.VERTICAL)
    room.x, room.y = rx, ry
    for rel in room.relations:
        # Only a shift can slide a room off its anchor. A non-shifted relation
        # in a two-axis pin may legitimately only pin a coordinate (corner-touch).
        if rel.shift != 0:
            _check_attached(room, rx, ry, by_id[rel.anchor], rel)
    _check_same_axis_flush(room, by_id)


def _check_same_axis_flush(room: Room, by_id: dict[str, Room]) -> None:
    """When two relations share an axis, each must produce a real shared wall.

    A sole-axis relation may legitimately just pin a coordinate (corner-touch),
    but a relation that shares its axis isn't load-bearing for position — so its
    only purpose is the wall, and it must be flush.
    """
    for axis in (Axis.HORIZONTAL, Axis.VERTICAL):
        rels = [rel for rel in room.relations if rel.direction.axis is axis]
        if len(rels) < 2:
            continue
        wall = _perp(axis)
        for rel in rels:
            anchor = by_id[rel.anchor]
            overlap = min(_axis_hi(room, wall), _axis_hi(anchor, wall)) - max(
                _axis_lo(room, wall), _axis_lo(anchor, wall)
            )
            if overlap <= 0:
                raise LayoutError(
                    f"room {room.id!r}: {rel.direction.value} {rel.anchor!r} is "
                    f"not flush (they share no wall)",
                    line=rel.line,
                )


def _axis_position(room: Room, by_id: dict[str, Room], axis: Axis) -> int:
    """The room's low coordinate on ``axis`` from its relations on that axis.

    Each relation on the axis derives the same low edge; they must agree (this is
    where snug-fit and same-direction colinearity are enforced). With no relation
    on the axis it falls to the free-axis alignment of the first perpendicular
    relation.
    """
    rels = [rel for rel in room.relations if rel.direction.axis is axis]
    dim = _axis_dim(room, axis)
    if not rels:
        return _free_axis_position(room, by_id, axis, dim)
    los = []
    for rel in rels:
        anchor = by_id[rel.anchor]
        if rel.direction in (Direction.RIGHT, Direction.DOWN):
            los.append(_axis_lo(anchor, axis) + _axis_dim(anchor, axis))  # near at far
        else:  # LEFT, UP: far edge meets the anchor's near edge
            los.append(_axis_lo(anchor, axis) - dim)
    if any(lo != los[0] for lo in los[1:]):
        _raise_axis_conflict(room, by_id, axis, rels, dim)
    return los[0]


def _free_axis_position(
    room: Room, by_id: dict[str, Room], axis: Axis, dim: int
) -> int:
    """Position on a free ``axis``.

    For a union ``?`` the near edge is the union's near edge (so the room spans
    every sizing anchor); otherwise it is the align/shift of the first
    perpendicular relation.
    """
    union = _union_bbox(room, by_id, axis)
    if union is not None:
        return union[0]
    for rel in room.relations:  # the first relation that leaves ``axis`` free
        if rel.direction.axis is not axis:
            anchor = by_id[rel.anchor]
            a_lo, a_dim = _axis_lo(anchor, axis), _axis_dim(anchor, axis)
            return _aligned(a_lo, a_dim, dim, rel.align) + rel.shift
    raise AssertionError("a non-root room always has a relation")  # unreachable


def _raise_axis_conflict(
    room: Room, by_id: dict[str, Room], axis: Axis, rels: list[Relation], dim: int
) -> None:
    """Report disagreeing same-axis relations: snug-fit miss vs. unaligned pins."""
    name = "width" if axis is Axis.HORIZONTAL else "height"
    gap = _opposite_gap(room, by_id, axis)
    if gap is not None:  # an opposite pair -> the room doesn't fill the gap
        raise LayoutError(
            f"room {room.id!r}: {name} {dim} does not fill the {gap} ft gap "
            f"between its anchors",
            line=room.line,
        )
    raise LayoutError(
        f"room {room.id!r}: its same-direction anchors are not aligned, so the "
        f"relations disagree on where to place it",
        line=room.line,
    )


def _check_attached(room: Room, rx: int, ry: int, anchor: Room, rel: Relation) -> None:
    """Raise if ``room`` shares no wall with ``anchor`` on the relation's free axis.

    A shift large enough to slide the room off its anchor leaves them touching
    at most at a corner; that detaches the relation and is rejected.
    """
    ax, ay = anchor.x, anchor.y
    assert ax is not None
    assert ay is not None
    if _free_axis(rel.direction) is Axis.HORIZONTAL:
        overlap = min(rx + room.width, ax + anchor.width) - max(rx, ax)
    else:
        overlap = min(ry + room.height, ay + anchor.height) - max(ry, ay)
    if overlap <= 0:
        raise LayoutError(
            f"room {room.id!r} shift={rel.shift} detaches it from "
            f"{anchor.id!r} (no shared wall)",
            line=rel.line,
        )


def _raise_unplaceable(pending: list[Room]) -> None:
    """Diagnose why rooms could not be placed: disconnected vs. a cycle."""
    orphan = next((room for room in pending if not room.relations), None)
    if orphan is not None:
        raise LayoutError(
            f"room {orphan.id!r} is not connected to the root", line=orphan.line
        )
    ids = ", ".join(repr(room.id) for room in pending)
    raise LayoutError(f"dependency cycle among rooms: {ids}", line=pending[0].line)
