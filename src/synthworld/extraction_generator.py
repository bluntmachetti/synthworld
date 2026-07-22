from __future__ import annotations

from synthworld.exposure_generator import generate_exposure_corpus
from synthworld.exposures import (
    BreachExposure,
    BrokerExposure,
    DataClass,
    ExposureCorpus,
    SearchExposure,
    SocialExposure,
)
from synthworld.extraction import (
    AnnotatedExtractionPage,
    ExtractionAnswerKey,
    ExtractionBenchmark,
    ExtractionCorpus,
    ExtractionPage,
    ExtractionPagePurpose,
    ExtractionSourceType,
    ExtractionSpan,
)
from synthworld.models import Persona

_PREFIXES: dict[ExtractionSourceType, dict[DataClass, str]] = {
    ExtractionSourceType.BREACH: {
        DataClass.EMAIL: "Account email: ",
        DataClass.PHONE: "Telephone: ",
        DataClass.ADDRESS: "Postal address: ",
        DataClass.DATE_OF_BIRTH: "Date of birth: ",
        DataClass.NATIONAL_ID: "National ID: ",
    },
    ExtractionSourceType.BROKER: {
        DataClass.EMAIL: "Email: ",
        DataClass.PHONE: "Phone: ",
        DataClass.ADDRESS: "Address: ",
    },
    ExtractionSourceType.SEARCH: {
        DataClass.EMAIL: "Email: ",
        DataClass.EMPLOYER: "Employer: ",
    },
    ExtractionSourceType.SOCIAL: {
        DataClass.USERNAME: "Handle: @",
        DataClass.EMPLOYER: "Employer: ",
        DataClass.EDUCATION: "Education: ",
    },
}
_PASSWORD_MARKER = "Credential status: exposed; value intentionally absent."  # noqa: S105
_NEGATIVE_CONTENT = (
    "Synthetic no-result page\n"
    "No email address, telephone number, postal address, date of birth, username, "
    "employer, school, or national identifier is published.\n"
)


class _PageBuilder:
    def __init__(self) -> None:
        self.content = ""
        self.spans: list[ExtractionSpan] = []

    def line(self, text: str) -> None:
        self.content += f"{text}\n"

    def identity_line(self, *, prefix: str, value: str, kind: DataClass) -> None:
        self.content += prefix
        start = len(self.content)
        self.content += value
        self.spans.append(
            ExtractionSpan(
                data_class=kind,
                start=start,
                end=len(self.content),
                text=value,
            )
        )
        self.content += "\n"


def generate_extraction_corpus(
    *,
    seed: int,
    persona_count: int = 10,
) -> ExtractionCorpus:
    """Render a separate exact-span benchmark from an exposure corpus."""

    exposure_corpus = generate_exposure_corpus(
        seed=seed,
        persona_count=persona_count,
    )
    personas = {persona.id: persona for persona in exposure_corpus.world.personas}
    pages: list[AnnotatedExtractionPage] = []

    for script in exposure_corpus.exposure_scripts:
        subject = personas[script.persona_id]
        pages.extend(_breach_page(subject, item) for item in script.breaches)
        pages.extend(_broker_page(subject, item) for item in script.brokers)
        pages.extend(
            _search_page(personas[item.actual_persona_id], item)
            for item in script.searches
        )
        pages.extend(_social_page(subject, item) for item in script.social_profiles)

    pages.append(_negative_page(exposure_corpus))
    return ExtractionCorpus(seed=seed, pages=tuple(pages))


def generate_extraction_benchmark(
    *,
    seed: int,
    persona_count: int = 10,
) -> ExtractionBenchmark:
    """Render the extraction benchmark as physically separate public and truth."""

    corpus = generate_extraction_corpus(seed=seed, persona_count=persona_count)
    return ExtractionBenchmark(
        seed=seed,
        public=corpus.to_public(),
        answers=corpus.to_answer_key(),
    )


def _breach_page(
    persona: Persona,
    exposure: BreachExposure,
) -> AnnotatedExtractionPage:
    builder = _PageBuilder()
    builder.line("Synthetic breach record")
    builder.line(f"Incident date: {exposure.occurred_on.isoformat()}")
    _render_exposed_values(
        builder=builder,
        persona=persona,
        source_type=ExtractionSourceType.BREACH,
        data_classes=exposure.exposed_data,
    )
    return _annotated_page(
        builder=builder,
        persona=persona,
        source_type=ExtractionSourceType.BREACH,
        source_record_id=exposure.id,
        title=exposure.breach_name,
    )


