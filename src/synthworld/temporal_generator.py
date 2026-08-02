"""Deterministic privacy-exposure histories for the temporal slice of issue #2.

Every world here is built from named cases rather than sampled, for the same reason
the ambiguity pack is hand-authored: a reviewer has to be able to read the fixture and
say whether it means what it claims. The seed varies surface values and the spacing of
ticks; it does not invent cases.

The cases exist because each is a way a privacy-removal workflow fails in practice:

``clean_removal``
    Requested, acknowledged, confirmed, and genuinely gone. The control. Without it a
    system that reports everything as still-listed would look cautious rather than
    useless.

``phantom_removal``
    Confirmed by the broker, still live in truth. The public events say the job is
    done, and only the evaluator knows otherwise.

``reappearance``
    Confirmed, genuinely removed, then back at a later tick. The case issue #5 exists
    for: a system that stops looking after a confirmation never sees it.

``reseller_copy``
    Confirmed and genuinely removed at the source, while downstream copies survive.
    Deletion is not propagation, and a report that treats them as the same overstates
    what was achieved.

``refused``
    The broker declines. The correct behaviour is to keep the exposure open, not to
    treat a closed ticket as a closed exposure.

``false_match``
    A listing that was never about the subject at all, taken through the whole
    lifecycle. A system that counts its removal as a win is scoring a point for
    deleting a stranger's record.

``stale_binding``
    The subject moves. The old address observation was right when taken and is wrong
    now, and those are separately scored: reporting it as a historical binding is
    correct, reporting it as current is not.

The metadata discipline is the one the ambiguity pack had to learn the hard way. Event
identifiers are content-addressed, so nothing about an identifier reveals which case
it belongs to; tick spacing is drawn from the seed rather than assigned per case; and
the emitted event list is sorted canonically rather than in the order the cases were
drafted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import blake2b
from typing import Literal

from synthworld.temporal import (
    ListingTruth,
    ObservationTruth,
    ObservationValidity,
    PrivacyEvent,
    PrivacyEventKind,
    TemporalTruth,
    TemporalWorld,
)

_K = PrivacyEventKind

#: The canonical horizon. Long enough for a request/acknowledge/confirm cycle plus a
#: later reappearance, short enough to read end to end.
TEMPORAL_HORIZON = 24
TEMPORAL_BASELINE_SEED = 20260802


@dataclass(frozen=True)
class _Case:
    """One named lifecycle, in relative ticks so the seed can space them out."""

    name: str
    stages: tuple[tuple[int, PrivacyEventKind], ...]
    concerns_subject: bool = True
    #: Relative tick at which the removal genuinely took effect, if it ever did.
    removed_at: int | None = None
    reappeared_at: int | None = None
    downstream: tuple[str, ...] = ()
    observations: tuple[tuple[int, ObservationValidity, bool], ...] = field(
        default_factory=tuple
    )


def _cases() -> tuple[_Case, ...]:
    confirm = (
        (0, _K.LISTING_DISCOVERED),
        (2, _K.REMOVAL_REQUESTED),
        (4, _K.REMOVAL_ACKNOWLEDGED),
        (7, _K.REMOVAL_CONFIRMED),
    )
    return (
        _Case("clean_removal", confirm, removed_at=7),
        # The broker says it is done. It is not. Nothing in the public events differs
        # from `clean_removal`, which is the whole difficulty.
        _Case("phantom_removal", confirm, removed_at=None),
        _Case(
            "reappearance",
            (*confirm, (14, _K.LISTING_REAPPEARED)),
            removed_at=7,
            reappeared_at=14,
        ),
        _Case(
            "reseller_copy",
            confirm,
            removed_at=7,
            downstream=("mirror-a", "mirror-b"),
        ),
        _Case(
            "refused",
            (
                (0, _K.LISTING_DISCOVERED),
                (2, _K.REMOVAL_REQUESTED),
                (5, _K.REMOVAL_REFUSED),
            ),
            removed_at=None,
        ),
        _Case("false_match", confirm, concerns_subject=False, removed_at=7),
        _Case(
            "stale_binding",
            ((0, _K.LISTING_DISCOVERED),),
            observations=(
                (0, ObservationValidity.VALID_WHEN_OBSERVED, False),
                (9, ObservationValidity.VALID_WHEN_OBSERVED, True),
            ),
        ),
    )


def _draw(seed: int, purpose: str, index: int) -> int:
    material = f"temporal|{seed}|{purpose}|{index}"
    return int.from_bytes(blake2b(material.encode(), digest_size=8).digest(), "big")


def _event_id(
    tick: int, kind: PrivacyEventKind, subject_ref: str, object_ref: str | None
) -> str:
    """Address an event by what it is, never by the order it was drafted in.

    Length-prefixed rather than delimited, so a reference containing the separator
    cannot reproduce another event's material.
    """

    parts = (str(tick), kind.value, subject_ref, object_ref or "")
    material = "".join(f"{len(part)}:{part}" for part in parts)
    return f"evt-{blake2b(material.encode(), digest_size=12).hexdigest()}"


def _listing_ref(seed: int, case: _Case) -> str:
    """A reference derived from the seed and the case's own shape, not its name.

    Naming these `listing-clean_removal` would hand the answer to anyone who read one,
    which is precisely the mistake the ambiguity pack shipped three times.
    """

    shape = "|".join(f"{tick}:{kind.value}" for tick, kind in case.stages)
    slot = _draw(seed, f"listing:{shape}:{case.name}", 0) % 10_000
    return f"listing-{slot:04d}"


def generate_temporal_world(
    *,
    seed: int = TEMPORAL_BASELINE_SEED,
    horizon: int = TEMPORAL_HORIZON,
) -> TemporalWorld:
    """Build one deterministic privacy-exposure history."""

    if horizon < TEMPORAL_HORIZON:
        raise ValueError(
            f"the case matrix needs a horizon of at least {TEMPORAL_HORIZON}"
        )

    subject_ref = f"subject-{_draw(seed, 'subject', 0) % 10_000:04d}"
    # One shared offset, so cases stay aligned relative to each other while the whole
    # history slides. A per-case offset would make the gap between two lifecycles a
    # function of which cases they are.
    offset = _draw(seed, "offset", 0) % 3

    events: list[PrivacyEvent] = []
    listings: list[ListingTruth] = []
    observations: list[ObservationTruth] = []

    for case in _cases():
        listing_ref = _listing_ref(seed, case)
        for relative, kind in case.stages:
            tick = relative + offset
            events.append(
                PrivacyEvent(
                    id=_event_id(tick, kind, subject_ref, listing_ref),
                    tick=tick,
                    kind=kind,
                    subject_ref=subject_ref,
                    object_ref=listing_ref,
                )
            )
        listings.append(
            ListingTruth(
                listing_ref=listing_ref,
                concerns_subject=case.concerns_subject,
                removed_at=(
                    None if case.removed_at is None else case.removed_at + offset
                ),
                reappeared_at=(
                    None if case.reappeared_at is None else case.reappeared_at + offset
                ),
                downstream_refs=tuple(
                    f"{listing_ref}-{name}" for name in case.downstream
                ),
            )
        )

        for index, (relative, validity, current) in enumerate(case.observations):
            tick = relative + offset
            observation_ref = f"{listing_ref}-obs-{index}"
            observations.append(
                ObservationTruth(
                    observation_ref=observation_ref,
                    observed_at=tick,
                    validity=validity,
                    current=current,
                    superseded_by=None,
                )
            )
            if index:
                # The earlier observation is superseded by this one, and the event
                # saying so is public: a consumer can see that something replaced it
                # without being told which of the two is right now.
                earlier = f"{listing_ref}-obs-{index - 1}"
                observations[-2] = observations[-2].model_copy(
                    update={"superseded_by": observation_ref}
                )
                events.append(
                    PrivacyEvent(
                        id=_event_id(
                            tick, _K.OBSERVATION_SUPERSEDED, subject_ref, earlier
                        ),
                        tick=tick,
                        kind=_K.OBSERVATION_SUPERSEDED,
                        subject_ref=subject_ref,
                        object_ref=earlier,
                        detail="address_changed",
                    )
                )
                events.append(
                    PrivacyEvent(
                        id=_event_id(tick, _K.ADDRESS_CHANGED, subject_ref, None),
                        tick=tick,
                        kind=_K.ADDRESS_CHANGED,
                        subject_ref=subject_ref,
                        detail=f"Example Street {slot(seed, tick)}|Testville|00000|ZZ",
                    )
                )

    for index, tick in enumerate(_rescan_schedule(seed, horizon)):
        events.append(
            PrivacyEvent(
                id=_event_id(tick, _K.RESCAN, subject_ref, None),
                tick=tick,
                kind=_K.RESCAN,
                subject_ref=subject_ref,
                detail=f"scheduled-{index}",
            )
        )

    ordered = tuple(sorted(events, key=lambda item: (item.tick, item.id)))
    return TemporalWorld(
        seed=seed,
        horizon=horizon,
        events=ordered,
        truth=TemporalTruth(
            seed=seed,
            horizon=horizon,
            listings=tuple(sorted(listings, key=lambda item: item.listing_ref)),
            observations=tuple(
                sorted(observations, key=lambda item: item.observation_ref)
            ),
        ),
    )


def slot(seed: int, tick: int) -> int:
    """A stable surface number for a detail string."""

    return _draw(seed, "surface", tick) % 900 + 100


def _rescan_schedule(seed: int, horizon: int) -> tuple[int, ...]:
    """Assessment points, spread across the history rather than placed at outcomes.

    Deliberately independent of the cases: a rescan that lands on the tick after every
    confirmation would tell a consumer where to look, which is the task rather than a
    schedule.
    """

    stride = 4 + _draw(seed, "rescan-stride", 0) % 2
    return tuple(range(stride, horizon + 1, stride))


TEMPORAL_CASE_NAMES: tuple[str, ...] = tuple(case.name for case in _cases())
TEMPORAL_SCHEMA: Literal["1.0.0"] = "1.0.0"

__all__ = [
    "TEMPORAL_BASELINE_SEED",
    "TEMPORAL_CASE_NAMES",
    "TEMPORAL_HORIZON",
    "generate_temporal_world",
]
