"""A worked Idcognito-style adapter for the broker-removal pack (#5).

The adapter pattern, end to end: hold **only** the public timeline, decide per listing,
emit a versioned :class:`BrokerAssessment`, and hand it to the unified evaluator, which
regenerates the world from the seed and scores against physically separate truth. At no
point does the adapter see a truth object, and nothing it emits could carry one.

The decision logic here is deliberately modest - real products do better - but it is
honest about the three things the pack punishes pretending about:

- it attributes only listings whose public record can settle attribution, abstaining on
  bare ones rather than guessing;
- it requests removal only for listings it itself attributed, because the pack
  contains a stranger's record and prices asking for its removal;
- it believes a removal only after a published confirmation, and keeps watching
  afterwards, alerting if the listing reappears in later events;
- it predicts propagation to complete a fixed grace period after confirmation, rather
  than claiming "done means done everywhere" - the credulous baseline's lag error is
  exactly that claim's size.

Run: ``uv run python examples/evaluate_broker_adapter.py --seed 11``
"""

from __future__ import annotations

import argparse

from synthworld.broker_metrics import BrokerAssessment, ListingAssessment
from synthworld.evaluation import EvaluationReport, evaluate_broker_removal
from synthworld.temporal import (
    ListingAttributeKind,
    PrivacyEventKind,
    PublicTimeline,
    materialise,
)
from synthworld.temporal_generator import generate_temporal_world

#: How many ticks after a confirmation this adapter expects downstream copies to take.
#: A real product would learn this per broker; the point is that it is a *prediction
#: about lag*, which the assessment schema can now express (#65).
_PROPAGATION_GRACE = 10


def assess(timeline: PublicTimeline) -> BrokerAssessment:
    """Decide every discovered listing from public events alone."""

    confirmed_at: dict[str, int] = {}
    reappeared: set[str] = set()
    discovered: list[str] = []
    for event in timeline.events:
        if event.object_ref is None:
            continue
        if event.kind is PrivacyEventKind.LISTING_DISCOVERED:
            discovered.append(event.object_ref)
        elif event.kind is PrivacyEventKind.REMOVAL_CONFIRMED:
            confirmed_at.setdefault(event.object_ref, event.tick)
        elif event.kind is PrivacyEventKind.LISTING_REAPPEARED:
            reappeared.add(event.object_ref)

    # The subject's published addresses, from the same public events. Attribution is
    # decided by comparing page content against them - and abstained on when the page
    # carries nothing comparable, because a guess is scored as unwarranted, not brave.
    subject_addresses = {
        event.detail
        for event in timeline.events
        if event.kind is PrivacyEventKind.ADDRESS_CHANGED and event.detail
    }
    pages = {listing.listing_ref: listing for listing in timeline.listings}

    def attributed(reference: str) -> bool | None:
        page = pages.get(reference)
        if page is None or not page.attributes:
            return None
        return any(
            item.value in subject_addresses
            for item in page.attributes
            if item.kind is ListingAttributeKind.ADDRESS
        )

    def decide(reference: str) -> ListingAssessment:
        confirmation = confirmed_at.get(reference)
        back = reference in reappeared
        gone = confirmation is not None and not back
        return ListingAssessment(
            listing_ref=reference,
            # Abstain where the public record cannot settle it - a guess would score
            # as an unwarranted decision, not a brave one.
            concerns_subject=attributed(reference),
            believed_removed=gone,
            # Request only what the adapter itself attributed. Requesting everything
            # maximises recall and is exactly what `unwarranted_requests` prices: the
            # pack contains a stranger's listing, and asking a broker to remove it is
            # the conduct a removal product must not learn.
            requested_removal=attributed(reference) is True,
            believed_propagated=False,
            reappearance_alerted=back,
            expected_propagation_complete_by=(
                None if confirmation is None else confirmation + _PROPAGATION_GRACE
            ),
        )

    return BrokerAssessment(
        as_of=timeline.as_of,
        listings=tuple(decide(reference) for reference in discovered),
    )


def run(seed: int) -> EvaluationReport:
    """Generate, project, assess from public data only, and score."""

    world = generate_temporal_world(seed=seed)
    timeline = materialise(world, as_of=world.horizon)
    return evaluate_broker_removal(assess(timeline), seed=seed)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=11)
    report = run(parser.parse_args().seed)
    print(f"task={report.task} seed={report.seed} scoring={report.scoring_version}")
    for metric in report.metrics:
        value = "undefined" if metric.value is None else f"{metric.value:.4f}"
        print(f"  {metric.family:>15}  {metric.name:<28} {value:>9} n={metric.support}")


if __name__ == "__main__":
    main()
