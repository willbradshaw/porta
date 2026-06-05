"""Parse ``.porta`` source text into the data model.

Owns all *syntax* errors (bad dimensions, unknown keywords, unbalanced
quotes), each reported with its source line number. Pure: text in, model out,
or raises :class:`~porta.errors.ParseError`.

One line per room::

    room <id> "<Name>" <W>x<H> [root] [<relation> <anchor> ...]
    relation = up-of | down-of | left-of | right-of

Reference resolution (does ``anchor`` exist? is there exactly one root?) is a
*layout* concern and is deliberately not checked here.
"""

import re

from porta.errors import ParseError
from porta.model import (
    Align,
    Building,
    Direction,
    Door,
    Doorway,
    ExternalDoor,
    Relation,
    Room,
)

# A token plus whether it was double-quoted in the source.
Token = tuple[str, bool]

_ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\Z")
_DIM_RE = re.compile(r"(\?|[0-9]+)x(\?|[0-9]+)\Z")
_GRID_FT = 5
_DEFAULT_DOOR_FT = 5
_MODIFIERS = ("shift=", "align=", "door", "no-door")  # relation-modifier prefixes
_KEYWORDS: dict[str, Direction] = {
    direction.value: direction for direction in Direction
}
# Bare side words for external doors (the relation keywords drop their '-of').
_SIDES: dict[str, Direction] = {
    direction.value.removesuffix("-of"): direction for direction in Direction
}


def parse(text: str) -> Building:
    """Parse ``.porta`` source into a :class:`~porta.model.Building`.

    Args:
        text: The full contents of a ``.porta`` file.

    Returns:
        The parsed building (rooms in source order, coordinates unresolved).

    Raises:
        ParseError: On the first syntax error, carrying its source line.
    """
    rooms: list[Room] = []
    doors: list[Doorway] = []
    external_doors: list[ExternalDoor] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        tokens = _tokenize(raw, lineno)
        if not tokens:
            continue  # blank or comment-only line (its line number is still spent)
        head, head_quoted = tokens[0]
        if not head_quoted and head.startswith("door"):
            # '<room> outside <side>' is an external door; '<a> <b>' an internal one.
            if len(tokens) >= 3 and not tokens[2][1] and tokens[2][0] == "outside":
                external_doors.append(_parse_external_door(tokens, lineno))
            else:
                doors.append(_parse_doorway(tokens, lineno))
            continue
        room = _parse_room(tokens, lineno)
        if room.id in seen:
            raise ParseError(f"duplicate room id {room.id!r}", line=lineno)
        seen.add(room.id)
        rooms.append(room)
    return Building(rooms, doors, external_doors)


def _parse_doorway(tokens: list[Token], lineno: int) -> Doorway:
    """Parse a standalone ``door[=W][@O] <a> <b>`` line."""
    spec = _parse_door(tokens[0][0], lineno)
    rest = tokens[1:]
    if len(rest) != 2:
        raise ParseError("a door needs exactly two room ids", line=lineno)
    for room_id, quoted in rest:
        if quoted or not _ID_RE.match(room_id):
            raise ParseError(f"invalid room id {room_id!r}", line=lineno)
    a, b = rest[0][0], rest[1][0]
    if a == b:
        raise ParseError("a door needs two different rooms", line=lineno)
    return Doorway(a=a, b=b, door=spec, line=lineno)


def _parse_external_door(tokens: list[Token], lineno: int) -> ExternalDoor:
    """Parse ``door[=W][@O] <room> outside <side>`` (side = up/down/left/right)."""
    spec = _parse_door(tokens[0][0], lineno)
    rest = tokens[1:]
    if len(rest) != 3:
        raise ParseError("an external door needs '<room> outside <side>'", line=lineno)
    (room, room_quoted), _outside, (side, side_quoted) = rest
    if room_quoted or not _ID_RE.match(room):
        raise ParseError(f"invalid room id {room!r}", line=lineno)
    direction = _SIDES.get(side)
    if side_quoted or direction is None:
        raise ParseError(f"side must be up/down/left/right, got {side!r}", line=lineno)
    return ExternalDoor(room=room, side=direction, door=spec, line=lineno)


def _tokenize(raw: str, lineno: int) -> list[Token]:
    """Split one source line into tokens, honouring quotes and ``#`` comments.

    A ``#`` outside quotes starts a comment to end of line; inside a quoted
    string it is literal. Each token is tagged with whether it was quoted.
    """
    tokens: list[Token] = []
    i, n = 0, len(raw)
    while i < n:
        char = raw[i]
        if char.isspace():
            i += 1
        elif char == "#":
            break
        elif char == '"':
            j = i + 1
            while j < n and raw[j] != '"':
                j += 1
            if j >= n:
                raise ParseError("unterminated quote", line=lineno)
            tokens.append((raw[i + 1 : j], True))
            i = j + 1
        else:
            j = i
            while j < n and not raw[j].isspace() and raw[j] not in '#"':
                j += 1
            tokens.append((raw[i:j], False))
            i = j
    return tokens


def _parse_room(tokens: list[Token], lineno: int) -> Room:
    """Turn a tokenised ``room`` line into a :class:`~porta.model.Room`."""
    if tokens[0][0] != "room":
        raise ParseError(
            f"unknown directive {tokens[0][0]!r}; expected 'room'", line=lineno
        )
    if len(tokens) < 4:
        raise ParseError(
            "a room needs an id, a quoted name, and WxH dimensions", line=lineno
        )

    room_id, id_quoted = tokens[1]
    if id_quoted or not _ID_RE.match(room_id):
        raise ParseError(f"invalid room id {room_id!r}", line=lineno)

    name, name_quoted = tokens[2]
    if not name_quoted:
        raise ParseError("room name must be wrapped in double quotes", line=lineno)

    width, height, auto_width, auto_height = _parse_dimensions(tokens[3][0], lineno)
    is_root, relations = _parse_modifiers(tokens[4:], lineno)

    return Room(
        id=room_id,
        name=name,
        width=width,
        height=height,
        auto_width=auto_width,
        auto_height=auto_height,
        is_root=is_root,
        relations=relations,
        line=lineno,
    )


