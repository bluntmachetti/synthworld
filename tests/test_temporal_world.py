"""What the temporal slice has to prove: no future leaks backwards, and time replays."""

from __future__ import annotations

import os
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.temporal import (
    ListingAttribute,
    ListingAttributeKind,
    ListingTruth,
    ObservationTruth,
    ObservationValidity,
    PrivacyEvent,
    PrivacyEventKind,
    PublicListingRecord,
    PublicTimeline,
    TemporalTruth,
    TemporalWorld,
    lifecycle_stage,
    materialise,
    rescan_ticks,
)
from synthworld.temporal_generator import (
    TEMPORAL_BASELINE_SEED,
    TEMPORAL_CASE_NAMES,
    TEMPORAL_HORIZON,
    _distinct_slots,
    generate_temporal_world,
)

_SEEDS = (1, 7, 42, TEMPORAL_BASELINE_SEED)


def test_a_materialised_view_cannot_contain_the_future() -> None:
    """The guarantee the whole slice rests on, checked at every tick of every seed.

    Not "the filter is correct" but "the result is built from the surviving events",
    which is why `materialise` takes the world and returns a new object rather than
    hiding fields on one that already holds everything.
    """

    for seed in _SEEDS:
        world = generate_temporal_world(seed=seed)
        for tick in range(world.horizon + 1):
            timeline = materialise(world, as_of=tick)

            assert timeline.as_of == tick
            assert all(item.tick <= tick for item in timeline.events)
            expected = [item for item in world.events if item.tick <= tick]
            assert list(timeline.events) == expected


def test_asking_for_an_earlier_tick_is_not_contaminated_by_a_later_one() -> None:
    """Order of questions must not change answers, or replay proves nothing."""

    world = generate_temporal_world(seed=3)
    forwards = [materialise(world, as_of=tick) for tick in range(world.horizon + 1)]
    backwards = [
        materialise(world, as_of=tick) for tick in reversed(range(world.horizon + 1))
    ]

    assert forwards == list(reversed(backwards))


def test_no_public_timeline_reveals_an_outcome() -> None:
    """A confirmed removal looks identical whether or not it really happened.

    `clean_removal` and `phantom_removal` run the same four events at the same ticks;
    only the evaluator knows one of them is a lie. If the public timeline could tell
    them apart, the hardest case in the pack would be free.
    """

    world = generate_temporal_world(seed=11)
    timeline = materialise(world, as_of=world.horizon)
    truth = {item.listing_ref: item for item in world.truth.listings}

    shapes: dict[tuple[tuple[int, str], ...], set[bool]] = {}
    for listing in truth.values():
        events = tuple(
            (item.tick, item.kind.value)
            for item in timeline.events
            if item.object_ref == listing.listing_ref
        )
        shapes.setdefault(events, set()).add(listing.removed_at is not None)

    # At least one public shape must carry both outcomes, or the events decide it.
    assert any(len(outcomes) > 1 for outcomes in shapes.values())


@pytest.mark.parametrize("seed", _SEEDS)
def test_the_same_seed_replays_byte_identically(seed: int) -> None:
    first = generate_temporal_world(seed=seed)
    second = generate_temporal_world(seed=seed)

    assert first.model_dump_json() == second.model_dump_json()


def test_bytes_do_not_depend_on_python_hash_iteration() -> None:
    """Set and dict iteration order has broken determinism in this repo before."""

    project_root = Path(__file__).parents[1]
    script = (
        "from synthworld.temporal_generator import generate_temporal_world; "
        "print(generate_temporal_world(seed=5).model_dump_json())"
    )
    outputs = set()
    for hash_seed in ("0", "1", "12345"):
        environment = {**os.environ, "PYTHONHASHSEED": hash_seed}
        result = subprocess.run(  # noqa: S603
            [sys.executable, "-c", script],
            capture_output=True,
            check=True,
            cwd=project_root,
            env=environment,
            text=True,
        )
        outputs.add(result.stdout)

    assert len(outputs) == 1


