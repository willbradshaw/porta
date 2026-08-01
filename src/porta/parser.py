"""Parse ``.porta`` source text into the data model.

Owns all *syntax* errors (bad dimensions, unknown keywords, unbalanced
quotes), each reported with its source line number. Pure: text in, model out,
or raises :class:`~porta.errors.ParseError`.

One line per room::

    room <id> "<Name>" <W>x<H> [glyph="<glyph>"] [root] [<relation> <anchor> ...]
    relation = up-of | down-of | left-of | right-of

A statement may span several physical lines: a trailing whitespace-separated
backslash (outside quotes and comments) continues it on the next line.

The name slot is required but may be empty (``""``) for a room labelled only by
its glyph and size.

Reference resolution (does ``anchor`` exist? is there exactly one root?) is a
*layout* concern and is deliberately not checked here.
"""

import re
from dataclasses import replace
from typing import NamedTuple

from porta.errors import ParseError
from porta.model import (
    Align,
    Block,
    Building,
    Direction,
    Door,
    Doorway,
    ExternalDoor,
    Link,
    Relation,
    Room,
)


class Token(NamedTuple):
    """One source token: its text, whether it was double-quoted, and the
    physical line it sits on (which may be a continuation line)."""

    value: str
    quoted: bool
    line: int


def _is_bare(token: Token, value: str) -> bool:
    """Whether ``token`` is the unquoted keyword ``value``."""
    return not token.quoted and token.value == value


_DOOR_ATTRS = ("open", "secret")  # bare attribute words a door spec can take


def _is_attr(token: Token) -> bool:
    """Whether ``token`` is a bare door attribute (``open``/``secret``)."""
    return not token.quoted and token.value in _DOOR_ATTRS


def _apply_door_attr(door: Door, token: Token) -> Door:
    """Apply a bare ``open``/``secret`` attribute token to a door spec.

    A door takes at most one attribute: doubled or combined attributes raise.
    """
    if door.open or door.secret:
        raise ParseError(
            "a door takes at most one of 'open' and 'secret'", line=token.line
        )
    if token.value == "open":
        return replace(door, open=True)
    return replace(door, secret=True)


_ID_RE = re.compile(r"[a-z][a-z0-9_-]*\Z")
_DIM_RE = re.compile(r"(\?|[0-9]+)x(\?|[0-9]+)\Z")
_GRID_FT = 5
_DEFAULT_DOOR_FT = 5
_MAX_NAME = 40  # room name length cap (the name drives the rendered key's width)
_MAX_GLYPH = 3  # display glyph length cap (fits multi-digit room numbers)
_MODIFIERS = ("shift=", "align=", "door", "no-door")  # relation-modifier prefixes
_KEYWORDS: dict[str, Direction] = {
    direction.value: direction for direction in Direction
}
# Bare side words for external doors (the relation keywords drop their '-of').
_SIDES: dict[str, Direction] = {
    direction.value.removesuffix("-of"): direction for direction in Direction
}
# Words that are part of the syntax, so they cannot double as room ids.
_RESERVED: frozenset[str] = frozenset(
    {
        "root",
        "door",
        "no-door",
        "open",
        "secret",
        "outside",
        "shift",
        "align",
        "link",
        *_KEYWORDS,
    }
)


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
    blocks: list[Block] = []
    links: list[Link] = []
    seen: set[str] = set()
    for tokens, lineno in _statements(text):
        head = tokens[0]
        if not head.quoted and head.value.startswith("door"):
            # '<room> outside <side>' is an external door; '<a> <b>' an internal
            # one. Attributes ('open'/'secret') sit between the spec and the ids.
            outside_at = 2
            while len(tokens) > outside_at and _is_attr(tokens[outside_at - 1]):
                outside_at += 1
            if len(tokens) > outside_at and _is_bare(tokens[outside_at], "outside"):
                external_doors.append(_parse_external_door(tokens, lineno))
            else:
                doors.append(_parse_doorway(tokens, lineno))
            continue
        if _is_bare(head, "link"):
            links.append(_parse_link(tokens, lineno))
            continue
        if _is_bare(head, "block"):
            block = _parse_block(tokens, lineno)
            if block.id in seen:
                raise ParseError(f"duplicate id {block.id!r}", line=lineno)
            seen.add(block.id)
            blocks.append(block)
            continue
        room = _parse_room(tokens, lineno)
        if room.id in seen:
            raise ParseError(f"duplicate room id {room.id!r}", line=lineno)
        seen.add(room.id)
        rooms.append(room)
    return Building(rooms, doors, external_doors, blocks=blocks, links=links)


