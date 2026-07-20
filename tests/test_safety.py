from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from synthworld import generate_exposure_corpus, generate_world

PHONE_PATTERN = re.compile(r"^\+1-\d{3}-555-01\d{2}$")
NATIONAL_ID_PATTERN = re.compile(r"^SYN-(\d{9})$")


def _luhn_valid(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for index, character in enumerate(digits):
        digit = int(character)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _assert_every_record_is_marked_synthetic(value: object) -> None:
    if isinstance(value, Mapping):
        assert value.get("synthetic") is True
        for nested in value.values():
            _assert_every_record_is_marked_synthetic(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for nested in value:
            _assert_every_record_is_marked_synthetic(nested)


def test_every_generated_record_is_explicitly_synthetic() -> None:
    dumped = generate_world(seed=20_260_719, persona_count=10).model_dump(mode="json")

    _assert_every_record_is_marked_synthetic(dumped)


def test_every_exposure_corpus_record_is_explicitly_synthetic() -> None:
    dumped = generate_exposure_corpus(
        seed=20_260_719,
        persona_count=10,
    ).model_dump(mode="json")

    _assert_every_record_is_marked_synthetic(dumped)


def test_identity_values_are_unmistakably_and_mechanically_fake() -> None:
    world = generate_world(seed=20_260_719, persona_count=100)

    for persona in world.personas:
        for email in persona.emails:
            assert email.value.endswith("@example.test")
        for phone in persona.phones:
            assert PHONE_PATTERN.fullmatch(phone.value)
        for address in persona.addresses:
            assert address.street_name.endswith("Example Avenue")
            assert address.city == "Testville"
            assert address.postal_code == "00000"
            assert address.country_code == "ZZ"
        for national_id in persona.national_ids:
            match = NATIONAL_ID_PATTERN.fullmatch(national_id.value)
            assert match is not None
            assert national_id.checksum_valid is False
            assert not _luhn_valid(match.group(1))


def test_generated_identifiers_are_unique_within_a_world() -> None:
    world = generate_world(seed=20_260_719, persona_count=1_000)

    emails = [email.value for persona in world.personas for email in persona.emails]
    phones = [phone.value for persona in world.personas for phone in persona.phones]
    national_ids = [
        national_id.value
        for persona in world.personas
        for national_id in persona.national_ids
    ]

    assert len(emails) == len(set(emails))
    assert len(phones) == len(set(phones))
    assert len(national_ids) == len(set(national_ids))