def test_seeds_move_surfaces_and_spacing_without_inventing_cases() -> None:
    """Different seeds, same seven cases: the fixture is authored, not sampled."""

    signatures = set()
    for seed in _SEEDS:
        world = generate_temporal_world(seed=seed)
        assert len(world.truth.listings) == len(TEMPORAL_CASE_NAMES)
        signatures.add(
            (
                tuple(item.listing_ref for item in world.truth.listings),
                rescan_ticks(world),
            )
        )
        # The kinds present never change; only when and to what they happen.
        kinds = Counter(item.kind for item in world.events)
        assert kinds[PrivacyEventKind.LISTING_DISCOVERED] == len(TEMPORAL_CASE_NAMES)

    assert len(signatures) == len(_SEEDS)


def test_an_identifier_does_not_reveal_which_case_it_belongs_to() -> None:
    """Names like `listing-clean_removal` are the mistake the ambiguity pack shipped."""

    world = generate_temporal_world(seed=13)
    references = {item.listing_ref for item in world.truth.listings}
    references |= {item.observation_ref for item in world.truth.observations}
    references |= {item.id for item in world.events}
    references |= {item.subject_ref for item in world.events}
    references |= {item.object_ref for item in world.events if item.object_ref}

    # Checked against references rather than the whole payload: `removal_refused` is a
    # public event *kind* and legitimately contains the case name "refused". The
    # question is whether an opaque identifier spells its case, not whether a
    # vocabulary word appears somewhere in the JSON.
    for name in TEMPORAL_CASE_NAMES:
        assert not any(name in reference for reference in references)

    # And the references must move with the seed, or one reading transfers to all.
    others = {
        item.listing_ref
        for seed in (14, 15)
        for item in generate_temporal_world(seed=seed).truth.listings
    }
    assert not {item.listing_ref for item in world.truth.listings} & others


def test_rescan_ticks_are_published_so_the_task_is_answerable() -> None:
    """A task whose scope lives only in the answer key forces the oracle open.

    Issue #50 shipped exactly that defect: 435 possible pairs, fifteen wanted, and the
    list only in the answer key.
    """

    world = generate_temporal_world(seed=17)
    ticks = rescan_ticks(world)
    timeline = materialise(world, as_of=world.horizon)

    assert ticks
    assert ticks == tuple(
        sorted(
            {
                item.tick
                for item in timeline.events
                if item.kind is PrivacyEventKind.RESCAN
            }
        )
    )


def test_lifecycle_stage_reads_only_public_events() -> None:
    world = generate_temporal_world(seed=19)
    timeline = materialise(world, as_of=world.horizon)
    listing = world.truth.listings[0].listing_ref

    assert lifecycle_stage(timeline.events, listing) is not None
    assert lifecycle_stage(timeline.events, "listing-does-not-exist") is None


def test_a_stale_observation_is_separable_from_a_wrong_one() -> None:
    """The distinction issue #5 needs, and the reason validity is its own field."""

    world = generate_temporal_world(seed=23)
    stale = [
        item
        for item in world.truth.observations
        if item.validity is ObservationValidity.VALID_WHEN_OBSERVED and not item.current
    ]

    assert stale
    assert all(item.superseded_by is not None for item in stale)


def test_an_impossible_history_is_refused() -> None:
    """Replay must reject worlds that cannot exist, not score systems against them."""

    world = generate_temporal_world(seed=29)
    subject = world.events[0].subject_ref
    orphan = PrivacyEvent(
        id="evt-orphan",
        tick=0,
        kind=PrivacyEventKind.REMOVAL_CONFIRMED,
        subject_ref=subject,
        object_ref="listing-unknown",
    )

    with pytest.raises(ValidationError, match="no preceding"):
        TemporalWorld(
            seed=world.seed,
            horizon=world.horizon,
            events=(orphan,),
            listings=world.listings,
            truth=world.truth,
        )


