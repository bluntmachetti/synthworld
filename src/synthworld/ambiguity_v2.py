"""Ambiguity pairs whose answer is derived from evidence rather than written beside it.

v1 is a fixed list of fifteen hand-authored cases, each with a hand-written disposition.
That construction has an unbounded supply of leaks and no amount of hygiene closes it:
when a case list assigns each case a label, *any* feature that identifies the case
identifies the label. Nine channels were closed one at a time in #59 and #66 - display
order, record UUIDs, provenance strings, source counts, case shapes - and the tenth was
found by recomputing the generator from a public seed. Closing channels one at a time is
losing a race that has no finish line.

So v2 removes what the channels were carrying rather than the channels. There is no
scenario here. A pair is built by sampling whether the two records are one person, then
drawing each piece of evidence from the distribution that fact implies, then *reading*
the disposition off the evidence with the same public rule a solver is invited to use.
Nothing identifies a case, because there are no cases.

Three properties follow from the construction rather than from tests:

- The disposition is a pure function of the relation vector, checked at construction. A
  pair whose label disagrees with its evidence cannot be built.
- `same_entity` and `disposition` are allowed to differ, and this is the point. The
  disposition is what the public evidence justifies; `same_entity` is what is true. v1
  forbade the difference, which is why it could not represent two people who look
  identical on paper - and why #77 exists.
- A held-out seed conceals the *values*, not the rule. `disposition_of` is public on
  purpose, and since #80 the rule is not the ceiling: the rendered values are a
  structured-noise channel whose Bayes error is computed and published, so recovering
  relations from them is the task and doing it *optimally* scores `1 - floor` — a
  residue of pairs is genuinely undecidable from any observation the pack can emit.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from synthworld.ambiguity import PairDisposition, PublicRecordPair
from synthworld.ambiguity_grammar import EvidenceKind, Relation, disposition_of
from synthworld.connection import PublicConnectionCorpus
from synthworld.models import SyntheticModel

AMBIGUITY_V2_SCHEMA_VERSION: Literal["2.1.0"] = "2.1.0"


class DerivedPairTruth(SyntheticModel):
    """One pair, with the evidence that produced it and the answer that evidence forces.

    Evaluator-only. The relation vector lives here rather than in the public task
    because it *is* the answer in a thinner disguise: a solver handed the relations has
    been handed the disposition, since the rule mapping one to the other is published.
    What the solver gets is rendered values, and turning those back into relations is
    the work being measured.
    """

    left_record_id: UUID
    right_record_id: UUID
    #: What is true, sampled first and independently of anything observable.
    same_entity: bool
    #: What the two records can be compared on, and how each comparison came out. Stored
    #: as a sorted tuple rather than a mapping because a mapping field is *mutable after
    #: validation*: `frozen=True` stops a field being reassigned, not a dict inside one
    #: being written to. A caller could set `relations[GIVEN_NAME] = FAR` on a merge
    #: pair, and the validator below would never rerun - leaving a truth object whose
    #: label contradicts its own evidence, the exact state this class exists to make
    #: unrepresentable. Read it through :attr:`relations`.
    comparisons: tuple[tuple[EvidenceKind, Relation], ...]
    #: What the evidence justifies. Not an independent field - see the validator.
    disposition: PairDisposition

    @property
    def relations(self) -> Mapping[EvidenceKind, Relation]:
        """The comparisons as a mapping, rebuilt per access so it cannot be
        written to."""

        return MappingProxyType(dict(self.comparisons))

    @model_validator(mode="before")
    @classmethod
    def accept_a_mapping(cls, data: object) -> object:
        """Let callers pass `comparisons={kind: relation}` and store it canonically.

        Sorted here rather than trusted from the caller, so the order comparisons were
        drawn in cannot survive into the artifact. Emission order was one of v1's leaks.
        """

        if isinstance(data, dict) and isinstance(data.get("comparisons"), Mapping):
            data = data | {"comparisons": tuple(sorted(data["comparisons"].items()))}
        return data

    @model_validator(mode="after")
    def require_the_answer_to_follow_from_the_evidence(self) -> Self:
        if self.left_record_id >= self.right_record_id:
            raise ValueError("pair records must be distinct and ordered by id")
        if not self.comparisons:
            raise ValueError("a pair must record at least one comparison")
        kinds = [kind for kind, _ in self.comparisons]
        if len(set(kinds)) != len(kinds):
            raise ValueError("a pair must not compare the same kind twice")
        if kinds != sorted(kinds):
            raise ValueError("comparisons must be in canonical kind order")
        # The whole design in one line. v1 asserted a disposition per scenario and
        # checked it against a lookup table, so the table *was* the ground truth and
        # every path to it was a leak. Here the disposition has no independent
        # existence: a generator that computed it any other way is refused at
        # construction rather than caught by a test that might not be written.
        implied = disposition_of(self.relations)
        if self.disposition is not implied:
            raise ValueError(
                f"disposition {self.disposition.value} does not follow from the "
                f"evidence, which implies {implied.value}"
            )
        return self


class PublicAmbiguityTaskV2(SyntheticModel):
    """What the solver sees: a corpus of records, and which of them to compare.

    Distractors need no model and no flag. A record the pair list never mentions *is* a
    distractor, so the corpus cannot be marked up with which records matter - v1's
    record set was exactly the records appearing in pairs, which made mere membership a
    signal and let a solver bound a record by how often it was asked about.
    """

    schema_version: Literal["2.1.0"] = AMBIGUITY_V2_SCHEMA_VERSION
    corpus: PublicConnectionCorpus
    pairs_to_decide: tuple[PublicRecordPair, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_canonical_pairs_over_known_records(self) -> Self:
        keys = [
            (item.left_record_id, item.right_record_id) for item in self.pairs_to_decide
        ]
        if keys != sorted(keys):
            raise ValueError("pairs_to_decide must be in canonical record-id order")
        if len(keys) != len(set(keys)):
            # How many times a pair is listed is a free choice, and a free choice bound
            # to the answer is an oracle. Measured in v1 at 15/15 from repetition alone.
            raise ValueError("pairs_to_decide must not repeat a pair")
        known = {item.id for item in self.corpus.identity_records}
        if {item for key in keys for item in key} - known:
            raise ValueError("pairs must name records present in the corpus")
        return self

    @property
    def distractor_ids(self) -> frozenset[UUID]:
        """Records no pair asks about. Derived, so it cannot disagree with the pack."""

        asked = {
            item
            for pair in self.pairs_to_decide
            for item in (pair.left_record_id, pair.right_record_id)
        }
        return frozenset(item.id for item in self.corpus.identity_records) - asked


def public_pairs_from_derived(
    pairs: Iterable[DerivedPairTruth],
) -> tuple[PublicRecordPair, ...]:
    """Project labelled pairs to the public list, in canonical order.

    Sorted by record id, so the order carries the ids and nothing else. v1 shipped a
    display order that tracked the label; this is the single place the projection
    happens so a second generator cannot reintroduce that.
    """

    return tuple(
        PublicRecordPair(left_record_id=left, right_record_id=right)
        for left, right in sorted(
            (item.left_record_id, item.right_record_id) for item in pairs
        )
    )


__all__ = [
    "AMBIGUITY_V2_SCHEMA_VERSION",
    "DerivedPairTruth",
    "PublicAmbiguityTaskV2",
    "public_pairs_from_derived",
]