def _parse_dimensions(text: str, lineno: int) -> tuple[int, int, bool, bool]:
    """Parse a ``WxH`` token into feet, where each side may be ``?`` (auto).

    Returns ``(width, height, auto_width, auto_height)``; an auto side has its
    value set to 0 for the layout to resolve.
    """
    match = _DIM_RE.match(text)
    if match is None:
        raise ParseError(f"expected WxH dimensions in feet, got {text!r}", line=lineno)
    width, auto_width = _parse_dimension(match.group(1), "width", lineno)
    height, auto_height = _parse_dimension(match.group(2), "height", lineno)
    return width, height, auto_width, auto_height


def _parse_dimension(raw: str, label: str, lineno: int) -> tuple[int, bool]:
    """Parse one dimension: ``?`` (auto → 0) or a positive on-grid integer."""
    if raw == "?":
        return 0, True
    value = int(raw)
    if value <= 0:
        raise ParseError(f"{label} must be positive, got {value}", line=lineno)
    if value % _GRID_FT != 0:
        raise ParseError(
            f"{label} must be a multiple of {_GRID_FT} (the grid), got {value}",
            line=lineno,
        )
    return value, False


def _parse_modifiers(tokens: list[Token], lineno: int) -> tuple[bool, list[Relation]]:
    """Parse the trailing ``root`` flag and relations (with modifiers, any order)."""
    is_root = False
    relations: list[Relation] = []
    i = 0
    while i < len(tokens):
        value, quoted = tokens[i]
        if quoted:
            raise ParseError(f"unexpected quoted value {value!r}", line=lineno)
        if value == "root":
            is_root = True
            i += 1
            continue
        direction = _KEYWORDS.get(value)
        if direction is None:
            if value.startswith(_MODIFIERS):
                raise ParseError(f"{value!r} must follow a relation", line=lineno)
            raise ParseError(f"unknown relation or keyword {value!r}", line=lineno)
        if i + 1 >= len(tokens):
            raise ParseError(f"relation {value!r} needs an anchor room id", line=lineno)
        anchor, anchor_quoted = tokens[i + 1]
        if anchor_quoted or not _ID_RE.match(anchor):
            raise ParseError(f"invalid anchor id {anchor!r}", line=lineno)
        i += 2

        align = Align.START
        shift = 0
        door: Door | None = None
        no_door = False
        while (
            i < len(tokens) and not tokens[i][1] and tokens[i][0].startswith(_MODIFIERS)
        ):
            token = tokens[i][0]
            if token.startswith("shift="):
                shift = _parse_shift(token, lineno)
            elif token.startswith("align="):
                align = _parse_align(token, lineno)
            elif token == "no-door":
                no_door = True
            else:
                door = _parse_door(token, lineno)
            i += 1

        relations.append(
            Relation(
                direction=direction,
                anchor=anchor,
                line=lineno,
                align=align,
                shift=shift,
                door=door,
                no_door=no_door,
            )
        )
    return is_root, relations


def _parse_door(token: str, lineno: int) -> Door:
    """Parse a ``door[=W][@O]`` modifier (width default 5, offset default centred)."""
    rest = token[len("door") :]
    width = _DEFAULT_DOOR_FT
    offset: int | None = None
    if "@" in rest:
        rest, _, raw = rest.partition("@")
        offset = _door_dimension(raw, "door offset", lineno, allow_zero=True)
    if rest.startswith("="):
        width = _door_dimension(rest[1:], "door width", lineno, allow_zero=False)
    elif rest:
        raise ParseError(f"malformed door modifier {token!r}", line=lineno)
    return Door(width=width, offset=offset)


def _door_dimension(raw: str, label: str, lineno: int, *, allow_zero: bool) -> int:
    """Parse a door width/offset: a grid-aligned, non-negative (or positive) int."""
    try:
        value = int(raw)
    except ValueError:
        raise ParseError(
            f"{label} must be an integer, got {raw!r}", line=lineno
        ) from None
    if value % _GRID_FT != 0:
        raise ParseError(
            f"{label} must be a multiple of {_GRID_FT}, got {value}", line=lineno
        )
    minimum = 0 if allow_zero else _GRID_FT
    if value < minimum:
        raise ParseError(
            f"{label} must be at least {minimum}, got {value}", line=lineno
        )
    return value


def _parse_align(token: str, lineno: int) -> Align:
    """Parse an ``align=start|end`` modifier."""
    raw = token[len("align=") :]
    try:
        return Align(raw)
    except ValueError:
        raise ParseError(
            f"align must be 'start' or 'end', got {raw!r}", line=lineno
        ) from None


def _parse_shift(token: str, lineno: int) -> int:
    """Parse a ``shift=N`` modifier into signed, grid-aligned feet."""
    raw = token[len("shift=") :]
    try:
        value = int(raw)
    except ValueError:
        raise ParseError(
            f"shift must be an integer, got {raw!r}", line=lineno
        ) from None
    if value % _GRID_FT != 0:
        raise ParseError(
            f"shift must be a multiple of {_GRID_FT} (the grid), got {value}",
            line=lineno,
        )
    return value
