from __future__ import annotations

from datetime import timedelta

from synthworld import (
    DataClass,
    LifecycleState,
    SearchMatchKind,
    evaluate_corpus,
    generate_exposure_corpus,
)
from synthworld.exposures import (
    BreachExposure,
    BrokerExposure,
    ExposureCorpus,
    ExposureScript,
    SearchExposure,
    SocialExposure,
)
from synthworld.models import Persona


def test_golden_corpus_ground_truth_metrics_are_perfect() -> None:
    metrics = evaluate_corpus(
        generate_exposure_corpus(seed=20_260_719, persona_count=10)
    )

    assert metrics.script_coverage == 1.0
    assert metrics.exposure_reference_integrity == 1.0
    assert metrics.safely_fake_record_rate == 1.0
    assert metrics.zero_exposure_persona_count == 1
    assert metrics.name_collision_false_positive_count > 0
    assert metrics.broker_reappearance_count > 0


def test_generated_hundred_person_eval_tier_has_perfect_integrity() -> None:
    metrics = evaluate_corpus(
        generate_exposure_corpus(seed=20_260_719, persona_count=100)
    )

    assert metrics.persona_count == 100
    assert metrics.script_count == 100
    assert metrics.script_coverage == 1.0
    assert metrics.exposure_reference_integrity == 1.0
    assert metrics.safely_fake_record_rate == 1.0
    assert metrics.zero_exposure_persona_count == 1


def test_reference_metric_rejects_missing_personas_and_attributes() -> None:
    corpus = generate_exposure_corpus(seed=20_260_719, persona_count=10)
    missing_persona_script = corpus.exposure_scripts[0].model_copy(
        update={"persona_id": "persona-missing"}
    )
    missing_persona = _replace_script(corpus, 0, missing_persona_script)

    first_persona = corpus.world.personas[0]
    persona_without_email = first_persona.model_copy(update={"emails": ()})
    missing_attribute = _replace_persona(corpus, 0, persona_without_email)

    broker = (
        corpus.exposure_scripts[2]
        .brokers[0]
        .model_copy(update={"exposed_data": (DataClass.EDUCATION,)})
    )
    broker_missing_data = _replace_persona(
        _replace_broker(corpus, 2, 0, broker),
        2,
        corpus.world.personas[2].model_copy(update={"education": ()}),
    )

    search = (
        corpus.exposure_scripts[1]
        .searches[0]
        .model_copy(update={"exposed_data": (DataClass.EDUCATION,)})
    )
    search_missing_data = _replace_persona(
        _replace_search(corpus, 1, 0, search),
        1,
        corpus.world.personas[1].model_copy(update={"education": ()}),
    )

    assert evaluate_corpus(missing_persona).exposure_reference_integrity < 1.0
    assert evaluate_corpus(missing_attribute).exposure_reference_integrity < 1.0
    assert evaluate_corpus(broker_missing_data).exposure_reference_integrity < 1.0
    assert evaluate_corpus(search_missing_data).exposure_reference_integrity < 1.0


def test_reference_metric_rejects_every_invalid_search_reference() -> None:
    corpus = generate_exposure_corpus(seed=20_260_719, persona_count=10)
    collision_script = corpus.exposure_scripts[0]
    collision = collision_script.searches[0]
    assert collision.match_kind is SearchMatchKind.NAME_COLLISION
    collision_as_self = collision.model_copy(
        update={"actual_persona_id": collision_script.persona_id}
    )

    true_script = corpus.exposure_scripts[1]
    true_match = true_script.searches[0]
    assert true_match.match_kind is SearchMatchKind.TRUE_MATCH
    true_as_other = true_match.model_copy(
        update={"actual_persona_id": corpus.world.personas[2].id}
    )
    dangling = true_match.model_copy(update={"actual_persona_id": "persona-missing"})

    invalid_corpora = (
        _replace_search(corpus, 0, 0, collision_as_self),
        _replace_search(corpus, 1, 0, true_as_other),
        _replace_search(corpus, 1, 0, dangling),
    )
    for invalid in invalid_corpora:
        assert evaluate_corpus(invalid).exposure_reference_integrity < 1.0


