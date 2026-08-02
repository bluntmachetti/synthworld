"""Contracts for the human identity-resolution ambiguity pack.

Issue #41 exists because a resolver scored pairwise F1 1.0 on the 18-record pack
while a one-factor mutation matrix broke it four different ways. A perfect
aggregate on positives that align with exact joins is not evidence of anything, so
this pack pairs every positive with a negative control that punishes the shortcut.

**Two truths, deliberately separate.** Canonical entity membership says who someone
really is. Pair disposition says what the *public record pair* justifies. They
disagree on purpose: two records can belong to one person while the public evidence
supports only ``insufficient``, and a system that merges them is guessing, not
resolving. Collapsing the two would make abstention unscoreable and reward
confident guessing, which is the failure this pack is built to expose.

The prediction contract is versioned independently of the cluster contract in
:mod:`synthworld.connection`. That contract is unchanged and remains valid on its
own; a system that only emits clusters is scored exactly as before.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from synthworld.connection import PublicConnectionCorpus, RecordMembership
from synthworld.models import SyntheticModel

AMBIGUITY_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"


class PairDisposition(StrEnum):
    """What the public evidence for a record pair justifies.

    ``INSUFFICIENT`` is not a third kind of answer between the other two. It is a
    claim about the *evidence*, not about the people: the pack contains pairs that
    are genuinely the same person and pairs that are genuinely different, both of
    which a correct system must decline to decide on public evidence alone.
    """

    MERGE = "merge"
    SEPARATE = "separate"
    INSUFFICIENT = "insufficient"


class ScenarioKind(StrEnum):
    """The case matrix required by issue #41, one member per required scenario."""

    # Must remain separate: each is a shortcut a resolver is tempted to take.
    RECYCLED_PHONE = "recycled_phone"
    SHARED_HOUSEHOLD_EMAIL = "shared_household_email"
    REUSED_USERNAME = "reused_username"
    SHARED_EMPLOYER_AND_ADDRESS = "shared_employer_and_address"
    SAME_NAME_AND_DATE_OF_BIRTH = "same_name_and_date_of_birth"
    CONTRADICTORY_STRONG_IDENTIFIERS = "contradictory_strong_identifiers"
    TWINS_OVERLAPPING_CONTEXT = "twins_overlapping_context"

    # Must resolve to the same entity.
    STALE_ATTRIBUTE = "stale_attribute"
    ALIAS_CHANGE = "alias_change"
    UNICODE_VARIANT = "unicode_variant"
    PARTIAL_BUT_SUFFICIENT = "partial_but_sufficient"
    DUPLICATE_OBSERVATION = "duplicate_observation"

    # Public evidence is insufficient, whatever the canonical truth happens to be.
    SINGLE_UNCORROBORATED_ATTRIBUTE = "single_uncorroborated_attribute"
    PARTIAL_WITH_CONTRADICTION = "partial_with_contradiction"
    SPARSE_RECORDS = "sparse_records"


#: The disposition each scenario must carry. Declared here rather than inferred
#: from the data, so a fixture that plants the wrong disposition fails a test
#: instead of silently redefining the scenario.
SCENARIO_DISPOSITIONS: dict[ScenarioKind, PairDisposition] = {
    ScenarioKind.RECYCLED_PHONE: PairDisposition.SEPARATE,
    ScenarioKind.SHARED_HOUSEHOLD_EMAIL: PairDisposition.SEPARATE,
    ScenarioKind.REUSED_USERNAME: PairDisposition.SEPARATE,
    ScenarioKind.SHARED_EMPLOYER_AND_ADDRESS: PairDisposition.SEPARATE,
    ScenarioKind.SAME_NAME_AND_DATE_OF_BIRTH: PairDisposition.SEPARATE,
    ScenarioKind.CONTRADICTORY_STRONG_IDENTIFIERS: PairDisposition.SEPARATE,
    ScenarioKind.TWINS_OVERLAPPING_CONTEXT: PairDisposition.SEPARATE,
    ScenarioKind.STALE_ATTRIBUTE: PairDisposition.MERGE,
    ScenarioKind.ALIAS_CHANGE: PairDisposition.MERGE,
    ScenarioKind.UNICODE_VARIANT: PairDisposition.MERGE,
    ScenarioKind.PARTIAL_BUT_SUFFICIENT: PairDisposition.MERGE,
    ScenarioKind.DUPLICATE_OBSERVATION: PairDisposition.MERGE,
    ScenarioKind.SINGLE_UNCORROBORATED_ATTRIBUTE: PairDisposition.INSUFFICIENT,
    ScenarioKind.PARTIAL_WITH_CONTRADICTION: PairDisposition.INSUFFICIENT,
    ScenarioKind.SPARSE_RECORDS: PairDisposition.INSUFFICIENT,
}


class PublicRecordPair(SyntheticModel):
    """A pair the system is asked to decide. Public: it is the task, not the answer.

    Without this the benchmark is unusable at its own boundary. Thirty records admit
    435 pairs and the evaluator demands exactly fifteen, so a consumer holding only
    the public corpus would have to read the answer key to learn which ones to
    decide - the oracle-free guarantee defeated by the task definition rather than
    by the data. Asteria publishes its `action_event_ids` for the same reason.

    Carries identifiers and nothing else: no disposition, no scenario, no hint of
    which pairs are alike.
    """

    left_record_id: UUID
    right_record_id: UUID

    @model_validator(mode="after")
    def require_ordered_distinct_records(self) -> Self:
        if self.left_record_id >= self.right_record_id:
            raise ValueError("pair records must be distinct and ordered by id")
        return self


