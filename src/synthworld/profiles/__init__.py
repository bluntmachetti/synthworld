"""Named world profiles.

The core generator in :mod:`synthworld.generator` is frozen: its artifacts and
checksums must not move, and its shape - ordinal-bearing identifiers, a path
graph, seeds that change values but not structure - is documented in the README as
a smoke surface rather than a transfer surface.

Realism therefore arrives as new profiles beside it, never as changes to it. A
profile emits the same :class:`synthworld.models.SynthWorld` schema, so every
downstream consumer keeps working, and nothing here reaches back into the core
generator.
"""

from __future__ import annotations

__all__: list[str] = []
