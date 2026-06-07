"""Stage 1: parser behaviour for the minimal .porta grammar.

Grammar under test::

    room <id> "<Name>" <W>x<H> [root] [<relation> ...]
    relation = (up-of | down-of | left-of | right-of) <anchor-id>

No align/gap/shift/type=/at-X,Y yet. Unknown-anchor references and missing /
duplicate roots are *layout* concerns (Stage 2), not syntax — so the parser
accepts them here.
"""

import textwrap

import pytest

from porta.errors import ParseError
from porta.model import Align, Building, Direction, Door
from porta.parser import parse

# Lines: 1 blank, 2 comment, 3 entrance, 4 kitchen, 5 hall.
MANOR = """
# manor.porta — feet, 5-ft grid, up = north
room entrance "Entrance Hall" 20x20 root
room kitchen  "Kitchen"       20x30 left-of entrance
room hall     "Great Hall"    40x30 up-of entrance right-of kitchen
"""


# --- structural extraction from a known-good file -------------------------


def test_parses_manor_into_three_ordered_rooms() -> None:
    building = parse(MANOR)
    assert isinstance(building, Building)
    assert [room.id for room in building.rooms] == ["entrance", "kitchen", "hall"]


def test_room_scalar_fields_are_captured() -> None:
    entrance = parse(MANOR).room("entrance")
    assert (entrance.name, entrance.width, entrance.height) == ("Entrance Hall", 20, 20)
    assert entrance.is_root is True
    assert entrance.relations == []


def test_empty_name_means_no_name() -> None:
    rooms = parse('room a "" 10x10 root\nroom b "B" 10x10 right-of a').rooms
    assert rooms[0].name is None
    assert rooms[1].name == "B"


def test_relations_are_captured_per_axis() -> None:
    hall = parse(MANOR).room("hall")
    assert hall.is_root is False
    assert {(rel.direction, rel.anchor) for rel in hall.relations} == {
        (Direction.UP, "entrance"),
        (Direction.RIGHT, "kitchen"),
    }


@pytest.mark.parametrize(
    ("room_id", "expected_line"),
    [("entrance", 3), ("kitchen", 4), ("hall", 5)],
)
def test_source_line_numbers_are_recorded(room_id: str, expected_line: int) -> None:
    assert parse(MANOR).room(room_id).line == expected_line


# a (line 1), comment (2), blank (3), b (line 4): numbering counts every line.
INTERLEAVED = 'room a "A" 10x10 root\n# note\n\nroom b "B" 10x10 right-of a'


@pytest.mark.parametrize(("room_id", "expected_line"), [("a", 1), ("b", 4)])
def test_line_numbers_advance_past_interior_comments_and_blanks(
    room_id: str, expected_line: int
) -> None:
    assert parse(INTERLEAVED).room(room_id).line == expected_line


# --- sources that should parse cleanly ------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        pytest.param('room a "A" 10x10 root', id="minimal-root"),
        pytest.param('room a "A" 10x10', id="no-root-no-relations-is-layout-concern"),
        pytest.param('room a "A" 10x10 up-of b', id="single-relation"),
        pytest.param('room a "A" 10x10 up-of b right-of c', id="two-axis-relations"),
        pytest.param('room a "A" 10x10 left-of b right-of c', id="same-axis-relations"),
        pytest.param('room a "Two Word Name" 10x10 root', id="multi-word-name"),
        pytest.param(
            'room store_room-2 "S" 10x10 root', id="id-with-hyphen-underscore"
        ),
        pytest.param('room a1 "S" 10x10 root', id="id-with-trailing-digit"),
        pytest.param('room a "A" 100x205 root', id="larger-grid-dims"),
        pytest.param('room   a    "A"    10x10    root', id="irregular-whitespace"),
        pytest.param('room a "A" 10x10 root  # trailing comment', id="inline-comment"),
        pytest.param('room a "A" 10x10 up-of nonesuch', id="unknown-anchor-deferred"),
        pytest.param('room a "" 10x10 root', id="empty-name"),
        pytest.param('room a "" 10x10 up-of b', id="empty-name-with-relation"),
    ],
)
def test_valid_source_parses_without_error(source: str) -> None:
    assert isinstance(parse(source), Building)


