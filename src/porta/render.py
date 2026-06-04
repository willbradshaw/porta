"""Render a *solved* model to output.

Two emitters that both consume a solved model: the SVG generator (Stage 4) and
the debug-ascii rasterizer below. SVG is built from stdlib string templating
only (no runtime dependencies).
"""

from xml.sax.saxutils import escape

from porta.model import Building, Room

_GRID_FT = 5
_EMPTY = "."
_FALLBACK_GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

_SVG_NS = "http://www.w3.org/2000/svg"
_MARGIN_FT = 10  # padding around the plan, in feet
_WALL_STROKE_FT = 0.5  # wall line thickness, in feet
_LABEL_RATIO = 0.6  # room glyph size as a fraction of the room's shorter side
_KEY_FONT_FT = 6  # key text size, in feet
_KEY_LINE_FT = 8  # key line spacing, in feet


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
    glyphs = _assign_glyphs(building.rooms)

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
    legend = "  ".join(f"{glyphs[room.id]}={room.id}" for room in building.rooms)
    return f"{body}\n\n{legend}"


def render_svg(building: Building) -> str:
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

    Returns:
        The SVG document as a string.

    Raises:
        ValueError: If any room has not been placed.
    """
    placed = _placed_rooms(building)
    glyphs = _assign_glyphs(building.rooms)

    min_x = min(x for _, x, _ in placed)
    min_y = min(y for _, _, y in placed)
    max_x = max(x + room.width for room, x, _ in placed)
    max_y = max(y + room.height for room, _, y in placed)

    view_x = min_x - _MARGIN_FT
    view_y = min_y - _MARGIN_FT
    view_w = (max_x - min_x) + 2 * _MARGIN_FT
    view_h = (max_y - min_y) + 3 * _MARGIN_FT + len(building.rooms) * _KEY_LINE_FT

    lines = [
        f'<svg xmlns="{_SVG_NS}" width="{_num(view_w)}" height="{_num(view_h)}" '
        f'viewBox="{_num(view_x)} {_num(view_y)} {_num(view_w)} {_num(view_h)}">'
    ]
    for room, x, y in placed:
        font = min(room.width, room.height) * _LABEL_RATIO
        lines.append(
            f'  <rect data-room="{room.id}" x="{_num(x)}" y="{_num(y)}" '
            f'width="{_num(room.width)}" height="{_num(room.height)}" '
            f'fill="white" stroke="black" stroke-width="{_num(_WALL_STROKE_FT)}" />'
        )
        lines.append(
            f'  <text data-room="{room.id}" x="{_num(x + room.width / 2)}" '
            f'y="{_num(y + room.height / 2)}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="{_num(font)}">'
            f"{glyphs[room.id]}</text>"
        )

    key_top = max_y + _MARGIN_FT
    for i, room in enumerate(building.rooms):
        label = escape(f"{glyphs[room.id]}  {room.name}")
        lines.append(
            f'  <text class="key" x="{_num(min_x)}" '
            f'y="{_num(key_top + (i + 1) * _KEY_LINE_FT)}" '
            f'font-size="{_num(_KEY_FONT_FT)}">{label}</text>'
        )

    lines.append("</svg>")
    return "\n".join(lines)


def _num(value: float) -> str:
    """Format a number for SVG: drop a trailing ``.0`` so 10.0 renders as ``10``."""
    return str(int(value)) if value == int(value) else str(value)


def _placed_rooms(building: Building) -> list[tuple[Room, int, int]]:
    """Return (room, x, y) triples, raising if any room is unplaced."""
    placed: list[tuple[Room, int, int]] = []
    for room in building.rooms:
        if room.x is None or room.y is None:
            raise ValueError(
                f"render_ascii needs a solved building; {room.id!r} is unplaced"
            )
        placed.append((room, room.x, room.y))
    return placed


def _assign_glyphs(rooms: list[Room]) -> dict[str, str]:
    """Assign each room a single display glyph (mnemonic-first, then a pool)."""
    used: set[str] = set()
    glyphs: dict[str, str] = {}
    for room in rooms:
        chosen = _pick_glyph(room.id, used)
        used.add(chosen)
        glyphs[room.id] = chosen
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
