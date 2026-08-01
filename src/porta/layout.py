"""Resolve relational placement into concrete geometry.

Topological DAG propagation: place each component's root at the origin, then
derive every other room's coordinates from an already-placed anchor's edge
plus a relation (align-start on the free axis). Also owns the *semantic*
validations: exactly one root per connected component, known anchors, no
cycles.

A plan may hold several disconnected components (rooms connected by
relations), each with its own root. Every component is solved internally as
usual, then whole components are packed into a west-to-east row with a fixed
gap — packing only translates, never reshapes.

Coordinates are integer feet; ``x`` increases east, ``y`` increases south
(north = up). A room's ``(x, y)`` is its top-left (NW) corner.

Overlap detection is Stage 3; the alignment/spacing modifiers and snug-fit
validation are tracked as separate issues.
"""

from porta.errors import LayoutError, OverlapError
from porta.model import (
    Align,
    Axis,
    Block,
    Building,
    Direction,
    Door,
    Doorway,
    ExternalDoor,
    Relation,
    Room,
)

_GRID_FT = 5
_COMPONENT_GAP_FT = 10  # space between packed components' bounding boxes
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
        LayoutError: On any structural problem (a component with zero or
            several roots, unknown anchor, cycle, or an unsupported
            construct).
    """
    rooms = building.rooms
    by_id = {room.id: room for room in rooms}

    _validate_relations(rooms, by_id)
    components = _components(rooms)
    if not components:
        raise LayoutError("the building needs exactly one root room, but has none")
    for component in components:
        _solve_component(component, by_id, sole=len(components) == 1)
    _pack_components(components)

    overlaps = find_overlaps(building)
    if overlaps:
        first, second, rect = overlaps[0]
        raise OverlapError((first.id, second.id), rect)

    _validate_blocks(building, by_id)
    _validate_glyphs(building)
    building.warnings.extend(_block_warnings(building, by_id, _block_of(building)))

    _placed_doors(building)  # validates every door (raises on a bad one)
    return building


def _block_of(building: Building) -> dict[str, str]:
    """Map each block member's room id to the id of the block it belongs to."""
    return {member: block.id for block in building.blocks for member in block.members}


def _same_block(a: str, b: str, block_of: dict[str, str]) -> bool:
    """Whether rooms ``a`` and ``b`` are members of the same block."""
    return a in block_of and block_of.get(a) == block_of.get(b)


def _validate_blocks(building: Building, by_id: dict[str, Room]) -> None:
    """Check each block: members exist, no room in two blocks, the glyph target is
    a member, and the union of members is contiguous. Assumes placed rooms.
    """
    member_block: dict[str, str] = {}
    for block in building.blocks:
        for member in block.members:
            if member not in by_id:
                raise LayoutError(
                    f"block {block.id!r} references unknown room {member!r}",
                    line=block.line,
                )
            if member in member_block:
                raise LayoutError(
                    f"room {member!r} is in two blocks "
                    f"({member_block[member]!r} and {block.id!r})",
                    line=block.line,
                )
            member_block[member] = block.id
        if block.glyph_member is not None and block.glyph_member not in block.members:
            raise LayoutError(
                f"block {block.id!r}: glyph member {block.glyph_member!r} is not "
                f"one of its members",
                line=block.line,
            )
        _check_block_contiguous(block, by_id)


def _validate_glyphs(building: Building) -> None:
    """Reject two entities carrying the same explicit display glyph.

    Only glyphs that are actually shown compete: a block member's glyph is
    suppressed by its block (warned about, not an error) and empty glyphs
    (``glyph=""``) label nothing.
    """
    member_of = _block_of(building)
    entities = [
        (room.id, room.glyph, room.line)
        for room in building.rooms
        if room.id not in member_of
    ]
    entities += [(block.id, block.glyph, block.line) for block in building.blocks]
    owners: dict[str, str] = {}
    for entity_id, glyph, line in entities:
        if not glyph:
            continue  # automatic (None) or explicitly unlabeled ("")
        if glyph in owners:
            raise LayoutError(
                f"glyph {glyph!r} is used by both {owners[glyph]!r} and {entity_id!r}",
                line=line,
            )
        owners[glyph] = entity_id


def _check_block_contiguous(block: Block, by_id: dict[str, Room]) -> None:
    """Raise unless the block's members form one wall-connected region."""
    members = [by_id[m] for m in block.members]
    adjacency: dict[str, set[str]] = {room.id: set() for room in members}
    for i, first in enumerate(members):
        for second in members[i + 1 :]:
            if _shared_wall(first, second) is not None:
                adjacency[first.id].add(second.id)
                adjacency[second.id].add(first.id)
    reached = {members[0].id}
    stack = [members[0].id]
    while stack:
        for neighbour in adjacency[stack.pop()]:
            if neighbour not in reached:
                reached.add(neighbour)
                stack.append(neighbour)
    if len(reached) != len(members):
        raise LayoutError(
            f"block {block.id!r} is not contiguous: its members do not all "
            f"connect by shared walls",
            line=block.line,
        )


