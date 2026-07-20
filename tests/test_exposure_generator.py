from __future__ import annotations

import hashlib

from synthworld import (
    LifecycleState,
    SearchMatchKind,
    corpus_to_json,
    generate_exposure_corpus,
    generate_world,
    world_to_json,
)

TRANCHE_SEED = 20_260_719
CORE_SHA256 = "0e19fe70e751d0d2d779c9112fcb9f847ef0eae055e701f06ffa6bad44dba4f4"


def test_exposure_corpus_is_byte_deterministic_for_a_fixed_seed() -> None:
    first = corpus_to_json(
        generate_exposure_corpus(seed=TRANCHE_SEED, persona_count=10)
    )
    second = corpus_to_json(
        generate_exposure_corpus(seed=TRANCHE_SEED, persona_count=10)
    )

    assert first == second


def test_changing_seed_changes_exposure_corpus_bytes() -> None:
    first = corpus_to_json(
        generate_exposure_corpus(seed=TRANCHE_SEED, persona_count=10)
    )
    second = corpus_to_json(
        generate_exposure_corpus(seed=TRANCHE_SEED + 1, persona_count=10)
    )

    assert first != second


def test_core_world_seed_contract_is_unchanged() -> None:
    serialized = world_to_json(
        generate_world(seed=TRANCHE_SEED, persona_count=10)
    ).encode()

    assert hashlib.sha256(serialized).hexdigest() == CORE_SHA256


def test_each_persona_has_one_script_and_exactly_one_has_zero_exposure() -> None:
    corpus = generate_exposure_corpus(seed=TRANCHE_SEED, persona_count=10)
    persona_ids = {persona.id for persona in corpus.world.personas}
    script_persona_ids = [script.persona_id for script in corpus.exposure_scripts]
    zero_exposure_scripts = [
        script for script in corpus.exposure_scripts if script.exposure_count == 0
    ]

    assert len(corpus.exposure_scripts) == 10
    assert set(script_persona_ids) == persona_ids
    assert len(script_persona_ids) == len(set(script_persona_ids))
    assert len(zero_exposure_scripts) == 1
    assert zero_exposure_scripts[0].persona_id == corpus.world.personas[-1].id


def test_corpus_contains_all_source_types_and_adversarial_lifecycles() -> None:
    corpus = generate_exposure_corpus(seed=TRANCHE_SEED, persona_count=10)
    breaches = [item for script in corpus.exposure_scripts for item in script.breaches]
    brokers = [item for script in corpus.exposure_scripts for item in script.brokers]
    searches = [item for script in corpus.exposure_scripts for item in script.searches]
    socials = [
        item for script in corpus.exposure_scripts for item in script.social_profiles
    ]

    assert breaches
    assert brokers
    assert searches
    assert socials
    assert any(
        search.match_kind is SearchMatchKind.NAME_COLLISION for search in searches
    )
    assert any(
        any(event.state is LifecycleState.REAPPEARED for event in broker.lifecycle)
        for broker in brokers
    )
