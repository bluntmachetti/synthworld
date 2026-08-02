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
    match_on_published_evidence,
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
def test_believing_the_broker_fails_the_cases_it_cannot_see(seed: int) -> None:
    """The phantom, the surviving copies and the reappearance.

    Not *only* those - it also attributes the false match to the subject and asks
    for its removal, which are publicly visible failures. An earlier version of this
    test said "and nothing else", which was wrong, and the wrongness mattered: it
    made the baseline look like a ceiling on what public evidence allows.
    """

    world, timeline = _at_horizon(seed)
    metrics = run_broker_baseline(
        believe_the_broker, timeline=timeline, truth=world.truth
    )

    assert metrics.discovery_coverage.value == 1.0
    assert metrics.missed_surviving_copies > 0
    assert metrics.recurrence_detected == 0
    assert metrics.recurrence_count > 0
    # It also asks for removal of a listing that is not the subject's.
    assert metrics.unwarranted_requests > 0


@pytest.mark.parametrize("seed", _SEEDS)
def test_watching_after_confirmation_gains_recurrence_and_completion(
    seed: int,
) -> None:
    """Catching the reappearance also corrects the completion claim for that listing.

    An earlier version said "and nothing else", which the arithmetic contradicts: a
    listing that has come back is not gone, so seeing the reappearance fixes two
    families at once. What neither baseline gains is the phantom or the copies.
    """

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
    assert watchful.missed_surviving_copies == naive.missed_surviving_copies


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


def test_a_reappearance_that_has_not_happened_yet_is_not_a_miss() -> None:
    """A future event is not one the system was wrong to stay silent about.

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


def test_abstaining_avoids_a_false_answer_but_is_not_free() -> None:
    """Declining is not an error; it is also not a way to keep a denominator small.

    Abstention shields the system from being charged a *false* attribution. It does
    not remove the listing from the denominator, because every family is scored over
    what the timeline showed rather than over what the system chose to answer.
    """

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
    assert metrics.unwarranted_attributions == 0
    # Credited only for the listing whose record genuinely cannot settle the question,
    # where declining is the right answer rather than a way of avoiding one.
    assert metrics.attribution_accuracy.value is not None
    assert 0.0 < metrics.attribution_accuracy.value < 0.5
    assert metrics.attribution_accuracy.denominator == len(scope)


def test_assessing_nothing_scores_nothing() -> None:
    """Silence must not buy a small denominator on the families it declined.

    A first revision denominated four families over *assessed* listings, so a system
    could assess only the single listing carrying a public reappearance and tie the
    truth-perfect oracle on five of the six at one-seventh coverage. Every denominator
    is the discovered world now, so an omission is a miss.
    """

    world, timeline = _at_horizon(17)
    empty = BrokerAssessment(as_of=timeline.as_of, listings=())
    metrics = evaluate_broker_assessment(empty, timeline=timeline, truth=world.truth)

    assert metrics.discovery_coverage.value == 0.0
    assert metrics.assessed_count == 0
    assert metrics.completion_accuracy.value == 0.0
    assert metrics.attribution_accuracy.value == 0.0
    assert metrics.recurrence_recall.value == 0.0


def test_a_sparse_submission_cannot_tie_a_complete_one() -> None:
    """The gaming strategy the denominator change exists to defeat.

    Assess only the listing carrying the public reappearance event, answer it
    perfectly, and ignore the rest. Under the old denominators that scored 1.0 on
    attribution, request, completion, propagation and recurrence alike.
    """

    world, timeline = _at_horizon(3)
    scope = discoverable_listings(timeline)
    reappeared = {
        item.object_ref
        for item in timeline.events
        if item.kind is PrivacyEventKind.LISTING_REAPPEARED and item.object_ref
    }
    facts = {item.listing_ref: item for item in world.truth.listings}
    sparse = BrokerAssessment(
        as_of=timeline.as_of,
        listings=tuple(
            ListingAssessment(
                listing_ref=reference,
                concerns_subject=facts[reference].concerns_subject,
                believed_removed=False,
                requested_removal=True,
                believed_propagated=False,
                reappearance_alerted=True,
            )
            for reference in scope
            if reference in reappeared
        ),
    )
    metrics = evaluate_broker_assessment(sparse, timeline=timeline, truth=world.truth)

    assert metrics.assessed_count == 1
    assert metrics.discovery_coverage.value is not None
    assert metrics.discovery_coverage.value < 0.2
    # Perfect on the one listing it answered, and nowhere near perfect overall.
    assert metrics.recurrence_recall.value == 1.0
    for family in ("attribution_accuracy", "completion_accuracy", "request_recall"):
        metric = getattr(metrics, family)
        assert metric.value is not None
        assert metric.value < 0.5


def test_every_score_publishes_the_denominator_it_used() -> None:
    """A report a reader cannot re-derive is one they have to trust."""

    world, timeline = _at_horizon(19)
    metrics = run_broker_baseline(
        watch_after_confirmation, timeline=timeline, truth=world.truth
    )

    for name in (
        "discovery_coverage",
        "attribution_accuracy",
        "request_recall",
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


def test_attribution_errors_in_both_directions_are_counted_separately() -> None:
    """Attribution has a counter each way. Propagation has one counter and a ratio.

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
    # `missed_surviving_copies` failure, which is calling a leaky removal complete.
    assert metrics.propagation_accuracy.value is not None
    assert metrics.propagation_accuracy.value < 1.0
    assert metrics.missed_surviving_copies == 0
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


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"assessed_count": 99}, "more listings were assessed"),
        ({"abstained_count": 8, "assessed_count": 7}, "more listings were abstained"),
        ({"recurrence_detected": 9}, "more reappearances were detected"),
        ({"false_attributions": -4}, "greater than or equal to 0"),
    ],
)
def test_an_arithmetically_impossible_report_is_refused(
    update: dict[str, int], message: str
) -> None:
    """A report is an artifact, so it has to be checkable on its own terms.

    The model previously accepted 99 listings assessed out of 7 discoverable, 9
    reappearances detected out of 1, and a negative error count. A consumer reading a
    serialized report has no way to tell those apart from a real one.
    """

    world, timeline = _at_horizon(3)
    metrics = run_broker_baseline(
        watch_after_confirmation, timeline=timeline, truth=world.truth
    )

    with pytest.raises(ValidationError, match=message):
        metrics.__class__.model_validate({**metrics.model_dump(), **update})