def _block_warnings(
    building: Building, by_id: dict[str, Room], block_of: dict[str, str]
) -> list[str]:
    """Advisories: a block suppresses its members' names, glyphs, and doors."""
    warnings: list[str] = []
    for block in building.blocks:
        for member in block.members:
            name = by_id[member].name
            if name is not None:
                warnings.append(
                    f"room {member!r}: name {name!r} is suppressed inside "
                    f"block {block.id!r}"
                )
            glyph = by_id[member].glyph
            if glyph:
                warnings.append(
                    f"room {member!r}: glyph {glyph!r} is suppressed inside "
                    f"block {block.id!r}"
                )
    for room in building.rooms:
        for rel in room.relations:
            if rel.door is not None and _same_block(room.id, rel.anchor, block_of):
                warnings.append(
                    f"explicit door from {room.id!r} to {rel.anchor!r} is "
                    f"suppressed (same block)"
                )
    for doorway in building.doors:
        if _same_block(doorway.a, doorway.b, block_of):
            warnings.append(
                f"door between {doorway.a!r} and {doorway.b!r} is suppressed "
                f"(same block)"
            )
    return warnings


def block_wall_segments(building: Building) -> list[Segment]:
    """Wall segments tracing each block's outer boundary (internal walls dropped).

    For every block member, each of its four edges is emitted only over the parts
    not shared with another member of the same block, so the union renders as one
    outline rather than separate rectangles. Open-door spans are dropped too, so
    an open boundary into a block is a real gap in its outline. Assumes a solved
    building.
    """
    by_id = {room.id: room for room in building.rooms}
    openings = open_door_segments(building)
    segments: list[Segment] = []
    for block in building.blocks:
        members = [by_id[m] for m in block.members]
        for member in members:
            segments.extend(_member_boundary(member, members, openings))
    return segments


def room_outline_segments(building: Building) -> dict[str, list[Segment]]:
    """Outlines of the rooms whose walls are cut by an open door.

    Maps each such room's id to its four edges with every open-door span
    removed. Rooms untouched by an opening are absent (they render as plain
    rectangles); block members are covered by :func:`block_wall_segments`.
    Assumes a solved building.
    """
    openings = open_door_segments(building)
    if not openings:
        return {}
    member_of = _block_of(building)
    outlines: dict[str, list[Segment]] = {}
    for room in building.rooms:
        if room.id in member_of:
            continue
        segments, cut = _room_outline(room, openings)
        if cut:
            outlines[room.id] = segments
    return outlines


def _room_outline(room: Room, openings: list[Segment]) -> tuple[list[Segment], bool]:
    """``room``'s edges minus any open-door spans, plus whether any were cut."""
    x, y = _axis_lo(room, Axis.HORIZONTAL), _axis_lo(room, Axis.VERTICAL)
    w, h = room.width, room.height
    segments: list[Segment] = []
    cut = False
    for at_y in (y, y + h):  # top, then bottom
        blocked = [(x1, x2) for x1, y1, x2, y2 in openings if y1 == y2 == at_y]
        exposed = _exposed(x, x + w, blocked)
        cut = cut or exposed != [(x, x + w)]
        segments += [(x0, at_y, x1, at_y) for x0, x1 in exposed]
    for at_x in (x, x + w):  # left, then right
        blocked = [(y1, y2) for x1, y1, x2, y2 in openings if x1 == x2 == at_x]
        exposed = _exposed(y, y + h, blocked)
        cut = cut or exposed != [(y, y + h)]
        segments += [(at_x, y0, at_x, y1) for y0, y1 in exposed]
    return segments, cut


def _member_boundary(
    member: Room, members: list[Room], openings: list[Segment]
) -> list[Segment]:
    """The parts of ``member``'s four edges not shared with a sibling member.

    Members never overlap, so any sibling edge lying on one of ``member``'s edge
    lines (with overlap) must be the abutting member on the other side — i.e. an
    internal wall to drop. Open-door spans on an edge are dropped the same way.
    """
    mx, my = _axis_lo(member, Axis.HORIZONTAL), _axis_lo(member, Axis.VERTICAL)
    mw, mh = member.width, member.height
    others = [n for n in members if n is not member]
    segments: list[Segment] = []
    for at_y in (my, my + mh):  # top, then bottom
        blocked = [
            (_axis_lo(n, Axis.HORIZONTAL), _axis_hi(n, Axis.HORIZONTAL))
            for n in others
            if at_y in (_axis_lo(n, Axis.VERTICAL), _axis_hi(n, Axis.VERTICAL))
        ]
        blocked += [(x1, x2) for x1, y1, x2, y2 in openings if y1 == y2 == at_y]
        segments += [(x0, at_y, x1, at_y) for x0, x1 in _exposed(mx, mx + mw, blocked)]
    for at_x in (mx, mx + mw):  # left, then right
        blocked = [
            (_axis_lo(n, Axis.VERTICAL), _axis_hi(n, Axis.VERTICAL))
            for n in others
            if at_x in (_axis_lo(n, Axis.HORIZONTAL), _axis_hi(n, Axis.HORIZONTAL))
        ]
        blocked += [(y1, y2) for x1, y1, x2, y2 in openings if x1 == x2 == at_x]
        segments += [(at_x, y0, at_x, y1) for y0, y1 in _exposed(my, my + mh, blocked)]
    return segments