def test_reference_metric_rejects_every_invalid_social_reference() -> None:
    corpus = generate_exposure_corpus(seed=20_260_719, persona_count=10)
    script = corpus.exposure_scripts[0]
    profile = script.social_profiles[0]
    wrong_username = profile.model_copy(update={"username": "synth_missing_0000"})
    self_connection = profile.model_copy(
        update={"connected_person_ids": (script.persona_id,)}
    )
    dangling_connection = profile.model_copy(
        update={"connected_person_ids": ("persona-missing",)}
    )

    persona_without_education = corpus.world.personas[0].model_copy(
        update={"education": ()}
    )
    unsupported_data = _replace_persona(corpus, 0, persona_without_education)

    invalid_corpora = (
        _replace_profile(corpus, 0, 0, wrong_username),
        unsupported_data,
        _replace_profile(corpus, 0, 0, self_connection),
        _replace_profile(corpus, 0, 0, dangling_connection),
    )
    for invalid in invalid_corpora:
        assert evaluate_corpus(invalid).exposure_reference_integrity < 1.0


def test_reference_metric_rejects_every_invalid_broker_lifecycle() -> None:
    corpus = generate_exposure_corpus(seed=20_260_719, persona_count=10)
    script = corpus.exposure_scripts[2]
    broker = script.brokers[0]
    first_event = broker.lifecycle[0]
    second_event = broker.lifecycle[1]
    empty = broker.model_copy(update={"lifecycle": ()})
    wrong_first = broker.model_copy(
        update={
            "lifecycle": (
                first_event.model_copy(
                    update={"state": LifecycleState.CONFIRMED_REMOVED}
                ),
            )
        }
    )
    out_of_order = broker.model_copy(
        update={
            "lifecycle": (
                first_event,
                second_event.model_copy(
                    update={"at": first_event.at - timedelta(days=1)}
                ),
            )
        }
    )
    duplicate_time = broker.model_copy(
        update={
            "lifecycle": (
                first_event,
                second_event.model_copy(update={"at": first_event.at}),
            )
        }
    )
    invalid_transition = broker.model_copy(
        update={
            "lifecycle": (
                first_event,
                second_event.model_copy(
                    update={"state": LifecycleState.CONFIRMED_REMOVED}
                ),
            )
        }
    )

    for invalid_broker in (
        empty,
        wrong_first,
        out_of_order,
        duplicate_time,
        invalid_transition,
    ):
        invalid = _replace_broker(corpus, 2, 0, invalid_broker)
        assert evaluate_corpus(invalid).exposure_reference_integrity < 1.0


def test_safety_metric_rejects_unsafe_exposure_records() -> None:
    corpus = generate_exposure_corpus(seed=20_260_719, persona_count=10)
    breach = corpus.exposure_scripts[0].breaches[0]
    broker = corpus.exposure_scripts[2].brokers[0]
    search = corpus.exposure_scripts[0].searches[0]
    profile = corpus.exposure_scripts[0].social_profiles[0]

    unsafe_corpora = (
        corpus.model_copy(update={"synthetic": False}),
        _replace_breach(
            corpus,
            0,
            0,
            breach.model_copy(update={"breach_name": "Unmarked Breach"}),
        ),
        _replace_broker(
            corpus,
            2,
            0,
            broker.model_copy(update={"broker_name": "Unmarked Broker"}),
        ),
        _replace_search(
            corpus,
            0,
            0,
            search.model_copy(update={"locator": "https://invalid.test/result"}),
        ),
        _replace_search(
            corpus,
            0,
            0,
            search.model_copy(update={"title": "Unmarked result"}),
        ),
        _replace_profile(
            corpus,
            0,
            0,
            profile.model_copy(update={"platform": "Unmarked Social"}),
        ),
        _replace_profile(
            corpus,
            0,
            0,
            profile.model_copy(update={"locator": "https://invalid.test/profile"}),
        ),
        _replace_profile(
            corpus,
            0,
            0,
            profile.model_copy(update={"username": "unmarked"}),
        ),
    )

    for unsafe in unsafe_corpora:
        assert evaluate_corpus(unsafe).safely_fake_record_rate < 1.0


