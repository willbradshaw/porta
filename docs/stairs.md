# Stairs

A **stairs** statement draws a flight of stairs inside a [room](room.md),
recording whether it leads up off this floor, down off it, or between two
levels within the floor:

```porta img/stairs.svg
room landing "Landing" 20x20 root
stairs up landing down=right at=0,0 to=level-1.hall
stairs down landing down=right at=10,15 to=level-3.entry
```

<img alt="A landing with one flight up and one flight down" src="img/stairs.svg" width="70%">

## The `stairs` statement

```
stairs <sense> <room> down=<side> [size=<WxH>] [at=<X,Y>] [to=<label>]
sense = up | down | in
side  = up | down | left | right
```

- **`<sense>`**: where the flight leads — `up` (to the floor above), `down`
  (to the floor below), or `in` (a level change within this floor, such as
  steps up to a dais).
- **`<room>`**: the room the stairs are drawn in, by [ID](room.md#room-id).
  A room may contain any number of stairs. Naming a
  [block](block.md) member places the flight in that member.
- **`down=<side>`** (required): the plan direction that leads *downward* on
  the flight — the direction the rendered arrow points.
- **`size=<WxH>`**: the footprint in feet (grid multiples). Defaults to one
  grid square across the run and two along it (`10x5` for a horizontal run,
  `5x10` for a vertical one).
- **`at=<X,Y>`**: the footprint's top-left corner in feet from the room's
  own top-left (NW) corner, on the grid. Defaults to centred in the room
  (rounded down to the grid).
- **`to=<label>`**: an optional destination recorded verbatim in the model
  (e.g. `to=level-2.entry`). Nothing is solved or rendered from it — it is
  bookkeeping for multi-floor plans.

## Reading the symbol

The arrow always points down the flight. The open (undrawn) sides are the
entrances, and they distinguish the three senses:

```porta img/stairs-senses.svg
room going-up "Stairs Up" 20x20 root
room going-down "Stairs Down" 20x20 root
room within "Steps Within" 20x20 root
stairs up going-up down=down
stairs down going-down down=down
stairs in within down=down
```

<img alt="The three stair senses side by side" src="img/stairs-senses.svg" width="70%">

- **`up`** opens on the side the arrow points toward: you enter at the
  bottom of the flight and climb away off the floor. Stepping *down* the
  arrow returns you to this floor.
- **`down`** opens on the side behind the arrow: you enter at the top and
  descend away off the floor.
- **`in`** opens at both ends — both the upper and lower levels are on this
  floor, and only the flanks are walled.

## Invalid stairs

`porta` rejects stairs it can't place:

- A room ID that isn't a room.
- A footprint (default or explicit) that does not fit inside the room.
- Two stair footprints that overlap.
- An off-grid `size=` or `at=`, or a missing `down=`.
- An inaccessible flight: an entrance flush with a stretch of wall that has
  no door on it. (A flight whose *closed* far side sits on a wall is fine —
  the run continues past it on another level — and so is an entrance
  covered by a door, like a stair closet entered from the next room.)

## Putting it together

```porta img/stairs-capstone.svg
room hall "Great Hall" 50x30 root
room tower "Tower" 20x20 right-of hall
stairs in hall down=left size=5x20 at=35,5
stairs up tower down=up at=10,5 to=battlements
stairs down tower down=down at=0,5 to=undercroft
```

<img alt="A hall with dais steps and a stair tower going both up and down" src="img/stairs-capstone.svg" width="70%">