def _exposed(lo: int, hi: int, blocked: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sub-intervals of ``[lo, hi]`` left uncovered by the ``blocked`` intervals."""
    cuts = sorted(
        (max(lo, b0), min(hi, b1)) for b0, b1 in blocked if min(hi, b1) > max(lo, b0)
    )
    result: list[tuple[int, int]] = []
    cursor = lo
    for b0, b1 in cuts:
        if b0 > cursor:
            result.append((cursor, b0))
        cursor = max(cursor, b1)
    if cursor < hi:
        result.append((cursor, hi))
    return result


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

    A union applies when ``axis`` carries the room's auto dimension and it is
    sized by *several* walls on the perpendicular axis (a same-direction pair, or
    an opposite pair on the other axis). The ``?`` then spans the bounding box of
    all those anchors. This drives the *size* regardless of whether the axis is
    also pinned — a pin on the axis only sets the position (and must line up with
    the union's near edge, else the flush check rejects it); a free axis takes
    its near edge from this bbox via :func:`_free_axis_position`.
    """
    auto = room.auto_width if axis is Axis.HORIZONTAL else room.auto_height
    if not auto:
        return None
    sizing = [rel for rel in room.relations if rel.direction.axis is _perp(axis)]
    if len(sizing) < 2:
        return None
    near = min(_axis_lo(by_id[rel.anchor], axis) for rel in sizing)
    far = max(_axis_hi(by_id[rel.anchor], axis) for rel in sizing)
    return near, far


def door_segments(building: Building) -> list[Segment]:
    """Return the door line ``(x1, y1, x2, y2)`` for every *solid* door.

    Doors are on by default: a relation with a real shared wall gets a default
    door unless ``no_door`` suppresses it; an explicit ``door`` overrides its
    width/position. Validates every door, open and secret ones included
    (raising on an explicit door that has no wall or doesn't fit). Assumes a
    solved building.
    """
    return [s for s, d in _placed_doors(building) if not d.open and not d.secret]


def open_door_segments(building: Building) -> list[Segment]:
    """Return the line ``(x1, y1, x2, y2)`` for every *open* door.

    Open doors are placed and validated exactly like solid ones; the renderer
    draws them as a gap in the wall instead of a door mark. Assumes a solved
    building.
    """
    return [seg for seg, door in _placed_doors(building) if door.open]


def secret_door_segments(building: Building) -> list[Segment]:
    """Return the line ``(x1, y1, x2, y2)`` for every *secret* door.

    Secret doors are placed and validated exactly like solid ones; the
    renderer keeps the wall intact and draws an "S" marker over the span.
    Assumes a solved building.
    """
    return [seg for seg, door in _placed_doors(building) if door.secret]


def _placed_doors(building: Building) -> list[tuple[Segment, Door]]:
    """Place and validate every door, as ``(segment, door)`` pairs.

    Solid, open, and secret doors share one placement pass so the overlap
    check sees them all together.
    """
    by_id = {room.id: room for room in building.rooms}
    block_of = _block_of(building)
    placed: list[tuple[Segment, Door]] = []
    for room in building.rooms:
        for rel in room.relations:
            if rel.no_door or _same_block(room.id, rel.anchor, block_of):
                continue  # ``no_door``, or an internal wall of a block (dropped)
            segment = _relation_door(room, by_id[rel.anchor], rel)
            if segment is not None:
                placed.append((segment, rel.door if rel.door is not None else Door()))
    for doorway in building.doors:
        if _same_block(doorway.a, doorway.b, block_of):
            continue  # internal wall of a block (dropped)
        placed.append((_doorway_door(doorway, by_id), doorway.door))
    for external in building.external_doors:
        segment = _external_door_line(external, by_id, building.rooms)
        placed.append((segment, external.door))
    _check_door_overlaps([seg for seg, _ in placed])
    return placed


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


def _components(rooms: list[Room]) -> list[list[Room]]:
    """Split the rooms into connected components (relations as undirected edges).

    Components are ordered by the first appearance of any of their rooms in the
    source, and each component lists its rooms in source order — so packing and
    diagnostics are deterministic. Assumes anchors have been validated.
    """
    neighbours: dict[str, set[str]] = {room.id: set() for room in rooms}
    for room in rooms:
        for rel in room.relations:
            neighbours[room.id].add(rel.anchor)
            neighbours[rel.anchor].add(room.id)
    components: list[list[Room]] = []
    seen: set[str] = set()
    for room in rooms:
        if room.id in seen:
            continue
        member_ids = {room.id}
        stack = [room.id]
        while stack:
            for neighbour in neighbours[stack.pop()]:
                if neighbour not in member_ids:
                    member_ids.add(neighbour)
                    stack.append(neighbour)
        seen |= member_ids
        components.append([r for r in rooms if r.id in member_ids])
    return components


def _solve_component(component: list[Room], by_id: dict[str, Room], sole: bool) -> None:
    """Place one component's rooms by DAG propagation, its root at the origin."""
    root = _component_root(component, sole)
    if root.auto_width or root.auto_height:
        raise LayoutError(
            f"root {root.id!r} cannot use '?' (no anchor to size against)",
            line=root.line,
        )

    root.x, root.y = 0, 0
    placed: set[str] = {root.id}
    pending = [room for room in component if not room.is_root]

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


def _pack_components(components: list[list[Room]]) -> None:
    """Translate the components into a west-to-east row, in order.

    The first component keeps its literal coordinates (root at the origin);
    each later one is shifted whole so its bounding box starts a fixed gap east
    of the previous box, top edges aligned. Translation only — every room keeps
    its internal geometry, doors, and relations.
    """
    if len(components) <= 1:
        return
    top = min(_axis_lo(room, Axis.VERTICAL) for room in components[0])
    east = max(_axis_hi(room, Axis.HORIZONTAL) for room in components[0])
    for component in components[1:]:
        dx = (
            east
            + _COMPONENT_GAP_FT
            - min(_axis_lo(room, Axis.HORIZONTAL) for room in component)
        )
        dy = top - min(_axis_lo(room, Axis.VERTICAL) for room in component)
        for room in component:
            assert room.x is not None
            assert room.y is not None
            room.x += dx
            room.y += dy
        east = max(_axis_hi(room, Axis.HORIZONTAL) for room in component)


def _component_root(component: list[Room], sole: bool) -> Room:
    """Return the component's sole root, or raise if it has zero or several.

    ``sole`` (the building is one connected component) keeps the classic
    building-level wording; with several components the diagnostic names the
    component instead.
    """
    roots = [room for room in component if room.is_root]
    if not roots:
        if sole:
            raise LayoutError("the building needs exactly one root room, but has none")
        first = component[0]
        raise LayoutError(
            f"the component containing room {first.id!r} has no root",
            line=first.line,
        )
    if len(roots) > 1:
        ids = ", ".join(repr(room.id) for room in roots)
        where = "the building" if sole else "one connected component"
        raise LayoutError(
            f"{where} has more than one root room ({ids})", line=roots[1].line
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
    room.x = _axis_position(room, by_id, Axis.HORIZONTAL)
    room.y = _axis_position(room, by_id, Axis.VERTICAL)
    _check_shared_walls(room, by_id)


def _check_shared_walls(room: Room, by_id: dict[str, Room]) -> None:
    """Every relation must form a real shared wall (>= 5 ft) with its anchor.

    A relation that meets its anchor only at a corner (or, after a shift, not at
    all) carries a position but no wall — usually because the room's placement on
    the *other* axis pushed it past the anchor. porta rejects that: a relation
    must share a wall, not just a point.
    """
    for rel in room.relations:
        anchor = by_id[rel.anchor]
        wall = _perp(rel.direction.axis)
        overlap = min(_axis_hi(room, wall), _axis_hi(anchor, wall)) - max(
            _axis_lo(room, wall), _axis_lo(anchor, wall)
        )
        if overlap < _GRID_FT:
            raise LayoutError(
                f"room {room.id!r}: {rel.direction.value} {rel.anchor!r} shares "
                f"{max(overlap, 0)} ft of wall (needs at least {_GRID_FT} ft)",
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


def _raise_unplaceable(pending: list[Room]) -> None:
    """Diagnose why rooms could not be placed: disconnected vs. a cycle."""
    orphan = next((room for room in pending if not room.relations), None)
    if orphan is not None:
        raise LayoutError(
            f"room {orphan.id!r} is not connected to the root", line=orphan.line
        )
    ids = ", ".join(repr(room.id) for room in pending)
    raise LayoutError(f"dependency cycle among rooms: {ids}", line=pending[0].line)
