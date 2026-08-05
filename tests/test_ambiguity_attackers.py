"""Adversarial regressions: the historical attacks must stay under the ceiling.

Issue #80's gate 3(i) is that every scripted attacker scores at most ``1 - floor +
epsilon``. These are *regressions*, not invariants: they pin the specific attacks that
sank the first two designs - a one-bit display-name comparison, an exact-attribute
matcher, and a pool-membership/inversion decoder - and assert none of them crosses the
published ceiling. The genie (which achieves the ceiling) is checked separately in the
floor suite; here the point is that cheaper decoders do not beat it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from synthworld.ambiguity import PairDisposition
from synthworld.ambiguity_channel import capped_distance, emitters_of, likelihood_of
from synthworld.ambiguity_evidence import EvidenceKind, Relation
from synthworld.ambiguity_floor import FLOOR_PUBLICATION
from synthworld.ambiguity_surfaces import invert_form
from synthworld.ambiguity_v2 import DerivedPairTruth
from synthworld.ambiguity_v2_generator import generate_ambiguity_v2_pack
from synthworld.connection import PublicIdentityRecord

_KEY = b"attacker-regression-key"
_SEEDS = range(300, 312)

#: Monte-Carlo slack for the attacker accuracy estimates: the attackers are
#: deterministic, but which pairs they see is sampled, so the estimate carries noise.
_EPSILON = 0.03


def _pairs() -> Iterator[
    tuple[PublicIdentityRecord, PublicIdentityRecord, DerivedPairTruth]
]:
    for seed in _SEEDS:
        task, truths = generate_ambiguity_v2_pack(seed=seed, key=_KEY)
        by_id = {record.id: record for record in task.corpus.identity_records}
        truth_by_pair = {
            (truth.left_record_id, truth.right_record_id): truth for truth in truths
        }
        for pair in task.pairs_to_decide:
            yield (
                by_id[pair.left_record_id],
                by_id[pair.right_record_id],
                truth_by_pair[(pair.left_record_id, pair.right_record_id)],
            )


def _accuracy(
    decide: Callable[[PublicIdentityRecord, PublicIdentityRecord], PairDisposition],
) -> float:
    correct = total = 0
    for left, right, truth in _pairs():
        total += 1
        correct += decide(left, right) is truth.disposition
    return correct / total


def test_one_bit_display_name_is_bounded_by_the_ceiling() -> None:
    """The one-bit classifier that scored 0.8096 on the second design.

    It merges on a byte-identical display name and separates otherwise. Under the
    structured-noise channel a shared name is no longer a near-certain merge, so the
    attack must sit below the published ceiling.
    """

    def decide(
        left: PublicIdentityRecord, right: PublicIdentityRecord
    ) -> PairDisposition:
        return (
            PairDisposition.MERGE
            if left.display_name == right.display_name
            else PairDisposition.SEPARATE
        )

    ceiling = 1.0 - FLOOR_PUBLICATION.floor
    assert _accuracy(decide) <= ceiling + _EPSILON


def test_exact_attribute_match_is_bounded_by_the_ceiling() -> None:
    """Merge when any attribute matches byte-for-byte, else separate."""

    def decide(
        left: PublicIdentityRecord, right: PublicIdentityRecord
    ) -> PairDisposition:
        left_values = {item.kind.value: item.value for item in left.attributes}
        right_values = {item.kind.value: item.value for item in right.attributes}
        shared = any(
            kind in right_values and left_values[kind] == right_values[kind]
            for kind in left_values
        )
        return PairDisposition.MERGE if shared else PairDisposition.SEPARATE

    ceiling = 1.0 - FLOOR_PUBLICATION.floor
    assert _accuracy(decide) <= ceiling + _EPSILON


def _map_base(kind: EvidenceKind, rendered: str) -> str | None:
    """Invert a rendered value to its most likely base, or None off the pool."""

    try:
        _form, core = invert_form(kind, rendered)
    except ValueError:
        return None
    emitters = emitters_of(kind, core)
    if not emitters:
        return None
    return max(emitters, key=lambda item: item[1])[0]


def _relation_of_bases(kind: EvidenceKind, left: str, right: str) -> Relation:
    """The MAP relation between two recovered bases, under the public law."""

    best, best_relation = -1.0, Relation.FAR
    for relation in (Relation.EQUAL, Relation.NEAR, Relation.FAR):
        like = likelihood_of(kind, relation, left, right)
        if like > best:
            best, best_relation = like, relation
    return best_relation


def test_pool_inversion_is_bounded_by_the_ceiling() -> None:
    """The attack that scored 0.9967 on the second design.

    Invert every rendered value to a base through the public codebook, read the
    relation off the recovered bases, and run the public rule. Identity recovery is
    free and expected - the codebook is published on purpose - so this decoder is a
    strong one; the assertion is that it does not *exceed* the ceiling, which is the
    data-processing inequality made empirical.
    """

    def decide(
        left: PublicIdentityRecord, right: PublicIdentityRecord
    ) -> PairDisposition:
        from synthworld.ambiguity_grammar import disposition_of

        left_name = left.display_name.split(", ")
        right_name = right.display_name.split(", ")
        relations: dict[EvidenceKind, Relation] = {}
        family_relation = _maybe_relation(
            EvidenceKind.FAMILY_NAME, left_name[0], right_name[0]
        )
        if family_relation is not None:
            relations[EvidenceKind.FAMILY_NAME] = family_relation
        if len(left_name) > 1 and len(right_name) > 1:
            given_relation = _maybe_relation(
                EvidenceKind.GIVEN_NAME, left_name[1], right_name[1]
            )
            if given_relation is not None:
                relations[EvidenceKind.GIVEN_NAME] = given_relation
        left_values = {item.kind.value: item.value for item in left.attributes}
        right_values = {item.kind.value: item.value for item in right.attributes}
        for kind in EvidenceKind:
            if kind in (EvidenceKind.GIVEN_NAME, EvidenceKind.FAMILY_NAME):
                continue
            if kind.value in left_values and kind.value in right_values:
                relation = _maybe_relation(
                    kind, left_values[kind.value], right_values[kind.value]
                )
                if relation is not None:
                    relations[kind] = relation
        if not relations:
            return PairDisposition.INSUFFICIENT
        return disposition_of(relations)

    ceiling = 1.0 - FLOOR_PUBLICATION.floor
    assert _accuracy(decide) <= ceiling + _EPSILON


def _maybe_relation(kind: EvidenceKind, left: str, right: str) -> Relation | None:
    left_base = _map_base(kind, left)
    right_base = _map_base(kind, right)
    if left_base is None or right_base is None:
        return None
    return _relation_of_bases(kind, left_base, right_base)


def test_distance_grading_does_not_exceed_the_ceiling() -> None:
    """A threshold solver on capped distance: merge if close, separate if far.

    Distance is the graded signal the pack rewards, so a solver may legitimately do
    well; the bound says it still cannot beat the Bayes-optimal genie.
    """

    def decide(
        left: PublicIdentityRecord, right: PublicIdentityRecord
    ) -> PairDisposition:
        left_name = left.display_name.split(", ")
        right_name = right.display_name.split(", ")
        distances = []
        for kind, lv, rv in ((EvidenceKind.FAMILY_NAME, left_name[0], right_name[0]),):
            try:
                _lf, lc = invert_form(kind, lv)
                _rf, rc = invert_form(kind, rv)
                distances.append(capped_distance(lc, rc))
            except ValueError:
                continue
        if not distances:
            return PairDisposition.INSUFFICIENT
        return (
            PairDisposition.MERGE if min(distances) <= 2 else PairDisposition.SEPARATE
        )

    ceiling = 1.0 - FLOOR_PUBLICATION.floor
    assert _accuracy(decide) <= ceiling + _EPSILON
