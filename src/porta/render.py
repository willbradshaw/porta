"""Render a *solved* model to output.

Two emitters that both consume a solved model: the SVG generator (Stage 4) and
the debug-ascii rasterizer below. SVG is built from stdlib string templating
only (no runtime dependencies).
"""

from dataclasses import dataclass
from itertools import pairwise
from unicodedata import category, east_asian_width
from xml.sax.saxutils import escape

from porta.errors import RenderError
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
from porta.model import MAX_GLYPH_LENGTH, Axis, Block, Building, Direction, Room, Stairs
from porta.style import DEFAULT_STYLE, Style
from porta.text_metrics import TextMetrics, text_bounds

_GRID_FT = 5
_EMPTY = "."
_NO_GLYPH = "_"  # ascii cell fill for an unlabeled (glyph="") room

_SVG_NS = "http://www.w3.org/2000/svg"


def render_ascii(building: Building, *, style: Style | None = None) -> str:
    """Render a solved building as an ASCII grid plus a glyph legend.

    One cell per 5-ft square, space-separated, north at the top; every cell is
    padded to the widest glyph in the plan. Empty cells are ``.``; an unlabeled
    room's cells are ``_``. A blank line then a ``glyph=id`` legend
    (numeric value first, then nonnumeric glyphs lexicographically) follows.
    Like doors, stairs are not rendered in the ascii grid (room extents only).

    Args:
        building: A building whose rooms have been placed by
            :func:`~porta.layout.solve`.
        style: Resolved style or built-in defaults; ASCII uses labels.scheme
            and labels.start.

    Returns:
        The multi-line ASCII rendering (no trailing newline).

    Raises:
        ValueError: If any room has not been placed.
        RenderError: If the automatic glyph scheme runs out of labels.
    """
    style = DEFAULT_STYLE if style is None else style
    placed = _placed_rooms(building)
    glyphs = _assign_glyphs(
        building, style["labels"]["scheme"], style["labels"]["start"]
    )

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