def test_comments_and_blank_lines_are_ignored() -> None:
    text = textwrap.dedent("""
        room a "A" 10x10 root   # trailing inline comment
        # a full-line comment

        room b "B" 10x10 right-of a
    """)
    assert [room.id for room in parse(text).rooms] == ["a", "b"]


def test_hash_inside_quotes_is_literal_not_a_comment() -> None:
    # '#' only starts a comment outside quotes; inside a name it is literal.
    assert parse('room study "Room #3" 10x10 root').room("study").name == "Room #3"


@pytest.mark.parametrize(
    ("dims", "expected"),
    [
        # (width, height, auto_width, auto_height); auto sides hold 0.
        ("20x10", (20, 10, False, False)),
        ("?x10", (0, 10, True, False)),
        ("20x?", (20, 0, False, True)),
        ("?x?", (0, 0, True, True)),
    ],
)
def test_auto_dimensions_are_parsed(
    dims: str, expected: tuple[int, int, bool, bool]
) -> None:
    room = parse(f'room b "B" {dims} right-of a').room("b")
    assert (room.width, room.height, room.auto_width, room.auto_height) == expected


def test_root_and_relations_accepted_in_any_order() -> None:
    def rels(source: str) -> set[tuple[Direction, str]]:
        room = parse(source).room("h")
        return {(r.direction, r.anchor) for r in room.relations}

    assert rels('room h "H" 10x10 up-of x right-of y') == rels(
        'room h "H" 10x10 right-of y up-of x'
    )
    assert parse('room h "H" 10x10 up-of x root').room("h").is_root is True


@pytest.mark.parametrize(
    ("keyword", "direction"),
    [
        ("up-of", Direction.UP),
        ("down-of", Direction.DOWN),
        ("left-of", Direction.LEFT),
        ("right-of", Direction.RIGHT),
    ],
)
def test_each_relation_keyword_maps_to_its_direction(
    keyword: str, direction: Direction
) -> None:
    room = parse(f'room h "H" 10x10 {keyword} anchor').room("h")
    assert room.relations[0].direction is direction
    assert room.relations[0].anchor == "anchor"


# --- sources that should raise ParseError ---------------------------------


@pytest.mark.parametrize(
    "source",
    [
        # dimensions
        pytest.param('room r "R" 20', id="dim-no-x"),
        pytest.param('room r "R" ?x7 right-of a', id="dim-auto-with-off-grid"),
        pytest.param('room r "R" 20x', id="dim-missing-height"),
        pytest.param('room r "R" x20', id="dim-missing-width"),
        pytest.param('room r "R" xx', id="dim-no-numbers"),
        pytest.param('room r "R" 20x20x20', id="dim-three-parts"),
        pytest.param('room r "R" 21x20', id="dim-width-off-grid"),
        pytest.param('room r "R" 20x21', id="dim-height-off-grid"),
        pytest.param('room r "R" 0x20', id="dim-zero-width"),
        pytest.param('room r "R" 20x0', id="dim-zero-height"),
        pytest.param('room r "R" -5x20', id="dim-negative-width"),
        pytest.param('room r "R" 20x-5', id="dim-negative-height"),
        pytest.param('room r "R" 2.5x20', id="dim-non-integer"),
        pytest.param('room r "R" axb', id="dim-non-numeric"),
        pytest.param('room r "R" 20by20', id="dim-wrong-separator"),
        # name
        pytest.param('room r "Kitchen 20x20 root', id="name-unterminated-quote"),
        # required pieces
        pytest.param('room r "R" root', id="dims-missing"),
        # name slot is required (use "" for none)
        pytest.param("room r 20x20 root", id="name-slot-unquoted"),
        pytest.param("room r 20x20", id="name-slot-and-relations-missing"),
        pytest.param("room", id="bare-room-keyword"),
        pytest.param('room "R" 20x20 root', id="id-missing"),
        # keywords / relations
        pytest.param('zone r "R" 20x20 root', id="unknown-leading-keyword"),
        pytest.param('room r "R" 20x20 north-of x', id="compass-not-supported"),
        pytest.param('room r "R" 20x20 uppof x', id="misspelled-relation"),
        pytest.param('room r "R" 20x20 up-of', id="relation-missing-anchor"),
        # ids
        pytest.param('room 2nd "Second" 10x10 root', id="id-starts-with-digit"),
        pytest.param('room r! "R" 10x10 root', id="id-illegal-char"),
        # shift modifier
        pytest.param('room r "R" 20x20 shift=10', id="shift-without-relation"),
        pytest.param('room r "R" 20x20 root shift=10', id="shift-after-root"),
        pytest.param('room r "R" 20x20 up-of a shift=7', id="shift-off-grid"),
        pytest.param('room r "R" 20x20 up-of a shift=x', id="shift-non-integer"),
        # align modifier
        pytest.param('room r "R" 20x20 align=end', id="align-without-relation"),
        pytest.param('room r "R" 20x20 up-of a align=center', id="align-center"),
        pytest.param('room r "R" 20x20 up-of a align=bogus', id="align-bogus"),
        # door modifier
        pytest.param('room r "R" 20x20 door', id="door-without-relation"),
        pytest.param('room r "R" 20x20 up-of a door=7', id="door-width-off-grid"),
        pytest.param('room r "R" 20x20 up-of a door@7', id="door-offset-off-grid"),
        pytest.param('room r "R" 20x20 up-of a door=0', id="door-zero-width"),
        pytest.param('room r "R" 20x20 up-of a doorx', id="door-malformed"),
        pytest.param('room r "R" 20x20 no-door', id="no-door-without-relation"),
        # standalone door statement
        pytest.param("door a", id="standalone-door-one-id"),
        pytest.param("door a b c", id="standalone-door-three-ids"),
        pytest.param("door a a", id="standalone-door-self"),
        pytest.param('door a "B"', id="standalone-door-quoted-id"),
        # external door statement
        pytest.param("door a outside", id="external-door-missing-side"),
        pytest.param("door a outside sideways", id="external-door-bad-side"),
        pytest.param("door a outside down extra", id="external-door-too-many"),
    ],
)
def test_invalid_source_raises(source: str) -> None:
    with pytest.raises(ParseError):
        parse(source)


