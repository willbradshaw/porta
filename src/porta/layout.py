"""Resolve relational placement into concrete geometry.

Topological DAG propagation: place the root at the origin, then derive every
other room's coordinates from an already-placed anchor's edge plus a relation.
Also owns the *semantic* validations (one root, no cycles, no disconnected
rooms, no overlap). Small, pure, unit-testable functions.

Stage 0: placeholder. The propagation engine lands in Stage 2.
"""

from __future__ import annotations
