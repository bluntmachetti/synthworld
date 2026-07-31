"""The realism report must describe the artifact, and the gate must bite."""

from __future__ import annotations

import pytest

from synthworld.profiles.households import (
    HouseholdsConfig,
    generate_households_benchmark,
    generate_households_world,
)
from synthworld.profiles.realism import (
    RealismError,
    RealismMinimums,
    measure_realism,
    validate_realism,
)

_SEEDS = (7, 11, 42)


@pytest.mark.parametrize("seed", _SEEDS)
def test_communities_break_up_the_giant_component(seed: int) -> None:
    """The gap #44 shipped with, and the reason communities exist.

    Membership drawn uniformly puts everyone who has any membership into one
    component. Issue #43 asks for weakly connected components of intermediate
    size, which means neither a giant nor only singletons.
    """

    report = measure_realism(generate_households_world(seed=seed))
    intermediate = [size for size in report.component_sizes if size > 1]

    assert report.component_count >= 4
    assert report.component_sizes[0] / report.person_count < 0.6
    assert len(intermediate) >= 3


def test_the_gate_rejects_a_world_that_misses_its_declared_shape() -> None:
    """One community reproduces the giant component, so the floor must refuse it.

    This is the test that keeps the gate from being decorative: it fails if the
    thresholds are ever loosened to whatever the generator happens to emit.
    """

    config = HouseholdsConfig(community_count=1)

    with pytest.raises(RealismError, match="largest component"):
        generate_households_benchmark(seed=42, config=config)


@pytest.mark.parametrize(
    ("minimums", "message"),
    [
        (RealismMinimums(min_component_count=10_000), "component_count"),
        (RealismMinimums(min_distinct_degrees=10_000), "distinct_degrees"),
        (RealismMinimums(min_household_sizes=10_000), "too few distinct addresses"),
    ],
)
def test_each_declared_floor_is_checked(
    minimums: RealismMinimums, message: str
) -> None:
    report = measure_realism(generate_households_world(seed=42))

    with pytest.raises(RealismError, match=message):
        validate_realism(report, minimums)


def test_a_leaking_field_fails_validation() -> None:
    """The core profile is the fixture: it leaks, so the gate must say so."""

    from synthworld.generator import generate_world

    report = measure_realism(generate_world(seed=42, persona_count=60))

    assert [item.field for item in report.leakage if item.verdict == "leaking"]
    with pytest.raises(RealismError, match="leak the generation index"):
        validate_realism(report, RealismMinimums())


def test_the_report_is_measured_from_the_artifact_not_the_configuration() -> None:
    """`measure_realism` takes only a world, so it structurally cannot echo config.

    Asking for a shape and reporting it back is the failure this guards: the check
    below asks for far more households than the world contains and shows that the
    measurement follows the artifact.
    """

    config = HouseholdsConfig(person_count=40, household_count=12, community_count=2)
    world = generate_households_world(seed=42, config=config)
    report = measure_realism(world)

    assert report.person_count == 40
    assert sum(report.household_sizes) == 40
    assert len(report.household_sizes) <= config.household_count + 40


@pytest.mark.parametrize("seed", _SEEDS)
def test_the_manifest_separates_identity_provenance_and_invariants(seed: int) -> None:
    manifest = generate_households_benchmark(seed=seed).manifest

    assert manifest.seed == seed
    assert manifest.config_digest == manifest.config.digest()
    assert manifest.python_version and manifest.platform
    assert manifest.realism.person_count == manifest.config.person_count
    assert manifest.realism.edge_count > 0


def test_the_manifest_replays_byte_identically_apart_from_provenance() -> None:
    """Identity and invariants are the artifact; provenance describes the host."""

    first = generate_households_benchmark(seed=42).manifest
    second = generate_households_benchmark(seed=42).manifest

    assert first.model_dump_json() == second.model_dump_json()
    assert (
        first.config_digest
        != generate_households_benchmark(
            seed=42, config=HouseholdsConfig(person_count=44)
        ).manifest.config_digest
    )


def test_an_empty_world_reports_without_dividing_by_zero() -> None:
    from synthworld.models import SynthWorld

    report = measure_realism(SynthWorld(seed=1, personas=(), relationships=()))

    assert report.person_count == 0
    assert report.component_sizes == ()
    with pytest.raises(RealismError, match="component_count"):
        validate_realism(report, RealismMinimums())


def test_leakage_can_be_declared_out_of_scope() -> None:
    """A profile may be measured for shape without gating on leakage.

    The core world leaks by design and is frozen, so a report on it is still
    useful; the gate is what a *new* profile opts into.
    """

    from synthworld.generator import generate_world

    report = measure_realism(generate_world(seed=42, persona_count=60))
    permissive = RealismMinimums(
        min_component_count=1,
        max_largest_component_fraction=1.0,
        min_distinct_degrees=1,
        require_no_leaking_field=False,
    )

    validate_realism(report, permissive)
