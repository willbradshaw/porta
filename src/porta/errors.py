"""Error types for porta.

A small hierarchy rooted at :class:`PortaError` so the CLI can draw a clean
boundary between *bad user input* (caught and rendered as a tidy diagnostic
with a line number) and genuine bugs in porta (which should propagate as
tracebacks). Each error carries the source line it concerns.
"""


class PortaError(Exception):
    """Base class for all errors that represent invalid ``.porta`` input."""

    def __init__(self, message: str, *, line: int | None = None) -> None:
        """Initialise the error.

        Args:
            message: Human-readable description of the problem.
            line: 1-based source line the problem concerns, if any. Some
                building-level layout errors (e.g. "no root") have no single
                line and leave this ``None``.
        """
        super().__init__(message)
        self.message = message
        self.line = line


class ParseError(PortaError):
    """A syntax error in ``.porta`` source (wrong shape, bad token, bad value)."""


class LayoutError(PortaError):
    """A semantic error found while resolving placement.

    Raised for structural problems the parser cannot see: no root or several
    roots, references to unknown rooms, dependency cycles, disconnected rooms,
    and (for now) constructs not yet supported by the layout engine.
    """


class OverlapError(LayoutError):
    """Two solved rooms occupy overlapping space.

    Carries the colliding room ids and the overlap rectangle structurally, so
    the CLI can render the diagnostic without parsing the message.
    """

    def __init__(self, rooms: tuple[str, str], rect: tuple[int, int, int, int]) -> None:
        """Initialise the error.

        Args:
            rooms: The ids of the two overlapping rooms (in source order).
            rect: The overlap rectangle as ``(x, y, width, height)`` in feet.
        """
        a, b = rooms
        x, y, w, h = rect
        super().__init__(
            f"rooms {a!r} and {b!r} overlap on a {w}x{h} area at ({x}, {y})"
        )
        self.rooms = rooms
        self.rect = rect
