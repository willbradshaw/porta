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
from porta.model import Building, Direction
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
        pytest.param("room r 20x20 root", id="name-missing"),
        # required pieces
        pytest.param('room r "R" root', id="dims-missing"),
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
    ],
)
def test_invalid_source_raises(source: str) -> None:
    with pytest.raises(ParseError):
        parse(source)


def test_duplicate_id_raises() -> None:
    with pytest.raises(ParseError):
        parse('room a "A" 10x10 root\nroom a "B" 10x10 right-of a')


def test_error_reports_the_offending_line_number() -> None:
    text = 'room a "A" 10x10 root\nroom b "B" 20x21 right-of a'
    with pytest.raises(ParseError) as exc:
        parse(text)
    assert exc.value.line == 2
