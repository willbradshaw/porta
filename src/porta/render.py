"""Render a *solved* model to output.

Two emitters that both consume a solved model: the SVG generator (Stage 4) and
the debug-ascii rasterizer below. SVG is built from stdlib string templating
only (no runtime dependencies).
"""

from xml.sax.saxutils import escape

from porta.layout import (
    Rect,
    block_wall_segments,
    door_segments,
    open_door_segments,
    room_outline_segments,
    secret_door_segments,
    stair_footprints,
)
from porta.model import Axis, Building, Direction, Room, Stairs, StairSense

_GRID_FT = 5
_EMPTY = "."
_NO_GLYPH = "_"  # ascii cell fill for an unlabeled (glyph="") room
_FALLBACK_GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

_SVG_NS = "http://www.w3.org/2000/svg"
_MARGIN_FT = 10  # padding around the plan, in feet
_WALL_STROKE_FT = 0.5  # wall line thickness, in feet
_LABEL_RATIO = 0.6  # room glyph size as a fraction of the room's shorter side
_LABEL_FIT = 0.9  # widest fraction of the room width a glyph may span
_KEY_FONT_FT = 6  # key/caption font, in feet (fixed, not tied to room sizes)
_KEY_LINE_RATIO = 1.6  # key line spacing as a multiple of the key font
_CHAR_W = 0.6  # rough average glyph width (fraction of font), for centring the key
_GRID_COLOUR = "#bbb"  # grey 5-ft grid
_GRID_STROKE_FT = 0.15  # grid line thickness, in feet
_DOOR_COLOUR = "black"  # door marks
_DOOR_STROKE_FT = 1.5  # door line thickness, in feet
# Open boundaries are dotted: a near-zero dash with a round cap renders as a
# dot of the wall's stroke width; the gap sets the dot spacing, in feet.
_OPEN_DASH = "0.01 1.5"
_SECRET_FONT_FT = 5  # "S" marker of a secret door, in feet (the map convention)
_SECRET_HALO_FT = 0.6  # background-coloured halo that keeps the S legible
# Stairs: treads cross the run every half grid; the arrow (pointing in the
# down= direction) is inset from the footprint ends and tipped with two barbs.
_TREAD_SPACING_FT = 2.5
_TREAD_STROKE_FT = 0.25
_STAIR_ARROW_INSET_FT = 2.5
_STAIR_ARROW_BARB_FT = 1.5
_OPPOSITE: dict[Direction, Direction] = {
    Direction.UP: Direction.DOWN,
    Direction.DOWN: Direction.UP,
    Direction.LEFT: Direction.RIGHT,
    Direction.RIGHT: Direction.LEFT,
}
_DISPLAY_SCALE = 10  # px per foot for the default render size (viewBox stays in feet)


