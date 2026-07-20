from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from itertools import pairwise
from urllib.parse import urlparse

from synthworld.exposures import (
    BreachExposure,
    BrokerExposure,
    BrokerLifecycleEvent,
    CorpusMetrics,
    DataClass,
    ExposureCorpus,
    ExposureScript,
    LifecycleState,
    SearchExposure,
    SearchMatchKind,
    SocialExposure,
)
from synthworld.metrics import _iter_records, _record_is_safely_fake
from synthworld.models import Persona, SyntheticModel

_ALLOWED_TRANSITIONS = {
    LifecycleState.FOUND: {LifecycleState.REMOVAL_REQUESTED},
    LifecycleState.REMOVAL_REQUESTED: {LifecycleState.CONFIRMED_REMOVED},
    LifecycleState.CONFIRMED_REMOVED: {LifecycleState.REAPPEARED},
    LifecycleState.REAPPEARED: set(),
}


def evaluate_corpus(corpus: ExposureCorpus) -> CorpusMetrics:
    """Measure completeness, safety, and referential ground truth."""

    personas = {persona.id: persona for persona in corpus.world.personas}
    script_counts = Counter(script.persona_id for script in corpus.exposure_scripts)
    covered_personas = sum(script_counts[persona_id] == 1 for persona_id in personas)
    valid_scripts = sum(
        _script_references_are_valid(script, personas)
        for script in corpus.exposure_scripts
    )
    records = tuple(_iter_corpus_records(corpus))
    safe_records = sum(_corpus_record_is_safely_fake(record) for record in records)

    return CorpusMetrics(
        persona_count=len(personas),
        script_count=len(corpus.exposure_scripts),
        script_coverage=_rate(covered_personas, len(personas)),
        exposure_reference_integrity=_rate(
            valid_scripts,
            len(corpus.exposure_scripts),
        ),
        safely_fake_record_rate=_rate(safe_records, len(records)),
        zero_exposure_persona_count=sum(
            script.exposure_count == 0 for script in corpus.exposure_scripts
        ),
        name_collision_false_positive_count=sum(
            search.match_kind is SearchMatchKind.NAME_COLLISION
            for script in corpus.exposure_scripts
            for search in script.searches
        ),
        broker_reappearance_count=sum(
            any(event.state is LifecycleState.REAPPEARED for event in broker.lifecycle)
            for script in corpus.exposure_scripts
            for broker in script.brokers
        ),
    )


def _script_references_are_valid(
    script: ExposureScript,
    personas: dict[str, Persona],
) -> bool:
    persona = personas.get(script.persona_id)
    if persona is None:
        return False
    for breach in script.breaches:
        if not _supports_all(persona, breach.exposed_data):
            return False
    for broker in script.brokers:
        if not _supports_all(persona, broker.exposed_data):
            return False
    for search in script.searches:
        if not _supports_all(persona, search.exposed_data):
            return False
    for broker in script.brokers:
        if not _lifecycle_is_valid(broker):
            return False
    for search in script.searches:
        if search.actual_persona_id not in personas:
            return False
        if (
            search.match_kind is SearchMatchKind.TRUE_MATCH
            and search.actual_persona_id != script.persona_id
        ):
            return False
        if (
            search.match_kind is SearchMatchKind.NAME_COLLISION
            and search.actual_persona_id == script.persona_id
        ):
            return False
    persona_usernames = {item.value for item in persona.usernames}
    for profile in script.social_profiles:
        if profile.username not in persona_usernames:
            return False
        if not _supports_all(persona, profile.exposed_data):
            return False
        if script.persona_id in profile.connected_person_ids:
            return False
        if not set(profile.connected_person_ids) <= personas.keys():
            return False
    return True


def _lifecycle_is_valid(broker: BrokerExposure) -> bool:
    states = [event.state for event in broker.lifecycle]
    timestamps = [event.at for event in broker.lifecycle]
    if not states or states[0] is not LifecycleState.FOUND:
        return False
    if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
        return False
    return all(
        current in _ALLOWED_TRANSITIONS[previous]
        for previous, current in pairwise(states)
    )


def _supports_all(persona: Persona, data_classes: tuple[DataClass, ...]) -> bool:
    return all(_persona_supports(persona, item) for item in data_classes)


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


def _iter_corpus_records(corpus: ExposureCorpus) -> Iterator[SyntheticModel]:
    yield corpus
    yield from _iter_records(corpus.world)
    for script in corpus.exposure_scripts:
        yield script
        yield from script.breaches
        for broker in script.brokers:
            yield broker
            yield from broker.lifecycle
        yield from script.searches
        yield from script.social_profiles


def _corpus_record_is_safely_fake(record: SyntheticModel) -> bool:
    if not _record_is_safely_fake(record):
        return False
    if isinstance(record, BreachExposure):
        return record.breach_name.startswith("Example Breach ")
    if isinstance(record, BrokerExposure):
        return record.broker_name.startswith("Example Broker ")
    if isinstance(record, SearchExposure):
        return urlparse(
            record.locator
        ).hostname == "search.example.test" and record.title.startswith(
            ("Synthetic ", "Example ")
        )
    if isinstance(record, SocialExposure):
        return (
            record.platform == "Example Social"
            and urlparse(record.locator).hostname == "social.example.test"
            and record.username.startswith("synth_")
        )
    if isinstance(record, BrokerLifecycleEvent):
        return True
    return True


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0
