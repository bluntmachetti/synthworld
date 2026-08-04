"""Deterministic privacy-exposure histories for the temporal slice of issue #2.

Every world here is built from named cases rather than sampled, for the same reason
the ambiguity pack is hand-authored: a reviewer has to be able to read the fixture and
say whether it means what it claims. The seed varies surface values, a global time
offset and the rescan stride; the gaps *within* a lifecycle are fixed, and the seed
never invents cases.

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
    DownstreamCopy,
    ListingAttribute,
    ListingAttributeKind,
    ListingTruth,
    ObservationTruth,
    ObservationValidity,
    PrivacyEvent,
    PrivacyEventKind,
    PublicListingRecord,
    TemporalTruth,
    TemporalWorld,
)

_K = PrivacyEventKind

#: The canonical horizon. Long enough for a request/acknowledge/confirm cycle plus a
#: later reappearance, short enough to read end to end.
TEMPORAL_HORIZON = 24

#: Local name pools. Deliberately not imported from the ambiguity pack: sharing them
#: would couple two benchmarks' surface values, so a change made for one would move the
#: other's bytes.
_GIVEN = ("Ada", "Bilal", "Chen", "Dara", "Esme", "Faisal", "Gita", "Hugo")
_FAMILY = ("Aldridge", "Barros", "Chevalier", "Delgado", "Eriksen", "Fontaine")
TEMPORAL_BASELINE_SEED = 20260802


#: How a listing's content relates to the subject's own identity.
#:
#: ``matching`` - the listed name and a corroborating attribute both agree, so the
#: attribution is decidable and positive.
#: ``contradicting`` - the name agrees and the corroborating attribute does not, which
#: is decidable and negative: a same-name collision.
#: ``bare`` - the name and nothing else. Whatever the truth, the public record cannot
#: settle it, and declining is the correct behaviour.
_ListingEvidence = Literal["matching", "contradicting", "bare"]


@dataclass(frozen=True)
class _Case:
    """One named lifecycle, in relative ticks so the seed can space them out."""

    name: str
    stages: tuple[tuple[int, PrivacyEventKind], ...]
    concerns_subject: bool = True
    evidence: _ListingEvidence = "matching"
    #: Relative tick at which the removal genuinely took effect, if it ever did.
    removed_at: int | None = None
    reappeared_at: int | None = None
    #: Downstream copies as `(name, relative removal tick)`. `None` never goes.
    downstream: tuple[tuple[str, int | None], ...] = ()
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
            downstream=(("mirror-a", None), ("mirror-b", None)),
        ),
        # Deletion propagating slowly, not failing (#65). The source goes at 7 and the
        # copies catch up at 15 and 21, so a system that reports completion the moment
        # the source is gone is wrong here in a way `reseller_copy` cannot show - there
        # the copies never go, and "wrong forever" and "wrong for a while" need
        # different answers from a resolver watching the same public events.
        _Case(
            "slow_propagation",
            confirm,
            removed_at=7,
            downstream=(("mirror-a", 15), ("mirror-b", 21)),
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
        _Case(
            "false_match",
            confirm,
            concerns_subject=False,
            evidence="contradicting",
            removed_at=7,
        ),
        # A second stranger, listed twice. One false match made the negative class a
        # singleton, and a decoder counting how many pages shared an address separated
        # it perfectly without reading anything.
        _Case(
            "false_match_syndicated",
            confirm,
            concerns_subject=False,
            evidence="contradicting",
            removed_at=7,
        ),
        # Carries a common name and nothing to corroborate it. It really is the
        # subject's, but the page does not say so, and a system that declines is
        # behaving correctly where one that guesses is not.
        _Case("unattributable_listing", confirm, evidence="bare", removed_at=7),
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


def _distinct_slots(
    seed: int, purpose: str, count: int, modulus: int
) -> tuple[int, ...]:
    """`count` distinct values below `modulus`, drawn deterministically.

    Drawing each slot independently and reducing modulo 10,000 collides: four seeds in
    the first two thousand assigned one reference to two cases, and generation failed
    outright rather than emitting a world. Rejecting duplicates as they appear keeps
    the assignment injective without making it affine in the slot, which would put an
    arithmetic progression back into a public value.
    """

    values: list[int] = []
    seen: set[int] = set()
    index = 0
    while len(values) < count:
        candidate = _draw(seed, purpose, index) % modulus
        index += 1
        if candidate not in seen:
            seen.add(candidate)
            values.append(candidate)
    return tuple(values)


def _event_id(
    tick: int,
    kind: PrivacyEventKind,
    subject_ref: str,
    object_ref: str | None,
    detail: str | None = None,
) -> str:
    """Address an event by what it is, never by the order it was drafted in.

    Length-prefixed rather than delimited, so a reference containing the separator
    cannot reproduce another event's material. ``detail`` is part of the material: two
    events at one tick differing only in a broker's stated reason are different events,
    and omitting it gave them one identifier.
    """

    parts = (str(tick), kind.value, subject_ref, object_ref or "", detail or "")
    material = "".join(f"{len(part)}:{part}" for part in parts)
    return f"evt-{blake2b(material.encode(), digest_size=12).hexdigest()}"


def _listing_refs(seed: int) -> dict[str, str]:
    """Assign every case a reference by keyed rank, carrying nothing about the case.

    Two things were wrong with the first version, and its docstring claimed neither.
    It said the reference derived from "the case's own shape, not its name" while
    hashing `case.name` directly — renaming a case with its events and truth unchanged
    moved public bytes in 60 of 60 seeds. And the shape it hashed was the case's
    *entire* stage list, so the identifier on a discovery event at tick 0 was a
    function of what that listing would do at tick 14: moving a reappearance from tick
    14 to 16 changed the public prefix at ticks well before either.

    Slots are now a seed-keyed permutation over positions. The mapping moves with the
    seed, so no reading transfers, and nothing about a case — its name, its outcome, or
    its future — reaches the identifier.
    """

    names = [case.name for case in _cases()]
    order = sorted(
        range(len(names)), key=lambda index: _draw(seed, "listing-slot", index)
    )
    values = _distinct_slots(seed, "listing-value", len(names), 10_000)
    return {
        names[case_index]: f"listing-{values[slot]:04d}"
        for slot, case_index in enumerate(order)
    }


def _observation_ref(seed: int, listing_ref: str, index: int) -> str:
    """An opaque reference that names neither its listing nor its position.

    A first revision emitted `f"{listing_ref}-obs-{index}"`. Both halves were channels.
    The prefix bound an observation to a listing whose reference a consumer already
    holds, and the suffix was a draft position; and because only one case carries
    observations at all, any publicly visible `-obs-` reference named that case on 50
    of 50 seeds. Joining is still possible - a consumer sees the reference in the event
    that concerns it - but the reference no longer says what it belongs to.
    """

    material = f"{len(listing_ref)}:{listing_ref}{len(str(index))}:{index}"
    return f"obs-{_draw(seed, f'observation:{material}', 0) % 100_000:05d}"


def _subject_identity(seed: int) -> tuple[str, str, str]:
    """The subject's name, address and employer, drawn from the seed.

    Published as events at tick 0. Without them a consumer has nothing to compare a
    broker page against, which is why attribution used to be unanswerable.
    """

    given = _GIVEN[_draw(seed, "subject-given", 0) % len(_GIVEN)]
    family = _FAMILY[_draw(seed, "subject-family", 0) % len(_FAMILY)]
    address = (
        f"{_draw(seed, 'subject-house', 0) % 200 + 1}|"
        f"Example Street {_draw(seed, 'subject-street', 0) % 900 + 100}|"
        "Testville|00000|ZZ"
    )
    employer = f"Example {_FAMILY[_draw(seed, 'subject-work', 0) % len(_FAMILY)]} Works"
    return f"{given} {family}", address, employer


def _listing_content(
    seed: int,
    case: _Case,
    listing_ref: str,
    identity: tuple[str, str, str],
    tick: int,
    prior_address: str,
) -> PublicListingRecord:
    """What one broker page says, given the case's declared evidence relation."""

    name, address, employer = identity
    if case.evidence == "bare":
        # A common name and nothing to corroborate it. Undecidable by construction.
        return PublicListingRecord(
            listing_ref=listing_ref, listed_name=name, first_observed_at=tick
        )
    if case.evidence == "contradicting":
        # Same name, different person: neither the address nor the employer is theirs.
        #
        # Both attributes are present, and both are drawn from the same vocabulary the
        # subject's own use. A first revision published only the address, and put it in
        # a distinct town - which made the page recognisable without reading anything.
        # A decoder keyed on nothing but the attribute *count* scored 1.000 on 75 of 75
        # held-out seeds, as did one grepping for the town name, so the evidence was
        # decorative: the shape of the record answered the question the values were
        # supposed to. The comment here used to claim the employer was wrong too, while
        # the code emitted no employer at all; building the page the comment described
        # is what closes it.
        # Drawn until they differ. Sampling once let the "wrong" employer equal the
        # subject's on 16.7% of seeds and the address on a handful, and on at least one
        # seed the whole record matched a positive page byte for byte while truth still
        # said `attributable` - so attribution was unanswerable on a valid world.
        other_address = next(
            candidate
            for index in range(64)
            if (
                candidate := f"{_draw(seed, 'other-house', index) % 200 + 1}|"
                f"Example Street {_draw(seed, 'other-street', index) % 900 + 100}|"
                "Testville|00000|ZZ"
            )
            != address
        )
        other_employer = next(
            candidate
            for index in range(64)
            if (
                candidate := "Example "
                f"{_FAMILY[_draw(seed, 'other-work', index) % len(_FAMILY)]} Works"
            )
            != employer
        )
        return PublicListingRecord(
            listing_ref=listing_ref,
            listed_name=name,
            attributes=(
                ListingAttribute(
                    kind=ListingAttributeKind.ADDRESS, value=other_address
                ),
                ListingAttribute(
                    kind=ListingAttributeKind.EMPLOYER, value=other_employer
                ),
            ),
            first_observed_at=tick,
        )
    # Brokers hold the subject at different points in their history, so a matching page
    # carries either the current address or the one before it. Publishing the same
    # string on every positive made multiplicity the answer: counting how many pages
    # shared an address separated subject from stranger on 2800 of 2800 records.
    on_prior = _draw(seed, f"listing-address:{case.name}", 0) % 3 == 0
    return PublicListingRecord(
        listing_ref=listing_ref,
        listed_name=name,
        attributes=(
            ListingAttribute(
                kind=ListingAttributeKind.ADDRESS,
                value=prior_address if on_prior else address,
            ),
            ListingAttribute(kind=ListingAttributeKind.EMPLOYER, value=employer),
        ),
        first_observed_at=tick,
    )


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
    # function of which cases they are. Gaps *within* a lifecycle are fixed.
    offset = _draw(seed, "offset", 0) % 3
    references = _listing_refs(seed)

    identity = _subject_identity(seed)
    # The address the subject held before the move in `stale_binding`. A broker holding
    # it is holding a real, older binding rather than someone else's record.
    prior_address = (
        f"{_draw(seed, 'prior-house', 0) % 200 + 1}|"
        f"Example Street {_draw(seed, 'prior-street', 0) % 900 + 100}|"
        "Testville|00000|ZZ"
    )
    events: list[PrivacyEvent] = []
    listings: list[ListingTruth] = []
    content: list[PublicListingRecord] = []
    observations: list[ObservationTruth] = []

    for kind, value in (
        (_K.NAME_CHANGED, identity[0]),
        (_K.ADDRESS_CHANGED, prior_address),
        (_K.EMPLOYER_CHANGED, identity[2]),
    ):
        events.append(
            PrivacyEvent(
                id=_event_id(0, kind, subject_ref, None, value),
                tick=0,
                kind=kind,
                subject_ref=subject_ref,
                detail=value,
            )
        )

    for case in _cases():
        listing_ref = references[case.name]
        content.append(
            _listing_content(
                seed,
                case,
                listing_ref,
                identity,
                case.stages[0][0] + offset,
                prior_address,
            )
        )
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
                attributable=case.evidence != "bare",
                removed_at=(
                    None if case.removed_at is None else case.removed_at + offset
                ),
                reappeared_at=(
                    None if case.reappeared_at is None else case.reappeared_at + offset
                ),
                downstream_copies=tuple(
                    DownstreamCopy(
                        copy_ref=f"{listing_ref}-{name}",
                        removed_at=None if gone is None else gone + offset,
                    )
                    for name, gone in case.downstream
                ),
            )
        )

        for index, (relative, validity, current) in enumerate(case.observations):
            tick = relative + offset
            observation_ref = _observation_ref(seed, listing_ref, index)
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
                earlier = _observation_ref(seed, listing_ref, index - 1)
                observations[-2] = observations[-2].model_copy(
                    update={"superseded_by": observation_ref}
                )
                events.append(
                    PrivacyEvent(
                        id=_event_id(
                            tick,
                            _K.OBSERVATION_SUPERSEDED,
                            subject_ref,
                            earlier,
                            "address_changed",
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
                        id=_event_id(
                            tick,
                            _K.ADDRESS_CHANGED,
                            subject_ref,
                            None,
                            f"Example Street {slot(seed, tick)}|Testville|00000|ZZ",
                        ),
                        tick=tick,
                        kind=_K.ADDRESS_CHANGED,
                        subject_ref=subject_ref,
                        detail=identity[1],
                    )
                )

    for index, tick in enumerate(_rescan_schedule(seed, horizon)):
        events.append(
            PrivacyEvent(
                id=_event_id(tick, _K.RESCAN, subject_ref, None, f"scheduled-{index}"),
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
        listings=tuple(sorted(content, key=lambda item: item.listing_ref)),
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