def render_ascii(building: Building) -> str:
    """Render a solved building as an ASCII grid plus a glyph legend.

    One cell per 5-ft square, space-separated, north at the top; every cell is
    padded to the widest glyph in the plan. Empty cells are ``.``; an unlabeled
    room's cells are ``_``. A blank line then a ``glyph=id`` legend
    (shortest-glyph-first, then lexicographic) follows. Like doors, stairs
    are not rendered in the ascii grid (it shows room extents only).

    Args:
        building: A building whose rooms have been placed by
            :func:`~porta.layout.solve`.

    Returns:
        The multi-line ASCII rendering (no trailing newline).

    Raises:
        ValueError: If any room has not been placed.
    """
    placed = _placed_rooms(building)
    glyphs = _assign_glyphs(building)

    min_x = min(x for _, x, _ in placed)
    min_y = min(y for _, _, y in placed)
    max_x = max(x + room.width for room, x, _ in placed)
    max_y = max(y + room.height for room, _, y in placed)
    cols = (max_x - min_x) // _GRID_FT
    rows = (max_y - min_y) // _GRID_FT

    grid = [[_EMPTY] * cols for _ in range(rows)]
    for room, x, y in placed:
        c0 = (x - min_x) // _GRID_FT
        r0 = (y - min_y) // _GRID_FT
        for r in range(r0, r0 + room.height // _GRID_FT):
            for c in range(c0, c0 + room.width // _GRID_FT):
                grid[r][c] = glyphs[room.id] or _NO_GLYPH

    cell_w = max(1, *(len(glyph) for glyph in glyphs.values()))
    body = "\n".join(
        " ".join(cell.ljust(cell_w) for cell in row).rstrip() for row in grid
    )
    member_block = _member_block(building)
    ordered = _legend_ids(building, member_block, glyphs)
    legend = "  ".join(f"{glyphs[eid]}={eid}" for eid in ordered)
    return f"{body}\n\n{legend}"


def render_svg(building: Building, *, background: str = "white") -> str:
    """Render a solved building as SVG.

    Geometry is drawn directly in feet (1 user unit = 1 foot); no scaling or
    y-flip is needed (the layout's x-east/y-south coordinates are already
    SVG-native). The viewBox frames the room bounding box plus a margin, so
    rooms are emitted at their literal (possibly negative) coordinates. Each
    room is a bordered rectangle with a centered glyph; a key (glyph to name)
    is drawn below the plan.

    Args:
        building: A building whose rooms have been placed by
            :func:`~porta.layout.solve`.
        background: Fill for the SVG backdrop (default ``"white"``).

    Returns:
        The SVG document as a string.

    Raises:
        ValueError: If any room has not been placed.
    """
    placed = _placed_rooms(building)
    glyphs = _assign_glyphs(building)
    by_id = {room.id: room for room in building.rooms}
    member_block = _member_block(building)

    min_x = min(x for _, x, _ in placed)
    min_y = min(y for _, _, y in placed)
    max_x = max(x + room.width for room, x, _ in placed)
    max_y = max(y + room.height for room, _, y in placed)

    plan_w = max_x - min_x
    plan_h = max_y - min_y

    caption = f"1 square = {_GRID_FT} ft"
    entity_ids = _legend_ids(building, member_block, glyphs)
    entries = [_key_line(building, by_id, eid, glyphs[eid]) for eid in entity_ids]
    chrome = [caption, *entries]
    # The key is a fixed readable size (not tied to room sizes — a single small
    # room would otherwise shrink the whole key). If a key line is wider than
    # the plan, the canvas grows and plan + key are centred (no dead space).
    key_font = _KEY_FONT_FT
    key_line = key_font * _KEY_LINE_RATIO
    key_width = max(len(line) for line in chrome) * key_font * _CHAR_W

    center_x = (min_x + max_x) / 2
    view_w = max(plan_w, key_width) + 2 * _MARGIN_FT
    view_h = plan_h + _MARGIN_FT + (len(chrome) + 2) * key_line
    view_x = center_x - view_w / 2
    view_y = min_y - _MARGIN_FT

    lines = [
        f'<svg xmlns="{_SVG_NS}" '
        f'width="{_num(view_w * _DISPLAY_SCALE)}" '
        f'height="{_num(view_h * _DISPLAY_SCALE)}" '
        f'viewBox="{_num(view_x)} {_num(view_y)} {_num(view_w)} {_num(view_h)}">'
    ]

    # Opaque background so the drawing is legible on any viewer backdrop.
    lines.append(
        f'  <rect x="{_num(view_x)}" y="{_num(view_y)}" '
        f'width="{_num(view_w)}" height="{_num(view_h)}" fill="{background}" />'
    )

    # 5-ft grid, drawn behind the rooms (over the background).
    lines.append(
        f'  <g stroke="{_GRID_COLOUR}" stroke-width="{_num(_GRID_STROKE_FT)}">'
    )
    for gx in range(min_x, max_x + 1, _GRID_FT):
        lines.append(
            f'    <line x1="{_num(gx)}" y1="{_num(min_y)}" '
            f'x2="{_num(gx)}" y2="{_num(max_y)}" />'
        )
    for gy in range(min_y, max_y + 1, _GRID_FT):
        lines.append(
            f'    <line x1="{_num(min_x)}" y1="{_num(gy)}" '
            f'x2="{_num(max_x)}" y2="{_num(gy)}" />'
        )
    lines.append("  </g>")

    # A room bordering an open door loses its plain rect: its outline is drawn
    # as per-edge wall segments with the open spans cut out.
    outlines = room_outline_segments(building)
    for room, x, y in sorted(placed, key=lambda t: t[0].id):
        if room.id in member_block:
            continue  # drawn as part of its block's outline below
        if room.id in outlines:
            for x1, y1, x2, y2 in sorted(outlines[room.id]):
                lines.append(
                    f'  <line data-room="{room.id}" x1="{_num(x1)}" y1="{_num(y1)}" '
                    f'x2="{_num(x2)}" y2="{_num(y2)}" '
                    f'stroke="black" stroke-width="{_num(_WALL_STROKE_FT)}" '
                    f'stroke-linecap="square" />'
                )
        else:
            lines.append(
                f'  <rect data-room="{room.id}" x="{_num(x)}" y="{_num(y)}" '
                f'width="{_num(room.width)}" height="{_num(room.height)}" '
                f'fill="none" stroke="black" stroke-width="{_num(_WALL_STROKE_FT)}" />'
            )
        glyph = glyphs[room.id]
        if not glyph:
            continue  # unlabeled room
        font = _glyph_font(room.width, room.height, glyph)
        lines.append(
            f'  <text data-room="{room.id}" x="{_num(x + room.width / 2)}" '
            f'y="{_num(y + room.height / 2)}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="{_num(font)}">'
            f"{escape(glyph)}</text>"
        )

    # Blocks: the union boundary as wall lines (internal walls dropped), then one
    # glyph at the block's glyph member's centre. Square caps extend each segment
    # by half its width so perpendicular segments meet in a clean corner.
    for x1, y1, x2, y2 in sorted(block_wall_segments(building)):
        lines.append(
            f'  <line x1="{_num(x1)}" y1="{_num(y1)}" '
            f'x2="{_num(x2)}" y2="{_num(y2)}" '
            f'stroke="black" stroke-width="{_num(_WALL_STROKE_FT)}" '
            f'stroke-linecap="square" />'
        )
    for block in sorted(building.blocks, key=lambda b: b.id):
        glyph = glyphs[block.id]
        if not glyph:
            continue  # unlabeled block
        member = by_id[block.glyph_member or block.members[0]]
        mx, my = member.x, member.y
        assert mx is not None
        assert my is not None
        font = _glyph_font(member.width, member.height, glyph)
        lines.append(
            f'  <text data-block="{block.id}" x="{_num(mx + member.width / 2)}" '
            f'y="{_num(my + member.height / 2)}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="{_num(font)}">'
            f"{escape(glyph)}</text>"
        )

    # Stairs: hard lines on the non-entrance sides, treads across the run,
    # and an arrow pointing in the downhill (down=) direction.
    for stairs, rect in stair_footprints(building):
        lines.append(f'  <g class="stairs" data-room="{stairs.room}">')
        for sx1, sy1, sx2, sy2 in _stair_hard_edges(stairs, rect):
            lines.append(
                f'    <line x1="{_num(sx1)}" y1="{_num(sy1)}" '
                f'x2="{_num(sx2)}" y2="{_num(sy2)}" '
                f'stroke="black" stroke-width="{_num(_WALL_STROKE_FT)}" '
                f'stroke-linecap="square" />'
            )
        for sx1, sy1, sx2, sy2 in _stair_treads(stairs, rect):
            lines.append(
                f'    <line x1="{_num(sx1)}" y1="{_num(sy1)}" '
                f'x2="{_num(sx2)}" y2="{_num(sy2)}" '
                f'stroke="black" stroke-width="{_num(_TREAD_STROKE_FT)}" />'
            )
        for sx1, sy1, sx2, sy2 in _stair_arrow(stairs, rect):
            lines.append(
                f'    <line x1="{_num(sx1)}" y1="{_num(sy1)}" '
                f'x2="{_num(sx2)}" y2="{_num(sy2)}" '
                f'stroke="black" stroke-width="{_num(_WALL_STROKE_FT)}" '
                f'stroke-linecap="round" />'
            )
        lines.append("  </g>")

    # Open doors: a dotted line across the gap left in the walls above.
    for x1, y1, x2, y2 in sorted(open_door_segments(building)):
        lines.append(
            f'  <line class="open" x1="{_num(x1)}" y1="{_num(y1)}" '
            f'x2="{_num(x2)}" y2="{_num(y2)}" stroke="black" '
            f'stroke-width="{_num(_WALL_STROKE_FT)}" '
            f'stroke-dasharray="{_OPEN_DASH}" stroke-linecap="round" />'
        )

    # Doors: a thick coloured line along the shared wall, over the rooms.
    # Sorted so the output is independent of statement order.
    for x1, y1, x2, y2 in sorted(door_segments(building)):
        lines.append(
            f'  <line class="door" x1="{_num(x1)}" y1="{_num(y1)}" '
            f'x2="{_num(x2)}" y2="{_num(y2)}" stroke="{_DOOR_COLOUR}" '
            f'stroke-width="{_num(_DOOR_STROKE_FT)}" />'
        )

    # Secret doors: a normal-style door mark shows the size and position, and
    # an "S" over it (haloed in the background colour to stay legible) says
    # the door is concealed.
    for x1, y1, x2, y2 in sorted(secret_door_segments(building)):
        lines.append(
            f'  <line class="secret" x1="{_num(x1)}" y1="{_num(y1)}" '
            f'x2="{_num(x2)}" y2="{_num(y2)}" stroke="{_DOOR_COLOUR}" '
            f'stroke-width="{_num(_DOOR_STROKE_FT)}" />'
        )
        lines.append(
            f'  <text class="secret" x="{_num((x1 + x2) / 2)}" '
            f'y="{_num((y1 + y2) / 2)}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="{_num(_SECRET_FONT_FT)}" '
            f'stroke="{background}" stroke-width="{_num(_SECRET_HALO_FT)}" '
            f'paint-order="stroke">S</text>'
        )

    # Centre the key block but left-align the lines within it (a legend reads
    # best as a left-aligned list).
    key_left = center_x - key_width / 2
    for j, line in enumerate(chrome):
        css = "scale" if j == 0 else "key"
        lines.append(
            f'  <text class="{css}" x="{_num(key_left)}" '
            f'y="{_num(max_y + (j + 2) * key_line)}" '
            f'font-size="{_num(key_font)}">{escape(line)}</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines)


def _key_line(
    building: Building, by_id: dict[str, Room], entity_id: str, glyph: str
) -> str:
    """One key line: ``glyph  name``, or just ``glyph`` when there is no name.

    Applies the same way to rooms and blocks (each is named or not).
    """
    room = by_id.get(entity_id)
    if room is not None:
        name = room.name
    else:
        name = next(block.name for block in building.blocks if block.id == entity_id)
    return f"{glyph}  {name}" if name else glyph


def _num(value: float) -> str:
    """Format a number for SVG: round off float noise, drop a trailing ``.0``."""
    value = round(value, 3)
    return str(int(value)) if value == int(value) else str(value)


def _placed_rooms(building: Building) -> list[tuple[Room, int, int]]:
    """Return (room, x, y) triples, raising if any room is unplaced."""
    placed: list[tuple[Room, int, int]] = []
    for room in building.rooms:
        if room.x is None or room.y is None:
            raise ValueError(
                f"rendering needs a solved building; {room.id!r} is unplaced"
            )
        placed.append((room, room.x, room.y))
    return placed


def _member_block(building: Building) -> dict[str, str]:
    """Map each block member's room id to its block id."""
    return {member: block.id for block in building.blocks for member in block.members}


def _entity_ids(building: Building, member_block: dict[str, str]) -> list[str]:
    """Ids that own a glyph slot: non-member rooms, then blocks."""
    rooms = [room.id for room in building.rooms if room.id not in member_block]
    return rooms + [block.id for block in building.blocks]


def _legend_ids(
    building: Building, member_block: dict[str, str], glyphs: dict[str, str]
) -> list[str]:
    """Entities that earn a key line: those with a non-empty glyph.

    Ordered shortest-glyph-first then lexicographic, so numeric glyphs read
    ``1``..``9`` before ``10``.
    """
    ids = [eid for eid in _entity_ids(building, member_block) if glyphs[eid]]
    return sorted(ids, key=lambda eid: (len(glyphs[eid]), glyphs[eid]))


# A drawn line as (x1, y1, x2, y2) in feet (may fall on half-grid points).
_Line = tuple[float, float, float, float]


def _stair_hard_edges(stairs: Stairs, rect: Rect) -> list[_Line]:
    """The footprint edges drawn solid: every side that isn't an entrance.

    ``UP`` stairs open where the arrow points (you would step down back onto
    this floor); ``DOWN`` stairs open behind the arrow (you descend away);
    ``IN`` steps open at both ends of the run, keeping only the flanks.
    """
    x, y, w, h = rect
    edges: dict[Direction, _Line] = {
        Direction.UP: (x, y, x + w, y),
        Direction.DOWN: (x, y + h, x + w, y + h),
        Direction.LEFT: (x, y, x, y + h),
        Direction.RIGHT: (x + w, y, x + w, y + h),
    }
    if stairs.sense is StairSense.UP:
        open_sides = {stairs.down}
    elif stairs.sense is StairSense.DOWN:
        open_sides = {_OPPOSITE[stairs.down]}
    else:  # IN
        open_sides = {stairs.down, _OPPOSITE[stairs.down]}
    return [edge for side, edge in edges.items() if side not in open_sides]


def _stair_treads(stairs: Stairs, rect: Rect) -> list[_Line]:
    """Tread lines crossing the run every half grid (footprint ends excluded)."""
    x, y, w, h = rect
    treads: list[_Line] = []
    if stairs.down.axis is Axis.HORIZONTAL:
        t = _TREAD_SPACING_FT
        while t < w:
            treads.append((x + t, y, x + t, y + h))
            t += _TREAD_SPACING_FT
    else:
        t = _TREAD_SPACING_FT
        while t < h:
            treads.append((x, y + t, x + w, y + t))
            t += _TREAD_SPACING_FT
    return treads


def _stair_arrow(stairs: Stairs, rect: Rect) -> list[_Line]:
    """The downhill arrow: a centred shaft along the run plus two tip barbs."""
    x, y, w, h = rect
    barb = _STAIR_ARROW_BARB_FT
    if stairs.down.axis is Axis.HORIZONTAL:
        cy = y + h / 2
        inset = min(_STAIR_ARROW_INSET_FT, w / 4)
        if stairs.down is Direction.RIGHT:
            tail, tip = x + inset, x + w - inset
            step = -barb
        else:
            tail, tip = x + w - inset, x + inset
            step = barb
        return [
            (tail, cy, tip, cy),
            (tip, cy, tip + step, cy - barb),
            (tip, cy, tip + step, cy + barb),
        ]
    cx = x + w / 2
    inset = min(_STAIR_ARROW_INSET_FT, h / 4)
    if stairs.down is Direction.DOWN:
        tail, tip = y + inset, y + h - inset
        step = -barb
    else:
        tail, tip = y + h - inset, y + inset
        step = barb
    return [
        (cx, tail, cx, tip),
        (cx, tip, cx - barb, tip + step),
        (cx, tip, cx + barb, tip + step),
    ]


def _glyph_font(width: int, height: int, glyph: str) -> float:
    """Glyph font size: the usual fraction of the shorter side, shrunk when a
    multi-character glyph would otherwise overflow the room's width."""
    size = min(width, height) * _LABEL_RATIO
    return min(size, width * _LABEL_FIT / (len(glyph) * _CHAR_W))


def _assign_glyphs(building: Building) -> dict[str, str]:
    """Assign a glyph to each non-member room and each block; members inherit
    their block's glyph.

    An explicit ``glyph="..."`` is used verbatim (``""`` = unlabeled). The rest
    are automatic — processed in id order, so contention for a letter resolves
    alphabetically and the result is independent of statement order — and never
    collide with an explicit glyph.
    """
    member_block = _member_block(building)
    explicit = [
        (room.id, room.glyph) for room in building.rooms if room.id not in member_block
    ]
    explicit += [(block.id, block.glyph) for block in building.blocks]
    glyphs: dict[str, str] = {
        eid: glyph for eid, glyph in explicit if glyph is not None
    }
    used = {glyph for glyph in glyphs.values() if glyph}
    for entity_id in sorted(_entity_ids(building, member_block)):
        if entity_id in glyphs:
            continue
        chosen = _pick_glyph(entity_id, used)
        used.add(chosen)
        glyphs[entity_id] = chosen
    for member, block_id in member_block.items():
        glyphs[member] = glyphs[block_id]
    return glyphs


def _pick_glyph(room_id: str, used: set[str]) -> str:
    """First unused uppercased alphanumeric of ``room_id``, else from the pool."""
    for char in room_id:
        glyph = char.upper()
        if glyph.isalnum() and glyph not in used:
            return glyph
    for glyph in _FALLBACK_GLYPHS:
        if glyph not in used:
            return glyph
    raise ValueError("ran out of glyphs for the ascii legend")  # pragma: no cover
