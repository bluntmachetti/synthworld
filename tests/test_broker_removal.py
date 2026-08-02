"""What the broker pack has to prove: six failures stay separate, and none is free."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from synthworld.broker_metrics import (
    BROKER_BASELINES,
    BrokerAssessment,
    BrokerEvaluationError,
    ListingAssessment,
    believe_the_broker,
    discoverable_listings,
    evaluate_broker_assessment,
    run_broker_baseline,
    watch_after_confirmation,
)
from synthworld.temporal import (
    PrivacyEventKind,
    PublicTimeline,
    TemporalWorld,
    materialise,
)
from synthworld.temporal_generator import generate_temporal_world

_SEEDS = (1, 7, 42)


def _at_horizon(seed: int) -> tuple[TemporalWorld, PublicTimeline]:
    world = generate_temporal_world(seed=seed)
    return world, materialise(world, as_of=world.horizon)


@pytest.mark.parametrize("seed", _SEEDS)
def test_no_baseline_resolves_the_pack(seed: int) -> None:
    """The property, not a number. A pack a reference policy solves measures nothing."""

    world, timeline = _at_horizon(seed)
    for _name, policy in BROKER_BASELINES:
        metrics = run_broker_baseline(policy, timeline=timeline, truth=world.truth)

        assert metrics.completion_accuracy.value is not None
        assert metrics.completion_accuracy.value < 1.0
        assert metrics.false_completions > 0


@pytest.mark.parametrize("seed", _SEEDS)
def test_believing_the_broker_misses_exactly_what_it_cannot_see(seed: int) -> None:
    """The phantom, the surviving copies and the reappearance - and nothing else.

    Trusting confirmations is not stupidity: it is correct on every case where the
    broker told the truth. What separates it from a good system is the three cases the
    public timeline cannot settle, so those are what its errors must be.
    """

    world, timeline = _at_horizon(seed)
    metrics = run_broker_baseline(
        believe_the_broker, timeline=timeline, truth=world.truth
    )

    assert metrics.discovery_coverage.value == 1.0
    assert metrics.overstated_propagation > 0
    assert metrics.recurrence_detected == 0
    assert metrics.recurrence_count > 0
    # It also asks for removal of a listing that is not the subject's.
    assert metrics.unwarranted_requests > 0


@pytest.mark.parametrize("seed", _SEEDS)
def test_watching_after_confirmation_gains_recurrence_and_nothing_else(
    seed: int,
) -> None:
    """The gap between the two baselines is exactly the publicly visible part."""

    world, timeline = _at_horizon(seed)
    naive = run_broker_baseline(
        believe_the_broker, timeline=timeline, truth=world.truth
    )
    watchful = run_broker_baseline(
        watch_after_confirmation, timeline=timeline, truth=world.truth
    )

    assert watchful.recurrence_detected == watchful.recurrence_count
    assert naive.recurrence_detected == 0
    # Neither can see the phantom removal or the reseller copies.
    assert watchful.false_completions > 0
    assert watchful.overstated_propagation == naive.overstated_propagation


def test_the_scope_of_the_task_is_public() -> None:
    """A consumer must learn which listings to assess without opening truth."""

    world, timeline = _at_horizon(3)
    scope = discoverable_listings(timeline)
    discovered = {
        item.object_ref
        for item in timeline.events
        if item.kind is PrivacyEventKind.LISTING_DISCOVERED and item.object_ref
    }

    assert set(scope) == discovered
    assert list(scope) == sorted(scope)
    assert set(scope) <= {item.listing_ref for item in world.truth.listings}


def test_truth_is_read_as_of_the_tick_being_scored() -> None:
    """A removal that has not happened yet is not one the system was wrong to deny.

    Scoring an early tick against final truth would punish a correct answer for being
    given before the fact, which is the opposite of what a temporal benchmark is for.
    """

    world = generate_temporal_world(seed=11)
    reappeared_at = next(
        item.reappeared_at
        for item in world.truth.listings
        if item.reappeared_at is not None
    )
    before = reappeared_at - 1
    timeline = materialise(world, as_of=before)
    scope = discoverable_listings(timeline)

    silent = BrokerAssessment(
        as_of=before,
        listings=tuple(
            ListingAssessment(
                listing_ref=reference,
                concerns_subject=True,
                believed_removed=False,
                requested_removal=True,
                reappearance_alerted=False,
            )
            for reference in scope
        ),
    )
    metrics = evaluate_broker_assessment(silent, timeline=timeline, truth=world.truth)

    # The reappearance has not happened yet, so not alerting is not a miss.
    assert metrics.recurrence_count == 0
    assert metrics.recurrence_recall.value is None


def test_abstention_is_recorded_rather_than_scored_as_error() -> None:
    world, timeline = _at_horizon(13)
    scope = discoverable_listings(timeline)
    abstaining = BrokerAssessment(
        as_of=timeline.as_of,
        listings=tuple(
            ListingAssessment(
                listing_ref=reference,
                concerns_subject=None,
                believed_removed=False,
                requested_removal=False,
            )
            for reference in scope
        ),
    )
    metrics = evaluate_broker_assessment(
        abstaining, timeline=timeline, truth=world.truth
    )

    assert metrics.abstained_count == len(scope)
    assert metrics.false_attributions == 0
    assert metrics.missed_attributions == 0
    assert metrics.attribution_accuracy.value is None


def test_assessing_nothing_shows_up_in_coverage_not_in_accuracy() -> None:
    """Silence must not buy a perfect score on the families it declined to answer."""

    world, timeline = _at_horizon(17)
    empty = BrokerAssessment(as_of=timeline.as_of, listings=())
    metrics = evaluate_broker_assessment(empty, timeline=timeline, truth=world.truth)

    assert metrics.discovery_coverage.value == 0.0
    assert metrics.assessed_count == 0
    assert metrics.completion_accuracy.value is None


def test_every_score_publishes_the_denominator_it_used() -> None:
    """A report a reader cannot re-derive is one they have to trust."""

    world, timeline = _at_horizon(19)
    metrics = run_broker_baseline(
        watch_after_confirmation, timeline=timeline, truth=world.truth
    )

    for name in (
        "discovery_coverage",
        "attribution_accuracy",
        "request_correctness",
        "completion_accuracy",
        "propagation_accuracy",
        "recurrence_recall",
    ):
        metric = getattr(metrics, name)
        assert metric.denominator_meaning
        if metric.value is not None:
            assert metric.value == pytest.approx(metric.numerator / metric.denominator)


def test_a_submission_for_the_wrong_tick_is_refused() -> None:
    world, timeline = _at_horizon(23)
    assessment = believe_the_broker(timeline)

    with pytest.raises(BrokerEvaluationError, match="different ticks"):
        evaluate_broker_assessment(
            assessment.model_copy(update={"as_of": timeline.as_of - 1}),
            timeline=timeline,
            truth=world.truth,
        )


def test_a_submission_naming_an_undiscovered_listing_is_refused() -> None:
    """Otherwise a system can be credited for a listing it was never shown."""

    world, timeline = _at_horizon(29)
    assessment = believe_the_broker(timeline)
    invented = BrokerAssessment(
        as_of=timeline.as_of,
        listings=(
            *assessment.listings,
            ListingAssessment(
                listing_ref="listing-invented",
                concerns_subject=True,
                believed_removed=True,
                requested_removal=True,
            ),
        ),
    )

    with pytest.raises(BrokerEvaluationError, match="has not discovered"):
        evaluate_broker_assessment(invented, timeline=timeline, truth=world.truth)


def test_a_listing_assessed_twice_is_refused() -> None:
    _world, timeline = _at_horizon(31)
    one = believe_the_broker(timeline).listings[0]

    with pytest.raises(ValidationError, match="assessed twice"):
        BrokerAssessment(as_of=timeline.as_of, listings=(one, one))


def test_truth_missing_a_discovered_listing_is_refused() -> None:
    world, timeline = _at_horizon(37)
    assessment = believe_the_broker(timeline)
    thinned = world.truth.model_copy(update={"listings": world.truth.listings[:1]})

    with pytest.raises(BrokerEvaluationError, match="does not cover"):
        evaluate_broker_assessment(assessment, timeline=timeline, truth=thinned)


def test_the_opposite_errors_are_counted_separately() -> None:
    """Under-claiming is a different failure from over-claiming, and both are real.

    The reference policies only ever err in one direction — they trust the broker and
    attribute everything to the subject — so a submission that errs the other way is
    built by hand. Denying a listing that really is the subject's leaves exposure
    unfound; claiming copies survive where none do sends a user chasing nothing.
    """

    world, timeline = _at_horizon(43)
    scope = discoverable_listings(timeline)
    truth = {item.listing_ref: item for item in world.truth.listings}

    contrarian = BrokerAssessment(
        as_of=timeline.as_of,
        listings=tuple(
            ListingAssessment(
                listing_ref=reference,
                # Exactly wrong on attribution, in the direction no baseline takes.
                concerns_subject=not truth[reference].concerns_subject,
                believed_removed=False,
                requested_removal=False,
                believed_propagated=True,
            )
            for reference in scope
        ),
    )
    metrics = evaluate_broker_assessment(
        contrarian, timeline=timeline, truth=world.truth
    )

    assert metrics.missed_attributions > 0
    assert metrics.false_attributions > 0
    assert metrics.attribution_accuracy.value == 0.0
    # Claiming propagation where no copies survive is wrong, but it is not the
    # `overstated_propagation` failure, which is calling a leaky removal complete.
    assert metrics.propagation_accuracy.value is not None
    assert metrics.propagation_accuracy.value < 1.0
    assert metrics.overstated_propagation == 0
    # It never asked for removal, so nothing it did was unwarranted.
    assert metrics.unwarranted_requests == 0


def test_a_refusal_is_not_a_confirmation() -> None:
    """The bug a comment about avoiding hard-coded values introduced.

    `believe_the_broker` compared `lifecycle_stage(...) >= _LIFECYCLE_ORDER[
    REMOVAL_CONFIRMED]`. Those integers order the vocabulary for reading only, and
    refusal shares the value 3 with confirmation, so the baseline believed a refused
    listing had been removed - a failure on a case where the broker told the truth,
    and one that is publicly visible.
    """

    world, timeline = _at_horizon(3)
    refused = {
        item.object_ref
        for item in timeline.events
        if item.kind is PrivacyEventKind.REMOVAL_REFUSED and item.object_ref
    }
    assessment = believe_the_broker(timeline)
    by_reference = {item.listing_ref: item for item in assessment.listings}

    assert refused
    assert all(not by_reference[item].believed_removed for item in refused)
    # And what it still gets wrong is the phantom, which no public event reveals.
    metrics = evaluate_broker_assessment(
        assessment, timeline=timeline, truth=world.truth
    )
    assert metrics.false_completions > 0


def test_alerting_on_everything_is_no_longer_free() -> None:
    """Recall alone made recurrence a family a spammer could win outright."""

    world, timeline = _at_horizon(3)
    scope = discoverable_listings(timeline)
    spam = BrokerAssessment(
        as_of=timeline.as_of,
        listings=tuple(
            ListingAssessment(
                listing_ref=reference,
                concerns_subject=True,
                believed_removed=False,
                requested_removal=True,
                reappearance_alerted=True,
            )
            for reference in scope
        ),
    )
    metrics = evaluate_broker_assessment(spam, timeline=timeline, truth=world.truth)
    watchful = run_broker_baseline(
        watch_after_confirmation, timeline=timeline, truth=world.truth
    )

    # It matches the watchful baseline's headline recall...
    assert metrics.recurrence_recall.value == watchful.recurrence_recall.value
    # ...and the report tells them apart anyway.
    assert metrics.false_recurrence_alerts > 0
    assert watchful.false_recurrence_alerts == 0