def _statements(text: str) -> list[tuple[list[Token], int]]:
    """Split source into logical statements: ``(tokens, starting line)`` pairs.

    A trailing backslash (the last non-whitespace character on a line, outside
    quotes and comments) joins the next physical line into the same statement.
    Blank and comment-only lines separate statements and cannot appear inside a
    continued one. Each token remembers its own physical line.
    """
    lines = text.splitlines()
    statements: list[tuple[list[Token], int]] = []
    index = 0
    while index < len(lines):
        lineno = index + 1
        tokens, continued = _tokenize(lines[index], lineno)
        index += 1
        while continued:
            if index >= len(lines):
                raise ParseError(
                    "unterminated line continuation at end of file", line=index
                )
            more, continued = _tokenize(lines[index], index + 1)
            if not more and not continued:
                raise ParseError(
                    "a continued statement cannot contain a blank or comment-only line",
                    line=index + 1,
                )
            tokens.extend(more)
            index += 1
        for token in tokens:
            if _is_bare(token, "\\"):
                raise ParseError(
                    "a continuation backslash must be the last thing on its line",
                    line=token.line,
                )
        if tokens:
            statements.append((tokens, lineno))
    return statements


def _validate_id(value: str, quoted: bool, lineno: int) -> None:
    """Check a token is a usable room id: bare, matching the pattern, not reserved."""
    if quoted or not _ID_RE.match(value):
        raise ParseError(f"invalid room id {value!r}", line=lineno)
    if value in _RESERVED:
        raise ParseError(f"{value!r} is a reserved word, not a room id", line=lineno)


def _validate_name(value: str, quoted: bool, lineno: int) -> None:
    """Check a room name: a required, double-quoted slot; ``""`` means no name."""
    if not quoted:
        raise ParseError(
            'room name must be in double quotes (use "" for no name)', line=lineno
        )
    if value == "":
        return  # empty quotes: no name
    if not 1 <= len(value) <= _MAX_NAME:
        raise ParseError(
            f"room name must be 1-{_MAX_NAME} characters, got {len(value)}",
            line=lineno,
        )
    if not value.strip():
        raise ParseError("room name cannot be blank", line=lineno)
    if value != value.strip():
        raise ParseError("room name cannot start or end with whitespace", line=lineno)
    if not value.isprintable():
        raise ParseError("room name has unprintable characters", line=lineno)


def _parse_glyph(tokens: list[Token], i: int) -> str:
    """Parse the quoted value after a bare ``glyph=`` token at index ``i``.

    ``glyph="12"`` tokenizes as a bare ``glyph=`` followed by a quoted value;
    ``""`` explicitly means *no* glyph (the room is unlabeled).
    """
    lineno = tokens[i].line
    if i + 1 >= len(tokens) or not tokens[i + 1].quoted:
        raise ParseError(
            'glyph= needs a double-quoted value (use glyph="" for none)', line=lineno
        )
    value = tokens[i + 1].value
    if value == "":
        return value  # empty quotes: explicitly unlabeled
    if len(value) > _MAX_GLYPH:
        raise ParseError(
            f"glyph must be 1-{_MAX_GLYPH} characters, got {len(value)}", line=lineno
        )
    if any(char.isspace() for char in value):
        raise ParseError("glyph cannot contain whitespace", line=lineno)
    if not value.isprintable():
        raise ParseError("glyph has unprintable characters", line=lineno)
    return value


def _parse_door_spec(tokens: list[Token], lineno: int) -> tuple[Door, list[Token]]:
    """Parse a statement's leading door token plus an optional bare attribute
    (``open``/``secret``).

    Returns the door spec and the remaining tokens after it.
    """
    spec = _parse_door(tokens[0].value, lineno)
    rest = tokens[1:]
    while rest and _is_attr(rest[0]):
        spec = _apply_door_attr(spec, rest[0])
        rest = rest[1:]
    return spec, rest


def _parse_doorway(tokens: list[Token], lineno: int) -> Doorway:
    """Parse a standalone ``door[=W][@O] [open] <a> <b>`` line."""
    spec, rest = _parse_door_spec(tokens, lineno)
    if len(rest) != 2:
        raise ParseError("a door needs exactly two room ids", line=lineno)
    for token in rest:
        _validate_id(token.value, token.quoted, token.line)
    a, b = rest[0].value, rest[1].value
    if a == b:
        raise ParseError("a door needs two different rooms", line=lineno)
    return Doorway(a=a, b=b, door=spec, line=lineno)


