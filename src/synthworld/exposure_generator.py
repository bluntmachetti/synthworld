from __future__ import annotations

from datetime import date, timedelta

from synthworld.exposures import (
    BreachExposure,
    BrokerExposure,
    BrokerLifecycleEvent,
    DataClass,
    ExposureCorpus,
    ExposureScript,
    ExposureSeverity,
    LifecycleState,
    SearchExposure,
    SearchMatchKind,
    SearchResultKind,
    SocialExposure,
)
from synthworld.generator import generate_world
from synthworld.models import Persona, SynthWorld

_SEVERITIES = tuple(ExposureSeverity)
_BREACH_DATA = (
    (DataClass.EMAIL, DataClass.PASSWORD),
    (DataClass.EMAIL, DataClass.PHONE, DataClass.ADDRESS),
    (DataClass.EMAIL, DataClass.NATIONAL_ID, DataClass.DATE_OF_BIRTH),
)
_SEARCH_KINDS = tuple(SearchResultKind)
_BROKER_EPOCH = date(2026, 1, 1)


def generate_exposure_corpus(
    *,
    seed: int,
    persona_count: int = 10,
) -> ExposureCorpus:
    """Generate exposure answer keys derived entirely from a core world."""

    world = generate_world(seed=seed, persona_count=persona_count)
    scripts = tuple(
        _exposure_script(world=world, persona=persona, index=index)
        for index, persona in enumerate(world.personas)
    )
    return ExposureCorpus(seed=seed, world=world, exposure_scripts=scripts)


def _exposure_script(
    *,
    world: SynthWorld,
    persona: Persona,
    index: int,
) -> ExposureScript:
    if index == len(world.personas) - 1:
        return ExposureScript(
            persona_id=persona.id,
            breaches=(),
            brokers=(),
            searches=(),
            social_profiles=(),
        )

    breaches = tuple(
        _breach(persona=persona, persona_index=index, exposure_index=offset)
        for offset in range(1 + (index % 3))
    )
    brokers = tuple(
        _broker(persona=persona, persona_index=index, exposure_index=offset)
        for offset in range(index % 3)
    )
    searches = tuple(
        _search(
            world=world,
            persona=persona,
            persona_index=index,
            exposure_index=offset,
            is_collision=index % 2 == 0 and offset == index % 4,
        )
        for offset in range(1 + (index % 4))
    )
    social_profiles = tuple(
        _social(
            world=world,
            persona=persona,
            persona_index=index,
            exposure_index=offset,
        )
        for offset in range(1 + (index % 2))
    )
    return ExposureScript(
        persona_id=persona.id,
        breaches=breaches,
        brokers=brokers,
        searches=searches,
        social_profiles=social_profiles,
    )


def _breach(
    *,
    persona: Persona,
    persona_index: int,
    exposure_index: int,
) -> BreachExposure:
    pattern_index = (persona_index + exposure_index) % len(_BREACH_DATA)
    return BreachExposure(
        id=f"breach-{persona_index + 1:04d}-{exposure_index + 1:02d}",
        breach_name=(
            f"Example Breach {persona_index + 1:04d}-{exposure_index + 1:02d}"
        ),
        occurred_on=date(
            2022 + ((persona_index + exposure_index) % 4),
            1 + ((persona_index * 2 + exposure_index) % 12),
            1 + ((persona_index + exposure_index * 3) % 28),
        ),
        severity=_SEVERITIES[(persona_index + exposure_index) % len(_SEVERITIES)],
        exposed_data=_BREACH_DATA[pattern_index],
    )


def _broker(
    *,
    persona: Persona,
    persona_index: int,
    exposure_index: int,
) -> BrokerExposure:
    found_at = _BROKER_EPOCH + timedelta(days=persona_index * 10 + exposure_index)
    lifecycle_kind = (persona_index + exposure_index) % 3
    lifecycle = [BrokerLifecycleEvent(state=LifecycleState.FOUND, at=found_at)]
    if lifecycle_kind != 1:
        lifecycle.extend(
            (
                BrokerLifecycleEvent(
                    state=LifecycleState.REMOVAL_REQUESTED,
                    at=found_at + timedelta(days=5),
                ),
                BrokerLifecycleEvent(
                    state=LifecycleState.CONFIRMED_REMOVED,
                    at=found_at + timedelta(days=35),
                ),
            )
        )
    if lifecycle_kind == 0:
        lifecycle.append(
            BrokerLifecycleEvent(
                state=LifecycleState.REAPPEARED,
                at=found_at + timedelta(days=80),
            )
        )

    return BrokerExposure(
        id=f"broker-{persona_index + 1:04d}-{exposure_index + 1:02d}",
        broker_name=(
            f"Example Broker {persona_index + 1:04d}-{exposure_index + 1:02d}"
        ),
        exposed_data=(DataClass.EMAIL, DataClass.ADDRESS, DataClass.PHONE),
        lifecycle=tuple(lifecycle),
    )


def _search(
    *,
    world: SynthWorld,
    persona: Persona,
    persona_index: int,
    exposure_index: int,
    is_collision: bool,
) -> SearchExposure:
    actual_persona = (
        world.personas[(persona_index + 1) % len(world.personas)]
        if is_collision
        else persona
    )
    match_kind = (
        SearchMatchKind.NAME_COLLISION if is_collision else SearchMatchKind.TRUE_MATCH
    )
    title_prefix = "Example name-collision" if is_collision else "Synthetic profile"
    return SearchExposure(
        id=f"search-{persona_index + 1:04d}-{exposure_index + 1:02d}",
        result_kind=_SEARCH_KINDS[
            (persona_index + exposure_index) % len(_SEARCH_KINDS)
        ],
        title=f"{title_prefix} result {persona_index + 1:04d}-{exposure_index + 1:02d}",
        locator=(
            f"https://search.example.test/results/{persona.id}/{exposure_index + 1:02d}"
        ),
        match_kind=match_kind,
        actual_persona_id=actual_persona.id,
        exposed_data=(DataClass.EMAIL, DataClass.EMPLOYER),
    )


def _social(
    *,
    world: SynthWorld,
    persona: Persona,
    persona_index: int,
    exposure_index: int,
) -> SocialExposure:
    connected_person = world.personas[
        (persona_index + exposure_index + 1) % len(world.personas)
    ]
    return SocialExposure(
        id=f"social-{persona_index + 1:04d}-{exposure_index + 1:02d}",
        username=persona.usernames[0].value,
        locator=(
            "https://social.example.test/profiles/"
            f"{persona.usernames[0].value}/{exposure_index + 1:02d}"
        ),
        exposed_data=(
            DataClass.USERNAME,
            DataClass.EMPLOYER,
            DataClass.EDUCATION,
        ),
        connected_person_ids=(connected_person.id,),
    )
