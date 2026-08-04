"""Pinned standards and reference profiles for enterprise authorization work."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from synthworld.enterprise.canonical import canonical_json_bytes
from synthworld.enterprise.models import EnterpriseOperatorModel

STANDARDS_PROFILE_LEDGER_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
STANDARDS_PROFILE_REVIEW_DATE = date(2026, 8, 4)


class StandardsProfileCategory(StrEnum):
    """Why a source is relevant to the bounded native model or a projection."""

    NORMATIVE_STANDARD = "normative_standard"
    GOVERNMENT_REFERENCE = "government_reference"
    RESEARCH = "research"
    IMPLEMENTATION_MODEL = "implementation_model"
    COMMUNITY_WORK = "community_work"
    TEST_METHOD = "test_method"


class StandardsProfileStatus(StrEnum):
    """Publication maturity; draft-like inputs never masquerade as final."""

    FINAL = "final"
    REAFFIRMED = "reaffirmed"
    DRAFT = "draft"
    EXPIRED = "expired"
    RESEARCH = "research"
    IMPLEMENTATION = "implementation"


class StandardsProfileEntryV1(EnterpriseOperatorModel):
    """One exact external source mapped to one SynthWorld profile revision."""

    source_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    category: StandardsProfileCategory
    source_edition: str = Field(min_length=1)
    status: StandardsProfileStatus
    authoritative_uri: str = Field(min_length=1, pattern=r"^https://")
    selected_profile_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    selected_profile_version: str = Field(min_length=1)
    reviewed_on: date


class StandardsProfileLedgerV1(EnterpriseOperatorModel):
    """Dated, canonical standards selection; never an ambient latest lookup."""

    schema_version: Literal["1.0.0"] = STANDARDS_PROFILE_LEDGER_SCHEMA_VERSION
    entries: tuple[StandardsProfileEntryV1, ...] = Field(min_length=1)

    @field_validator("entries")
    @classmethod
    def canonical_entries(
        cls, value: tuple[StandardsProfileEntryV1, ...]
    ) -> tuple[StandardsProfileEntryV1, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.source_id))
        source_ids = tuple(item.source_id for item in ordered)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate_standards_source_id")
        profile_bindings = tuple(
            (item.selected_profile_id, item.selected_profile_version)
            for item in ordered
        )
        if len(profile_bindings) != len(set(profile_bindings)):
            raise ValueError("duplicate_standards_profile_binding")
        return ordered

    @model_validator(mode="after")
    def enforce_one_review_snapshot(self) -> Self:
        if any(
            item.reviewed_on != STANDARDS_PROFILE_REVIEW_DATE for item in self.entries
        ):
            raise ValueError("standards_review_date_mismatch")
        return self


class StandardsProfileLedgerError(ValueError):
    """Raised when a serialized standards ledger is missing or non-canonical."""


def standards_profile_ledger_v1() -> StandardsProfileLedgerV1:
    """Return the exact profiles selected before the PR3 contracts are frozen."""

    return StandardsProfileLedgerV1(
        entries=(
            _entry(
                source_id="authzen-authorization-api-1.0",
                category=StandardsProfileCategory.NORMATIVE_STANDARD,
                source_edition="OpenID Authorization API 1.0 Final, 2026-01-11",
                status=StandardsProfileStatus.FINAL,
                authoritative_uri="https://openid.net/specs/authorization-api-1_0.html",
                profile_id="synthworld-authzen-projection",
            ),
            _entry(
                source_id="incits-359-2012-r2022",
                category=StandardsProfileCategory.NORMATIVE_STANDARD,
                source_edition="INCITS 359-2012 (R2022)",
                status=StandardsProfileStatus.REAFFIRMED,
                authoritative_uri=(
                    "https://webstore.ansi.org/standards/incits/incits3592012r2022"
                ),
                profile_id="synthworld-directory-rbac",
            ),
            _entry(
                source_id="nist-sp-800-162-2019",
                category=StandardsProfileCategory.GOVERNMENT_REFERENCE,
                source_edition="NIST SP 800-162, updated 2019-02-25",
                status=StandardsProfileStatus.FINAL,
                authoritative_uri=("https://csrc.nist.gov/pubs/sp/800/162/upd2/final"),
                profile_id="synthworld-bounded-abac",
            ),
            _entry(
                source_id="nist-sp-800-192-2017",
                category=StandardsProfileCategory.TEST_METHOD,
                source_edition="NIST SP 800-192, 2017-06",
                status=StandardsProfileStatus.FINAL,
                authoritative_uri="https://csrc.nist.gov/pubs/sp/800/192/final",
                profile_id="synthworld-policy-test-coverage",
            ),
            _entry(
                source_id="openid-aiim-mcp-interop-2026-07-14",
                category=StandardsProfileCategory.COMMUNITY_WORK,
                source_edition="AIIM MCP interop call snapshot, 2026-07-14",
                status=StandardsProfileStatus.DRAFT,
                authoritative_uri=(
                    "https://openid.net/call-for-participation-demonstrate-mcp-"
                    "based-ai-agent-security-with-open-identity-standards-2/"
                ),
                profile_id="synthworld-aiim-scenario-tags",
                profile_version="0.1.0-experimental",
            ),
            _entry(
                source_id="openid-caep-1.0-final",
                category=StandardsProfileCategory.NORMATIVE_STANDARD,
                source_edition="OpenID Continuous Access Evaluation Profile 1.0 Final",
                status=StandardsProfileStatus.FINAL,
                authoritative_uri=(
                    "https://openid.net/specs/openid-caep-1_0-final.html"
                ),
                profile_id="synthworld-caep-projection",
            ),
            _entry(
                source_id="openid-ssf-1.0-final",
                category=StandardsProfileCategory.NORMATIVE_STANDARD,
                source_edition="OpenID Shared Signals Framework 1.0 Final",
                status=StandardsProfileStatus.FINAL,
                authoritative_uri=(
                    "https://openid.net/specs/"
                    "openid-sharedsignals-framework-1_0-final.html"
                ),
                profile_id="synthworld-shared-signals-projection",
            ),
            _entry(
                source_id="openfga-authorization-model-schema-1.1",
                category=StandardsProfileCategory.IMPLEMENTATION_MODEL,
                source_edition="OpenFGA authorization model schema 1.1",
                status=StandardsProfileStatus.IMPLEMENTATION,
                authoritative_uri=(
                    "https://openfga.dev/docs/getting-started/configure-model"
                ),
                profile_id="synthworld-openfga-projection",
            ),
            _entry(
                source_id="rfc-7643",
                category=StandardsProfileCategory.NORMATIVE_STANDARD,
                source_edition="RFC 7643, 2015-09",
                status=StandardsProfileStatus.FINAL,
                authoritative_uri="https://www.rfc-editor.org/info/rfc7643",
                profile_id="synthworld-scim-core-projection",
            ),
            _entry(
                source_id="rfc-7644",
                category=StandardsProfileCategory.NORMATIVE_STANDARD,
                source_edition="RFC 7644, 2015-09",
                status=StandardsProfileStatus.FINAL,
                authoritative_uri="https://www.rfc-editor.org/info/rfc7644",
                profile_id="synthworld-scim-protocol-projection",
            ),
            _entry(
                source_id="zanzibar-usenix-atc-2019",
                category=StandardsProfileCategory.RESEARCH,
                source_edition="Zanzibar, USENIX ATC 2019",
                status=StandardsProfileStatus.RESEARCH,
                authoritative_uri=(
                    "https://www.usenix.org/conference/atc19/presentation/pang"
                ),
                profile_id="synthworld-bounded-rebac",
            ),
        )
    )


def load_standards_profile_ledger(path: Path) -> StandardsProfileLedgerV1:
    """Load an exact canonical ledger without resolving any remote version."""

    try:
        payload = path.read_bytes()
        ledger = StandardsProfileLedgerV1.model_validate_json(payload)
    except (OSError, ValueError, ValidationError) as error:
        raise StandardsProfileLedgerError("standards ledger is invalid") from error
    if payload != canonical_json_bytes(ledger):
        raise StandardsProfileLedgerError("standards ledger is not canonical JSON")
    return ledger


def _entry(
    *,
    source_id: str,
    category: StandardsProfileCategory,
    source_edition: str,
    status: StandardsProfileStatus,
    authoritative_uri: str,
    profile_id: str,
    profile_version: str = "1.0.0",
) -> StandardsProfileEntryV1:
    return StandardsProfileEntryV1(
        source_id=source_id,
        category=category,
        source_edition=source_edition,
        status=status,
        authoritative_uri=authoritative_uri,
        selected_profile_id=profile_id,
        selected_profile_version=profile_version,
        reviewed_on=STANDARDS_PROFILE_REVIEW_DATE,
    )


__all__ = [
    "STANDARDS_PROFILE_LEDGER_SCHEMA_VERSION",
    "STANDARDS_PROFILE_REVIEW_DATE",
    "StandardsProfileCategory",
    "StandardsProfileEntryV1",
    "StandardsProfileLedgerError",
    "StandardsProfileLedgerV1",
    "StandardsProfileStatus",
    "load_standards_profile_ledger",
    "standards_profile_ledger_v1",
]
