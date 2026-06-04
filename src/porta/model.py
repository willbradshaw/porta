"""Data model for porta.

Plain dataclasses passed between the parser, layout engine, and renderers.
These carry no behaviour beyond holding parsed/solved state. See
``docs/design.md`` for the placement model these structures encode.

Stage 0: placeholder. The real dataclasses (``Room``, ``Relation``,
``Building``) land in Stage 1.
"""

from __future__ import annotations
