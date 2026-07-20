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


class AnnotatedExtractionPage(SyntheticModel):
    page: ExtractionPage
    answer_key: ExtractionAnswerKey

    @model_validator(mode="after")
    def validate_span_occurrences(self) -> AnnotatedExtractionPage:
        spans = self.answer_key.spans
        if spans != tuple(sorted(spans, key=lambda item: (item.start, item.end))):
            raise ValueError("answer-key spans must be sorted")
        if any(current.start < previous.end for previous, current in pairwise(spans)):
            raise ValueError("answer-key spans cannot overlap")
        for span in spans:
            if span.end > len(self.page.content):
                raise ValueError("answer-key span is outside page content")
            if self.page.content[span.start : span.end] != span.text:
                raise ValueError("answer-key span text does not match page content")
        return self


class ExtractionCorpus(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    seed: int
    pages: tuple[AnnotatedExtractionPage, ...]

    @model_validator(mode="after")
    def validate_page_set(self) -> ExtractionCorpus:
        keys = [
            (item.page.source_type, item.page.source_record_id) for item in self.pages
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("extraction page keys must be unique")
        control_count = sum(
            item.page.purpose is ExtractionPagePurpose.NEGATIVE_CONTROL
            for item in self.pages
        )
        if control_count != 1:
            raise ValueError("extraction corpus requires exactly one negative control")
        return self


__all__ = [
    "AnnotatedExtractionPage",
    "ExtractionAnswerKey",
    "ExtractionCorpus",
    "ExtractionPage",
    "ExtractionPagePurpose",
    "ExtractionSourceType",
    "ExtractionSpan",
]
