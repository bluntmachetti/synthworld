"""Scoring for the search projection, joined to truth only after processing.

A consumer decides, for each public result, whether it concerns the subject. The
join to truth happens here and nowhere earlier: the projection hands out opaque
result identifiers precisely so a system cannot reach truth while it is deciding.

Three things this reports that a single accuracy figure would hide.

**Accepts and rejects are separated.** Accepting someone else's record attaches a
stranger's exposure to a person; rejecting a real one leaves exposure unfound. They
are different harms and a single score trades them silently.

**Abstention is scoreable.** Some results are genuinely undecidable from the public
text, so a system that declines is right and one that guesses is not. Deciding an
`insufficient_evidence` result is counted apart - not a wrong answer, an
unwarranted one.

**Syndication is collapsed.** Three aggregator copies of one source record are one
finding. A consumer that counts them separately overstates exposure threefold, and
`distinct_findings` against `accepted_results` is where that shows.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import model_validator

from synthworld.models import SyntheticModel
from synthworld.search import SearchMatchTruth, SearchTruthBundle

SEARCH_SCORING_VERSION: Literal["1.0.0"] = "1.0.0"


class ResultDecision(StrEnum):
    """What a consumer concluded about one public result."""

    ACCEPT = "accept"
    REJECT = "reject"
    ABSTAIN = "abstain"


class ResultJudgement(SyntheticModel):
    """One decision, keyed by the opaque public identifier."""

    result_id: UUID
    decision: ResultDecision


class SearchEvaluationError(ValueError):
    """Raised when a submission does not cover the projection's results exactly."""


class DifficultyOutcome(SyntheticModel):
    """One difficulty tier, with the denominator its error count needs.

    Errors alone rank tiers backwards. On seed 1 the accept-everything baseline makes
    18 errors at difficulty 1 and 12 at difficulty 3, which reads as "tier 1 is where
    we fail". Tier 1 has 42 results and tier 3 has 12, so the rates are 0.43 and 1.00:
    total failure on the hardest tier, presented as the milder problem. A tier with no
    errors also has to appear, or its absence is indistinguishable from not existing.
    """

    difficulty: int
    support: int
    errors: int


class SearchMetrics(SyntheticModel):
    """No aggregate score: the separated counts are the report.

    Denominators are fields rather than prose, matching
    :class:`~synthworld.ambiguity_metrics.AmbiguityDispositionMetrics`: ``coverage``
    is ``decided_count / result_count``; ``decided_precision`` is
    ``correct_decided_count / decided_count``; ``decided_recall`` is
    ``correct_decided_count / decidable_count``. A serialized report that cannot be
    re-derived is one a reader has to trust rather than check.
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
    scoring_version: Literal["1.0.0"] = SEARCH_SCORING_VERSION
    task: Literal["search_result_decision"] = "search_result_decision"
    result_count: int
    decided_count: int
    abstained_count: int
    #: Results whose truth is not `insufficient_evidence`, and how many of those the
    #: submission decided correctly. The two denominators above, published.
    decidable_count: int
    correct_decided_count: int
    coverage: float
    #: Accepted a result that concerns someone else. Attaches a stranger's exposure.
    false_accepts: int
    #: Rejected a result that really concerns the subject. Leaves exposure unfound.
    false_rejects: int
    #: Decided a result the public text cannot settle. Not wrong - unwarranted.
    unwarranted_decisions: int
    decided_precision: float | None
    decided_recall: float | None
    #: Accepted results, and the number of distinct sources they represent. Equal
    #: only when a consumer has collapsed syndicated copies.
    accepted_results: int
    distinct_findings: int
    stale_accepted: int
    by_difficulty: tuple[DifficultyOutcome, ...] = ()


class SearchEvaluation(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    seed: int
    truth_schema_version: str
    metrics: SearchMetrics
    #: Echoed so a report cannot be paired with a projection it did not score. The
    #: public artifact's own schema version is not reachable from truth, and a field
    #: that has to be guessed is worse than one that is absent; the digest is what
    #: binds this report to a specific projection.
    public_digest: str

    @model_validator(mode="after")
    def require_digest(self) -> Self:
        if not self.public_digest:
            raise ValueError("an evaluation must name the projection it scored")
        return self


def evaluate_search_judgements(
    judgements: Iterable[ResultJudgement], *, truth: SearchTruthBundle
) -> SearchEvaluation:
    """Score decisions against truth. The only place the two meet."""

    expected = {item.result_id: item for item in truth.results}
    submitted: dict[UUID, ResultDecision] = {}
    for judgement in judgements:
        if judgement.result_id in submitted:
            raise SearchEvaluationError("a result was judged twice")
        submitted[judgement.result_id] = judgement.decision
    if set(submitted) != set(expected):
        raise SearchEvaluationError(
            "judgements must cover exactly the projection's results"
        )

    false_accepts = false_rejects = unwarranted = 0
    decided = correct = decidable = accepted = stale_accepted = 0
    groups: set[str] = set()
    ungrouped_accepts = 0
    difficulty: Counter[int] = Counter()

    for result_id, row in expected.items():
        decision = submitted[result_id]
        if row.match is not SearchMatchTruth.INSUFFICIENT_EVIDENCE:
            decidable += 1
        if decision is ResultDecision.ABSTAIN:
            continue
        decided += 1
        if decision is ResultDecision.ACCEPT:
            accepted += 1
            if row.syndication_group is not None:
                groups.add(row.syndication_group)
            else:
                ungrouped_accepts += 1
            if row.stale:
                stale_accepted += 1
        if row.match is SearchMatchTruth.INSUFFICIENT_EVIDENCE:
            unwarranted += 1
            difficulty[row.difficulty] += 1
            continue
        wanted = (
            ResultDecision.ACCEPT
            if row.match is SearchMatchTruth.TRUE_MATCH
            else ResultDecision.REJECT
        )
        if decision is wanted:
            correct += 1
        else:
            difficulty[row.difficulty] += 1
            if decision is ResultDecision.ACCEPT:
                false_accepts += 1
            else:
                false_rejects += 1

    total = len(expected)
    support: Counter[int] = Counter(row.difficulty for row in expected.values())
    return SearchEvaluation(
        seed=truth.seed,
        truth_schema_version=truth.schema_version,
        public_digest=truth.public_digest,
        metrics=SearchMetrics(
            result_count=total,
            decided_count=decided,
            abstained_count=total - decided,
            decidable_count=decidable,
            correct_decided_count=correct,
            coverage=decided / total,
            false_accepts=false_accepts,
            false_rejects=false_rejects,
            unwarranted_decisions=unwarranted,
            decided_precision=correct / decided if decided else None,
            decided_recall=correct / decidable if decidable else None,
            accepted_results=accepted,
            distinct_findings=len(groups) + ungrouped_accepts,
            stale_accepted=stale_accepted,
            # Every tier present in the projection, including the ones with no
            # errors: a missing key reads as "tier absent", not "tier clean".
            by_difficulty=tuple(
                DifficultyOutcome(
                    difficulty=tier,
                    support=support[tier],
                    errors=difficulty.get(tier, 0),
                )
                for tier in sorted(support)
            ),
        ),
    )


__all__ = [
    "SEARCH_SCORING_VERSION",
    "DifficultyOutcome",
    "ResultDecision",
    "ResultJudgement",
    "SearchEvaluation",
    "SearchEvaluationError",
    "SearchMetrics",
    "evaluate_search_judgements",
]
