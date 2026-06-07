"""Render a *solved* model to output.

Two emitters that both consume a solved model: the SVG generator (Stage 4) and
the debug-ascii rasterizer below. SVG is built from stdlib string templating
only (no runtime dependencies).
"""

from xml.sax.saxutils import escape

from porta.layout import block_wall_segments, door_segments
from porta.model import Building, Room

_GRID_FT = 5
_EMPTY = "."
_FALLBACK_GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

_SVG_NS = "http://www.w3.org/2000/svg"
_MARGIN_FT = 10  # padding around the plan, in feet
_WALL_STROKE_FT = 0.5  # wall line thickness, in feet
_LABEL_RATIO = 0.6  # room glyph size as a fraction of the room's shorter side
_KEY_FONT_FT = 6  # key/caption font, in feet (fixed, not tied to room sizes)
_KEY_LINE_RATIO = 1.6  # key line spacing as a multiple of the key font
_CHAR_W = 0.6  # rough average glyph width (fraction of font), for centring the key
_GRID_COLOUR = "#bbb"  # grey 5-ft grid
_GRID_STROKE_FT = 0.15  # grid line thickness, in feet
_DOOR_COLOUR = "black"  # door marks
_DOOR_STROKE_FT = 1.5  # door line thickness, in feet
_DISPLAY_SCALE = 10  # px per foot for the default render size (viewBox stays in feet)


def render_ascii(building: Building) -> str:
    """Render a solved building as an ASCII grid plus a glyph legend.

    One character per 5-ft cell, space-separated, north at the top; empty
    cells are ``.``. A blank line then a ``glyph=id`` legend (in source order)
    follows.

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
                grid[r][c] = glyphs[room.id]

    body = "\n".join(" ".join(cell for cell in row) for row in grid)
    member_block = _member_block(building)
    ordered = sorted(_legend_ids(building, member_block), key=lambda eid: glyphs[eid])
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
    entity_ids = sorted(
        _legend_ids(building, member_block), key=lambda eid: glyphs[eid]
    )
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

    for room, x, y in sorted(placed, key=lambda t: t[0].id):
        if room.id in member_block:
            continue  # drawn as part of its block's outline below
        font = min(room.width, room.height) * _LABEL_RATIO
        lines.append(
            f'  <rect data-room="{room.id}" x="{_num(x)}" y="{_num(y)}" '
            f'width="{_num(room.width)}" height="{_num(room.height)}" '
            f'fill="none" stroke="black" stroke-width="{_num(_WALL_STROKE_FT)}" />'
        )
        lines.append(
            f'  <text data-room="{room.id}" x="{_num(x + room.width / 2)}" '
            f'y="{_num(y + room.height / 2)}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="{_num(font)}">'
            f"{glyphs[room.id]}</text>"
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
        member = by_id[block.glyph_member or block.members[0]]
        mx, my = member.x, member.y
        assert mx is not None
        assert my is not None
        font = min(member.width, member.height) * _LABEL_RATIO
        lines.append(
            f'  <text data-block="{block.id}" x="{_num(mx + member.width / 2)}" '
            f'y="{_num(my + member.height / 2)}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="{_num(font)}">'
            f"{glyphs[block.id]}</text>"
        )

    # Doors: a thick coloured line along the shared wall, over the rooms.
    # Sorted so the output is independent of statement order.
    for x1, y1, x2, y2 in sorted(door_segments(building)):
        lines.append(
            f'  <line class="door" x1="{_num(x1)}" y1="{_num(y1)}" '
            f'x2="{_num(x2)}" y2="{_num(y2)}" stroke="{_DOOR_COLOUR}" '
            f'stroke-width="{_num(_DOOR_STROKE_FT)}" />'
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


def _legend_ids(building: Building, member_block: dict[str, str]) -> list[str]:
    """Ids that earn a glyph and a key line: non-member rooms, then blocks."""
    rooms = [room.id for room in building.rooms if room.id not in member_block]
    return rooms + [block.id for block in building.blocks]


def _assign_glyphs(building: Building) -> dict[str, str]:
    """Assign a glyph to each non-member room and each block; members inherit
    their block's glyph.

    Entities are processed in id order, so contention for a letter resolves
    alphabetically and the result is independent of statement order.
    """
    member_block = _member_block(building)
    used: set[str] = set()
    glyphs: dict[str, str] = {}
    for entity_id in sorted(_legend_ids(building, member_block)):
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