def render_svg(
    building: Building, *, background: str | None = None, style: Style | None = None
) -> str:
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
        background: Optional backdrop override; takes precedence over the style.
        style: Resolved dictionary from load_style, or built-in defaults if omitted.

    Returns:
        The SVG document as a string.

    Raises:
        ValueError: If any room has not been placed.
        RenderError: If the automatic glyph scheme runs out of labels.
    """
    style = DEFAULT_STYLE if style is None else style
    background = style["page"]["background"] if background is None else background
    placed = _placed_rooms(building)
    glyphs = _assign_glyphs(
        building, style["labels"]["scheme"], style["labels"]["start"]
    )
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
    key = _key_layout(entries, plan_w, style)
    scale_width = _scale_width(style)
    furniture_width = max(key.width, scale_width)
    center_x = (min_x + max_x) / 2
    view_w = max(plan_w, furniture_width) + 2 * style["page"]["margin_ft"]
    scale_y = max_y + style["scale_bar"]["gap_ft"]
    key_top = (
        scale_y
        + (style["key"]["font_ft"] * 1.2)
        + style["scale_bar"]["gap_ft"]
        - style["key"]["font_ft"]
    )
    view_h = (
        key_top
        + key.height
        + style["page"]["margin_ft"]
        - (min_y - style["page"]["margin_ft"])
    )
    view_x = center_x - view_w / 2
    view_y = min_y - style["page"]["margin_ft"]

    lines = [
        f'<svg xmlns="{_SVG_NS}" '
        f'width="{_num(view_w * style["page"]["display_scale"])}" '
        f'height="{_num(view_h * style["page"]["display_scale"])}" '
        f'viewBox="{_num(view_x)} {_num(view_y)} {_num(view_w)} {_num(view_h)}" '
        f'font-family="{_attr(style["typography"]["font_family"])}" '
        f'font-weight="{style["typography"]["font_weight"]}" '
        f'fill="{_attr(style["page"]["line_color"])}">'
    ]

    # Opaque background so the drawing is legible on any viewer backdrop.
    lines.append(
        f'  <rect x="{_num(view_x)}" y="{_num(view_y)}" '
        f'width="{_num(view_w)}" height="{_num(view_h)}" fill="{_attr(background)}" />'
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
        f'stroke="{_attr(style["page"]["line_color"])}" '
        f'opacity="{_num(style["grid"]["opacity"])}" '
        f'stroke-width="{_num(style["grid"]["stroke_ft"])}">'
    )
    for gx in range(min_x, max_x + 1, style["grid"]["spacing_ft"]):
        lines.append(
            f'    <line x1="{_num(gx)}" y1="{_num(min_y)}" '
            f'x2="{_num(gx)}" y2="{_num(max_y)}" />'
        )
    for gy in range(min_y, max_y + 1, style["grid"]["spacing_ft"]):
        lines.append(
            f'    <line x1="{_num(min_x)}" y1="{_num(gy)}" '
            f'x2="{_num(max_x)}" y2="{_num(gy)}" />'
        )
    lines.append("  </g>")

    # Shared walls appear once. Square caps close perpendicular corners.
    exterior, interior = wall_segments(building)
    for kind, segments, width in (
        ("interior", interior, style["walls"]["interior_stroke_ft"]),
        ("exterior", exterior, style["walls"]["exterior_stroke_ft"]),
    ):
        for x1, y1, x2, y2 in segments:
            lines.append(
                f'  <line class="wall {kind}" x1="{_num(x1)}" y1="{_num(y1)}" '
                f'x2="{_num(x2)}" y2="{_num(y2)}" '
                f'stroke="{_attr(style["page"]["line_color"])}" '
                f'stroke-width="{_num(width)}" '
                f'stroke-linecap="square" />'
            )

    for room, x, y in sorted(placed, key=lambda t: t[0].id):
        if room.id in member_block:
            continue
        glyph = glyphs[room.id]
        if not glyph:
            continue  # unlabeled room
        lx, ly, font = _glyph_spot(room, room_stairs.get(room.id, []), glyph, style)
        lines.append(
            f'  <text data-room="{room.id}" x="{_num(x + lx)}" '
            f'y="{_num(y + ly)}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="{_num(font)}" '
            f'fill="{_attr(style["typography"]["text_color"])}">'
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
        lx, ly, font = _glyph_spot(member, room_stairs.get(member.id, []), glyph, style)
        lines.append(
            f'  <text data-block="{block.id}" x="{_num(mx + lx)}" '
            f'y="{_num(my + ly)}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="{_num(font)}" '
            f'fill="{_attr(style["typography"]["text_color"])}">'
            f"{escape(glyph)}</text>"
        )

    # Dividers: a dashed dividing line along a suppressed block boundary,
    # cut where a stair entrance lies on it.
    for x1, y1, x2, y2 in sorted(divider_segments(building)):
        lines.append(
            f'  <line class="divider" x1="{_num(x1)}" y1="{_num(y1)}" '
            f'x2="{_num(x2)}" '
            f'y2="{_num(y2)}" '
            f'stroke="{_attr(style["page"]["line_color"])}" '
            f'stroke-width="{_num(style["dividers"]["stroke_ft"])}" '
            f'stroke-dasharray="{_attr(style["dividers"]["dash"])}" />'
        )

    # Stairs: hard lines on the non-entrance sides and treads across the run,
    # narrowing toward the downhill (down=) end.
    for stairs, rect in footprints:
        lines.append(f'  <g class="stairs" data-room="{stairs.room}">')
        for sx1, sy1, sx2, sy2 in _stair_hard_edges(stairs, rect):
            lines.append(
                f'    <line x1="{_num(sx1)}" y1="{_num(sy1)}" '
                f'x2="{_num(sx2)}" y2="{_num(sy2)}" '
                f'stroke="{_attr(style["page"]["line_color"])}" '
                f'stroke-width="{_num(style["walls"]["interior_stroke_ft"])}" '
                f'stroke-linecap="square" />'
            )
        for sx1, sy1, sx2, sy2 in _stair_treads(stairs, rect, style):
            lines.append(
                f'    <line x1="{_num(sx1)}" y1="{_num(sy1)}" '
                f'x2="{_num(sx2)}" y2="{_num(sy2)}" '
                f'stroke="{_attr(style["page"]["line_color"])}" '
                f'stroke-width="{_num(style["stairs"]["stroke_ft"])}" />'
            )
        lines.append("  </g>")

    # Windows have background-colored interiors between two strokes, half a foot apart.
    for x1, y1, x2, y2 in sorted(window_segments(building)):
        lines.append(
            f'  <line class="window-fill" x1="{_num(x1)}" y1="{_num(y1)}" '
            f'x2="{_num(x2)}" '
            f'y2="{_num(y2)}" '
            f'stroke="{_attr(background)}" '
            f'stroke-width="{_num(style["windows"]["gap_ft"])}" />'
        )
        for offset in (-style["windows"]["gap_ft"] / 2, style["windows"]["gap_ft"] / 2):
            dx, dy = (0, offset) if y1 == y2 else (offset, 0)
            lines.append(
                f'  <line class="window" x1="{_num(x1 + dx)}" '
                f'y1="{_num(y1 + dy)}" x2="{_num(x2 + dx)}" '
                f'y2="{_num(y2 + dy)}" '
                f'stroke="{_attr(style["page"]["line_color"])}" '
                f'stroke-width="{_num(style["windows"]["stroke_ft"])}" />'
            )

    # Open doors: a dotted line across the gap left in the walls above.
    for x1, y1, x2, y2 in sorted(open_door_segments(building)):
        lines.append(
            f'  <line class="open" x1="{_num(x1)}" y1="{_num(y1)}" '
            f'x2="{_num(x2)}" '
            f'y2="{_num(y2)}" '
            f'stroke="{_attr(style["page"]["line_color"])}" '
            f'stroke-width="{_num(style["walls"]["interior_stroke_ft"])}" '
            f'stroke-dasharray="{_attr(style["doors"]["open_dash"])}" '
            f'stroke-linecap="round" />'
        )

    # Doors: a thick colored line along the shared wall, over the rooms.
    # Sorted so the output is independent of statement order.
    for x1, y1, x2, y2 in sorted(door_segments(building)):
        lines.append(
            f'  <line class="door" x1="{_num(x1)}" y1="{_num(y1)}" '
            f'x2="{_num(x2)}" '
            f'y2="{_num(y2)}" '
            f'stroke="{_attr(style["page"]["line_color"])}" '
            f'stroke-width="{_num(style["doors"]["stroke_ft"])}" />'
        )

    # Secret doors: a normal-style door mark shows the size and position, and
    # an "S" over it (haloed in the background color to stay legible) says
    # the door is concealed.
    for x1, y1, x2, y2 in sorted(secret_door_segments(building)):
        lines.append(
            f'  <line class="secret" x1="{_num(x1)}" y1="{_num(y1)}" '
            f'x2="{_num(x2)}" '
            f'y2="{_num(y2)}" '
            f'stroke="{_attr(style["page"]["line_color"])}" '
            f'stroke-width="{_num(style["doors"]["stroke_ft"])}" />'
        )
        lines.append(
            f'  <text class="secret" x="{_num((x1 + x2) / 2)}" '
            f'y="{_num((y1 + y2) / 2)}" text-anchor="middle" '
            f'dominant-baseline="central" '
            f'font-size="{_num(style["doors"]["secret_font_ft"])}" '
            f'stroke="{_attr(background)}" '
            f'stroke-width="{_num(style["doors"]["secret_halo_ft"])}" '
            f'paint-order="stroke">S</text>'
        )

    lines.append(
        f'  <g class="scale" '
        f'font-size="{_num(style["key"]["font_ft"])}" '
        f'fill="{_attr(style["typography"]["text_color"])}">'
    )
    for dx, dy, label in _scale_labels(style):
        bounds = text_bounds(label, (style["key"]["font_ft"]))
        lines.append(
            f'    <text x="{_num(center_x + dx - bounds.width / 2 - bounds.x)}" '
            f'y="{_num(scale_y + dy)}">{label}</text>'
        )
    for dx, fill in (
        (-style["scale_bar"]["length_ft"] / 2, style["page"]["line_color"]),
        (0, background),
    ):
        lines.append(
            f'    <rect x="{_num(center_x + dx)}" '
            f'y="{_num(scale_y - (style["key"]["font_ft"] * 0.3))}" '
            f'width="{_num(style["scale_bar"]["length_ft"] / 2)}" '
            f'height="{_num(style["key"]["font_ft"] * 0.3)}" '
            f'fill="{_attr(fill)}" '
            f'stroke="{_attr(style["page"]["line_color"])}" '
            f'stroke-width="{_num(style["key"]["font_ft"] * 0.04)}" />'
        )
    lines.append("  </g>")

    key_left = center_x - key.width / 2
    for entry in key.entries:
        key_x, key_y = key_left + entry.x, key_top + entry.y
        glyph_bounds = text_bounds(entry.glyph, style["key"]["font_ft"])
        glyph_x = key_x - glyph_bounds.width - glyph_bounds.x
        lines.append(
            f'  <g class="key" '
            f'font-size="{_num(style["key"]["font_ft"])}" '
            f'fill="{_attr(style["typography"]["text_color"])}">'
            f'<text x="{_num(glyph_x)}" '
            f'y="{_num(key_y)}">{escape(entry.glyph)}</text>'
        )
        for row, name in enumerate(entry.names):
            name_x = (
                key_x
                + style["key"]["identifier_gap_ft"]
                - text_bounds(name, style["key"]["font_ft"]).x
            )
            lines.append(
                f'    <text x="{_num(name_x)}" '
                f'y="{_num(key_y + row * style["key"]["line_spacing_ft"])}">'
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


def _scale_labels(style: Style = DEFAULT_STYLE) -> list[tuple[float, float, str]]:
    return [
        (-style["scale_bar"]["length_ft"] / 2, (style["key"]["font_ft"] * -0.6), "0"),
        (
            0,
            (style["key"]["font_ft"] * -0.6),
            _num(style["scale_bar"]["length_ft"] / 2),
        ),
        (
            style["scale_bar"]["length_ft"] / 2,
            (style["key"]["font_ft"] * -0.6),
            f"{_num(style['scale_bar']['length_ft'])} ft",
        ),
        (
            0,
            (style["key"]["font_ft"] * 1.2),
            f"{style['grid']['spacing_ft']}-ft squares",
        ),
    ]


def _scale_width(style: Style = DEFAULT_STYLE) -> float:
    # Symmetric footprint keeps the bar centered while reserving its end labels.
    return float(
        max(
            style["scale_bar"]["length_ft"] + (style["key"]["font_ft"] * 0.04),
            *(
                2 * abs(dx) + text_bounds(label, (style["key"]["font_ft"])).width
                for dx, _, label in _scale_labels(style)
            ),
        )
    )


def _key_layout(
    entries: list[tuple[str, str]], plan_width: float, style: Style = DEFAULT_STYLE
) -> _KeyLayout:
    """Lay out the lowest-scoring equal-width key using approved coefficients."""
    metrics = TextMetrics(size=style["key"]["font_ft"])
    candidate = choose_layout(
        entries,
        plan_width,
        metrics,
        _scale_width(style),
        style=style,
    )
    if candidate is None:
        return _KeyLayout([], 0, 0)
    result = []
    left = -candidate.left_trim
    line_height = style["key"]["line_spacing_ft"]
    for column, width, glyph_width in zip(
        candidate.columns, candidate.widths, candidate.glyph_widths, strict=True
    ):
        y = style["key"]["font_ft"]
        for glyph, name in column:
            rows = candidate.rows[name]
            result.append(_KeyEntry(glyph, rows, left + glyph_width, y))
            y += max(1, len(rows)) * line_height
        left += width + style["key"]["column_gap_ft"]
    height = (candidate.lines - 1) * line_height + style["key"]["font_ft"] * 1.3
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

    Numeric glyphs sort by value, then verbatim text; nonnumeric glyphs follow
    in Unicode code-point order. IDs break any remaining ties.
    """
    ids = [eid for eid in _entity_ids(building, member_block) if glyphs[eid]]

    def key(eid: str) -> tuple[bool, int, str, str]:
        glyph = glyphs[eid]
        number = _glyph_number(glyph)
        return number is None, number if number is not None else 0, glyph, eid

    return sorted(ids, key=key)