def test_a_repeated_request_and_a_conflicting_status_are_representable() -> None:
    """Issue #5 names both as scenarios, so they must be worlds, not rejections.

    A first revision enforced strictly increasing lifecycle stages, which made
    "removal requested, refused, requested again" and "confirmed, then reappeared,
    then confirmed again" invalid histories. That is not hygiene - it rules out two of
    the cases the consuming pack exists to cover.
    """

    world = generate_temporal_world(seed=53)
    listing = next(
        item.object_ref
        for item in world.events
        if item.kind is PrivacyEventKind.REMOVAL_REQUESTED and item.object_ref
    )
    subject = world.events[0].subject_ref
    existing = {item.tick for item in world.events}
    free = next(tick for tick in range(world.horizon, 0, -1) if tick not in existing)
    again = PrivacyEvent(
        id="evt-repeat-request",
        tick=free,
        kind=PrivacyEventKind.REMOVAL_REQUESTED,
        subject_ref=subject,
        object_ref=listing,
    )

    replayed = TemporalWorld(
        seed=world.seed,
        horizon=world.horizon,
        events=tuple(
            sorted((again, *world.events), key=lambda item: (item.tick, item.id))
        ),
        listings=world.listings,
        truth=world.truth,
    )

    assert again in replayed.events


def test_a_duplicated_event_is_refused() -> None:
    """Applying an event twice must fail rather than silently double a lifecycle."""

    world = generate_temporal_world(seed=31)
    first = world.events[0]

    with pytest.raises(ValidationError, match="used twice"):
        TemporalWorld(
            seed=world.seed,
            horizon=world.horizon,
            events=(first, *world.events),
            listings=world.listings,
            truth=world.truth,
        )


def test_a_timeline_out_of_canonical_order_is_refused() -> None:
    """Emission order is a free choice, so it must not be allowed to carry meaning."""

    world = generate_temporal_world(seed=37)
    timeline = materialise(world, as_of=world.horizon)

    with pytest.raises(ValidationError, match="canonical tick and id order"):
        PublicTimeline(
            as_of=timeline.as_of,
            events=tuple(reversed(timeline.events)),
        )


def test_a_horizon_too_short_for_the_case_matrix_is_refused() -> None:
    """Clamping would make the manifest describe a world nobody generated."""

    with pytest.raises(ValueError, match="horizon of at least"):
        generate_temporal_world(seed=1, horizon=TEMPORAL_HORIZON - 1)


def test_materialising_before_the_start_is_refused() -> None:
    world = generate_temporal_world(seed=1)

    with pytest.raises(ValueError, match="cannot be negative"):
        materialise(world, as_of=-1)


def test_every_named_failure_mode_is_present_in_truth() -> None:
    """The pack is only worth running if each case it advertises is really in it."""

    world = generate_temporal_world(seed=TEMPORAL_BASELINE_SEED)
    listings = world.truth.listings

    assert any(
        item.removed_at is not None and not item.reappeared_at for item in listings
    )
    assert any(item.removed_at is None for item in listings)  # phantom or refused
    assert any(item.reappeared_at is not None for item in listings)
    assert any(item.downstream_refs for item in listings)
    assert any(not item.concerns_subject for item in listings)


def _event(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "evt-1",
        "tick": 0,
        "kind": PrivacyEventKind.RESCAN,
        "subject_ref": "subject-1",
    }
    return {**base, **overrides}


def _listing(**overrides: object) -> dict[str, object]:
    return {"listing_ref": "listing-1", "concerns_subject": True, **overrides}