def _parse_external_door(tokens: list[Token], lineno: int) -> ExternalDoor:
    """Parse ``door[=W][@O] [open] <room> outside <side>`` (side = up/down/...)."""
    spec, rest = _parse_door_spec(tokens, lineno)
    if len(rest) != 3:
        raise ParseError("an external door needs '<room> outside <side>'", line=lineno)
    room, _outside, side = rest
    _validate_id(room.value, room.quoted, room.line)
    direction = _SIDES.get(side.value)
    if side.quoted or direction is None:
        raise ParseError(
            f"side must be up/down/left/right, got {side.value!r}", line=side.line
        )
    return ExternalDoor(room=room.value, side=direction, door=spec, line=lineno)


def _parse_block(tokens: list[Token], lineno: int) -> Block:
    """Parse a ``block <id> "<name>" [glyph=...] <member-id>...`` line.

    The id and name follow the same rules as a room's: the name slot is required
    but may be empty (``""``). A bare ``glyph=<member>`` picks which member the
    glyph is drawn in; a quoted ``glyph="<glyph>"`` sets the display glyph
    itself. Whether the members exist, the glyph target is one of them, and the
    union is contiguous are *semantic* checks left to layout.
    """
    if len(tokens) < 4:
        raise ParseError(
            'a block needs an id, a name (use "" for none), and a member',
            line=lineno,
        )
    block_id, id_quoted, id_line = tokens[1]
    _validate_id(block_id, id_quoted, id_line)

    name_value, name_quoted, name_line = tokens[2]
    _validate_name(name_value, name_quoted, name_line)
    name = name_value or None  # "" -> no name

    members: list[str] = []
    glyph_member: str | None = None
    glyph: str | None = None
    i = 3
    while i < len(tokens):
        value, quoted, line = tokens[i]
        if not quoted and value == "glyph=":
            glyph = _parse_glyph(tokens, i)
            i += 2
            continue
        if not quoted and value.startswith("glyph="):
            glyph_member = value[len("glyph=") :]
            _validate_id(glyph_member, False, line)
        else:
            _validate_id(value, quoted, line)
            members.append(value)
        i += 1
    if not members:
        raise ParseError("a block needs at least one member room", line=lineno)
    if len(members) != len(set(members)):
        raise ParseError("a block lists a member more than once", line=lineno)
    return Block(
        id=block_id,
        name=name,
        members=members,
        glyph_member=glyph_member,
        glyph=glyph,
        line=lineno,
    )


def _tokenize(raw: str, lineno: int) -> tuple[list[Token], bool]:
    """Split one source line into tokens, honouring quotes and ``#`` comments.

    A ``#`` outside quotes starts a comment to end of line; inside a quoted
    string it is literal. Each token is tagged with whether it was quoted and
    the line it sits on. Also reports whether the line ends in a continuation:
    a whitespace-separated ``\\`` as its last non-whitespace character (a ``\\``
    anywhere else survives as a token for the caller to reject).
    """
    tokens: list[Token] = []
    i, n = 0, len(raw)
    while i < n:
        char = raw[i]
        if char.isspace():
            i += 1
        elif char == "#":
            break
        elif char == "\\" and raw[i + 1 :].strip() == "":
            return tokens, True
        elif char == '"':
            j = i + 1
            while j < n and raw[j] != '"':
                j += 1
            if j >= n:
                raise ParseError("unterminated quote", line=lineno)
            tokens.append(Token(raw[i + 1 : j], True, lineno))
            i = j + 1
        else:
            j = i
            while j < n and not raw[j].isspace() and raw[j] not in '#"':
                j += 1
            tokens.append(Token(raw[i:j], False, lineno))
            i = j
    return tokens, False


