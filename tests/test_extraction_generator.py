from __future__ import annotations

import re
from collections import Counter

import pytest
from pydantic import ValidationError

from synthworld import DataClass, generate_exposure_corpus
from synthworld.extraction import (
    AnnotatedExtractionPage,
    ExtractionAnswerKey,
    ExtractionCorpus,
    ExtractionPage,
    ExtractionPagePurpose,
    ExtractionSourceType,
    ExtractionSpan,
)
from synthworld.extraction_generator import generate_extraction_corpus


@pytest.mark.parametrize(
    ("persona_count", "page_count", "span_count", "expected_by_kind"),
    [
        (
            10,
            62,
            150,
            {
                DataClass.EMAIL: 48,
                DataClass.USERNAME: 13,
                DataClass.PHONE: 15,
                DataClass.ADDRESS: 15,
                DataClass.DATE_OF_BIRTH: 6,
                DataClass.EMPLOYER: 34,
                DataClass.EDUCATION: 13,
                DataClass.NATIONAL_ID: 6,
            },
        ),
        (
            100,
            692,
            1_695,
            {
                DataClass.EMAIL: 543,
                DataClass.USERNAME: 148,
                DataClass.PHONE: 165,
                DataClass.ADDRESS: 165,
                DataClass.DATE_OF_BIRTH: 66,
                DataClass.EMPLOYER: 394,
                DataClass.EDUCATION: 148,
                DataClass.NATIONAL_ID: 66,
            },
        ),
    ],
)
def test_extraction_corpus_has_exact_page_and_span_counts(
    persona_count: int,
    page_count: int,
    span_count: int,
    expected_by_kind: dict[DataClass, int],
) -> None:
    corpus = generate_extraction_corpus(
        seed=20_260_719,
        persona_count=persona_count,
    )
    spans = [span for item in corpus.pages for span in item.answer_key.spans]

    assert len(corpus.pages) == page_count
    assert len(spans) == span_count
    assert Counter(span.data_class for span in spans) == expected_by_kind
    assert (
        sum(
            page.page.purpose is ExtractionPagePurpose.NEGATIVE_CONTROL
            for page in corpus.pages
        )
        == 1
    )


def test_exposure_pages_cover_every_script_record_once() -> None:
    exposure = generate_exposure_corpus(seed=20_260_719, persona_count=10)
    extraction = generate_extraction_corpus(seed=20_260_719, persona_count=10)
    expected = {
        (source_type, item.id)
        for script in exposure.exposure_scripts
        for source_type, records in (
            (ExtractionSourceType.BREACH, script.breaches),
            (ExtractionSourceType.BROKER, script.brokers),
            (ExtractionSourceType.SEARCH, script.searches),
            (ExtractionSourceType.SOCIAL, script.social_profiles),
        )
        for item in records
    }
    actual = {
        (item.page.source_type, item.page.source_record_id)
        for item in extraction.pages
        if item.page.purpose is ExtractionPagePurpose.EXPOSURE
    }

    assert actual == expected
    assert len(actual) == 61


def test_rendering_has_exact_offsets_and_passwords_never_have_values() -> None:
    corpus = generate_extraction_corpus(seed=20_260_719, persona_count=10)
    first_breach = _page(corpus, "breach-0001-01")

    assert first_breach.page.content == (
        "Synthetic breach record\n"
        "Incident date: 2022-01-01\n"
        "Account email: synth_joel_fisher_0001@example.test\n"
        "Credential status: exposed; value intentionally absent.\n"
    )
    assert [span.data_class for span in first_breach.answer_key.spans] == [
        DataClass.EMAIL
    ]
    assert all(
        first_breach.page.content[span.start : span.end] == span.text
        for span in first_breach.answer_key.spans
    )
    assert "2022-01-01" not in {span.text for span in first_breach.answer_key.spans}

    password_page_count = sum(
        "Credential status: exposed" in item.page.content for item in corpus.pages
    )
    assert password_page_count == 6
    assert all(
        span.data_class is not DataClass.PASSWORD
        for item in corpus.pages
        for span in item.answer_key.spans
    )


def test_each_source_type_uses_stable_contextual_rendering() -> None:
    corpus = generate_extraction_corpus(seed=20_260_719, persona_count=10)

    breach = _page(corpus, "breach-0002-01")
    assert "Account email: " in breach.page.content
    assert "Telephone: +1-200-555-0101\n" in breach.page.content
    assert "Postal address: 100 1 Example Avenue, Testville 00000\n" in (
        breach.page.content
    )

    broker = _page(corpus, "broker-0002-01")
    assert broker.page.content.startswith("Synthetic broker listing\n")
    assert "Email: synth_leslie_begum_0002@example.test\n" in broker.page.content
    assert "Address: 100 1 Example Avenue, Testville 00000\n" in (broker.page.content)
    assert "Phone: +1-200-555-0101\n" in broker.page.content

    social = _page(corpus, "social-0001-01")
    assert social.page.content == (
        "Synthetic social profile\n"
        "Platform: Example Social\n"
        "Handle: @synth_joel_fisher_0001\n"
        "Employer: Example Works 0001\n"
        "Education: Test University 0001\n"
    )
    username = next(
        span
        for span in social.answer_key.spans
        if span.data_class is DataClass.USERNAME
    )
    assert social.page.content[username.start - 1] == "@"
    assert username.text == "synth_joel_fisher_0001"