def _broker_page(
    persona: Persona,
    exposure: BrokerExposure,
) -> AnnotatedExtractionPage:
    builder = _PageBuilder()
    builder.line("Synthetic broker listing")
    _render_exposed_values(
        builder=builder,
        persona=persona,
        source_type=ExtractionSourceType.BROKER,
        data_classes=exposure.exposed_data,
    )
    return _annotated_page(
        builder=builder,
        persona=persona,
        source_type=ExtractionSourceType.BROKER,
        source_record_id=exposure.id,
        title=exposure.broker_name,
    )


def _search_page(
    persona: Persona,
    exposure: SearchExposure,
) -> AnnotatedExtractionPage:
    builder = _PageBuilder()
    builder.line("Synthetic search result")
    _render_exposed_values(
        builder=builder,
        persona=persona,
        source_type=ExtractionSourceType.SEARCH,
        data_classes=exposure.exposed_data,
    )
    return _annotated_page(
        builder=builder,
        persona=persona,
        source_type=ExtractionSourceType.SEARCH,
        source_record_id=exposure.id,
        title=exposure.title,
    )


def _social_page(
    persona: Persona,
    exposure: SocialExposure,
) -> AnnotatedExtractionPage:
    builder = _PageBuilder()
    builder.line("Synthetic social profile")
    builder.line(f"Platform: {exposure.platform}")
    _render_exposed_values(
        builder=builder,
        persona=persona,
        source_type=ExtractionSourceType.SOCIAL,
        data_classes=exposure.exposed_data,
    )
    return _annotated_page(
        builder=builder,
        persona=persona,
        source_type=ExtractionSourceType.SOCIAL,
        source_record_id=exposure.id,
        title=f"{exposure.platform} profile @{exposure.username}",
    )


def _render_exposed_values(
    *,
    builder: _PageBuilder,
    persona: Persona,
    source_type: ExtractionSourceType,
    data_classes: tuple[DataClass, ...],
) -> None:
    for data_class in data_classes:
        if data_class is DataClass.PASSWORD:
            builder.line(_PASSWORD_MARKER)
        else:
            builder.identity_line(
                prefix=_PREFIXES[source_type][data_class],
                value=_persona_value(persona, data_class),
                kind=data_class,
            )


def _persona_value(persona: Persona, data_class: DataClass) -> str:
    address = persona.addresses[0]
    values = {
        DataClass.EMAIL: persona.emails[0].value,
        DataClass.USERNAME: persona.usernames[0].value,
        DataClass.PHONE: persona.phones[0].value,
        DataClass.ADDRESS: (
            f"{address.house_number} {address.street_name}, "
            f"{address.city} {address.postal_code}"
        ),
        DataClass.DATE_OF_BIRTH: persona.date_of_birth.isoformat(),
        DataClass.EMPLOYER: persona.employment[0].organization,
        DataClass.EDUCATION: persona.education[0].institution,
        DataClass.NATIONAL_ID: persona.national_ids[0].value,
    }
    return values[data_class]


def _annotated_page(
    *,
    builder: _PageBuilder,
    persona: Persona,
    source_type: ExtractionSourceType,
    source_record_id: str,
    title: str,
) -> AnnotatedExtractionPage:
    return AnnotatedExtractionPage(
        page=ExtractionPage(
            source_type=source_type,
            source_record_id=source_record_id,
            purpose=ExtractionPagePurpose.EXPOSURE,
            title=title,
            content=builder.content,
        ),
        answer_key=ExtractionAnswerKey(
            content_persona_id=persona.id,
            spans=tuple(builder.spans),
        ),
    )


def _negative_page(corpus: ExposureCorpus) -> AnnotatedExtractionPage:
    zero_exposure_script = next(
        script for script in corpus.exposure_scripts if script.exposure_count == 0
    )
    return AnnotatedExtractionPage(
        page=ExtractionPage(
            source_type=ExtractionSourceType.SEARCH,
            source_record_id="negative-control-0001",
            purpose=ExtractionPagePurpose.NEGATIVE_CONTROL,
            title="Synthetic no-result page",
            content=_NEGATIVE_CONTENT,
        ),
        answer_key=ExtractionAnswerKey(
            content_persona_id=zero_exposure_script.persona_id,
            spans=(),
        ),
    )


__all__ = ["generate_extraction_benchmark", "generate_extraction_corpus"]
