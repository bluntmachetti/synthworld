"""Contracts for the privacy-exposure temporal slice of issue #2.

A static world asks "can you resolve these records?". A temporal one asks a harder
question: **what did you know, and when could you have known it?** Almost every
interesting privacy failure is a timing failure — a listing that reappears after a
confirmed deletion, an observation that was right when it was taken and is wrong now,
a removal request answered for a record that had already moved.

Three ideas carry the design.

**A tick is the only clock.** Virtual time is an integer, never a wall clock. Real
timestamps are the classic way to lose reproducibility, and this repository has
already been bitten once by a generator that anchored to ``datetime.now()``.

**Materialisation is a prefix, not a filter.** :func:`materialise` builds the public
view at tick ``T`` from the events at or before ``T`` and nothing else. It cannot see
later events, so it cannot leak them — the guarantee is structural rather than a
promise a reviewer has to check. Asking for tick ``T`` twice returns the same bytes;
asking for ``T`` then ``T-1`` does not contaminate the second answer.

**Being right and being justified are scored apart.** ``ObservationValidity`` records
whether a retained observation was true *when it was taken*, which is independent of
whether it is true now. A system that reports a stale address as current is wrong; one
that reports it as a historical binding is right. Collapsing the two would make the
second indistinguishable from the first, and the whole point of issue #5's
reappearance cases is that they are different failures.

The metadata standard from the ambiguity pack applies here from the start: a public
value may depend on the seed and on the evidence, never on the label. Event
identifiers are content-addressed and public collections are ordered canonically, so
neither the identity nor the position of an event can encode its outcome.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from synthworld.models import SyntheticModel

TEMPORAL_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"


class PrivacyEventKind(StrEnum):
    """What happened at a tick.

    Deliberately narrow. Issue #2's full event vocabulary spans credentials,
    delegation and policy; this slice covers only what a privacy-exposure workflow
    needs, because a general event abstraction with one consumer is a guess about the
    second consumer. The generic primitives come out once a second concrete pack
    proves the same semantics.
    """

    # The subject's own life moving on.
    NAME_CHANGED = "name_changed"
    ADDRESS_CHANGED = "address_changed"
    EMPLOYER_CHANGED = "employer_changed"
    ALIAS_REGISTERED = "alias_registered"
    SOCIAL_PROFILE_CREATED = "social_profile_created"

    # A broker lifecycle, which is issue #5's subject.
    LISTING_DISCOVERED = "listing_discovered"
    REMOVAL_REQUESTED = "removal_requested"
    REMOVAL_ACKNOWLEDGED = "removal_acknowledged"
    REMOVAL_CONFIRMED = "removal_confirmed"
    REMOVAL_REFUSED = "removal_refused"
    LISTING_REAPPEARED = "listing_reappeared"

    # What happens to an observation that was already taken.
    OBSERVATION_SUPERSEDED = "observation_superseded"
    OBSERVATION_CONTRADICTED = "observation_contradicted"
    OBSERVATION_WITHDRAWN = "observation_withdrawn"

    # A deterministic assessment point. Carries no state of its own; it exists so a
    # consumer can be asked "what did you conclude here?" at reproducible moments.
    RESCAN = "rescan"


#: Events that close a listing's lifecycle, and the state each implies. A listing that
#: reappears after `REMOVAL_CONFIRMED` is the case issue #5 exists for.
_LIFECYCLE_ORDER: dict[PrivacyEventKind, int] = {
    PrivacyEventKind.LISTING_DISCOVERED: 0,
    PrivacyEventKind.REMOVAL_REQUESTED: 1,
    PrivacyEventKind.REMOVAL_ACKNOWLEDGED: 2,
    PrivacyEventKind.REMOVAL_CONFIRMED: 3,
    PrivacyEventKind.REMOVAL_REFUSED: 3,
    PrivacyEventKind.LISTING_REAPPEARED: 4,
}


class ObservationValidity(StrEnum):
    """Whether a retained observation was true when it was taken.

    Separate from whether it is true now, because those are different questions and a
    system that conflates them cannot be scored on either.
    """

    VALID_WHEN_OBSERVED = "valid_when_observed"
    WRONG_WHEN_OBSERVED = "wrong_when_observed"
    UNKNOWABLE_WHEN_OBSERVED = "unknowable_when_observed"


class PrivacyEvent(SyntheticModel):
    """One thing that happened, at one tick, to one referenced object.

    ``subject_ref`` and ``object_ref`` are opaque strings a consumer can join on. They
    carry no truth: an event says a listing was discovered, never whether the listing
    is really about the subject.
    """

    schema_version: Literal["1.0.0"] = TEMPORAL_SCHEMA_VERSION
    id: str = Field(min_length=1)
    tick: int = Field(ge=0)
    kind: PrivacyEventKind
    subject_ref: str = Field(min_length=1)
    #: The listing, observation or profile this event concerns. ``None`` for events
    #: about the subject alone, such as a rescan or a name change.
    object_ref: str | None = None
    #: Observable detail — a new employer name, a broker's stated reason. Never a
    #: label, an outcome, or anything about a later tick.
    detail: str | None = None

    @model_validator(mode="after")
    def require_object_for_object_events(self) -> Self:
        needs_object = self.kind in _LIFECYCLE_ORDER or self.kind in {
            PrivacyEventKind.OBSERVATION_SUPERSEDED,
            PrivacyEventKind.OBSERVATION_CONTRADICTED,
            PrivacyEventKind.OBSERVATION_WITHDRAWN,
        }
        if needs_object and self.object_ref is None:
            raise ValueError(f"{self.kind.value} must name the object it concerns")
        if not needs_object and self.object_ref is not None:
            raise ValueError(f"{self.kind.value} does not concern an object")
        return self


class PublicTimeline(SyntheticModel):
    """Everything a system may see, as of one tick.

    ``as_of`` is part of the artifact rather than an argument a caller remembers,
    because a timeline that does not say when it was taken can be compared against the
    wrong truth and still look coherent.
    """

    schema_version: Literal["1.0.0"] = TEMPORAL_SCHEMA_VERSION
    seed: int
    as_of: int = Field(ge=0)
    events: tuple[PrivacyEvent, ...]

    @model_validator(mode="after")
    def require_canonical_prefix(self) -> Self:
        if any(item.tick > self.as_of for item in self.events):
            raise ValueError("a timeline cannot contain an event from after its tick")
        identifiers = [item.id for item in self.events]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("timeline event identifiers must be unique")
        # Ordered by tick, then by identifier — never by outcome, and never by the
        # order a generator happened to draft them in. The ambiguity pack shipped an
        # oracle for exactly that reason.
        keys = [(item.tick, item.id) for item in self.events]
        if keys != sorted(keys):
            raise ValueError("timeline events must be in canonical tick and id order")
        return self


class ListingTruth(SyntheticModel):
    """Evaluator-only truth about one broker listing."""

    listing_ref: str = Field(min_length=1)
    #: Whether the listing really concerns the subject. A listing can be discovered,
    #: requested and confirmed removed while never having been about them at all.
    concerns_subject: bool
    #: The tick a confirmed removal actually took effect, if it ever did. `None` means
    #: the listing was never really removed, whatever the events claimed.
    removed_at: int | None = None
    #: The tick the listing came back, if it did.
    reappeared_at: int | None = None
    #: Downstream copies that survive the removal of this listing. The reason a
    #: confirmed deletion is not the end of the story.
    downstream_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_coherent_lifecycle(self) -> Self:
        if self.reappeared_at is not None:
            if self.removed_at is None:
                raise ValueError(
                    "a listing cannot reappear without having been removed"
                )
            if self.reappeared_at <= self.removed_at:
                raise ValueError("a listing must reappear after it was removed")
        if len(self.downstream_refs) != len(set(self.downstream_refs)):
            raise ValueError("downstream references must be unique")
        return self


class ObservationTruth(SyntheticModel):
    """Evaluator-only truth about one retained observation.

    The pair of fields is the point. ``validity`` says whether the observation was
    right at ``observed_at``; ``current`` says whether it is right now. A stale address
    is ``VALID_WHEN_OBSERVED`` and not ``current``, and a system that calls it a
    historical binding is correct while one that calls it the current address is not.
    """

    observation_ref: str = Field(min_length=1)
    observed_at: int = Field(ge=0)
    validity: ObservationValidity
    current: bool
    #: What replaced it, when something did.
    superseded_by: str | None = None

    @model_validator(mode="after")
    def require_superseded_not_current(self) -> Self:
        if self.superseded_by is not None and self.current:
            raise ValueError("a superseded observation cannot also be current")
        if self.superseded_by == self.observation_ref:
            raise ValueError("an observation cannot supersede itself")
        return self


class TemporalTruth(SyntheticModel):
    """Evaluator-only truth, physically separate from any timeline."""

    schema_version: Literal["1.0.0"] = TEMPORAL_SCHEMA_VERSION
    seed: int
    #: The last tick the world was generated for. Truth is stated once, for the whole
    #: run; a timeline is a prefix of it.
    horizon: int = Field(ge=0)
    listings: tuple[ListingTruth, ...] = ()
    observations: tuple[ObservationTruth, ...] = ()

    @model_validator(mode="after")
    def require_unique_references_within_horizon(self) -> Self:
        listing_refs = [item.listing_ref for item in self.listings]
        observation_refs = [item.observation_ref for item in self.observations]
        if len(listing_refs) != len(set(listing_refs)):
            raise ValueError("listing truth must not repeat a listing")
        if len(observation_refs) != len(set(observation_refs)):
            raise ValueError("observation truth must not repeat an observation")
        ticks = [
            tick
            for item in self.listings
            for tick in (item.removed_at, item.reappeared_at)
            if tick is not None
        ] + [item.observed_at for item in self.observations]
        if any(tick > self.horizon for tick in ticks):
            raise ValueError("truth cannot reference a tick beyond the horizon")
        known = set(observation_refs)
        if any(
            item.superseded_by is not None and item.superseded_by not in known
            for item in self.observations
        ):
            raise ValueError("an observation is superseded by an unknown observation")
        return self


class TemporalWorld(SyntheticModel):
    """A full run: every event to the horizon, plus the truth about it.

    Evaluator-side. A consumer receives :func:`materialise` output, never this.
    """

    schema_version: Literal["1.0.0"] = TEMPORAL_SCHEMA_VERSION
    seed: int
    horizon: int = Field(ge=0)
    events: tuple[PrivacyEvent, ...]
    truth: TemporalTruth

    @model_validator(mode="after")
    def require_replayable_history(self) -> Self:
        if self.truth.seed != self.seed or self.truth.horizon != self.horizon:
            raise ValueError("truth does not describe this world")
        identifiers = [item.id for item in self.events]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("an event identifier is used twice")
        keys = [(item.tick, item.id) for item in self.events]
        if keys != sorted(keys):
            raise ValueError("world events must be in canonical tick and id order")
        if any(item.tick > self.horizon for item in self.events):
            raise ValueError("an event happens after the horizon")

        # Lifecycle ordering, per listing. An acknowledgement before a request, or a
        # reappearance before a removal, is an impossible history rather than a hard
        # case, and replaying it would score systems against a world that cannot exist.
        seen: dict[str, int] = {}
        for event in self.events:
            if event.kind not in _LIFECYCLE_ORDER or event.object_ref is None:
                continue
            stage = _LIFECYCLE_ORDER[event.kind]
            previous = seen.get(event.object_ref)
            if previous is None:
                if stage != _LIFECYCLE_ORDER[PrivacyEventKind.LISTING_DISCOVERED]:
                    raise ValueError(
                        f"{event.object_ref} reaches {event.kind.value} "
                        "before discovery"
                    )
            elif stage <= previous:
                raise ValueError(
                    f"{event.object_ref} moves backwards to {event.kind.value}"
                )
            seen[event.object_ref] = stage

        known = {item.listing_ref for item in self.truth.listings}
        if not set(seen) <= known:
            raise ValueError("an event concerns a listing with no truth")
        return self


def materialise(world: TemporalWorld, *, as_of: int) -> PublicTimeline:
    """Build the public view at ``as_of`` from the events at or before it.

    A prefix rather than a filter over a fuller object: what is returned is built from
    the surviving events alone, so no later event and no truth can reach the result.
    That is why this is a function over the world rather than a method on a snapshot
    that already holds everything.
    """

    if as_of < 0:
        raise ValueError("a tick cannot be negative")
    return PublicTimeline(
        seed=world.seed,
        as_of=as_of,
        events=tuple(item for item in world.events if item.tick <= as_of),
    )


def rescan_ticks(world: TemporalWorld) -> tuple[int, ...]:
    """The ticks a consumer is expected to answer at, in order.

    Published so a consumer knows where the questions are without reading truth to
    find them. The ambiguity pack had to learn this: a task whose scope is only in the
    answer key forces the consumer to open the answer key.
    """

    return tuple(
        sorted(
            {item.tick for item in world.events if item.kind is PrivacyEventKind.RESCAN}
        )
    )


def lifecycle_stage(events: Iterable[PrivacyEvent], listing_ref: str) -> int | None:
    """How far a listing has progressed in the events given, or ``None`` if unseen.

    Public-only: it reads the timeline a consumer holds. What it cannot say is whether
    a confirmed removal was real — that is `ListingTruth.removed_at`, and the gap
    between the two is what the benchmark scores.
    """

    stages = [
        _LIFECYCLE_ORDER[item.kind]
        for item in events
        if item.object_ref == listing_ref and item.kind in _LIFECYCLE_ORDER
    ]
    return max(stages) if stages else None


__all__ = [
    "TEMPORAL_SCHEMA_VERSION",
    "ListingTruth",
    "ObservationTruth",
    "ObservationValidity",
    "PrivacyEvent",
    "PrivacyEventKind",
    "PublicTimeline",
    "TemporalTruth",
    "TemporalWorld",
    "lifecycle_stage",
    "materialise",
    "rescan_ticks",
]
