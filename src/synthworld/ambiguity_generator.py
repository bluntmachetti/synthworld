"""The frozen human identity-resolution ambiguity pack.

Every scenario in :class:`~synthworld.ambiguity.ScenarioKind` appears exactly once,
and the pack is written so that no single attribute decides any of them. Each
positive is paired with a negative that shares the attribute the positive turns on:
a stale phone that should merge sits beside a recycled phone that must not, a
household email that must not merge sits beside a duplicate observation that must.
A resolver keyed on any one field gets one of each pair wrong.

Records are hand-authored rather than generated. Fifteen scenarios is small enough
to read end to end, and a reviewer being able to check the pack by eye is worth more
here than scale - the pack's job is to be *correct about hard cases*, not large.
"""

from __future__ import annotations

from dataclasses import dataclass

from synthworld.ambiguity import (
    SCENARIO_DISPOSITIONS,
    AmbiguityAnswerKey,
    AmbiguityBenchmark,
    PairTruth,
    PublicAmbiguityTask,
    ScenarioKind,
    public_pairs_from_truth,
)
from synthworld.connection import (
    PublicConnectionCorpus,
    PublicIdentityAttribute,
    PublicIdentityAttributeKind,
    PublicIdentityRecord,
    PublicIdentitySourceType,
    RecordMembership,
)
from synthworld.connection_generator import _identity_record

_K = PublicIdentityAttributeKind
_S = PublicIdentitySourceType


def _attributes(**values: str) -> tuple[PublicIdentityAttribute, ...]:
    return tuple(
        PublicIdentityAttribute(kind=_K(kind), value=value, confidence=1.0)
        for kind, value in sorted(values.items())
    )


@dataclass(frozen=True)
class _Draft:
    scenario: ScenarioKind
    entity_number: int
    display_name: str
    source_type: PublicIdentitySourceType
    attributes: tuple[PublicIdentityAttribute, ...]