class PublicAmbiguityTask(SyntheticModel):
    """Everything a system may see: the records, and which pairs to decide.

    ``pairs_to_decide`` must be in canonical record-id order, and the model refuses
    any other order rather than quietly sorting it. Emitting the pairs in the order
    the fixture happened to draft them made the *position* of a pair an answer key:
    the i-th public pair was the i-th :class:`ScenarioKind`, measured 15/15 in the
    frozen pack and 750/750 across fifty generated seeds. Nothing in the data leaked
    - the leak was the ordering of a list, which no attribute-level check can see.

    Sorting is a property of the artifact, so it belongs to the model that defines
    the artifact. A generator that rebuilds this list in draft order now fails to
    construct rather than shipping a fresh oracle.
    """

    schema_version: Literal["1.0.0"] = AMBIGUITY_SCHEMA_VERSION
    corpus: PublicConnectionCorpus
    pairs_to_decide: tuple[PublicRecordPair, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_canonical_pair_order(self) -> Self:
        keys = [
            (item.left_record_id, item.right_record_id) for item in self.pairs_to_decide
        ]
        if keys != sorted(keys):
            raise ValueError(
                "pairs_to_decide must be in canonical record-id order, because the "
                "order a fixture drafts its pairs in is itself an oracle"
            )
        # Sorted is not enough: sorting puts duplicates next to each other, and how
        # many times a pair is listed is another free choice that can be bound to the
        # answer. A pack repeating merge, separate and insufficient pairs one, two and
        # three times is canonically ordered, constructs cleanly, and decodes 15/15
        # from repetition count alone.
        if len(keys) != len(set(keys)):
            raise ValueError("pairs_to_decide must not repeat a pair")
        return self


class PairTruth(SyntheticModel):
    """One labelled record pair. Evaluator-only; never serialized into input."""

    left_record_id: UUID
    right_record_id: UUID
    disposition: PairDisposition
    scenario: ScenarioKind
    #: Whether the two records are the same person in canonical truth. Independent
    #: of `disposition`: an `insufficient` pair may be either.
    same_entity: bool

    @model_validator(mode="after")
    def require_ordered_distinct_records(self) -> Self:
        if self.left_record_id >= self.right_record_id:
            raise ValueError("pair records must be distinct and ordered by id")
        if SCENARIO_DISPOSITIONS[self.scenario] is not self.disposition:
            raise ValueError(
                f"scenario {self.scenario.value} must carry disposition "
                f"{SCENARIO_DISPOSITIONS[self.scenario].value}"
            )
        if self.disposition is PairDisposition.MERGE and not self.same_entity:
            raise ValueError("a merge pair must be the same entity in truth")
        if self.disposition is PairDisposition.SEPARATE and self.same_entity:
            raise ValueError("a separate pair must be different entities in truth")
        return self


def public_pairs_from_truth(pairs: Iterable[PairTruth]) -> tuple[PublicRecordPair, ...]:
    """Project labelled pairs to the public task list, in canonical order.

    The single place the public pair list is built, so the sort cannot be remembered
    in one generator and forgotten in another.
    """

    return tuple(
        PublicRecordPair(left_record_id=left, right_record_id=right)
        for left, right in sorted(
            (item.left_record_id, item.right_record_id) for item in pairs
        )
    )


class AmbiguityAnswerKey(SyntheticModel):
    """Evaluator-only truth, physically separate from the public corpus."""

    schema_version: Literal["1.0.0"] = AMBIGUITY_SCHEMA_VERSION
    record_memberships: tuple[RecordMembership, ...] = Field(min_length=1)
    pairs: tuple[PairTruth, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_pairs_over_known_records(self) -> Self:
        known = {item.record_id for item in self.record_memberships}
        seen: set[tuple[UUID, UUID]] = set()
        for pair in self.pairs:
            key = (pair.left_record_id, pair.right_record_id)
            if key in seen:
                raise ValueError("record pairs must be unique")
            seen.add(key)
            if not {pair.left_record_id, pair.right_record_id} <= known:
                raise ValueError("a pair references a record with no membership")
            entities = {
                item.entity_id
                for item in self.record_memberships
                if item.record_id in key
            }
            if (len(entities) == 1) is not pair.same_entity:
                raise ValueError(
                    f"pair {key} declares same_entity={pair.same_entity} but "
                    "membership truth says otherwise"
                )
        return self


class PairPrediction(SyntheticModel):
    """A system's decision about one pair. Abstention is a first-class answer."""

    schema_version: Literal["1.0.0"] = AMBIGUITY_SCHEMA_VERSION
    left_record_id: UUID
    right_record_id: UUID
    disposition: PairDisposition


class AmbiguityBenchmark(SyntheticModel):
    schema_version: Literal["1.0.0"] = AMBIGUITY_SCHEMA_VERSION
    seed: int
    public: PublicAmbiguityTask
    answer_key: AmbiguityAnswerKey

    @model_validator(mode="after")
    def require_public_pairs_to_match_truth(self) -> Self:
        # Multiplicity, not just membership. Comparing sets discards how many times
        # each pair appears, which lets a public list repeat pairs at rates that
        # encode their dispositions while still matching truth "as a set".
        public = sorted(
            (item.left_record_id, item.right_record_id)
            for item in self.public.pairs_to_decide
        )
        labelled = sorted(
            (item.left_record_id, item.right_record_id)
            for item in self.answer_key.pairs
        )
        if public != labelled:
            raise ValueError(
                "the public pair list and the labelled pairs must be the same set"
            )
        return self


__all__ = [
    "AMBIGUITY_SCHEMA_VERSION",
    "SCENARIO_DISPOSITIONS",
    "AmbiguityAnswerKey",
    "AmbiguityBenchmark",
    "PairDisposition",
    "PairPrediction",
    "PairTruth",
    "PublicAmbiguityTask",
    "PublicRecordPair",
    "ScenarioKind",
    "public_pairs_from_truth",
]
