"""Render a *solved* model to output.

Two emitters that both consume a solved model: the SVG generator (Stage 4) and
the debug-ascii rasterizer below. SVG is built from stdlib string templating
only (no runtime dependencies).
"""

from porta.model import Building, Room

_GRID_FT = 5
_EMPTY = "."
_FALLBACK_GLYPHS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


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
