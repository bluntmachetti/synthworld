"""Standards-profile ledger contract and pinning tests."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.enterprise.canonical import canonical_json_bytes
from synthworld.enterprise.standards import (
    StandardsProfileEntryV1,
    StandardsProfileLedgerError,
    StandardsProfileLedgerV1,
    StandardsProfileStatus,
    load_standards_profile_ledger,
    standards_profile_ledger_v1,
)

LEDGER_PATH = "enterprise-identity-access-contract/standards-profile-ledger.json"


def test_selected_standards_are_dated_canonical_and_maturity_explicit() -> None:
    ledger = standards_profile_ledger_v1()
    assert tuple(item.source_id for item in ledger.entries) == tuple(
        sorted(item.source_id for item in ledger.entries)
    )
    assert {item.reviewed_on for item in ledger.entries} == {date(2026, 8, 4)}
    statuses = {item.source_id: item.status for item in ledger.entries}
    assert statuses["authzen-authorization-api-1.0"] is StandardsProfileStatus.FINAL
    assert statuses["incits-359-2012-r2022"] is StandardsProfileStatus.REAFFIRMED
    assert (
        statuses["openid-aiim-mcp-interop-2026-07-14"] is StandardsProfileStatus.DRAFT
    )
    assert statuses["zanzibar-usenix-atc-2019"] is StandardsProfileStatus.RESEARCH
    assert all(item.authoritative_uri.startswith("https://") for item in ledger.entries)


def test_standards_ledger_rejects_duplicate_bindings_and_mixed_dates() -> None:
    entry = standards_profile_ledger_v1().entries[0]
    with pytest.raises(ValidationError, match="duplicate_standards_source_id"):
        StandardsProfileLedgerV1(entries=(entry, entry))
    duplicate_profile = entry.model_copy(update={"source_id": "another-source"})
    with pytest.raises(ValidationError, match="duplicate_standards_profile_binding"):
        StandardsProfileLedgerV1(entries=(entry, duplicate_profile))
    wrong_date = entry.model_copy(update={"reviewed_on": date(2026, 8, 3)})
    with pytest.raises(ValidationError, match="standards_review_date_mismatch"):
        StandardsProfileLedgerV1(entries=(wrong_date,))


def test_standards_entries_are_strict_and_https_only() -> None:
    entry = standards_profile_ledger_v1().entries[0]
    document = entry.model_dump(mode="json")
    document["authoritative_uri"] = "http://example.invalid"
    with pytest.raises(ValidationError):
        StandardsProfileEntryV1.model_validate(document)
    document = entry.model_dump(mode="json")
    document["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs"):
        StandardsProfileEntryV1.model_validate(document)


def test_committed_standards_ledger_loads_only_as_canonical_json(
    tmp_path: Path,
) -> None:
    expected = standards_profile_ledger_v1()
    loaded = load_standards_profile_ledger(Path(LEDGER_PATH))
    assert loaded == expected

    absent = tmp_path / "absent.json"
    with pytest.raises(StandardsProfileLedgerError, match="invalid"):
        load_standards_profile_ledger(absent)

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{}\n")
    with pytest.raises(StandardsProfileLedgerError, match="invalid"):
        load_standards_profile_ledger(malformed)

    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_text(json.dumps(expected.model_dump(mode="json")) + "\n")
    assert noncanonical.read_bytes() != canonical_json_bytes(expected)
    with pytest.raises(StandardsProfileLedgerError, match="not canonical"):
        load_standards_profile_ledger(noncanonical)
