"""Scoring for the broker deletion-and-reappearance pack, issue #5.

A removal workflow can fail in six unrelated ways, and one number hides all of them.
So this reports six families and never combines them:

**Discovery** — did the system notice the listings the timeline showed it? A system
that assesses nothing has perfect precision on everything else.

**Identity matching** — is this listing actually about the subject? Getting this wrong
in one direction attaches a stranger's exposure to a person; in the other it leaves
real exposure unfound. They are different harms and are counted apart.

**Request correctness** — was a removal actually requested for the listings that
needed one, and not for the ones that did not? Requesting removal of someone else's
record is not a neutral act.

**Completion** — did the listing really go? The broker's confirmation is a *claim*.
The pack contains a listing confirmed removed that never was, and a system that
believes the confirmation is wrong in a way no public event reveals. This is the
metric the whole pack exists for.

**Propagation** — deletion is not propagation. A source listing can be genuinely gone
while reseller copies survive, and a report that calls that done overstates what was
achieved.

**Recurrence** — a listing that comes back after a confirmed removal. A system that
stops watching once it sees a confirmation never sees this, and its completion score
looks identical to one that keeps watching.

Every score carries its numerator, denominator and the denominator's meaning, matching
:class:`~synthworld.ambiguity_partition.DenominatedMetric`. A serialized report that
cannot be re-derived is one a reader has to trust rather than check.

The join to truth happens here and nowhere earlier. An assessment names listings by
the opaque references it met in the public timeline; it never sees `ListingTruth`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, Self

from pydantic import Field, model_validator

from synthworld.ambiguity_partition import DenominatedMetric
from synthworld.models import SyntheticModel
from synthworld.temporal import (
    _LIFECYCLE_ORDER,
    PrivacyEventKind,
    PublicTimeline,
    TemporalTruth,
    lifecycle_stage,
)

BROKER_SCORING_VERSION: Literal["1.0.0"] = "1.0.0"


class BrokerEvaluationError(ValueError):
    """Raised when a submission does not match the timeline it claims to assess."""


class ListingAssessment(SyntheticModel):
    """What a system concluded about one listing, at one tick.

    ``concerns_subject`` is ``None`` for an abstention. Some listings genuinely cannot
    be attributed from the public timeline, and a system that declines is behaving
    correctly where one that guesses is not - so declining is recorded rather than
    scored as an error.
    """

    listing_ref: str = Field(min_length=1)
    concerns_subject: bool | None
    #: Whether the system believes the listing is gone *in fact*, not whether it saw a
    #: confirmation. The pack is built so those differ.
    believed_removed: bool
    #: Whether the system asked for removal.
    requested_removal: bool
    #: Whether the system believes copies survive elsewhere.
    believed_propagated: bool = False
    #: Whether the system raised a reappearance alert.
    reappearance_alerted: bool = False


class BrokerAssessment(SyntheticModel):
    """A complete submission for one tick.

    Public-only: nothing reachable from it touches evaluator truth.
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
    as_of: int = Field(ge=0)
    listings: tuple[ListingAssessment, ...]

    @model_validator(mode="after")
    def require_unique_listings(self) -> Self:
        references = [item.listing_ref for item in self.listings]
        if len(references) != len(set(references)):
            raise ValueError("a listing was assessed twice")
        return self


