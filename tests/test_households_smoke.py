"""The frozen smoke fixture, and what freezing it is for.

The profile's other tests regenerate a world and assert properties of it, so they
move whenever the generator moves. A frozen artifact is the only check that fails
on *any* byte that shifts, including ones no property test happens to inspect.
"""

from __future__ import annotations

import hashlib
from importlib.resources import files

import pytest

from synthworld.profiles.realism import measure_realism, validate_realism
from synthworld.profiles.smoke import (
    SMOKE_CONFIG,
    SMOKE_SEED,
    HouseholdsSmokeIntegrityError,
    generate_smoke_world,
    load_golden_smoke_world,
    smoke_world_json,
)

_FROZEN_DIGEST = "dba52a49dbed6dadef9cace8b4a512121ae83abbea31ca77f5c12d15a6771bc4"


def test_the_frozen_artifact_matches_regeneration_byte_for_byte() -> None:
    artifact = (
        files("synthworld.benchmarks").joinpath("households-smoke-v1.json").read_bytes()
    )

    assert artifact == smoke_world_json().encode("utf-8")
    assert hashlib.sha256(artifact).hexdigest() == _FROZEN_DIGEST


def test_the_checksum_is_pinned_here_as_well_as_in_the_manifest() -> None:
    """Two independent records, so a regenerated manifest cannot bless a drift.

    Rewriting the artifact and its manifest together is a single edit; this
    constant is the second one that has to be changed deliberately.
    """

    manifest = (
        files("synthworld.benchmarks")
        .joinpath("HOUSEHOLDS_SMOKE_SHA256SUMS")
        .read_text(encoding="utf-8")
    )
    digest, name = manifest.strip().split()

    assert digest == _FROZEN_DIGEST
    assert name == "households-smoke-v1.json"


def test_the_loader_verifies_before_returning() -> None:
    world = load_golden_smoke_world()

    assert world == generate_smoke_world()
    assert len(world.personas) == SMOKE_CONFIG.person_count
    assert world.seed == SMOKE_SEED


def test_a_tampered_artifact_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from synthworld.profiles import smoke

    class _Tampered:
        def joinpath(self, name: str) -> _Tampered:
            self.name = name
            return self

        def read_bytes(self) -> bytes:
            return b'{"tampered": true}'

        def read_text(self, encoding: str) -> str:
            return f"{_FROZEN_DIGEST}  households-smoke-v1.json\n"

    monkeypatch.setattr(smoke, "files", lambda _package: _Tampered())

    with pytest.raises(HouseholdsSmokeIntegrityError, match="checksum differs"):
        smoke.load_golden_smoke_world()


def test_a_malformed_manifest_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from synthworld.profiles import smoke

    class _BadManifest:
        def joinpath(self, name: str) -> _BadManifest:
            return self

        def read_bytes(self) -> bytes:
            return b"{}"

        def read_text(self, encoding: str) -> str:
            return "not-a-manifest\n"

    monkeypatch.setattr(smoke, "files", lambda _package: _BadManifest())

    with pytest.raises(HouseholdsSmokeIntegrityError, match="manifest is invalid"):
        smoke.load_golden_smoke_world()


def test_the_frozen_world_still_meets_its_declared_minimums() -> None:
    """Freezing must not be a way to preserve a world that fails its own gate."""

    validate_realism(measure_realism(load_golden_smoke_world()), SMOKE_CONFIG.minimums)
