from __future__ import annotations

from synthworld.models import SynthWorld


def world_to_json(world: SynthWorld) -> str:
    """Serialize a world using stable model and field order."""

    return f"{world.model_dump_json(indent=2)}\n"