class BrokerRemovalMetrics(SyntheticModel):
    """Six families, never combined."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    scoring_version: Literal["1.0.0"] = BROKER_SCORING_VERSION
    task: Literal["broker_removal"] = "broker_removal"
    as_of: int
    #: Listings the public timeline had discovered by `as_of`. The denominator every
    #: other family is bounded by.
    discoverable_count: int
    assessed_count: int
    abstained_count: int
    discovery_coverage: DenominatedMetric
    #: Attributed a listing to the subject that is someone else's, and the reverse.
    false_attributions: int
    missed_attributions: int
    attribution_accuracy: DenominatedMetric
    #: Asked for removal of a listing that is not the subject's.
    unwarranted_requests: int
    request_correctness: DenominatedMetric
    #: Believed a listing gone when it is not, and the reverse. The phantom case makes
    #: the first of these unreachable from public evidence alone.
    false_completions: int
    missed_completions: int
    completion_accuracy: DenominatedMetric
    #: Listings with surviving downstream copies that the system called fully done.
    overstated_propagation: int
    propagation_accuracy: DenominatedMetric
    #: Reappearances by `as_of`, and how many were alerted.
    recurrence_count: int
    recurrence_detected: int
    recurrence_recall: DenominatedMetric


def _metric(
    numerator: float, denominator: float, meaning: str, *, undefined: str | None = None
) -> DenominatedMetric:
    if undefined is not None or not denominator:
        return DenominatedMetric(
            value=None,
            numerator=numerator,
            denominator=denominator,
            denominator_meaning=meaning,
            undefined_reason=undefined or "the metric denominator is zero",
        )
    return DenominatedMetric(
        value=numerator / denominator,
        numerator=numerator,
        denominator=denominator,
        denominator_meaning=meaning,
    )


def discoverable_listings(timeline: PublicTimeline) -> tuple[str, ...]:
    """Listings the timeline has shown, in canonical order.

    Published as a function of public input so a consumer knows the scope of the task
    without opening the answer key - the defect issue #50 shipped, where the pairs to
    decide existed only in evaluator truth.
    """

    return tuple(
        sorted(
            {
                item.object_ref
                for item in timeline.events
                if item.object_ref is not None
                and item.kind is PrivacyEventKind.LISTING_DISCOVERED
            }
        )
    )


def evaluate_broker_assessment(
    assessment: BrokerAssessment,
    *,
    timeline: PublicTimeline,
    truth: TemporalTruth,
) -> BrokerRemovalMetrics:
    """Score one tick's submission. The only place public and truth meet."""

    if assessment.as_of != timeline.as_of:
        raise BrokerEvaluationError(
            "the assessment and the timeline describe different ticks"
        )
    discoverable = discoverable_listings(timeline)
    submitted = {item.listing_ref: item for item in assessment.listings}
    if not set(submitted) <= set(discoverable):
        raise BrokerEvaluationError(
            "an assessment names a listing the timeline has not discovered"
        )

    known = {item.listing_ref: item for item in truth.listings}
    missing = set(discoverable) - set(known)
    if missing:
        raise BrokerEvaluationError(
            f"truth does not cover {len(missing)} discovered listing(s)"
        )

    tick = assessment.as_of
    abstained = sum(1 for item in submitted.values() if item.concerns_subject is None)
    false_attributions = missed_attributions = attribution_correct = 0
    unwarranted_requests = warranted = request_correct = 0
    false_completions = missed_completions = completion_correct = 0
    overstated = propagation_scored = propagation_correct = 0
    recurrence_total = recurrence_found = 0

    for reference in discoverable:
        fact = known[reference]
        # Truth is read *as of this tick*: a removal that has not happened yet is not
        # a removal the system was wrong to deny.
        really_removed = fact.removed_at is not None and fact.removed_at <= tick
        really_back = fact.reappeared_at is not None and fact.reappeared_at <= tick
        gone_now = really_removed and not really_back
        copies_survive = bool(fact.downstream_refs) and really_removed

        if really_back:
            recurrence_total += 1

        answer = submitted.get(reference)
        if answer is None:
            # Not assessed at all. Counted only against discovery coverage - inventing
            # a wrong answer on the system's behalf would make silence look like error.
            continue

        if answer.concerns_subject is not None:
            if answer.concerns_subject == fact.concerns_subject:
                attribution_correct += 1
            elif answer.concerns_subject:
                false_attributions += 1
            else:
                missed_attributions += 1

        if fact.concerns_subject:
            warranted += 1
            request_correct += answer.requested_removal
        elif answer.requested_removal:
            unwarranted_requests += 1

        if answer.believed_removed == gone_now:
            completion_correct += 1
        elif answer.believed_removed:
            false_completions += 1
        else:
            missed_completions += 1

        if really_removed:
            propagation_scored += 1
            if answer.believed_propagated == copies_survive:
                propagation_correct += 1
            elif copies_survive:
                overstated += 1

        if really_back:
            recurrence_found += answer.reappearance_alerted

    assessed = len(submitted)
    decided = assessed - abstained
    return BrokerRemovalMetrics(
        as_of=tick,
        discoverable_count=len(discoverable),
        assessed_count=assessed,
        abstained_count=abstained,
        discovery_coverage=_metric(
            assessed, len(discoverable), "listings the timeline has discovered"
        ),
        false_attributions=false_attributions,
        missed_attributions=missed_attributions,
        attribution_accuracy=_metric(
            attribution_correct, decided, "listings attributed rather than abstained"
        ),
        unwarranted_requests=unwarranted_requests,
        request_correctness=_metric(
            request_correct, warranted, "listings that really concern the subject"
        ),
        false_completions=false_completions,
        missed_completions=missed_completions,
        completion_accuracy=_metric(completion_correct, assessed, "listings assessed"),
        overstated_propagation=overstated,
        propagation_accuracy=_metric(
            propagation_correct, propagation_scored, "listings really removed by now"
        ),
        recurrence_count=recurrence_total,
        recurrence_detected=recurrence_found,
        recurrence_recall=_metric(
            recurrence_found, recurrence_total, "listings that have really reappeared"
        ),
    )


