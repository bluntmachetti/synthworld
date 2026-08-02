"""Scoring for the broker deletion-and-reappearance pack, issue #5.

A removal workflow can fail in six ways that no single number can distinguish, so
this reports six families and never combines them. They are separately *reportable*
rather than independent: a listing that has come back is not gone, so recurrence and
completion move together on that listing by construction. What the separation buys is
that a failure in one cannot be paid for by a success in another.

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
stops watching once it sees a confirmation never sees this, and is also wrong about
that listing's completion, which is the coupling noted above.

Every score carries its numerator, denominator and the denominator's meaning, matching
:class:`~synthworld.ambiguity_partition.DenominatedMetric`. A serialized report that
cannot be re-derived is one a reader has to trust rather than check.

Every family is denominated over the listings the timeline *showed*, not over the ones
a system chose to answer. Declining to assess is a miss rather than an exemption -
otherwise assessing one listing well beats assessing seven honestly.

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
    PrivacyEventKind,
    PublicTimeline,
    TemporalTruth,
)

BROKER_SCORING_VERSION: Literal["1.0.0"] = "1.0.0"


class BrokerEvaluationError(ValueError):
    """Raised when a submission, timeline and truth do not describe one another."""


class ListingAssessment(SyntheticModel):
    """What a system concluded about one listing, at one tick.

    ``concerns_subject`` is ``None`` for an abstention, which avoids being charged a
    *false* attribution without removing the listing from the denominator. Note the
    narrowness: only attribution can be abstained from. ``believed_removed`` and
    ``requested_removal`` are required, so a submission always makes those two claims.
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
    """One tick's submission. Partial and empty submissions are valid.

    Public-only: nothing reachable from it touches evaluator truth. A listing left out
    is scored as a miss rather than excluded, so partial is allowed but not free.
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
    as_of: int = Field(ge=0)
    #: Listings the public timeline had discovered by `as_of`. Every family is scored
    #: over this, so declining to assess costs rather than shrinks the denominator.
    discoverable_count: int = Field(ge=0)
    assessed_count: int = Field(ge=0)
    abstained_count: int = Field(ge=0)
    discovery_coverage: DenominatedMetric
    #: Attributed a listing to the subject that is someone else's, and the reverse.
    false_attributions: int = Field(ge=0)
    missed_attributions: int = Field(ge=0)
    attribution_accuracy: DenominatedMetric
    #: Asked for removal of a listing that is not the subject's. The precision half of
    #: this family: `request_recall` alone is maximised by requesting everything.
    unwarranted_requests: int = Field(ge=0)
    #: Named recall, not correctness. Its denominator is the listings that really are
    #: the subject's, so correctly *withholding* a request contributes nothing to it -
    #: that shows up in `unwarranted_requests`. The two are read together or not at all.
    request_recall: DenominatedMetric
    #: Believed a listing gone when it is not, and the reverse. The phantom case makes
    #: the first of these unreachable from public evidence alone.
    false_completions: int = Field(ge=0)
    missed_completions: int = Field(ge=0)
    completion_accuracy: DenominatedMetric
    #: Listings whose copies survive that the system said were not propagated. Named
    #: for what it counts: a first revision called it `overstated_propagation` and
    #: documented it as "called fully done", but it fires regardless of what the system
    #: claimed about completion.
    missed_surviving_copies: int
    propagation_accuracy: DenominatedMetric
    #: Reappearances by `as_of`, and how many were alerted.
    recurrence_count: int = Field(ge=0)
    recurrence_detected: int = Field(ge=0)
    #: Alerts raised on listings that have not reappeared. Without this, recall is a
    #: free family: alerting on everything scored a perfect 1.0 at no cost, and the
    #: report could not tell a spammer from a system that was watching.
    false_recurrence_alerts: int = Field(ge=0)
    recurrence_recall: DenominatedMetric

    @model_validator(mode="after")
    def require_counts_to_fit_their_denominators(self) -> Self:
        if self.assessed_count > self.discoverable_count:
            raise ValueError("more listings were assessed than were discoverable")
        if self.abstained_count > self.assessed_count:
            raise ValueError("more listings were abstained on than were assessed")
        if self.recurrence_detected > self.recurrence_count:
            raise ValueError("more reappearances were detected than occurred")
        return self


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
    missed_copies = propagation_scored = propagation_correct = 0
    recurrence_total = recurrence_found = false_alerts = 0

    for reference in discoverable:
        fact = known[reference]
        # Truth is read *as of this tick*: a removal that has not happened yet is not
        # a removal the system was wrong to deny.
        really_removed = fact.removed_at is not None and fact.removed_at <= tick
        really_back = fact.reappeared_at is not None and fact.reappeared_at <= tick
        gone_now = really_removed and not really_back
        copies_survive = bool(fact.downstream_refs) and really_removed

        # Every family is denominated over what the timeline *showed*, not over what
        # the system chose to answer. A first revision denominated four of them over
        # assessed listings, and that made silence free: assessing only the one listing
        # carrying a public reappearance tied the truth-perfect oracle on five families
        # at one-seventh coverage. Declining to answer is a miss, not an exemption.
        if fact.concerns_subject:
            warranted += 1
        if really_removed:
            propagation_scored += 1
        if really_back:
            recurrence_total += 1

        answer = submitted.get(reference)
        if answer is None:
            # Nothing is invented on the system's behalf - it is not charged a *false*
            # anything - but the denominators above already counted this listing, so
            # the omission shows up as a miss in every family it belonged to.
            continue

        if answer.concerns_subject is not None:
            if answer.concerns_subject == fact.concerns_subject:
                attribution_correct += 1
            elif answer.concerns_subject:
                false_attributions += 1
            else:
                missed_attributions += 1

        if fact.concerns_subject:
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
            if answer.believed_propagated == copies_survive:
                propagation_correct += 1
            elif copies_survive:
                missed_copies += 1

        if really_back:
            recurrence_found += answer.reappearance_alerted
        elif answer.reappearance_alerted:
            false_alerts += 1

    assessed = len(submitted)
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
            attribution_correct,
            len(discoverable),
            "listings the timeline has discovered",
        ),
        unwarranted_requests=unwarranted_requests,
        request_recall=_metric(
            request_correct,
            warranted,
            "discovered listings that really concern the subject",
        ),
        false_completions=false_completions,
        missed_completions=missed_completions,
        completion_accuracy=_metric(
            completion_correct,
            len(discoverable),
            "listings the timeline has discovered",
        ),
        missed_surviving_copies=missed_copies,
        propagation_accuracy=_metric(
            propagation_correct,
            propagation_scored,
            "discovered listings really removed by now",
        ),
        recurrence_count=recurrence_total,
        recurrence_detected=recurrence_found,
        false_recurrence_alerts=false_alerts,
        recurrence_recall=_metric(
            recurrence_found,
            recurrence_total,
            "listings that have really reappeared, assessed or not",
        ),
    )


def believe_the_broker(timeline: PublicTimeline) -> BrokerAssessment:
    """The baseline the pack exists to defeat: trust every confirmation.

    Believes a listing is gone exactly when a confirmation was published, attributes
    every listing to the subject and asks for every removal. It therefore fails the
    phantom removal, the reseller copies, the reappearance *and* the listing that was
    never the subject's - the last of which is publicly visible, so this is not a
    ceiling on what a good system can do. A pack on which this scores cleanly is not
    measuring anything.
    """

    # Read the confirming *event*, not a lifecycle ordinal. A first revision compared
    # `lifecycle_stage(...) >= _LIFECYCLE_ORDER[REMOVAL_CONFIRMED]`, and those integers
    # order the vocabulary for reading only - refusal and confirmation share the value
    # 3 - so the baseline believed a refused listing had been removed. The comment
    # above it claimed reading from the vocabulary made the baseline safe from exactly
    # that. It caused it.
    confirmed = {
        item.object_ref
        for item in timeline.events
        if item.kind is PrivacyEventKind.REMOVAL_CONFIRMED and item.object_ref
    }
    return BrokerAssessment(
        as_of=timeline.as_of,
        listings=tuple(
            ListingAssessment(
                listing_ref=reference,
                concerns_subject=True,
                believed_removed=reference in confirmed,
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