def test_empty_corpus_metrics_have_defined_denominator_behavior() -> None:
    corpus = generate_exposure_corpus(seed=20_260_719, persona_count=10)
    empty_world = corpus.world.model_copy(update={"personas": (), "relationships": ()})
    empty_corpus = corpus.model_copy(
        update={"world": empty_world, "exposure_scripts": ()}
    )

    metrics = evaluate_corpus(empty_corpus)

    assert metrics.script_coverage == 1.0
    assert metrics.exposure_reference_integrity == 1.0
    assert metrics.zero_exposure_persona_count == 0


def test_all_declared_data_classes_are_exercised_by_the_golden_corpus() -> None:
    corpus = generate_exposure_corpus(seed=20_260_719, persona_count=10)
    observed: set[DataClass] = set()
    for script in corpus.exposure_scripts:
        for breach in script.breaches:
            observed.update(breach.exposed_data)
        for broker in script.brokers:
            observed.update(broker.exposed_data)
        for search in script.searches:
            observed.update(search.exposed_data)
        for profile in script.social_profiles:
            observed.update(profile.exposed_data)

    assert observed == set(DataClass)


def _replace_script(
    corpus: ExposureCorpus,
    index: int,
    script: ExposureScript,
) -> ExposureCorpus:
    scripts = list(corpus.exposure_scripts)
    scripts[index] = script
    return corpus.model_copy(update={"exposure_scripts": tuple(scripts)})


def _replace_persona(
    corpus: ExposureCorpus,
    index: int,
    persona: Persona,
) -> ExposureCorpus:
    personas = list(corpus.world.personas)
    personas[index] = persona
    world = corpus.world.model_copy(update={"personas": tuple(personas)})
    return corpus.model_copy(update={"world": world})


def _replace_breach(
    corpus: ExposureCorpus,
    script_index: int,
    exposure_index: int,
    breach: BreachExposure,
) -> ExposureCorpus:
    script = corpus.exposure_scripts[script_index]
    breaches = list(script.breaches)
    breaches[exposure_index] = breach
    return _replace_script(
        corpus,
        script_index,
        script.model_copy(update={"breaches": tuple(breaches)}),
    )


def _replace_broker(
    corpus: ExposureCorpus,
    script_index: int,
    exposure_index: int,
    broker: BrokerExposure,
) -> ExposureCorpus:
    script = corpus.exposure_scripts[script_index]
    brokers = list(script.brokers)
    brokers[exposure_index] = broker
    return _replace_script(
        corpus,
        script_index,
        script.model_copy(update={"brokers": tuple(brokers)}),
    )


def _replace_search(
    corpus: ExposureCorpus,
    script_index: int,
    exposure_index: int,
    search: SearchExposure,
) -> ExposureCorpus:
    script = corpus.exposure_scripts[script_index]
    searches = list(script.searches)
    searches[exposure_index] = search
    return _replace_script(
        corpus,
        script_index,
        script.model_copy(update={"searches": tuple(searches)}),
    )


def _replace_profile(
    corpus: ExposureCorpus,
    script_index: int,
    exposure_index: int,
    profile: SocialExposure,
) -> ExposureCorpus:
    script = corpus.exposure_scripts[script_index]
    profiles = list(script.social_profiles)
    profiles[exposure_index] = profile
    return _replace_script(
        corpus,
        script_index,
        script.model_copy(update={"social_profiles": tuple(profiles)}),
    )
