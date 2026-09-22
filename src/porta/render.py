"""Render a *solved* model to output.

Two emitters that both consume a solved model: the SVG generator (Stage 4) and
the debug-ascii rasterizer below. SVG is built from stdlib string templating
only (no runtime dependencies).
"""

from dataclasses import dataclass
from itertools import pairwise
from unicodedata import category, east_asian_width
from xml.sax.saxutils import escape

from porta.key_layout import choose_layout
from porta.layout import (
    Rect,
    divider_segments,
    door_segments,
    open_door_segments,
    secret_door_segments,
    stair_footprints,
    stair_open_sides,
    wall_segments,
    window_segments,
)
from porta.model import Axis, Building, Direction, Room, Stairs
from porta.text_metrics import TextMetrics, text_bounds

_GRID_FT = 5
_EMPTY = "."
_NO_GLYPH = "_"  # ascii cell fill for an unlabeled (glyph="") room
_FALLBACK_GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

_SVG_NS = "http://www.w3.org/2000/svg"
_MARGIN_FT = 10  # padding around the plan, in feet
_WALL_STROKE_FT = 0.5  # interior walls and stair edges, in feet
_EXTERIOR_WALL_STROKE_FT = 0.8  # exposed envelope; 160% of interior walls, in feet
_LABEL_RATIO = 0.6  # room glyph size as a fraction of the room's shorter side
_LABEL_FIT = 0.9  # widest fraction of the room width a glyph may span
_FONT_FAMILY = "Palatino, Georgia, Times New Roman, serif"
_TEXT_COLOUR = "#333333"
_KEY_FONT_FT = 5.0  # fixed readable key size, in feet
_SCALE_FONT_FT = _KEY_FONT_FT
_SCALE_GAP_FT = 12  # map edge to bar bottom; caption to first key baseline
_SCALE_LENGTH_FT = 20
_SCALE_HEIGHT_FT = 1.5
_SCALE_STROKE_FT = 0.2
_SCALE_CAPTION_OFFSET_FT = 6
_KEY_GAP_FT = 2
_COLUMN_GAP_FT = 6
_KEY_LINE_RATIO = 1.6  # key line spacing as a multiple of the key font
_GRID_COLOUR = "#c4c4c4"  # grey 5-ft grid
_GRID_STROKE_FT = 0.125  # grid line thickness, in feet
_DOOR_COLOUR = "black"  # door marks
_DOOR_STROKE_FT = 1.5  # door line thickness, in feet
# Open boundaries are dotted: a near-zero dash with a round cap renders as a
# dot of the wall's stroke width; the gap sets the dot spacing, in feet.
_OPEN_DASH = "0.01 1.5"
_SECRET_FONT_FT = 5  # "S" marker of a secret door, in feet (the map convention)
_SECRET_HALO_FT = 0.6  # background-coloured halo that keeps the S legible
# Stairs: treads cross the run at even spacing, narrowing toward the
# downhill (down=) end.
_TREADS_PER_GRID = 3  # tread intervals per 5-ft grid square along the run
_TREAD_STROKE_FT = 0.25
# Tread length as a fraction of the footprint's *visible* breadth (the flank
# strokes are centred on the boundary, so half a wall stroke each side is
# already ink), interpolated from the high end to the downhill end. The cap
# stays below 1 so no tread ever spans flank to flank — a full-breadth line
# would read as a solid boundary.
_TREAD_MAX_RATIO = 0.7
_TREAD_MIN_RATIO = 0.3
# Dividers: a dividing line along a suppressed block boundary. Tread-thin
# and dashed so it reads as a marking on the floor, not a wall.
_DIVIDER_STROKE_FT = 0.25
_DIVIDER_DASH = "1.5 1"  # dash length and gap, in feet
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
        ValueError: If any room has not been placed or automatic glyphs run out.
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
    walls are emitted at their literal (possibly negative) coordinates, with
    stronger exterior strokes and shared interior walls drawn once. Rooms have
    centered glyphs; a key (glyph to name) is drawn below the plan.

    Args:
        building: A building whose rooms have been placed by
            :func:`~porta.layout.solve`.
        background: Fill for the SVG backdrop (default ``"white"``).

    Returns:
        The SVG document as a string.

    Raises:
        ValueError: If any room has not been placed or automatic glyphs run out.
    """
    placed = _placed_rooms(building)
    glyphs = _assign_glyphs(building)
    by_id = {room.id: room for room in building.rooms}
    member_block = _member_block(building)
    footprints = stair_footprints(building)
    # Stair footprints per room, in room-local coordinates (glyphs avoid them).
    room_stairs: dict[str, list[Rect]] = {}
    for stairs, (fx, fy, fw, fh) in footprints:
        stair_room = by_id[stairs.room]
        assert stair_room.x is not None
        assert stair_room.y is not None
        room_stairs.setdefault(stairs.room, []).append(
            (fx - stair_room.x, fy - stair_room.y, fw, fh)
        )

    min_x = min(x for _, x, _ in placed)
    min_y = min(y for _, _, y in placed)
    max_x = max(x + room.width for room, x, _ in placed)
    max_y = max(y + room.height for room, _, y in placed)

    plan_w = max_x - min_x

    entity_ids = _legend_ids(building, member_block, glyphs)
    entries = [(glyphs[eid], _key_name(building, by_id, eid)) for eid in entity_ids]
    key = _key_layout(entries, plan_w)
    scale_width = _scale_width()
    furniture_width = max(key.width, scale_width)
    center_x = (min_x + max_x) / 2
    view_w = max(plan_w, furniture_width) + 2 * _MARGIN_FT
    scale_y = max_y + _SCALE_GAP_FT
    key_top = scale_y + _SCALE_CAPTION_OFFSET_FT + _SCALE_GAP_FT - _KEY_FONT_FT
    view_h = key_top + key.height + _MARGIN_FT - (min_y - _MARGIN_FT)
    view_x = center_x - view_w / 2
    view_y = min_y - _MARGIN_FT

    lines = [
        f'<svg xmlns="{_SVG_NS}" '
        f'width="{_num(view_w * _DISPLAY_SCALE)}" '
        f'height="{_num(view_h * _DISPLAY_SCALE)}" '
        f'viewBox="{_num(view_x)} {_num(view_y)} {_num(view_w)} {_num(view_h)}" '
        f'font-family="{_FONT_FAMILY}" font-weight="400" fill="black">'
    ]

    # Opaque background so the drawing is legible on any viewer backdrop.
    lines.append(
        f'  <rect x="{_num(view_x)}" y="{_num(view_y)}" '
        f'width="{_num(view_w)}" height="{_num(view_h)}" fill="{background}" />'
    )

    # One globally aligned grid, clipped to the union of room footprints.
    # Courtyard voids and component gutters stay blank; declared outdoor rooms
    # keep the same measuring grid as indoor rooms. A single path avoids seams.
    outline = " ".join(
        f"M{_num(x)} {_num(y)}h{room.width}v{room.height}h{-room.width}z"
        for room, x, y in sorted(placed, key=lambda t: t[0].id)
    )
    lines.append(
        f'  <defs><clipPath id="plan-grid"><path d="{outline}" /></clipPath></defs>'
    )
    # 5-ft grid, drawn behind the rooms (over the background).
    lines.append(
        f'  <g class="grid" clip-path="url(#plan-grid)" '
        f'stroke="{_GRID_COLOUR}" stroke-width="{_num(_GRID_STROKE_FT)}">'
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

    # Shared walls appear once. Square caps close perpendicular corners.
    exterior, interior = wall_segments(building)
    for kind, segments, width in (
        ("interior", interior, _WALL_STROKE_FT),
        ("exterior", exterior, _EXTERIOR_WALL_STROKE_FT),
    ):
        for x1, y1, x2, y2 in segments:
            lines.append(
                f'  <line class="wall {kind}" x1="{_num(x1)}" y1="{_num(y1)}" '
                f'x2="{_num(x2)}" y2="{_num(y2)}" '
                f'stroke="black" stroke-width="{_num(width)}" '
                f'stroke-linecap="square" />'
            )

    for room, x, y in sorted(placed, key=lambda t: t[0].id):
        if room.id in member_block:
            continue
        glyph = glyphs[room.id]
        if not glyph:
            continue  # unlabeled room
        lx, ly, font = _glyph_spot(room, room_stairs.get(room.id, []), glyph)
        lines.append(
            f'  <text data-room="{room.id}" x="{_num(x + lx)}" '
            f'y="{_num(y + ly)}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="{_num(font)}" '
            f'fill="{_TEXT_COLOUR}">'
            f"{escape(glyph)}</text>"
        )

    # One glyph per block, at its selected member.
    for block in sorted(building.blocks, key=lambda b: b.id):
        glyph = glyphs[block.id]
        if not glyph:
            continue  # unlabeled block
        member = by_id[block.glyph_member or block.members[0]]
        mx, my = member.x, member.y
        assert mx is not None
        assert my is not None
        lx, ly, font = _glyph_spot(member, room_stairs.get(member.id, []), glyph)
        lines.append(
            f'  <text data-block="{block.id}" x="{_num(mx + lx)}" '
            f'y="{_num(my + ly)}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="{_num(font)}" '
            f'fill="{_TEXT_COLOUR}">'
            f"{escape(glyph)}</text>"
        )

    # Dividers: a dashed dividing line along a suppressed block boundary,
    # cut where a stair entrance lies on it.
    for x1, y1, x2, y2 in sorted(divider_segments(building)):
        lines.append(
            f'  <line class="divider" x1="{_num(x1)}" y1="{_num(y1)}" '
            f'x2="{_num(x2)}" y2="{_num(y2)}" stroke="black" '
            f'stroke-width="{_num(_DIVIDER_STROKE_FT)}" '
            f'stroke-dasharray="{_DIVIDER_DASH}" />'
        )

    # Stairs: hard lines on the non-entrance sides and treads across the run,
    # narrowing toward the downhill (down=) end.
    for stairs, rect in footprints:
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
        lines.append("  </g>")

    # Windows have white interiors between two strokes, half a foot apart.
    for x1, y1, x2, y2 in sorted(window_segments(building)):
        lines.append(
            f'  <line class="window-fill" x1="{_num(x1)}" y1="{_num(y1)}" '
            f'x2="{_num(x2)}" y2="{_num(y2)}" stroke="white" stroke-width="0.5" />'
        )
        for offset in (-0.25, 0.25):
            dx, dy = (0, offset) if y1 == y2 else (offset, 0)
            lines.append(
                f'  <line class="window" x1="{_num(x1 + dx)}" '
                f'y1="{_num(y1 + dy)}" x2="{_num(x2 + dx)}" '
                f'y2="{_num(y2 + dy)}" stroke="black" stroke-width="0.25" />'
            )

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

    lines.append(
        f'  <g class="scale" font-size="{_num(_SCALE_FONT_FT)}" fill="{_TEXT_COLOUR}">'
    )
    for dx, dy, label in _scale_labels():
        bounds = text_bounds(label, _SCALE_FONT_FT)
        lines.append(
            f'    <text x="{_num(center_x + dx - bounds.width / 2 - bounds.x)}" '
            f'y="{_num(scale_y + dy)}">{label}</text>'
        )
    for dx, fill in ((-_SCALE_LENGTH_FT / 2, "black"), (0, "white")):
        lines.append(
            f'    <rect x="{_num(center_x + dx)}" '
            f'y="{_num(scale_y - _SCALE_HEIGHT_FT)}" '
            f'width="{_num(_SCALE_LENGTH_FT / 2)}" height="{_num(_SCALE_HEIGHT_FT)}" '
            f'fill="{fill}" stroke="black" stroke-width="{_num(_SCALE_STROKE_FT)}" />'
        )
    lines.append("  </g>")

    key_left = center_x - key.width / 2
    for entry in key.entries:
        key_x, key_y = key_left + entry.x, key_top + entry.y
        glyph_bounds = text_bounds(entry.glyph)
        glyph_x = key_x - glyph_bounds.width - glyph_bounds.x
        lines.append(
            f'  <g class="key" font-size="{_num(_KEY_FONT_FT)}" fill="{_TEXT_COLOUR}">'
            f'<text x="{_num(glyph_x)}" '
            f'y="{_num(key_y)}">{escape(entry.glyph)}</text>'
        )
        for row, name in enumerate(entry.names):
            lines.append(
                f'    <text x="{_num(key_x + _KEY_GAP_FT - text_bounds(name).x)}" '
                f'y="{_num(key_y + row * _KEY_FONT_FT * _KEY_LINE_RATIO)}">'
                f"{escape(name)}</text>"
            )
        lines.append("  </g>")

    lines.append("</svg>")
    return "\n".join(lines)


def _key_name(building: Building, by_id: dict[str, Room], entity_id: str) -> str:
    """Return the name for a room or block key entry."""
    room = by_id.get(entity_id)
    if room is not None:
        return room.name or ""
    return next(block.name for block in building.blocks if block.id == entity_id) or ""


def _text_width(text: str) -> float:
    """Conservative em widths for the portable serif stack, without fonts.

    Wide Unicode and broad Latin characters need more space; combining marks
    add none. This is deliberately an upper estimate rather than font shaping.
    """
    return sum(
        0
        if category(char).startswith("M")
        else 1.1
        if east_asian_width(char) in ("W", "F")
        else 1.0
        if char in "MWmw@%&"
        else 0.7
        for char in text
    )


@dataclass
class _KeyEntry:
    glyph: str
    names: list[str]
    x: float
    y: float


@dataclass
class _KeyLayout:
    entries: list[_KeyEntry]
    width: float
    height: float


def _scale_labels() -> list[tuple[float, float, str]]:
    return [
        (-_SCALE_LENGTH_FT / 2, -3, "0"),
        (0, -3, _num(_SCALE_LENGTH_FT / 2)),
        (_SCALE_LENGTH_FT / 2, -3, f"{_num(_SCALE_LENGTH_FT)} ft"),
        (0, _SCALE_CAPTION_OFFSET_FT, f"{_GRID_FT}-ft squares"),
    ]


def _scale_width() -> float:
    # Symmetric footprint keeps the bar centered while reserving its end labels.
    return max(
        _SCALE_LENGTH_FT + _SCALE_STROKE_FT,
        *(
            2 * abs(dx) + text_bounds(label, _SCALE_FONT_FT).width
            for dx, _, label in _scale_labels()
        ),
    )


def _key_layout(entries: list[tuple[str, str]], plan_width: float) -> _KeyLayout:
    """Lay out the lowest-scoring equal-width key using approved coefficients."""
    metrics = TextMetrics()
    candidate = choose_layout(entries, plan_width, metrics, _scale_width())
    if candidate is None:
        return _KeyLayout([], 0, 0)
    result = []
    left = -candidate.left_trim
    line_height = _KEY_FONT_FT * _KEY_LINE_RATIO
    for column, width, glyph_width in zip(
        candidate.columns, candidate.widths, candidate.glyph_widths, strict=True
    ):
        y = _KEY_FONT_FT
        for glyph, name in column:
            rows = candidate.rows[name]
            result.append(_KeyEntry(glyph, rows, left + glyph_width, y))
            y += max(1, len(rows)) * line_height
        left += width + _COLUMN_GAP_FT
    height = (candidate.lines - 1) * line_height + _KEY_FONT_FT * 1.3
    return _KeyLayout(result, candidate.width, height)


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


def _glyph_spot(
    room: Room, obstacles: list[Rect], glyph: str
) -> tuple[float, float, float]:
    """Room-local glyph centre and font size, keeping clear of stair footprints.

    With no stairs the glyph sits at the room's centre at the usual size.
    Otherwise it is centred in the largest free full-width or full-height band
    between the room's edges and the footprints, sized to that band — falling
    back to the room centre when every band is blocked.
    """
    width, height = room.width, room.height
    if not obstacles:
        return width / 2, height / 2, _glyph_font(width, height, glyph)
    xs = sorted({0, width, *(x for r in obstacles for x in (r[0], r[0] + r[2]))})
    ys = sorted({0, height, *(y for r in obstacles for y in (r[1], r[1] + r[3]))})
    bands = [(0, y0, width, y1 - y0) for y0, y1 in pairwise(ys)]
    bands += [(x0, 0, x1 - x0, height) for x0, x1 in pairwise(xs)]
    best: Rect | None = None
    for band in bands:
        blocked = any(
            min(band[0] + band[2], r[0] + r[2]) > max(band[0], r[0])
            and min(band[1] + band[3], r[1] + r[3]) > max(band[1], r[1])
            for r in obstacles
        )
        if blocked:
            continue
        if best is None or band[2] * band[3] > best[2] * best[3]:
            best = band
    if best is None:
        return width / 2, height / 2, _glyph_font(width, height, glyph)
    bx, by, bw, bh = best
    return bx + bw / 2, by + bh / 2, _glyph_font(bw, bh, glyph)


# A drawn line as (x1, y1, x2, y2) in feet (may fall on half-grid points).
_Line = tuple[float, float, float, float]


def _stair_hard_edges(stairs: Stairs, rect: Rect) -> list[_Line]:
    """The footprint edges drawn solid: every side that isn't an entrance
    (see :func:`~porta.layout.stair_open_sides`)."""
    x, y, w, h = rect
    edges: dict[Direction, _Line] = {
        Direction.UP: (x, y, x + w, y),
        Direction.DOWN: (x, y + h, x + w, y + h),
        Direction.LEFT: (x, y, x, y + h),
        Direction.RIGHT: (x + w, y, x + w, y + h),
    }
    open_sides = stair_open_sides(stairs)
    return [edge for side, edge in edges.items() if side not in open_sides]


def _stair_treads(stairs: Stairs, rect: Rect) -> list[_Line]:
    """Tread lines crossing the run every ``1/_TREADS_PER_GRID`` of a grid
    square, ends included.

    Treads narrow toward the downhill end — the depth cue that shows which
    way the flight descends — shrinking linearly from ``_TREAD_MAX_RATIO``
    of the footprint's breadth at the high end to ``_TREAD_MIN_RATIO`` at
    the low end, centred across the run. At a closed end the hard edge
    already draws the line, so the end tread is emitted only where the
    footprint is open.
    """
    x, y, w, h = rect
    horizontal = stairs.down.axis is Axis.HORIZONTAL
    run = w if horizontal else h
    # Ratios apply to the breadth actually visible between the flank walls'
    # inner faces (each flank stroke intrudes half its width).
    cross = (h if horizontal else w) - _WALL_STROKE_FT
    open_sides = stair_open_sides(stairs)
    start_open = (Direction.LEFT if horizontal else Direction.UP) in open_sides
    end_open = (Direction.RIGHT if horizontal else Direction.DOWN) in open_sides
    treads: list[_Line] = []
    intervals = run * _TREADS_PER_GRID // _GRID_FT
    for i in range(intervals + 1):
        if (i == 0 and not start_open) or (i == intervals and not end_open):
            continue
        t = run * i / intervals
        downhill = t if stairs.down in (Direction.RIGHT, Direction.DOWN) else run - t
        scale = _TREAD_MAX_RATIO - (
            (_TREAD_MAX_RATIO - _TREAD_MIN_RATIO) * downhill / run
        )
        half = cross * scale / 2
        if horizontal:
            treads.append((x + t, y + h / 2 - half, x + t, y + h / 2 + half))
        else:
            treads.append((x + w / 2 - half, y + t, x + w / 2 + half, y + t))
    return treads


def _glyph_font(width: int, height: int, glyph: str) -> float:
    """Size labels proportionally to the available room or stair band."""
    size = min(width, height) * _LABEL_RATIO
    # Standalone combining marks are valid explicit glyphs too.
    advance = max(0.7, _text_width(glyph))
    return min(size, width * _LABEL_FIT / advance)


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
    raise ValueError(
        f"automatic glyphs exhausted for {room_id!r} (36 used); "
        'use unique multi-character glyphs or glyph=""'
    )
