from __future__ import annotations

from itertools import pairwise
from urllib.parse import urlparse

from synthworld import (
    DataClass,
    LifecycleState,
    Persona,
    SearchMatchKind,
    generate_exposure_corpus,
)


def test_exposed_persona_attributes_and_social_references_exist() -> None:
    corpus = generate_exposure_corpus(seed=20_260_719, persona_count=10)
    personas = {persona.id: persona for persona in corpus.world.personas}
    usernames = {
        username.value
        for persona in corpus.world.personas
        for username in persona.usernames
    }

    for script in corpus.exposure_scripts:
        persona = personas[script.persona_id]
        for breach in script.breaches:
            for data_class in breach.exposed_data:
                assert _persona_supports(persona, data_class)
        for broker in script.brokers:
            for data_class in broker.exposed_data:
                assert _persona_supports(persona, data_class)
        for search in script.searches:
            for data_class in search.exposed_data:
                assert _persona_supports(persona, data_class)
        for profile in script.social_profiles:
            for data_class in profile.exposed_data:
                assert _persona_supports(persona, data_class)
            assert profile.username in usernames
            assert profile.username in {item.value for item in persona.usernames}
            assert set(profile.connected_person_ids) <= personas.keys()
            assert script.persona_id not in profile.connected_person_ids


def test_name_collisions_point_to_a_different_existing_persona() -> None:
    corpus = generate_exposure_corpus(seed=20_260_719, persona_count=10)
    persona_ids = {persona.id for persona in corpus.world.personas}
    collisions = [
        (script, search)
        for script in corpus.exposure_scripts
        for search in script.searches
        if search.match_kind is SearchMatchKind.NAME_COLLISION
    ]

    assert collisions
    for script, search in collisions:
        assert search.actual_persona_id in persona_ids
        assert search.actual_persona_id != script.persona_id


def test_broker_lifecycles_are_chronological_and_state_valid() -> None:
    corpus = generate_exposure_corpus(seed=20_260_719, persona_count=10)
    allowed = {
        LifecycleState.FOUND: {LifecycleState.REMOVAL_REQUESTED},
        LifecycleState.REMOVAL_REQUESTED: {LifecycleState.CONFIRMED_REMOVED},
        LifecycleState.CONFIRMED_REMOVED: {LifecycleState.REAPPEARED},
        LifecycleState.REAPPEARED: set(),
    }

    for script in corpus.exposure_scripts:
        for broker in script.brokers:
            states = [event.state for event in broker.lifecycle]
            timestamps = [event.at for event in broker.lifecycle]
            assert states[0] is LifecycleState.FOUND
            assert timestamps == sorted(timestamps)
            assert len(timestamps) == len(set(timestamps))
            for previous, current in pairwise(states):
                assert current in allowed[previous]


def test_names_and_locators_are_explicitly_synthetic() -> None:
    corpus = generate_exposure_corpus(seed=20_260_719, persona_count=10)

    for script in corpus.exposure_scripts:
        assert all(
            item.breach_name.startswith("Example Breach ") for item in script.breaches
        )
        assert all(
            item.broker_name.startswith("Example Broker ") for item in script.brokers
        )
        for search in script.searches:
            assert urlparse(search.locator).hostname == "search.example.test"
            assert search.title.startswith(("Synthetic ", "Example "))
        for profile in script.social_profiles:
            assert profile.platform == "Example Social"
            assert urlparse(profile.locator).hostname == "social.example.test"


def _persona_supports(persona: Persona, data_class: DataClass) -> bool:
    if data_class is DataClass.EMAIL:
        return bool(persona.emails)
    if data_class is DataClass.USERNAME:
        return bool(persona.usernames)
    if data_class is DataClass.PHONE:
        return bool(persona.phones)
    if data_class is DataClass.ADDRESS:
        return bool(persona.addresses)
    if data_class is DataClass.DATE_OF_BIRTH:
        return bool(persona.date_of_birth)
    if data_class is DataClass.EMPLOYER:
        return bool(persona.employment)
    if data_class is DataClass.EDUCATION:
        return bool(persona.education)
    if data_class is DataClass.NATIONAL_ID:
        return bool(persona.national_ids)
    return data_class is DataClass.PASSWORD