def _observation(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "observation_ref": "obs-1",
        "observed_at": 0,
        "validity": ObservationValidity.VALID_WHEN_OBSERVED,
        "current": True,
    }
    return {**base, **overrides}


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (
            lambda: PrivacyEvent.model_validate(
                _event(kind=PrivacyEventKind.REMOVAL_CONFIRMED)
            ),
            "must name the object",
        ),
        (
            lambda: PrivacyEvent.model_validate(_event(object_ref="listing-1")),
            "does not concern an object",
        ),
        (
            lambda: PublicTimeline(
                as_of=0,
                events=(PrivacyEvent.model_validate(_event(tick=3)),),
            ),
            "from after its tick",
        ),
        (
            lambda: PublicTimeline(
                as_of=0,
                events=(
                    PrivacyEvent.model_validate(_event()),
                    PrivacyEvent.model_validate(_event()),
                ),
            ),
            "identifiers must be unique",
        ),
        (
            lambda: PublicTimeline(
                as_of=2,
                events=(
                    PrivacyEvent.model_validate(_event(id="evt-b", tick=2)),
                    PrivacyEvent.model_validate(_event(id="evt-a", tick=1)),
                ),
            ),
            "canonical tick and id order",
        ),
        (
            lambda: ListingTruth.model_validate(_listing(reappeared_at=4)),
            "cannot reappear without having been removed",
        ),
        (
            lambda: ListingTruth.model_validate(
                _listing(removed_at=4, reappeared_at=4)
            ),
            "must reappear after it was removed",
        ),
        (
            lambda: ListingTruth.model_validate(_listing(downstream_refs=("a", "a"))),
            "downstream references must be unique",
        ),
        (
            lambda: ObservationTruth.model_validate(
                _observation(superseded_by="obs-2", current=True)
            ),
            "cannot also be current",
        ),
        (
            lambda: ObservationTruth.model_validate(
                _observation(superseded_by="obs-1", current=False)
            ),
            "cannot supersede itself",
        ),
        (
            lambda: TemporalTruth(
                seed=1,
                horizon=9,
                listings=(
                    ListingTruth.model_validate(_listing()),
                    ListingTruth.model_validate(_listing()),
                ),
            ),
            "must not repeat a listing",
        ),
        (
            lambda: TemporalTruth(
                seed=1,
                horizon=9,
                observations=(
                    ObservationTruth.model_validate(_observation()),
                    ObservationTruth.model_validate(_observation()),
                ),
            ),
            "must not repeat an observation",
        ),
        (
            lambda: TemporalTruth(
                seed=1,
                horizon=2,
                listings=(ListingTruth.model_validate(_listing(removed_at=5)),),
            ),
            "beyond the horizon",
        ),
        (
            lambda: TemporalTruth(
                seed=1,
                horizon=9,
                observations=(
                    ObservationTruth.model_validate(
                        _observation(superseded_by="obs-missing", current=False)
                    ),
                ),
            ),
            "superseded by an unknown observation",
        ),
    ],
)
def test_an_incoherent_history_is_refused(
    build: Callable[[], object], message: str
) -> None:
    """Every rejection path, because a validator nobody exercises is a comment."""

    with pytest.raises(ValidationError, match=message):
        build()


def test_a_world_whose_truth_describes_another_run_is_refused() -> None:
    world = generate_temporal_world(seed=41)

    with pytest.raises(ValidationError, match="does not describe this world"):
        TemporalWorld(
            seed=world.seed + 1,
            horizon=world.horizon,
            events=world.events,
            listings=world.listings,
            truth=world.truth,
        )


def test_a_world_with_events_out_of_order_or_past_the_horizon_is_refused() -> None:
    world = generate_temporal_world(seed=43)

    with pytest.raises(ValidationError, match="canonical tick and id order"):
        TemporalWorld(
            seed=world.seed,
            horizon=world.horizon,
            events=tuple(reversed(world.events)),
            listings=world.listings,
            truth=world.truth,
        )

    late = PrivacyEvent(
        id="evt-zzz-late",
        tick=world.horizon + 5,
        kind=PrivacyEventKind.RESCAN,
        subject_ref=world.events[0].subject_ref,
    )
    with pytest.raises(ValidationError, match="after the horizon"):
        TemporalWorld(
            seed=world.seed,
            horizon=world.horizon,
            events=(*world.events, late),
            listings=world.listings,
            truth=world.truth,
        )


def test_an_event_for_a_listing_with_no_truth_is_refused() -> None:
    """Otherwise a system is scored on a listing the evaluator cannot adjudicate."""

    world = generate_temporal_world(seed=47)
    subject = world.events[0].subject_ref
    stranger = PrivacyEvent(
        id="evt-aaa-stranger",
        tick=0,
        kind=PrivacyEventKind.LISTING_DISCOVERED,
        subject_ref=subject,
        object_ref="listing-untracked",
    )

    with pytest.raises(ValidationError, match="listing with no truth"):
        TemporalWorld(
            seed=world.seed,
            horizon=world.horizon,
            events=tuple(
                sorted((stranger, *world.events), key=lambda item: (item.tick, item.id))
            ),
            listings=world.listings,
            truth=world.truth,
        )


