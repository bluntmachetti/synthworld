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

**Materialisation returns a prefix.** :func:`materialise` builds the public view at
tick ``T`` from the events at or before ``T``, and the result carries no reference back
to the world it came from. That is a property the tests measure at every tick of four
seeds — not a structural impossibility, since the function does hold the whole world
while it runs. An earlier draft of this docstring claimed the guarantee was structural,
which described a design that had not been built.

**Being right and being justified are scored apart.** ``ObservationValidity`` records
whether a retained observation was true *when it was taken*, which is independent of
whether it is true now. A system that reports a stale address as current is wrong; one
that reports it as a historical binding is right. Collapsing the two would make the
second indistinguishable from the first, and the whole point of issue #5's
reappearance cases is that they are different failures.

The metadata standard from the ambiguity pack applies here from the start: a public
value may depend on the seed and on the evidence, never on the label. Event
identifiers are digests of the event's own visible fields and public collections are
ordered canonically. An event's *position* carries nothing — measured uniform across
twenty thousand seeds. Its *identity* depends on references that are themselves drawn
from the seed, which is why the seed is evaluator-side.
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


#: The events that make up a listing's lifecycle. The integers order them for reading
#: only; what constrains a history is `_LIFECYCLE_REQUIRES` below.
_LIFECYCLE_ORDER: dict[PrivacyEventKind, int] = {
    PrivacyEventKind.LISTING_DISCOVERED: 0,
    PrivacyEventKind.REMOVAL_REQUESTED: 1,
    PrivacyEventKind.REMOVAL_ACKNOWLEDGED: 2,
    PrivacyEventKind.REMOVAL_CONFIRMED: 3,
    PrivacyEventKind.REMOVAL_REFUSED: 3,
    PrivacyEventKind.LISTING_REAPPEARED: 4,
}