def _glyph_spot(
    room: Room, obstacles: list[Rect], glyph: str, style: Style = DEFAULT_STYLE
) -> tuple[float, float, float]:
    """Room-local glyph centre and font size, keeping clear of stair footprints.

    With no stairs the glyph sits at the room's centre at the usual size.
    Otherwise it is centred in the largest free full-width or full-height band
    between the room's edges and the footprints, sized to that band — falling
    back to the room centre when every band is blocked.
    """
    width, height = room.width, room.height
    if not obstacles:
        return width / 2, height / 2, _glyph_font(width, height, glyph, style)
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
        return width / 2, height / 2, _glyph_font(width, height, glyph, style)
    bx, by, bw, bh = best
    return bx + bw / 2, by + bh / 2, _glyph_font(bw, bh, glyph, style)


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


def _stair_treads(
    stairs: Stairs, rect: Rect, style: Style = DEFAULT_STYLE
) -> list[_Line]:
    """Tread lines at the configured number of intervals per grid square.

    Treads narrow toward the downhill end — the depth cue that shows which
    way the flight descends — shrinking linearly from the maximum ratio
    of the footprint's breadth at the high end to the minimum ratio at
    the low end, centred across the run. At a closed end the hard edge
    already draws the line, so the end tread is emitted only where the
    footprint is open.
    """
    x, y, w, h = rect
    horizontal = stairs.down.axis is Axis.HORIZONTAL
    run = w if horizontal else h
    # Ratios apply to the breadth actually visible between the flank walls'
    # inner faces (each flank stroke intrudes half its width).
    cross = (h if horizontal else w) - style["walls"]["interior_stroke_ft"]
    open_sides = stair_open_sides(stairs)
    start_open = (Direction.LEFT if horizontal else Direction.UP) in open_sides
    end_open = (Direction.RIGHT if horizontal else Direction.DOWN) in open_sides
    treads: list[_Line] = []
    intervals = max(
        1, run * style["stairs"]["treads_per_grid"] // style["grid"]["spacing_ft"]
    )
    for i in range(intervals + 1):
        if (i == 0 and not start_open) or (i == intervals and not end_open):
            continue
        t = run * i / intervals
        downhill = t if stairs.down in (Direction.RIGHT, Direction.DOWN) else run - t
        scale = style["stairs"]["max_ratio"] - (
            (style["stairs"]["max_ratio"] - style["stairs"]["min_ratio"])
            * downhill
            / run
        )
        half = cross * scale / 2
        if horizontal:
            treads.append((x + t, y + h / 2 - half, x + t, y + h / 2 + half))
        else:
            treads.append((x + w / 2 - half, y + t, x + w / 2 + half, y + t))
    return treads


