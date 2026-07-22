from __future__ import annotations

import re
from enum import StrEnum
from itertools import pairwise
from typing import Literal

from pydantic import Field, field_validator, model_validator

from synthworld.exposures import DataClass
from synthworld.models import SyntheticModel

_CORPUS_PERSONA_ID = re.compile(r"\bpersona-\d{4}\b")
_EXACT_CORPUS_PERSONA_ID = re.compile(r"persona-\d{4}")


class ExtractionSourceType(StrEnum):
    BREACH = "breach"
    BROKER = "broker"
    SEARCH = "search"
    SOCIAL = "social"


class ExtractionPagePurpose(StrEnum):
    EXPOSURE = "exposure"
    NEGATIVE_CONTROL = "negative_control"


class ExtractionPage(SyntheticModel):
    """The product-safe side of one deterministic source document."""

    source_type: ExtractionSourceType
    source_record_id: str
    purpose: ExtractionPagePurpose
    title: str
    content: str

    @field_validator("source_record_id", "title", "content")
    @classmethod
    def require_safe_nonblank_page_field(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("page fields must be nonblank")
        if _CORPUS_PERSONA_ID.search(value):
            raise ValueError("page fields cannot contain a corpus routing key")
        return value


class ExtractionSpan(SyntheticModel):
    """One exact occurrence in an evaluator-only answer key."""

    data_class: DataClass
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str

    @field_validator("data_class")
    @classmethod
    def reject_password_value(cls, value: DataClass) -> DataClass:
        if value is DataClass.PASSWORD:
            raise ValueError("password values are forbidden")
        return value

    @field_validator("text")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        if not value:
            raise ValueError("span text must be nonblank")
        return value

    @model_validator(mode="after")
    def require_forward_range(self) -> ExtractionSpan:
        if self.end <= self.start:
            raise ValueError("span end must follow start")
        return self


class ExtractionAnswerKey(SyntheticModel):
    """Evaluator-only ownership and exact occurrence labels."""

    content_persona_id: str
    spans: tuple[ExtractionSpan, ...]

    @field_validator("content_persona_id")
    @classmethod
    def require_corpus_persona_id(cls, value: str) -> str:
        if _EXACT_CORPUS_PERSONA_ID.fullmatch(value) is None:
            raise ValueError("answer key requires a content persona ID")
        return value


def _validate_span_ordering(spans: tuple[ExtractionSpan, ...]) -> None:
    """Reject spans that are unsorted or overlapping without needing content."""

    if spans != tuple(sorted(spans, key=lambda item: (item.start, item.end))):
        raise ValueError("answer-key spans must be sorted")
    if any(current.start < previous.end for previous, current in pairwise(spans)):
        raise ValueError("answer-key spans cannot overlap")


def _validate_span_occurrences(content: str, spans: tuple[ExtractionSpan, ...]) -> None:
    """Reject spans that do not sit exactly on their page content."""

    _validate_span_ordering(spans)
    for span in spans:
        if span.end > len(content):
            raise ValueError("answer-key span is outside page content")
        if content[span.start : span.end] != span.text:
            raise ValueError("answer-key span text does not match page content")


def _require_unique_page_keys(
    keys: tuple[tuple[ExtractionSourceType, str], ...],
) -> None:
    if len(keys) != len(set(keys)):
        raise ValueError("extraction page keys must be unique")


def _require_single_negative_control(
    purposes: tuple[ExtractionPagePurpose, ...],
) -> None:
    controls = sum(
        purpose is ExtractionPagePurpose.NEGATIVE_CONTROL for purpose in purposes
    )
    if controls != 1:
        raise ValueError("extraction corpus requires exactly one negative control")


class AnnotatedExtractionPage(SyntheticModel):
    page: ExtractionPage
    answer_key: ExtractionAnswerKey

    @model_validator(mode="after")
    def validate_span_occurrences(self) -> AnnotatedExtractionPage:
        _validate_span_occurrences(self.page.content, self.answer_key.spans)
        return self


class ExtractionCorpus(SyntheticModel):
    """The annotated evaluator bundle: safe pages paired with answer keys."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    seed: int
    pages: tuple[AnnotatedExtractionPage, ...]

    @model_validator(mode="after")
    def validate_page_set(self) -> ExtractionCorpus:
        _require_unique_page_keys(
            tuple(
                (item.page.source_type, item.page.source_record_id)
                for item in self.pages
            )
        )
        _require_single_negative_control(
            tuple(item.page.purpose for item in self.pages)
        )
        return self

    def to_public(self) -> PublicExtractionCorpus:
        """Project the product-safe pages with no answer keys attached."""

        return PublicExtractionCorpus(
            seed=self.seed,
            pages=tuple(item.page for item in self.pages),
        )

    def to_answer_key(self) -> ExtractionAnswerKeyCorpus:
        """Project the evaluator-only answers keyed back to each page."""

        return ExtractionAnswerKeyCorpus(
            seed=self.seed,
            answers=tuple(
                ExtractionPageAnswer(
                    source_type=item.page.source_type,
                    source_record_id=item.page.source_record_id,
                    answer_key=item.answer_key,
                )
                for item in self.pages
            ),
        )


class PublicExtractionCorpus(SyntheticModel):
    """The product-safe side of the extraction benchmark: pages, no truth."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    seed: int
    pages: tuple[ExtractionPage, ...]

    @model_validator(mode="after")
    def validate_page_set(self) -> PublicExtractionCorpus:
        _require_unique_page_keys(
            tuple((page.source_type, page.source_record_id) for page in self.pages)
        )
        _require_single_negative_control(tuple(page.purpose for page in self.pages))
        return self


class ExtractionPageAnswer(SyntheticModel):
    """One page's evaluator-only truth, keyed to its public page."""

    source_type: ExtractionSourceType
    source_record_id: str
    answer_key: ExtractionAnswerKey

    @field_validator("source_record_id")
    @classmethod
    def require_safe_source_record_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("page fields must be nonblank")
        if _CORPUS_PERSONA_ID.search(value):
            raise ValueError("page fields cannot contain a corpus routing key")
        return value

    @model_validator(mode="after")
    def validate_span_ordering(self) -> ExtractionPageAnswer:
        _validate_span_ordering(self.answer_key.spans)
        return self


class ExtractionAnswerKeyCorpus(SyntheticModel):
    """The evaluator-only side of the extraction benchmark."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    seed: int
    answers: tuple[ExtractionPageAnswer, ...]

    @model_validator(mode="after")
    def validate_answer_set(self) -> ExtractionAnswerKeyCorpus:
        _require_unique_page_keys(
            tuple(
                (answer.source_type, answer.source_record_id) for answer in self.answers
            )
        )
        return self


class ExtractionBenchmark(SyntheticModel):
    """A public extraction corpus joined to its physically separate answers."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    seed: int
    public: PublicExtractionCorpus
    answers: ExtractionAnswerKeyCorpus

    @model_validator(mode="after")
    def require_exact_separated_truth(self) -> ExtractionBenchmark:
        if self.public.seed != self.seed or self.answers.seed != self.seed:
            raise ValueError("extraction benchmark seeds must match")
        pages = {
            (page.source_type, page.source_record_id): page
            for page in self.public.pages
        }
        answers = {
            (answer.source_type, answer.source_record_id): answer
            for answer in self.answers.answers
        }
        if pages.keys() != answers.keys():
            raise ValueError("extraction benchmark public and answer pages must match")
        for key, page in pages.items():
            _validate_span_occurrences(page.content, answers[key].answer_key.spans)
        return self


__all__ = [
    "AnnotatedExtractionPage",
    "ExtractionAnswerKey",
    "ExtractionAnswerKeyCorpus",
    "ExtractionBenchmark",
    "ExtractionCorpus",
    "ExtractionPage",
    "ExtractionPageAnswer",
    "ExtractionPagePurpose",
    "ExtractionSourceType",
    "ExtractionSpan",
    "PublicExtractionCorpus",
]