#: What must already have happened to a listing before each event can. Satisfied by
#: any earlier tick and satisfiable repeatedly, so "requested, refused, requested
#: again" and a second removal cycle after a reappearance are both representable while
#: a confirmation with no request is not.
_LIFECYCLE_REQUIRES: dict[PrivacyEventKind, frozenset[PrivacyEventKind]] = {
    PrivacyEventKind.REMOVAL_REQUESTED: frozenset(
        {PrivacyEventKind.LISTING_DISCOVERED}
    ),
    PrivacyEventKind.REMOVAL_ACKNOWLEDGED: frozenset(
        {PrivacyEventKind.REMOVAL_REQUESTED}
    ),
    PrivacyEventKind.REMOVAL_CONFIRMED: frozenset({PrivacyEventKind.REMOVAL_REQUESTED}),
    PrivacyEventKind.REMOVAL_REFUSED: frozenset({PrivacyEventKind.REMOVAL_REQUESTED}),
    PrivacyEventKind.LISTING_REAPPEARED: frozenset(
        {PrivacyEventKind.REMOVAL_CONFIRMED}
    ),
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


class ListingAttributeKind(StrEnum):
    """The observable fields a broker page carries about a person."""

    ADDRESS = "address"
    EMPLOYER = "employer"


class ListingAttribute(SyntheticModel):
    kind: ListingAttributeKind
    value: str = Field(min_length=1)


class PublicListingRecord(SyntheticModel):
    """What a broker page actually says, as a consumer would read it.

    Without this there is no evidence to attribute a listing on. A first revision
    published only lifecycle events with no content at all and never said who the
    subject was, so no listing could be attributed at all: `false_match` was
    indistinguishable from the six that really are the subject's, and its lifecycle
    events were byte-identical to three of them. Attribution could only be won by
    abstaining or guessing, which means it was measuring luck.

    Content only. Whether the listing really concerns the subject is
    :class:`ListingTruth`'s business, and a consumer decides it by comparing this
    against what the timeline says about the subject.
    """

    listing_ref: str = Field(min_length=1)
    listed_name: str = Field(min_length=1)
    attributes: tuple[ListingAttribute, ...] = ()
    first_observed_at: int = Field(ge=0)

    @model_validator(mode="after")
    def require_one_value_per_kind(self) -> Self:
        kinds = [item.kind for item in self.attributes]
        if len(kinds) != len(set(kinds)):
            raise ValueError("a listing repeats an attribute kind")
        return self


class PublicTimeline(SyntheticModel):
    """Everything a system may see, as of one tick.

    ``as_of`` is part of the artifact rather than an argument a caller remembers,
    because a timeline that does not say when it was taken can be compared against the
    wrong truth and still look coherent.

    The seed is deliberately *not* here. It lives on :class:`TemporalTruth`, where
    :class:`~synthworld.search.SearchTruthBundle` also keeps it and for the same
    reason: this generator is public, so a public seed lets a consumer rebuild the
    world and read the answer key out of it. A first revision put it here and handed
    over every listing's full truth.
    """

    schema_version: Literal["1.0.0"] = TEMPORAL_SCHEMA_VERSION
    as_of: int = Field(ge=0)
    events: tuple[PrivacyEvent, ...]
    #: What each discovered listing says, for the listings discovered by `as_of`.
    listings: tuple[PublicListingRecord, ...] = ()

    @model_validator(mode="after")
    def require_canonical_prefix(self) -> Self:
        if any(item.first_observed_at > self.as_of for item in self.listings):
            raise ValueError("a timeline cannot contain a listing from after its tick")
        references = [item.listing_ref for item in self.listings]
        if len(references) != len(set(references)):
            raise ValueError("timeline listing references must be unique")
        if references != sorted(references):
            raise ValueError("timeline listings must be in canonical reference order")
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
    #: Whether the public record carries enough to settle `concerns_subject`. A
    #: listing bearing only a common name is *not* attributable whatever the truth
    #: happens to be, and a system that declines it is behaving correctly where one
    #: that guesses is not. The same distinction the ambiguity pack draws with
    #: `PairDisposition.INSUFFICIENT` and the search pack with
    #: `SearchMatchTruth.INSUFFICIENT_EVIDENCE`.
    attributable: bool = True
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
    #: Public content for every listing in the run.
    listings: tuple[PublicListingRecord, ...] = ()
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

        # Causality, not monotonicity. A first revision required stages to strictly
        # increase, which rejected repeated removal requests and conflicting statuses -
        # both named in issue #5's scenarios, so both cases rather than corruptions.
        # Dropping the rule altogether over-corrected: it then accepted a confirmation
        # with no request and a reappearance with no removal, which no workflow
        # produces. What each event needs is its own precondition, satisfied at any
        # earlier tick and satisfiable more than once.
        seen: dict[str, set[PrivacyEventKind]] = {}
        for event in self.events:
            if event.kind not in _LIFECYCLE_ORDER or event.object_ref is None:
                continue
            history = seen.setdefault(event.object_ref, set())
            required = _LIFECYCLE_REQUIRES.get(event.kind)
            if required is not None and not (required & history):
                wanted = " or ".join(sorted(item.value for item in required))
                raise ValueError(
                    f"{event.object_ref} reaches {event.kind.value} "
                    f"with no preceding {wanted}"
                )
            history.add(event.kind)

        known = {item.listing_ref for item in self.truth.listings}
        if not set(seen) <= known:
            raise ValueError("an event concerns a listing with no truth")

        observations = {item.observation_ref for item in self.truth.observations}
        referenced = {
            item.object_ref
            for item in self.events
            if item.object_ref is not None
            and item.kind
            in {
                PrivacyEventKind.OBSERVATION_SUPERSEDED,
                PrivacyEventKind.OBSERVATION_CONTRADICTED,
                PrivacyEventKind.OBSERVATION_WITHDRAWN,
            }
        }
        if not referenced <= observations:
            raise ValueError("an event concerns an observation with no truth")

        # A public reappearance is an observable fact, so truth must know about it.
        # Note what is deliberately *not* checked: `removed_at` is not required to
        # match a `REMOVAL_CONFIRMED` tick. A confirmation is the broker's claim, which
        # the phantom case exists to show can be false; tying true completion to it
        # would make delayed and early actual deletion unrepresentable and take
        # propagation lag out of issue #5's reach. A first revision did exactly that.
        # Content must exist for exactly the listings truth knows about, or a system
        # is asked to attribute a listing it cannot read, or shown one nobody scores.
        described = [item.listing_ref for item in self.listings]
        if len(described) != len(set(described)):
            raise ValueError("a listing is described twice")
        if set(described) != {item.listing_ref for item in self.truth.listings}:
            raise ValueError("listing content and listing truth cover different sets")

        # Content cannot predate the discovery that reveals it. Events already refuse a
        # stage before discovery; without the same rule here a world validates in which
        # a page is readable at a tick where the listing has not been found, and any
        # consumer joining the two crashes rather than scoring.
        discovered: dict[str, int] = {}
        for event in self.events:
            if event.kind is PrivacyEventKind.LISTING_DISCOVERED and event.object_ref:
                discovered.setdefault(event.object_ref, event.tick)
        for record in self.listings:
            if discovered.get(record.listing_ref) != record.first_observed_at:
                raise ValueError(
                    f"{record.listing_ref} content does not appear at its discovery"
                )

        reappearances = {
            event.object_ref
            for event in self.events
            if event.kind is PrivacyEventKind.LISTING_REAPPEARED and event.object_ref
        }
        for listing in self.truth.listings:
            if listing.listing_ref in reappearances and listing.reappeared_at is None:
                raise ValueError(
                    f"{listing.listing_ref} reappears publicly but truth does not "
                    "record it"
                )
        return self


def materialise(world: TemporalWorld, *, as_of: int) -> PublicTimeline:
    """Build the public view at ``as_of`` from the events at or before it.

    A filter, and honestly labelled as one: the world it reads holds the truth and the
    future while this runs. What the tests establish is that nothing beyond the
    surviving events reaches the returned object — a measured property, not an
    impossibility. It is a function rather than a method so the result has no reference
    back to the world.
    """

    if as_of < 0:
        raise ValueError("a tick cannot be negative")
    if as_of > world.horizon:
        raise ValueError("a tick cannot exceed the world's horizon")
    return PublicTimeline(
        as_of=as_of,
        events=tuple(item for item in world.events if item.tick <= as_of),
        listings=tuple(
            item for item in world.listings if item.first_observed_at <= as_of
        ),
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
    "ListingAttribute",
    "ListingAttributeKind",
    "ListingTruth",
    "ObservationTruth",
    "ObservationValidity",
    "PrivacyEvent",
    "PrivacyEventKind",
    "PublicListingRecord",
    "PublicTimeline",
    "TemporalTruth",
    "TemporalWorld",
    "lifecycle_stage",
    "materialise",
    "rescan_ticks",
]