def _drafts() -> tuple[_Draft, ...]:
    """Two records per scenario, in scenario order. Entity numbers are canonical."""

    return (
        # --- must remain separate -------------------------------------------------
        # A number reassigned between subscribers. The only shared attribute.
        _Draft(
            ScenarioKind.RECYCLED_PHONE,
            1,
            "Nadia Farouk",
            _S.DIRECTORY,
            _attributes(
                phone="+1-212-555-0117",
                email="n.farouk@example.test",
                full_address="14|Example Avenue|Testville|00000|ZZ",
            ),
        ),
        _Draft(
            ScenarioKind.RECYCLED_PHONE,
            2,
            "Peter Hollis",
            _S.BROKER,
            _attributes(
                phone="+1-212-555-0117",
                email="p.hollis@example.invalid",
                full_address="82|Test Lane|Sampleton|00000|ZZ",
            ),
        ),
        # One mailbox for a household. Different people, same inbox.
        _Draft(
            ScenarioKind.SHARED_HOUSEHOLD_EMAIL,
            3,
            "Ruth Ellery",
            _S.DIRECTORY,
            _attributes(
                email="ellery.house@example.test",
                date_of_birth="1968-03-04",
                full_address="9|Sample Row|Testville|00000|ZZ",
            ),
        ),
        _Draft(
            ScenarioKind.SHARED_HOUSEHOLD_EMAIL,
            4,
            "Tomas Ellery",
            _S.SOCIAL,
            _attributes(
                email="ellery.house@example.test",
                date_of_birth="1995-11-22",
                full_address="9|Sample Row|Testville|00000|ZZ",
            ),
        ),
        # A handle released and re-registered by someone unrelated.
        _Draft(
            ScenarioKind.REUSED_USERNAME,
            5,
            "Iris Bello",
            _S.SOCIAL,
            _attributes(
                username="quietlantern",
                date_of_birth="1990-07-19",
                employer="Example Harbour Works",
            ),
        ),
        _Draft(
            ScenarioKind.REUSED_USERNAME,
            6,
            "Callum Wren",
            _S.SOCIAL,
            _attributes(
                username="quietlantern",
                date_of_birth="1983-01-08",
                employer="Test Meridian Logistics",
            ),
        ),
        # Colleagues at one office address: the join every naive matcher takes.
        _Draft(
            ScenarioKind.SHARED_EMPLOYER_AND_ADDRESS,
            7,
            "Ana Prieto",
            _S.CONFERENCE,
            _attributes(
                employer="Sample Quarry Analytics",
                full_address="300|Fictional Way|Exampleford|00000|ZZ",
                email="a.prieto@example.test",
            ),
        ),
        _Draft(
            ScenarioKind.SHARED_EMPLOYER_AND_ADDRESS,
            8,
            "Devi Raman",
            _S.CONFERENCE,
            _attributes(
                employer="Sample Quarry Analytics",
                full_address="300|Fictional Way|Exampleford|00000|ZZ",
                email="d.raman@example.test",
            ),
        ),
        # Same normalised name and birth date, different people.
        _Draft(
            ScenarioKind.SAME_NAME_AND_DATE_OF_BIRTH,
            9,
            "John Smith",
            _S.DIRECTORY,
            _attributes(
                date_of_birth="1979-05-30",
                family_name="Smith",
                full_address="21|Specimen Street|Testville|00000|ZZ",
            ),
        ),
        _Draft(
            ScenarioKind.SAME_NAME_AND_DATE_OF_BIRTH,
            10,
            "John Smith",
            _S.ALUMNI,
            _attributes(
                date_of_birth="1979-05-30",
                family_name="Smith",
                full_address="404|Placeholder Close|Sampleton|00000|ZZ",
            ),
        ),
        # Context agrees, strong identifiers contradict. The contradiction wins.
        _Draft(
            ScenarioKind.CONTRADICTORY_STRONG_IDENTIFIERS,
            11,
            "Mei Lin Chao",
            _S.DIRECTORY,
            _attributes(
                employer="Fictional Thicket Foundry",
                school_year="Example Northgate Academy|2004",
                email="m.chao@example.test",
                phone="+1-212-555-0141",
            ),
        ),
        _Draft(
            ScenarioKind.CONTRADICTORY_STRONG_IDENTIFIERS,
            12,
            "Mei Lin Chao",
            _S.BROKER,
            _attributes(
                employer="Fictional Thicket Foundry",
                school_year="Example Northgate Academy|2004",
                email="mlc@example.invalid",
                phone="+1-212-555-0198",
            ),
        ),
        # Twins: one address, one surname, one school year, two people.
        _Draft(
            ScenarioKind.TWINS_OVERLAPPING_CONTEXT,
            13,
            "Lena Vasquez",
            _S.ALUMNI,
            _attributes(
                family_name="Vasquez",
                date_of_birth="2001-09-12",
                full_address="7|Test Lane|Testville|00000|ZZ",
                school_year="Sample Westbrook College|2019",
            ),
        ),
        _Draft(
            ScenarioKind.TWINS_OVERLAPPING_CONTEXT,
            14,
            "Mara Vasquez",
            _S.ALUMNI,
            _attributes(
                family_name="Vasquez",
                date_of_birth="2001-09-12",
                full_address="7|Test Lane|Testville|00000|ZZ",
                school_year="Sample Westbrook College|2019",
            ),
        ),
        # --- must resolve to the same entity --------------------------------------
        # An old number beside a current one, with corroborating identifiers.
        _Draft(
            ScenarioKind.STALE_ATTRIBUTE,
            15,
            "Owen Brackley",
            _S.DIRECTORY,
            _attributes(
                phone="+1-212-555-0163",
                email="o.brackley@example.test",
                date_of_birth="1974-02-11",
            ),
        ),
        _Draft(
            ScenarioKind.STALE_ATTRIBUTE,
            15,
            "Owen Brackley",
            _S.BROKER,
            _attributes(
                phone="+1-212-555-0177",
                email="o.brackley@example.test",
                date_of_birth="1974-02-11",
            ),
        ),
        # Maiden and married names, joined by a managed alias and birth date.
        _Draft(
            ScenarioKind.ALIAS_CHANGE,
            16,
            "Priya Nandakumar",
            _S.ALUMNI,
            _attributes(
                family_name="Nandakumar",
                date_of_birth="1988-06-25",
                username="p.nandakumar",
                school_year="Test Ashby Institute|2010",
            ),
        ),
        _Draft(
            ScenarioKind.ALIAS_CHANGE,
            16,
            "Priya Whitlock",
            _S.DIRECTORY,
            _attributes(
                family_name="Whitlock",
                date_of_birth="1988-06-25",
                username="p.nandakumar",
                school_year="Test Ashby Institute|2010",
            ),
        ),
        # Diacritics stripped by one source, kept by another.
        _Draft(
            ScenarioKind.UNICODE_VARIANT,
            17,
            "Björn Sørensen",
            _S.CONFERENCE,
            _attributes(
                family_name="Sørensen",
                date_of_birth="1981-12-03",
                email="b.sorensen@example.test",
            ),
        ),
        _Draft(
            ScenarioKind.UNICODE_VARIANT,
            17,
            "Bjorn Sorensen",
            _S.BROKER,
            _attributes(
                family_name="Sorensen",
                date_of_birth="1981-12-03",
                email="b.sorensen@example.test",
            ),
        ),
        # Neither record is sufficient alone; together they are.
        _Draft(
            ScenarioKind.PARTIAL_BUT_SUFFICIENT,
            18,
            "H. Okonkwo",
            _S.DIRECTORY,
            _attributes(
                family_name="Okonkwo",
                employer="Example Granite Works",
                school_year="Fictional Fenwick College|1998",
            ),
        ),
        _Draft(
            ScenarioKind.PARTIAL_BUT_SUFFICIENT,
            18,
            "Helen Okonkwo",
            _S.ALUMNI,
            _attributes(
                family_name="Okonkwo",
                employer="Example Granite Works",
                school_year="Fictional Fenwick College|1998",
                date_of_birth="1976-04-17",
            ),
        ),
        # The same source record, syndicated to a second aggregator.
        _Draft(
            ScenarioKind.DUPLICATE_OBSERVATION,
            19,
            "Sofia Marchetti",
            _S.BROKER,
            _attributes(
                email="s.marchetti@example.test",
                phone="+1-212-555-0182",
                full_address="55|Example Avenue|Fictionbury|00000|ZZ",
            ),
        ),
        _Draft(
            ScenarioKind.DUPLICATE_OBSERVATION,
            19,
            "Sofia Marchetti",
            _S.DIRECTORY,
            _attributes(
                email="s.marchetti@example.test",
                phone="+1-212-555-0182",
                full_address="55|Example Avenue|Fictionbury|00000|ZZ",
            ),
        ),
        # --- public evidence is insufficient --------------------------------------
        # One shared employer, nothing else. Same person, but the record cannot say.
        _Draft(
            ScenarioKind.SINGLE_UNCORROBORATED_ATTRIBUTE,
            20,
            "R. Adeyemi",
            _S.CONFERENCE,
            _attributes(employer="Test Bramble Logistics"),
        ),
        _Draft(
            ScenarioKind.SINGLE_UNCORROBORATED_ATTRIBUTE,
            20,
            "Rotimi Adeyemi",
            _S.DIRECTORY,
            _attributes(employer="Test Bramble Logistics"),
        ),
        # Corroborating school year, contradicting birth date. Different people,
        # but public evidence cannot settle which signal to believe.
        _Draft(
            ScenarioKind.PARTIAL_WITH_CONTRADICTION,
            21,
            "Grace Underhill",
            _S.ALUMNI,
            _attributes(
                school_year="Sample Eastmoor Academy|2007",
                date_of_birth="1989-08-14",
                family_name="Underhill",
            ),
        ),
        _Draft(
            ScenarioKind.PARTIAL_WITH_CONTRADICTION,
            22,
            "Grace Underhill",
            _S.BROKER,
            _attributes(
                school_year="Sample Eastmoor Academy|2007",
                date_of_birth="1991-02-02",
                family_name="Underhill",
            ),
        ),
        # Two near-empty records. Nothing to reason with either way.
        _Draft(
            ScenarioKind.SPARSE_RECORDS,
            23,
            "K. Osei",
            _S.SOCIAL,
            _attributes(family_name="Osei"),
        ),
        _Draft(
            ScenarioKind.SPARSE_RECORDS,
            23,
            "Kwame Osei",
            _S.BROKER,
            _attributes(family_name="Osei"),
        ),
    )


