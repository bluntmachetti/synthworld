"""Seed variants of the ambiguity pack.

Issue #41 asks for variants that "change surface values and scenario assignments
while preserving declared case prevalence". Two different requirements, and issue
#43 is the reason to keep them apart: a generator whose seeds change identifiers
but not structure passes byte-inequality while testing exactly one world.

So variants do two things, and the second is the one that matters:

**Surface substitution.** Every value is rewritten consistently, preserving which
records share a value and which contradict. This changes the data without changing
what any scenario tests.

**Realization choice.** Where a scenario does not name its own attribute, the seed
picks which attribute carries it - a stale phone in one variant, a stale email in
another. That changes what a resolver has to reason about, not merely what it reads.

Six of the fifteen scenarios admit a realization choice. The other nine are defined
by their attribute - `recycled_phone` is about a phone - so for those a variant is
surface substitution only, and that limit is stated rather than papered over.
"""

from __future__ import annotations

from hashlib import blake2b

from synthworld.ambiguity import (
    SCENARIO_DISPOSITIONS,
    AmbiguityAnswerKey,
    AmbiguityBenchmark,
    PairTruth,
    PublicAmbiguityTask,
    PublicRecordPair,
    ScenarioKind,
)
from synthworld.ambiguity_generator import _drafts
from synthworld.connection import (
    PublicConnectionCorpus,
    PublicIdentityAttribute,
    PublicIdentityAttributeKind,
    RecordMembership,
)
from synthworld.connection_generator import _identity_record

#: Scenarios whose defining attribute is fixed by the scenario itself. A variant
#: cannot move `recycled_phone` onto an email without it becoming a different case.
FIXED_REALIZATION = frozenset(
    {
        ScenarioKind.RECYCLED_PHONE,
        ScenarioKind.SHARED_HOUSEHOLD_EMAIL,
        ScenarioKind.REUSED_USERNAME,
        ScenarioKind.SHARED_EMPLOYER_AND_ADDRESS,
        ScenarioKind.SAME_NAME_AND_DATE_OF_BIRTH,
        ScenarioKind.TWINS_OVERLAPPING_CONTEXT,
        ScenarioKind.ALIAS_CHANGE,
        ScenarioKind.DUPLICATE_OBSERVATION,
        ScenarioKind.SPARSE_RECORDS,
    }
)

#: Where the scenario leaves the carrying attribute open, these are the choices.
REALIZATIONS: dict[ScenarioKind, tuple[PublicIdentityAttributeKind, ...]] = {
    ScenarioKind.CONTRADICTORY_STRONG_IDENTIFIERS: (
        PublicIdentityAttributeKind.EMAIL,
        PublicIdentityAttributeKind.PHONE,
    ),
    ScenarioKind.STALE_ATTRIBUTE: (
        PublicIdentityAttributeKind.PHONE,
        PublicIdentityAttributeKind.FULL_ADDRESS,
    ),
    ScenarioKind.UNICODE_VARIANT: (PublicIdentityAttributeKind.FAMILY_NAME,),
    ScenarioKind.PARTIAL_BUT_SUFFICIENT: (
        PublicIdentityAttributeKind.DATE_OF_BIRTH,
        PublicIdentityAttributeKind.SCHOOL_YEAR,
    ),
    ScenarioKind.SINGLE_UNCORROBORATED_ATTRIBUTE: (
        PublicIdentityAttributeKind.EMPLOYER,
        PublicIdentityAttributeKind.SCHOOL_YEAR,
    ),
    ScenarioKind.PARTIAL_WITH_CONTRADICTION: (
        PublicIdentityAttributeKind.DATE_OF_BIRTH,
        PublicIdentityAttributeKind.SCHOOL_YEAR,
    ),
}

_GIVEN = ("Ada", "Bilal", "Chen", "Dara", "Esme", "Faisal", "Gita", "Hugo")
_FAMILY = ("Aldridge", "Barros", "Chevalier", "Delgado", "Eriksen", "Fontaine")
_DOMAINS = ("example.test", "example.invalid", "mail.example.test")


def _draw(seed: int, purpose: str, index: int) -> int:
    material = f"ambiguity-variant|{seed}|{purpose}|{index}"
    return int.from_bytes(blake2b(material.encode(), digest_size=8).digest(), "big")