def _glyph_font(
    width: int, height: int, glyph: str, style: Style = DEFAULT_STYLE
) -> float:
    """Size labels proportionally to the available room or stair band."""
    size = min(width, height) * style["labels"]["ratio"]
    # Standalone combining marks are valid explicit glyphs too.
    advance = max(0.7, _text_width(glyph))
    return float(min(size, width * style["labels"]["fit"] / advance))


def _assign_glyphs(building: Building, scheme: str, start: int) -> dict[str, str]:
    """Assign a glyph to each non-member room and each block; members inherit
    their block's glyph.

    Explicit glyphs are preserved and ASCII digit glyphs reserve their numeric
    values. Automatic numbers begin at start in casefolded name order, then ID order.
    Empty names sort first. Mnemonic glyphs use ID order and unused ID characters.
    Suppressed member glyphs do not reserve labels.
    """
    member_block = _member_block(building)
    entities: list[Room | Block] = [
        room for room in building.rooms if room.id not in member_block
    ]
    entities.extend(building.blocks)
    glyphs = {
        entity.id: entity.glyph for entity in entities if entity.glyph is not None
    }
    used = {
        number
        for glyph in glyphs.values()
        if (number := _glyph_number(glyph)) is not None
    }
    used_glyphs = set(glyphs.values())
    next_number = start
    ordered = sorted(
        entities,
        key=lambda entity: (
            (entity.name or "").casefold() if scheme == "numeric" else "",
            entity.id,
        ),
    )
    for entity in ordered:
        if entity.id in glyphs:
            continue
        if scheme == "mnemonic":
            glyph = _pick_mnemonic(entity, used_glyphs)
            glyphs[entity.id] = glyph
            used_glyphs.add(glyph)
            continue
        while next_number in used:
            next_number += 1
        if next_number >= 10**MAX_GLYPH_LENGTH:
            raise RenderError(
                f"automatic numbers exhausted for {entity.id!r}: "
                f"all glyphs are limited to {MAX_GLYPH_LENGTH} characters; "
                'use nonnumeric custom glyphs or glyph="" to free numbers, '
                "or lower labels.start",
                line=entity.line,
            )
        glyphs[entity.id] = str(next_number)
        next_number += 1
    for member, block_id in member_block.items():
        glyphs[member] = glyphs[block_id]
    return glyphs


def _pick_mnemonic(entity: Room | Block, used: set[str]) -> str:
    """Use the first available ID character, then the legacy fallback pool."""
    for char in entity.id.upper() + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        if char.isalnum() and char not in used:
            return char
    raise RenderError(
        f"automatic mnemonic glyphs exhausted for {entity.id!r} (36 used); "
        'use unique multi-character glyphs, glyph="", or labels.scheme="numeric"',
        line=entity.line,
    )


def _glyph_number(glyph: str) -> int | None:
    """Numeric value of a nonempty ASCII digit glyph, including leading zeros."""
    return int(glyph) if glyph.isascii() and glyph.isdecimal() else None


def _attr(value: str) -> str:
    """Escape text for a double-quoted SVG attribute."""
    return escape(value, {'"': "&quot;"})