def generate_ambiguity_benchmark(*, seed: int) -> AmbiguityBenchmark:
    """Build the frozen ambiguity pack for a seed.

    The seed only opaques record identifiers; the cases themselves are fixed, which
    is what makes this the canonical pack rather than a variant.
    """

    drafts = _drafts()
    records: tuple[PublicIdentityRecord, ...] = tuple(
        _identity_record(
            seed=seed,
            key=f"ambiguity:{index}",
            source_type=draft.source_type,
            display_name=draft.display_name,
            attributes=draft.attributes,
        )
        for index, draft in enumerate(drafts, start=1)
    )
    memberships = tuple(
        RecordMembership(
            record_id=record.id, entity_id=f"entity-{draft.entity_number:04d}"
        )
        for record, draft in zip(records, drafts, strict=True)
    )
    pairs = []
    for position in range(0, len(drafts), 2):
        left, right = records[position], records[position + 1]
        draft = drafts[position]
        first, second = sorted((left.id, right.id))
        pairs.append(
            PairTruth(
                left_record_id=first,
                right_record_id=second,
                disposition=SCENARIO_DISPOSITIONS[draft.scenario],
                scenario=draft.scenario,
                same_entity=drafts[position].entity_number
                == drafts[position + 1].entity_number,
            )
        )
    return AmbiguityBenchmark(
        seed=seed,
        public=PublicAmbiguityTask(
            corpus=PublicConnectionCorpus(
                seed=seed, identity_records=records, association_records=()
            ),
            pairs_to_decide=public_pairs_from_truth(pairs),
        ),
        answer_key=AmbiguityAnswerKey(
            record_memberships=memberships, pairs=tuple(pairs)
        ),
    )


__all__ = ["generate_ambiguity_benchmark"]