def _parse_room(tokens: list[Token], lineno: int) -> Room:
    """Turn a tokenised ``room`` line into a :class:`~porta.model.Room`.

    The name slot is required but may be empty (``""``) for a room labelled only
    by its glyph and size.
    """
    if tokens[0].value != "room":
        raise ParseError(
            f"unknown directive {tokens[0].value!r}; expected 'room'", line=lineno
        )
    if len(tokens) < 4:
        raise ParseError(
            'a room needs an id, a name (use "" for none), and WxH dimensions',
            line=lineno,
        )

    room_id, id_quoted, id_line = tokens[1]
    _validate_id(room_id, id_quoted, id_line)

    name_value, name_quoted, name_line = tokens[2]
    _validate_name(name_value, name_quoted, name_line)
    name = name_value or None  # "" -> no name

    width, height, auto_width, auto_height = _parse_dimensions(
        tokens[3].value, tokens[3].line
    )
    is_root, glyph, relations = _parse_modifiers(tokens[4:])

    return Room(
        id=room_id,
        name=name,
        width=width,
        height=height,
        glyph=glyph,
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


def _parse_modifiers(tokens: list[Token]) -> tuple[bool, str | None, list[Relation]]:
    """Parse the trailing ``root``/``glyph=`` flags and relations (any order).

    Errors (and each relation's recorded line) point at the physical line of
    the token concerned, which may be a continuation line.
    """
    is_root = False
    glyph: str | None = None
    relations: list[Relation] = []
    i = 0
    while i < len(tokens):
        value, quoted, line = tokens[i]
        if quoted:
            raise ParseError(f"unexpected quoted value {value!r}", line=line)
        if value == "root":
            is_root = True
            i += 1
            continue
        if value == "glyph=":
            glyph = _parse_glyph(tokens, i)
            i += 2
            continue
        if value.startswith("glyph="):
            raise ParseError(
                f'a glyph must be double-quoted: glyph="{value[len("glyph=") :]}"',
                line=line,
            )
        if value in _DOOR_ATTRS:
            raise ParseError(f"{value!r} must immediately follow a door", line=line)
        if _KEYWORDS.get(value) is None:
            if value.startswith(_MODIFIERS):
                raise ParseError(f"{value!r} must follow a relation", line=line)
            raise ParseError(f"unknown relation or keyword {value!r}", line=line)
        relation, i = _parse_relation_at(tokens, i)
        relations.append(relation)
    return is_root, glyph, relations


def _parse_relation_at(tokens: list[Token], i: int) -> tuple[Relation, int]:
    """Parse ``<direction> <anchor> [modifiers...]`` at index ``i``.

    The caller guarantees ``tokens[i]`` is a relation keyword. Returns the
    relation and the index of the first token after it.
    """
    value, _, rel_line = tokens[i]
    direction = _KEYWORDS[value]
    if i + 1 >= len(tokens):
        raise ParseError(f"relation {value!r} needs an anchor room id", line=rel_line)
    anchor, anchor_quoted, anchor_line = tokens[i + 1]
    _validate_id(anchor, anchor_quoted, anchor_line)
    i += 2

    align = Align.START
    shift = 0
    door: Door | None = None
    no_door = False
    while (
        i < len(tokens)
        and not tokens[i].quoted
        and tokens[i].value.startswith(_MODIFIERS)
    ):
        token, _, token_line = tokens[i]
        if token.startswith("shift="):
            shift = _parse_shift(token, token_line)
        elif token.startswith("align="):
            align = _parse_align(token, token_line)
        elif token == "no-door":
            no_door = True
        else:
            door = _parse_door(token, token_line)
            while i + 1 < len(tokens) and _is_attr(tokens[i + 1]):
                door = _apply_door_attr(door, tokens[i + 1])
                i += 1
        i += 1

    if no_door and door is not None and (door.open or door.secret):
        kind = "an open" if door.open else "a secret"
        raise ParseError(
            f"cannot combine no-door with {kind} door on one relation",
            line=rel_line,
        )
    relation = Relation(
        direction=direction,
        anchor=anchor,
        line=rel_line,
        align=align,
        shift=shift,
        door=door,
        no_door=no_door,
    )
    return relation, i


def _parse_link(tokens: list[Token], lineno: int) -> Link:
    """Parse a ``link <room> <direction> <room> [modifiers...]`` line.

    The modifiers are exactly a relation's (``align=``/``shift=``/door
    handling). Whether the rooms exist and sit in different components are
    *semantic* checks left to layout.
    """
    if len(tokens) < 4:
        raise ParseError("a link needs '<room> <relation> <room>'", line=lineno)
    room, room_quoted, room_line = tokens[1]
    _validate_id(room, room_quoted, room_line)
    keyword = tokens[2]
    if keyword.quoted or keyword.value not in _KEYWORDS:
        raise ParseError(
            f"link relation must be up-of/down-of/left-of/right-of, "
            f"got {keyword.value!r}",
            line=keyword.line,
        )
    relation, after = _parse_relation_at(tokens, 2)
    if after != len(tokens):
        raise ParseError(
            f"unexpected {tokens[after].value!r} after the link",
            line=tokens[after].line,
        )
    if relation.anchor == room:
        raise ParseError("a link needs two different rooms", line=lineno)
    return Link(room=room, relation=relation, line=lineno)


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
