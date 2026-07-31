"""The frozen households smoke fixture.

Issue #43 asks for "a small frozen/checksummed smoke configuration suitable for
CI". Frozen matters for a reason the generated tiers do not cover: the profile's
own tests regenerate a world and assert properties of it, so they move whenever the
generator moves. A frozen artifact is the only thing that can tell you the
generator changed *at all* - it fails on any byte that shifts, including ones no
property test happens to look at.

The configuration is deliberately small: it has to run in CI on every commit, and a
reviewer should be able to read the whole world.
"""

from __future__ import annotations

import hashlib
from importlib.resources import files

from synthworld.models import SynthWorld
from synthworld.profiles.households import (
    HouseholdsConfig,
    canonical_world_json,
    generate_households_benchmark,
)
from synthworld.profiles.realism import RealismMinimums

_WORLD_FILENAME = "households-smoke-v1.json"
_MANIFEST_FILENAME = "HOUSEHOLDS_SMOKE_SHA256SUMS"

#: Small enough to read, large enough to exercise communities, households, teams,
#: cohorts and isolated controls. Frozen with the artifact: changing it changes the
#: fixture, which is the point of pinning it here rather than in a caller.
SMOKE_CONFIG = HouseholdsConfig(
    person_count=24,
    household_count=8,
    workplace_count=4,
    school_count=4,
    isolated_person_count=3,
    colleagues_per_person=2,
    community_count=2,
    minimums=RealismMinimums(
        min_component_count=3,
        max_largest_component_fraction=0.75,
        min_distinct_degrees=3,
        min_household_sizes=2,
    ),
)
SMOKE_SEED = 20_260_731


class HouseholdsSmokeIntegrityError(ValueError):
    """Raised when the frozen smoke artifact fails its integrity gate."""


def generate_smoke_world() -> SynthWorld:
    """Regenerate the smoke world from its pinned seed and configuration."""

    return generate_households_benchmark(seed=SMOKE_SEED, config=SMOKE_CONFIG).world


def smoke_world_json() -> str:
    """The exact serialization the frozen artifact holds."""

    return f"{canonical_world_json(generate_smoke_world())}\n"


def load_golden_smoke_world() -> SynthWorld:
    """Load the frozen smoke world, verifying its checksum first."""

    directory = files("synthworld.benchmarks")
    artifact = directory.joinpath(_WORLD_FILENAME).read_bytes()
    manifest = directory.joinpath(_MANIFEST_FILENAME).read_text(encoding="utf-8")
    fields = manifest.strip().split()
    if len(fields) != 2 or fields[1] != _WORLD_FILENAME:
        raise HouseholdsSmokeIntegrityError("frozen smoke manifest is invalid")
    if hashlib.sha256(artifact).hexdigest() != fields[0]:
        raise HouseholdsSmokeIntegrityError("frozen smoke artifact checksum differs")
    return SynthWorld.model_validate_json(artifact)


__all__ = [
    "SMOKE_CONFIG",
    "SMOKE_SEED",
    "HouseholdsSmokeIntegrityError",
    "generate_smoke_world",
    "load_golden_smoke_world",
    "smoke_world_json",
]