def test_uppercase_id_is_rejected() -> None:
    # Ids are lowercase only (the name carries any display capitalisation).
    with pytest.raises(ParseError):
        parse('room Hall "Hall" 10x10 root')


@pytest.mark.parametrize(
    "word",
    [
        "root",
        "door",
        "no-door",
        "outside",
        "shift",
        "align",
        "up-of",
        "down-of",
        "left-of",
        "right-of",
    ],
)
def test_reserved_word_is_not_a_valid_id(word: str) -> None:
    with pytest.raises(ParseError):
        parse(f'room {word} "X" 10x10 root')


def test_reserved_word_is_not_a_valid_anchor() -> None:
    with pytest.raises(ParseError):
        parse('room a "A" 10x10 root\nroom b "B" 10x10 right-of shift')


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("   ", id="blank"),
        pytest.param("A\tB", id="unprintable-tab"),
        pytest.param("x" * 41, id="too-long"),
        pytest.param(" Hall", id="leading-space"),
        pytest.param("Hall ", id="trailing-space"),
    ],
)
def test_invalid_room_name_raises(name: str) -> None:
    with pytest.raises(ParseError):
        parse(f'room a "{name}" 10x10 root')


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("Café", id="accented"),
        pytest.param("x" * 40, id="max-length"),
        pytest.param("Great Hall", id="with-space"),
    ],
)
def test_valid_room_name_accepted(name: str) -> None:
    assert parse(f'room a "{name}" 10x10 root').room("a").name == name


def test_duplicate_id_raises() -> None:
    with pytest.raises(ParseError):
        parse('room a "A" 10x10 root\nroom a "B" 10x10 right-of a')


def test_error_reports_the_offending_line_number() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 20x21 right-of a'
    with pytest.raises(ParseError) as exc:
        parse(text)
    assert exc.value.line == 2


@pytest.mark.parametrize(
    ("source", "expected_shift"),
    [
        ('room b "B" 10x10 up-of a', 0),  # default
        ('room b "B" 10x10 up-of a shift=10', 10),
        ('room b "B" 10x10 up-of a shift=-5', -5),
        ('room b "B" 10x10 up-of a shift=0', 0),
    ],
)
def test_shift_is_parsed_onto_the_relation(source: str, expected_shift: int) -> None:
    assert parse(source).room("b").relations[0].shift == expected_shift


