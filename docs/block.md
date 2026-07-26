# Blocks

A **block** joins several [rooms](room.md) into a single space, suppressing
walls and doors between them. They are most commonly used to create non-rectangular
spaces in the rendered SVG map:

```porta img/block-l.svg
room main "" 40x30 root
room wing "" 20x20 down-of main
room annexe "" 10x10 down-of main align=end
block hall "Great Hall" main wing annexe
```

<img alt="An L-shaped room built from two rectangles" src="img/block-l.svg" width="70%">

The combined space is visualized in the SVG map as a single room, with a
single glyph and key entry determined by the `block` statement. Relations
with other spaces in the map (adjacency, doors, etc) are handled at the room
level.

## The `block` statement

```
block <id> "<name>" [glyph="<glyph>"] [glyph=<member-id>] <member-id>...
```

- **`<id>`**: the block's own ID; its first letter is the union's default
  glyph. Same rules as a [room ID](room.md#room-id), in the same namespace
  (unique across all rooms and blocks).
- **`"<name>"`**: labels the union in the key, with the same rules as a
  [room name](room.md#room-name). As for a room, the slot is **required** but
  may be empty (`""`); an empty name keys the union by its glyph alone.
- **`glyph="<glyph>"`** (quoted): optional; an explicit
  [display glyph](room.md#glyphs) for the union, with the same rules as a
  room's — including `glyph=""` for an unlabeled block with no key entry.
- **`glyph=<member-id>`** (bare): optional; which member the glyph is drawn in
  (default: the first member listed). If present, must match a specified member
  room ID.
- **`<member-id>...`**: one or more member rooms, specified by [ID](room.md#room-id).
  Each ID must correspond to a room declared elsewhere in the plan, and specified
  rooms must be **contiguous**: each must be adjacent to at least one other room
  in the block. Adjacency is determined from the solved floorplan; two adjacent
  rooms can share a block even if neither is anchored to the other.

## Member rooms

The member rooms included in a block are ordinary
[`room` statements](room.md#the-room-statement), with all the features that
implies: relations, `align`/`shift`, `?` auto-dimensions, doors, etc.
When a group of rooms are combined into a block, the walls and doors
between those rooms are suppressed, but walls and doors on the outer edge
of the block persist:

```porta img/block-neighbour.svg
room main  ""      40x30 root
room wing  ""      20x20 down-of main
room study "Study" 20x20 right-of main
room chapel "Chapel" 20x20 right-of wing
door main outside up
door wing outside left
block hall "Great Hall" main wing
```

<img alt="An L-shaped hall with a neighbouring study and chapel" src="img/block-neighbour.svg" width="70%">

Names and [glyphs](room.md#glyphs) given to individual member rooms are
suppressed in the SVG map; the block is labeled with the glyph and name
specified in the `block` statement. Consequently, names of member rooms are
typically empty (`""`); nonempty member names — and explicit member glyphs —
are permitted but will raise a warning. Similarly, explicit
[door declarations](door.md#door-declarations) and [statements](door.md#the-door-statement)
targeting doors on walls within the block will raise a warning that they have
been dropped.

## Invalid blocks

`porta` rejects a block it can't form:

- A member ID that isn't a room.
- A room listed in more than one block.
- A `glyph=` target that isn't one of the members.
- Members that don't form a single contiguous region.

## Putting it together

```porta img/block-capstone.svg
room back  ""      60x20 root
room west  ""      20x30 down-of back
room east  ""      20x30 down-of back align=end
room study "Study" 20x20 right-of back align=end
room annexe "Annexe" 20x10 right-of west left-of east
block hall "Great Hall" back west east
door west outside down
door=10 back outside up
```

<img alt="A U-shaped great hall with a study off one end" src="img/block-capstone.svg" width="70%">