def test_collision_page_contains_only_the_actual_personas_values() -> None:
    corpus = generate_extraction_corpus(seed=20_260_719, persona_count=10)
    collision = _page(corpus, "search-0001-01")

    assert collision.answer_key.content_persona_id == "persona-0002"
    assert "synth_leslie_begum_0002@example.test" in collision.page.content
    assert "Example Works 0002" in collision.page.content
    assert "synth_joel_fisher_0001@example.test" not in collision.page.content
    assert re.search(r"persona-\d{4}", collision.page.model_dump_json()) is None


def test_negative_page_has_no_identity_values_or_spans() -> None:
    corpus = generate_extraction_corpus(seed=20_260_719, persona_count=10)
    negative = next(
        item
        for item in corpus.pages
        if item.page.purpose is ExtractionPagePurpose.NEGATIVE_CONTROL
    )

    assert negative.page.source_record_id == "negative-control-0001"
    assert negative.answer_key.content_persona_id == "persona-0010"
    assert negative.answer_key.spans == ()
    assert negative.page.content == (
        "Synthetic no-result page\n"
        "No email address, telephone number, postal address, date of birth, "
        "username, employer, school, or national identifier is published.\n"
    )
    assert re.search(r"persona-\d{4}", negative.page.model_dump_json()) is None


def test_span_model_rejects_passwords_and_invalid_ranges() -> None:
    with pytest.raises(ValidationError, match="password values are forbidden"):
        ExtractionSpan(
            data_class=DataClass.PASSWORD,
            start=0,
            end=8,
            text="password",
        )

    with pytest.raises(ValidationError, match="span end must follow start"):
        ExtractionSpan(
            data_class=DataClass.EMAIL,
            start=3,
            end=3,
            text="x",
        )

    with pytest.raises(ValidationError, match="span text must be nonblank"):
        ExtractionSpan(
            data_class=DataClass.EMAIL,
            start=0,
            end=1,
            text="",
        )


def test_page_and_answer_key_models_reject_unsafe_or_malformed_data() -> None:
    with pytest.raises(ValidationError, match="page fields must be nonblank"):
        _safe_page(title=" ")
    with pytest.raises(ValidationError, match="corpus routing key"):
        _safe_page(content="persona-0001")
    with pytest.raises(ValidationError, match="content persona ID"):
        ExtractionAnswerKey(content_persona_id="not-a-persona", spans=())

    page = _safe_page(content="one two three")
    early = ExtractionSpan(
        data_class=DataClass.EMAIL,
        start=0,
        end=3,
        text="one",
    )
    late = ExtractionSpan(
        data_class=DataClass.PHONE,
        start=8,
        end=13,
        text="three",
    )
    overlap = ExtractionSpan(
        data_class=DataClass.ADDRESS,
        start=2,
        end=7,
        text="e two",
    )
    mismatch = ExtractionSpan(
        data_class=DataClass.EMAIL,
        start=0,
        end=3,
        text="two",
    )
    out_of_bounds = ExtractionSpan(
        data_class=DataClass.EMAIL,
        start=12,
        end=15,
        text="end",
    )

    with pytest.raises(ValidationError, match="sorted"):
        _annotated(page, (late, early))
    with pytest.raises(ValidationError, match="overlap"):
        _annotated(page, (early, overlap))
    with pytest.raises(ValidationError, match="does not match"):
        _annotated(page, (mismatch,))
    with pytest.raises(ValidationError, match="outside page content"):
        _annotated(page, (out_of_bounds,))


def test_corpus_rejects_duplicate_page_keys_and_missing_control() -> None:
    page = _annotated(_safe_page(content="safe"), ())
    with pytest.raises(ValidationError, match="page keys must be unique"):
        ExtractionCorpus(seed=1, pages=(page, page))
    with pytest.raises(ValidationError, match="exactly one negative control"):
        ExtractionCorpus(seed=1, pages=(page,))


def _page(corpus: ExtractionCorpus, source_record_id: str) -> AnnotatedExtractionPage:
    return next(
        item for item in corpus.pages if item.page.source_record_id == source_record_id
    )


def _safe_page(
    *,
    title: str = "Safe title",
    content: str = "safe content",
) -> ExtractionPage:
    return ExtractionPage(
        source_type=ExtractionSourceType.SEARCH,
        source_record_id="safe-record",
        purpose=ExtractionPagePurpose.EXPOSURE,
        title=title,
        content=content,
    )


def _annotated(
    page: ExtractionPage,
    spans: tuple[ExtractionSpan, ...],
) -> AnnotatedExtractionPage:
    return AnnotatedExtractionPage(
        page=page,
        answer_key=ExtractionAnswerKey(
            content_persona_id="persona-0001",
            spans=spans,
        ),
    )