def test_attribution_is_answerable_from_published_evidence() -> None:
    """The contract question this pack could not answer before.

    Lifecycle events carried no content and the subject's identity was never published,
    so the listing that is *not* the subject's was publicly indistinguishable from
    those that are, in 50 of 50 seeds. Attribution could only be won by abstaining or
    guessing, which means the family measured luck.
    """

    world, timeline = _at_horizon(3)
    guessing = run_broker_baseline(
        believe_the_broker, timeline=timeline, truth=world.truth
    )
    reading = run_broker_baseline(
        match_on_published_evidence, timeline=timeline, truth=world.truth
    )

    assert reading.attribution_accuracy.value == 1.0
    assert reading.unwarranted_attributions == 0
    assert guessing.attribution_accuracy.value is not None
    assert guessing.attribution_accuracy.value < reading.attribution_accuracy.value
    assert guessing.unwarranted_attributions > 0
    # Reading the evidence buys attribution and nothing else: neither policy can see
    # the phantom removal, because no public event reveals it.
    assert reading.false_completions > 0


def test_deciding_an_unreadable_listing_is_unwarranted_not_wrong() -> None:
    """One listing carries a common name and nothing to corroborate it.

    Whatever the truth happens to be, the page cannot settle it, so declining is
    correct and deciding is unjustified rather than incorrect - the distinction the
    ambiguity and search packs already draw.
    """

    world, timeline = _at_horizon(3)
    unreadable = [item for item in world.truth.listings if not item.attributable]
    decisive = BrokerAssessment(
        as_of=timeline.as_of,
        listings=tuple(
            ListingAssessment(
                listing_ref=item.listing_ref,
                concerns_subject=True,
                believed_removed=False,
                requested_removal=True,
            )
            for item in unreadable
        ),
    )
    metrics = evaluate_broker_assessment(decisive, timeline=timeline, truth=world.truth)

    assert len(unreadable) == 1
    assert metrics.unwarranted_attributions == 1
    assert metrics.false_attributions == 0
    assert metrics.missed_attributions == 0


def test_a_claim_that_cannot_be_true_is_refused() -> None:
    """Believed removed *and* reappeared is not wrong, it is incoherent.

    A listing that has come back is not gone, and truth carries a single `removed_at`,
    so no world can make both right. Scoring an unsatisfiable claim as merely incorrect
    would tell a consumer their answer was wrong when it was meaningless.
    """

    with pytest.raises(ValidationError, match="cannot be believed removed"):
        ListingAssessment(
            listing_ref="listing-0001",
            concerns_subject=True,
            believed_removed=True,
            requested_removal=True,
            reappearance_alerted=True,
        )


def test_attribution_cannot_be_won_from_the_shape_of_a_record() -> None:
    """The evidence has to be in the values, not in how many of them there are.

    A first revision gave a matching page two attributes and a contradicting page one,
    in a different town. A decoder reading nothing but the attribute count scored 1.000
    on 75 of 75 held-out seeds, as did one grepping for the town name - so the values
    were decorative and the record's *shape* answered the question.
    """

    shapes: dict[int, set[bool]] = {}
    tokens: set[str] = set()
    for seed in range(40):
        world = generate_temporal_world(seed=seed)
        timeline = materialise(world, as_of=world.horizon)
        facts = {item.listing_ref: item for item in world.truth.listings}
        for record in timeline.listings:
            fact = facts[record.listing_ref]
            if not fact.attributable:
                continue
            shapes.setdefault(len(record.attributes), set()).add(fact.concerns_subject)
            tokens |= {
                item.value.split("|")[-3]
                for item in record.attributes
                if "|" in item.value
            }

    # Among readable pages, the attribute count says nothing about the answer.
    assert shapes
    assert all(len(outcomes) > 1 for outcomes in shapes.values())
    # And every address shares one town, so no token separates them either.
    assert len(tokens) == 1


def test_requesting_removal_of_an_unreadable_listing_is_unwarranted() -> None:
    """Acting on what you could not attribute is not free.

    The bare listing really is the subject's, so requesting its removal used to be pure
    upside: a policy that read the evidence and then requested everything anyway
    strictly dominated on 100 of 100 seeds while doing the thing the pack calls
    unwarranted.
    """

    world, timeline = _at_horizon(3)
    careful = match_on_published_evidence(timeline)
    greedy = BrokerAssessment(
        as_of=timeline.as_of,
        listings=tuple(
            item.model_copy(update={"requested_removal": True})
            for item in careful.listings
        ),
    )

    measured = [
        evaluate_broker_assessment(item, timeline=timeline, truth=world.truth)
        for item in (careful, greedy)
    ]

    assert measured[0].unwarranted_requests == 0
    assert measured[1].unwarranted_requests > 0
    assert measured[1].request_recall.value == measured[0].request_recall.value