def _substituted(value: str, kind: str, seed: int, ordinal: int) -> str:
    """Rewrite one value, keyed on the value itself.

    Keyed on the value, so two records that shared a value still share the
    rewritten one and two that differed still differ. That is what preserves every
    scenario through the substitution.
    """

    slot = _draw(seed, f"value:{kind}:{value}", ordinal)
    if kind == "email":
        local = f"{_GIVEN[slot % len(_GIVEN)].lower()}.{slot % 900 + 100}"
        return f"{local}@{_DOMAINS[slot % len(_DOMAINS)]}"
    if kind == "phone":
        return f"+1-212-555-{slot % 9000 + 1000}"
    if kind == "username":
        return f"{_GIVEN[slot % len(_GIVEN)].lower()}{slot % 90 + 10}"
    if kind == "family_name":
        return _FAMILY[slot % len(_FAMILY)]
    if kind == "full_address":
        return f"{slot % 400 + 1}|Example Avenue|Testville|00000|ZZ"
    if kind == "employer":
        return f"Example {_FAMILY[slot % len(_FAMILY)]} Works"
    if kind == "school_year":
        return f"Test {_FAMILY[slot % len(_FAMILY)]} Academy|{slot % 30 + 1990}"
    if kind == "date_of_birth":
        return f"{slot % 40 + 1960}-{slot % 12 + 1:02d}-{slot % 27 + 1:02d}"
    return value


def generate_ambiguity_variant(*, seed: int) -> AmbiguityBenchmark:
    """A variant preserving every scenario and its disposition."""

    drafts = _drafts()
    records = []
    for index, draft in enumerate(drafts, start=1):
        realizations = REALIZATIONS.get(draft.scenario)
        keep = (
            None
            if draft.scenario in FIXED_REALIZATION or realizations is None
            else realizations[
                _draw(seed, f"realization:{draft.scenario.value}", 0)
                % len(realizations)
            ]
        )
        attributes = tuple(
            PublicIdentityAttribute(
                kind=item.kind,
                value=_substituted(item.value, item.kind.value, seed, index),
                confidence=item.confidence,
            )
            for item in draft.attributes
            # Drop the attributes the chosen realization does not use, so the
            # scenario is carried by a different field than in the canonical pack.
            if keep is None
            or item.kind is keep
            or item.kind not in (realizations or ())
        )
        given = _GIVEN[_draw(seed, "given", index) % len(_GIVEN)]
        family = next(
            (item.value for item in attributes if item.kind.value == "family_name"),
            _FAMILY[_draw(seed, "family", index) % len(_FAMILY)],
        )
        records.append(
            _identity_record(
                seed=seed,
                key=f"ambiguity-variant:{index}",
                source_type=draft.source_type,
                display_name=f"{given} {family}",
                attributes=attributes,
            )
        )

    memberships = tuple(
        RecordMembership(
            record_id=record.id, entity_id=f"entity-{draft.entity_number:04d}"
        )
        for record, draft in zip(records, drafts, strict=True)
    )
    pairs = []
    for position in range(0, len(drafts), 2):
        first, second = sorted((records[position].id, records[position + 1].id))
        pairs.append(
            PairTruth(
                left_record_id=first,
                right_record_id=second,
                disposition=SCENARIO_DISPOSITIONS[drafts[position].scenario],
                scenario=drafts[position].scenario,
                same_entity=drafts[position].entity_number
                == drafts[position + 1].entity_number,
            )
        )
    return AmbiguityBenchmark(
        seed=seed,
        public=PublicAmbiguityTask(
            corpus=PublicConnectionCorpus(
                seed=seed, identity_records=tuple(records), association_records=()
            ),
            pairs_to_decide=tuple(
                PublicRecordPair(
                    left_record_id=item.left_record_id,
                    right_record_id=item.right_record_id,
                )
                for item in pairs
            ),
        ),
        answer_key=AmbiguityAnswerKey(
            record_memberships=memberships, pairs=tuple(pairs)
        ),
    )


__all__ = ["FIXED_REALIZATION", "REALIZATIONS", "generate_ambiguity_variant"]