def test_a_stage_reached_before_discovery_is_still_refused() -> None:
    """Repeating a stage is a case; skipping discovery entirely is not a world."""

    world = generate_temporal_world(seed=59)
    subject = world.events[0].subject_ref
    listing = next(
        item.object_ref
        for item in world.events
        if item.kind is PrivacyEventKind.REMOVAL_REQUESTED and item.object_ref
    )
    without_discovery = tuple(
        item
        for item in world.events
        if not (
            item.object_ref == listing
            and item.kind is PrivacyEventKind.LISTING_DISCOVERED
        )
    )

    with pytest.raises(ValidationError, match="no preceding"):
        TemporalWorld(
            seed=world.seed,
            horizon=world.horizon,
            events=without_discovery,
            listings=world.listings,
            truth=world.truth,
        )
    assert subject


def test_an_event_for_an_observation_with_no_truth_is_refused() -> None:
    world = generate_temporal_world(seed=61)
    subject = world.events[0].subject_ref
    stranger = PrivacyEvent(
        id="evt-aaa-obs-stranger",
        tick=0,
        kind=PrivacyEventKind.OBSERVATION_WITHDRAWN,
        subject_ref=subject,
        object_ref="obs-untracked",
    )

    with pytest.raises(ValidationError, match="observation with no truth"):
        TemporalWorld(
            seed=world.seed,
            horizon=world.horizon,
            events=tuple(
                sorted((stranger, *world.events), key=lambda item: (item.tick, item.id))
            ),
            listings=world.listings,
            truth=world.truth,
        )


def test_true_completion_is_not_tied_to_the_broker_s_claim() -> None:
    """A confirmation is what the broker said, not what happened.

    A first revision required `removed_at` to equal a `REMOVAL_CONFIRMED` tick. That
    reads well and is wrong: the phantom case exists precisely because a confirmation
    can be false, and tying true completion to it makes delayed and early actual
    deletion unrepresentable - taking propagation lag out of issue #5's reach.
    """

    world = generate_temporal_world(seed=67)
    removed = next(item for item in world.truth.listings if item.removed_at is not None)
    delayed = tuple(
        item.model_copy(update={"removed_at": world.horizon})
        if item.listing_ref == removed.listing_ref
        else item
        for item in world.truth.listings
    )

    later = TemporalWorld(
        seed=world.seed,
        horizon=world.horizon,
        events=world.events,
        listings=world.listings,
        truth=world.truth.model_copy(update={"listings": delayed}),
    )

    assert later.truth.listings != world.truth.listings
    # The public events are untouched, which is the point: a system cannot see the
    # difference between a deletion that happened on time and one that lagged.
    assert materialise(later, as_of=world.horizon) == materialise(
        world, as_of=world.horizon
    )


def test_a_public_reappearance_absent_from_truth_is_refused() -> None:
    """Hidden truth is the design; a hidden *public* event is a broken history."""

    world = generate_temporal_world(seed=73)
    reappeared = next(
        item for item in world.truth.listings if item.reappeared_at is not None
    )
    forgotten = tuple(
        item.model_copy(update={"reappeared_at": None, "removed_at": None})
        if item.listing_ref == reappeared.listing_ref
        else item
        for item in world.truth.listings
    )

    with pytest.raises(ValidationError, match="truth does not record it"):
        TemporalWorld(
            seed=world.seed,
            horizon=world.horizon,
            events=world.events,
            listings=world.listings,
            truth=world.truth.model_copy(update={"listings": forgotten}),
        )


def test_materialising_past_the_horizon_is_refused() -> None:
    """Silently returning the whole history would make a horizon advisory."""

    world = generate_temporal_world(seed=71)

    with pytest.raises(ValueError, match="exceed the world's horizon"):
        materialise(world, as_of=world.horizon + 1)