@pytest.mark.parametrize(
    ("source", "expected_align"),
    [
        ('room b "B" 10x10 up-of a', Align.START),  # default
        ('room b "B" 10x10 up-of a align=start', Align.START),
        ('room b "B" 10x10 up-of a align=end', Align.END),
    ],
)
def test_align_is_parsed_onto_the_relation(source: str, expected_align: Align) -> None:
    assert parse(source).room("b").relations[0].align == expected_align


@pytest.mark.parametrize(
    ("source", "expected_door"),
    [
        ('room b "B" 10x10 up-of a', None),  # no door
        ('room b "B" 10x10 up-of a door', Door(width=5, offset=None)),
        ('room b "B" 10x10 up-of a door=10', Door(width=10, offset=None)),
        ('room b "B" 10x10 up-of a door@10', Door(width=5, offset=10)),
        ('room b "B" 10x10 up-of a door=10@15', Door(width=10, offset=15)),
    ],
)
def test_door_is_parsed_onto_the_relation(
    source: str, expected_door: Door | None
) -> None:
    assert parse(source).room("b").relations[0].door == expected_door


def test_no_door_is_parsed_onto_the_relation() -> None:
    assert parse('room b "B" 10x10 up-of a no-door').room("b").relations[0].no_door
    assert not parse('room b "B" 10x10 up-of a').room("b").relations[0].no_door


def test_standalone_door_is_parsed() -> None:
    building = parse('room a "A" 10x10 root\nroom b "B" 10x10 right-of a\ndoor a b')
    assert len(building.doors) == 1
    doorway = building.doors[0]
    assert (doorway.a, doorway.b) == ("a", "b")
    assert doorway.door == Door(width=5, offset=None)


def test_standalone_door_carries_width_and_offset() -> None:
    building = parse(
        'room a "A" 10x10 root\nroom b "B" 10x10 right-of a\ndoor=10@5 a b'
    )
    assert building.doors[0].door == Door(width=10, offset=5)


def test_external_door_is_parsed() -> None:
    building = parse('room a "A" 20x20 root\ndoor a outside down')
    assert len(building.external_doors) == 1
    ext = building.external_doors[0]
    assert (ext.room, ext.side, ext.door) == ("a", Direction.DOWN, Door(5, None))


def test_external_door_carries_side_and_spec() -> None:
    building = parse('room a "A" 20x20 root\ndoor=10@5 a outside left')
    ext = building.external_doors[0]
    assert (ext.room, ext.side, ext.door) == ("a", Direction.LEFT, Door(10, 5))


# --- block statements ------------------------------------------------------


def test_block_is_parsed() -> None:
    building = parse(
        'room a "" 10x10 root\nroom b "" 10x10 right-of a\nblock hall "Great Hall" a b'
    )
    assert len(building.blocks) == 1
    block = building.blocks[0]
    assert (block.id, block.name, block.members) == ("hall", "Great Hall", ["a", "b"])
    assert block.glyph_member is None


def test_block_name_is_optional() -> None:
    block = parse('room a "" 10x10 root\nblock hall a').blocks[0]
    assert block.name is None
    assert block.members == ["a"]


def test_block_glyph_member_is_parsed() -> None:
    source = (
        'room a "" 10x10 root\nroom b "" 10x10 right-of a\nblock hall "H" a b glyph=b'
    )
    block = parse(source).blocks[0]
    assert block.glyph_member == "b"
    assert block.members == ["a", "b"]


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("block hall", id="block-no-members"),
        pytest.param('block hall "H"', id="block-name-no-members"),
        pytest.param("block hall a a", id="block-duplicate-member"),
        pytest.param('block hall a "b"', id="block-quoted-member"),
        pytest.param("block Hall a", id="block-uppercase-id"),
        pytest.param("block root a", id="block-reserved-id"),
    ],
)
def test_invalid_block_raises(source: str) -> None:
    with pytest.raises(ParseError):
        parse(source)


def test_block_id_colliding_with_a_room_raises() -> None:
    with pytest.raises(ParseError):
        parse('room a "" 10x10 root\nblock a a')