def believe_the_broker(timeline: PublicTimeline) -> BrokerAssessment:
    """The baseline the pack exists to defeat: trust every confirmation.

    Scores perfectly on the six cases where the broker told the truth and fails the
    phantom, the reseller copies and the reappearance. A pack on which this scores
    cleanly is not measuring anything.
    """

    # Read from the vocabulary rather than written as a literal, so a change to the
    # lifecycle cannot silently change what this baseline believes.
    confirmed = _LIFECYCLE_ORDER[PrivacyEventKind.REMOVAL_CONFIRMED]
    return BrokerAssessment(
        as_of=timeline.as_of,
        listings=tuple(
            ListingAssessment(
                listing_ref=reference,
                concerns_subject=True,
                believed_removed=(lifecycle_stage(timeline.events, reference) or 0)
                >= confirmed,
                requested_removal=True,
                believed_propagated=False,
                reappearance_alerted=False,
            )
            for reference in discoverable_listings(timeline)
        ),
    )


def watch_after_confirmation(timeline: PublicTimeline) -> BrokerAssessment:
    """A better baseline: keeps watching, so it catches the public reappearance.

    Still cannot see the phantom removal or the surviving copies, because neither is
    in the public timeline at all. The gap between this and a perfect score is exactly
    the part of the task that is not free.
    """

    reappeared = {
        item.object_ref
        for item in timeline.events
        if item.kind is PrivacyEventKind.LISTING_REAPPEARED and item.object_ref
    }
    baseline = believe_the_broker(timeline)
    return BrokerAssessment(
        as_of=timeline.as_of,
        listings=tuple(
            item.model_copy(
                update={
                    "believed_removed": item.believed_removed
                    and item.listing_ref not in reappeared,
                    "reappearance_alerted": item.listing_ref in reappeared,
                }
            )
            for item in baseline.listings
        ),
    )


BROKER_BASELINES: tuple[
    tuple[str, Callable[[PublicTimeline], BrokerAssessment]], ...
] = (
    ("Believes every broker confirmation", believe_the_broker),
    ("Keeps watching after confirmation", watch_after_confirmation),
)


def run_broker_baseline(
    policy: Callable[[PublicTimeline], BrokerAssessment],
    *,
    timeline: PublicTimeline,
    truth: TemporalTruth,
) -> BrokerRemovalMetrics:
    """Score one reference policy, so CI can assert none of them resolves the pack."""

    return evaluate_broker_assessment(policy(timeline), timeline=timeline, truth=truth)


__all__ = [
    "BROKER_BASELINES",
    "BROKER_SCORING_VERSION",
    "BrokerAssessment",
    "BrokerEvaluationError",
    "BrokerRemovalMetrics",
    "ListingAssessment",
    "believe_the_broker",
    "discoverable_listings",
    "evaluate_broker_assessment",
    "run_broker_baseline",
    "watch_after_confirmation",
]