def test_an_observation_reference_names_neither_its_listing_nor_its_position() -> None:
    """The channel the first review missed, because it looked at listings.

    References were `f"{listing_ref}-obs-{index}"`. The prefix bound an observation to
    a listing whose reference a consumer already holds, the suffix was a draft
    position, and because only one case carries observations at all, a publicly
    visible `-obs-` reference named that case on 50 of 50 seeds.
    """

    seen: set[str] = set()
    for seed in range(1, 31):
        world = generate_temporal_world(seed=seed)
        timeline = materialise(world, as_of=world.horizon)
        listings = {item.listing_ref for item in world.truth.listings}
        references = {
            item.object_ref
            for item in timeline.events
            if item.object_ref is not None and item.object_ref.startswith("obs-")
        }

        assert references
        assert not any(
            listing in reference for reference in references for listing in listings
        )
        seen |= references

    # And they must move with the seed, or one reading serves every world.
    assert len(seen) == 30


def test_slot_assignment_rejects_duplicates_rather_than_colliding() -> None:
    """The path that only fires on unlucky seeds, so it is exercised deliberately.

    Drawing each slot independently and reducing modulo the pool collided on four
    seeds in the first two thousand, and generation failed outright rather than
    emitting a world. A small pool forces the collision every time.
    """

    crowded = _distinct_slots(seed=1, purpose="test", count=8, modulus=8)

    assert len(set(crowded)) == 8
    assert sorted(crowded) == list(range(8))
    # Deterministic, and the order is not the identity permutation.
    assert _distinct_slots(seed=1, purpose="test", count=8, modulus=8) == crowded


def test_every_seed_in_a_wide_sweep_generates() -> None:
    """Generation must not fail on an unlucky seed, which it used to."""

    for seed in range(200):
        generate_temporal_world(seed=seed)


def _record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "listing_ref": "listing-0001",
        "listed_name": "Ada Barros",
        "first_observed_at": 0,
    }
    return {**base, **overrides}


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (
            lambda: PublicListingRecord.model_validate(
                _record(
                    attributes=(
                        ListingAttribute(kind=ListingAttributeKind.ADDRESS, value="a"),
                        ListingAttribute(kind=ListingAttributeKind.ADDRESS, value="b"),
                    )
                )
            ),
            "repeats an attribute kind",
        ),
        (
            lambda: PublicTimeline(
                as_of=0,
                events=(),
                listings=(
                    PublicListingRecord.model_validate(_record(first_observed_at=5)),
                ),
            ),
            "listing from after its tick",
        ),
        (
            lambda: PublicTimeline(
                as_of=0,
                events=(),
                listings=(
                    PublicListingRecord.model_validate(_record()),
                    PublicListingRecord.model_validate(_record()),
                ),
            ),
            "listing references must be unique",
        ),
        (
            lambda: PublicTimeline(
                as_of=0,
                events=(),
                listings=(
                    PublicListingRecord.model_validate(_record(listing_ref="b")),
                    PublicListingRecord.model_validate(_record(listing_ref="a")),
                ),
            ),
            "canonical reference order",
        ),
    ],
)
def test_listing_content_is_validated_like_every_other_public_collection(
    build: Callable[[], object], message: str
) -> None:
    """Content is public, so it is ordered and deduped like the events beside it."""

    with pytest.raises(ValidationError, match=message):
        build()


def test_content_and_truth_must_describe_the_same_listings() -> None:
    """Otherwise a system attributes a listing nobody scores, or the reverse."""

    world = generate_temporal_world(seed=79)

    with pytest.raises(ValidationError, match="described twice"):
        TemporalWorld(
            seed=world.seed,
            horizon=world.horizon,
            events=world.events,
            listings=(*world.listings, world.listings[0]),
            truth=world.truth,
        )

    with pytest.raises(ValidationError, match="cover different sets"):
        TemporalWorld(
            seed=world.seed,
            horizon=world.horizon,
            events=world.events,
            listings=world.listings[:-1],
            truth=world.truth,
        )
