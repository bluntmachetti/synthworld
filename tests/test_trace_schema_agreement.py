"""Assert the published JSON Schema and the pydantic model agree.

The schemas in ``agent-authority-contract/schemas`` are generated from the models,
so they cannot drift structurally - ``generate_trace_schema.py --check`` guards that
in CI. Drift is not the interesting failure though. The interesting failure is
*semantic divergence*: the two accepting different bytes while both being perfectly
up to date. A non-Python adapter validates against the schema and is then scored by
the model, so any divergence is a trace that one side blesses and the other rejects.

Divergences are declared explicitly below rather than discovered in the field. A new
one fails this suite with "model and schema disagree and nobody declared it", and
closing it means either narrowing the generator or adding a declaration in the same
commit as the model change.

``jsonschema[format]`` plus an explicit ``FormatChecker`` is required: ``format`` is
an annotation in Draft 2020-12, so without both the schema silently stops checking
``date-time`` at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from synthworld.agentic import (
    always_deny_agentic_trace,
    generate_asteria_agentic_v1,
    reference_agentic_trace,
)
from synthworld.agentic.models import AgenticTraceSubmission, ObservedActionTrace

SCHEMA_DIR = Path("agent-authority-contract/schemas")
BENCHMARK = generate_asteria_agentic_v1()
EVENT_ID = BENCHMARK.public.scenario.action_event_ids[0]


def _row_validator() -> Draft202012Validator:
    schema = json.loads(
        (SCHEMA_DIR / "observed-action-trace.schema.json").read_text(encoding="utf-8")
    )
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _model_accepts(document: dict[str, Any]) -> bool:
    try:
        ObservedActionTrace.model_validate(document)
    except ValidationError:
        return False
    return True


def _schema_accepts_without_format(document: dict[str, Any]) -> bool:
    """Validate with format assertion OFF, which is many consumers' default."""

    schema = json.loads(
        (SCHEMA_DIR / "observed-action-trace.schema.json").read_text(encoding="utf-8")
    )
    return bool(Draft202012Validator(schema).is_valid(document))


def _schema_accepts(document: dict[str, Any]) -> bool:
    return bool(_row_validator().is_valid(document))


def _row(**fields: object) -> dict[str, Any]:
    return {"event_id": EVENT_ID, **fields}


# Every declared divergence, with the reason it is tolerated rather than closed.
# (label, document, model verdict, schema verdict, reason)
DECLARED_DIVERGENCES: tuple[tuple[str, dict[str, Any], bool, bool, str], ...] = (
    (
        "int-epoch-timestamp",
        _row(timestamp=1_700_000_000),
        True,
        False,
        "Pydantic coerces an integer epoch to a datetime; the schema requires the "
        "serialized string form. An earlier version of this note claimed the coercion "
        "was unreachable because the scorer only reads serialized output - that was "
        "wrong, since the scorer parses arbitrary adapter JSONL. It is tolerated "
        "because the schema is the stricter target and imitating pydantic's laxity "
        "would let an adapter emit forms no serializer produces.",
    ),
    (
        "bool-from-string",
        _row(reconstructable_from_retained_evidence="false"),
        True,
        False,
        'Pydantic parses the string "false" as a boolean; the schema requires a real '
        "JSON boolean. Kept as a divergence because the schema is the stricter and "
        "safer target for an adapter, and narrowing pydantic would change scorer "
        "behaviour for existing submissions.",
    ),
    (
        "lowercase-timestamp-designators",
        _row(timestamp="2026-07-29t12:00:00z"),
        True,
        False,
        "RFC 3339 permits lowercase t and z and pydantic accepts them; the generated "
        "pattern requires the uppercase forms every serializer in this repo emits. "
        "Tolerated rather than widened: loosening the pattern would also admit forms "
        "no serializer produces.",
    ),
    (
        "space-separated-timestamp",
        _row(timestamp="2026-07-29 12:00:00Z"),
        True,
        False,
        "Pydantic accepts a space in place of the T separator; the schema does not.",
    ),
    (
        "numeric-timestamp-string",
        _row(timestamp="1700000000"),
        True,
        False,
        "Pydantic parses a numeric string as an epoch; the schema requires the "
        "serialized date-time form.",
    ),
    (
        "int-coerced-boolean",
        _row(reconstructable_from_retained_evidence=1),
        True,
        False,
        "Pydantic coerces 1 to True; the schema requires a real JSON boolean. Same "
        "reasoning: the stricter side is the one an adapter should target.",
    ),
)

# Inputs where the two MUST agree. Chosen to sit on type and coercion boundaries and
# to exercise both custom validators, because a round-trip of the reference trace only
# ever exercises the safe intersection of the two.
MUTATION_CORPUS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("bare-row", _row()),
    ("utc-z", _row(timestamp="2026-07-29T12:00:00Z")),
    ("utc-offset", _row(timestamp="2026-07-29T12:00:00+00:00")),
    ("utc-fractional", _row(timestamp="2026-07-29T12:00:00.123456Z")),
    ("naive-timestamp", _row(timestamp="2026-07-29T12:00:00")),
    ("non-utc-offset", _row(timestamp="2026-07-29T12:00:00+02:00")),
    ("garbage-timestamp", _row(timestamp="not-a-date")),
    ("impossible-components", _row(timestamp="2026-99-99T99:99:99Z")),
    ("month-13", _row(timestamp="2026-13-01T12:00:00Z")),
    ("month-00", _row(timestamp="2026-00-10T12:00:00Z")),
    ("hour-25", _row(timestamp="2026-07-29T25:00:00Z")),
    ("second-60", _row(timestamp="2026-07-29T12:00:60Z")),
    ("day-32", _row(timestamp="2026-07-32T12:00:00Z")),
    # Agreement here depends on format assertion, which is why this suite enables
    # it and why the contract README tells consumers to. The pattern constrains
    # component ranges but cannot do calendar arithmetic, so a consumer validating
    # WITHOUT a format checker accepts this date while the model rejects it.
    ("impossible-calendar-date", _row(timestamp="2026-02-30T12:00:00Z")),
    ("unknown-field", _row(bogus=1)),
    ("bad-decision", _row(decision="maybe")),
    ("good-decision", _row(decision="allow")),
    ("bad-schema-version", _row(schema_version="9.9.9")),
    ("synthetic-false", _row(synthetic=False)),
    ("null-everywhere", _row(decision=None, evidence_refs=None)),
    ("empty-evidence-refs", _row(evidence_refs=[])),
    ("evidence-refs-list", _row(evidence_refs=["evidence:policy:v1"])),
    ("evidence-refs-wrong-type", _row(evidence_refs="evidence:policy:v1")),
    ("chain-list", _row(delegation_chain_ids=["del-1"])),
    ("real-boolean", _row(reconstructable_from_retained_evidence=True)),
    ("missing-event-id", {"decision": "allow"}),
    ("numeric-event-id", {"event_id": 5}),
)

# The corpus must not restate a declared divergence, or the agreement assertion
# below would contradict the declaration suite. Enforced rather than assumed.
assert not {entry[0] for entry in DECLARED_DIVERGENCES} & {
    entry[0] for entry in MUTATION_CORPUS
}


@pytest.mark.parametrize(
    ("label", "document", "model_verdict", "schema_verdict", "reason"),
    DECLARED_DIVERGENCES,
    ids=[entry[0] for entry in DECLARED_DIVERGENCES],
)
def test_declared_divergences_still_behave_as_recorded(
    label: str,
    document: dict[str, Any],
    model_verdict: bool,
    schema_verdict: bool,
    reason: str,
) -> None:
    """A declared divergence that silently closes should be removed, not left."""

    assert reason
    assert _model_accepts(document) is model_verdict, f"{label}: model verdict changed"
    assert _schema_accepts(document) is schema_verdict, (
        f"{label}: schema verdict changed"
    )
    assert model_verdict != schema_verdict, (
        f"{label}: no longer diverges, so remove it from DECLARED_DIVERGENCES"
    )


@pytest.mark.parametrize(
    ("label", "document"), MUTATION_CORPUS, ids=[entry[0] for entry in MUTATION_CORPUS]
)
def test_model_and_schema_agree_across_the_mutation_corpus(
    label: str, document: dict[str, Any]
) -> None:
    model_verdict = _model_accepts(document)
    schema_verdict = _schema_accepts(document)
    assert model_verdict == schema_verdict, (
        f"{label}: model and schema disagree and nobody declared it "
        f"(model={model_verdict}, schema={schema_verdict}). Either narrow the "
        f"generator in agent-authority-contract/tools/generate_trace_schema.py, or "
        f"add an entry to DECLARED_DIVERGENCES in the same commit as the model change."
    )


@pytest.mark.parametrize(
    "submission",
    [reference_agentic_trace(BENCHMARK), always_deny_agentic_trace(BENCHMARK.public)],
    ids=["reference", "always-deny"],
)
def test_real_submissions_satisfy_the_published_schema(
    submission: AgenticTraceSubmission,
) -> None:
    """Whatever the baselines emit must validate for a non-Python consumer too."""

    validator = _row_validator()
    for row in submission.rows:
        document = json.loads(row.model_dump_json())
        assert validator.is_valid(document), list(validator.iter_errors(document))


def test_format_assertion_is_actually_enabled() -> None:
    """Guard the guard: without the format extra this suite would quietly weaken."""

    checker = FormatChecker()
    assert "date-time" in checker.checkers, (
        "jsonschema is not asserting date-time; install the [format] extra, or this "
        "suite stops testing the timestamp contract"
    )


# Component ranges the generated pattern must enforce on its own, since a consumer
# that does not assert `format` gets nothing else. Without these the range checks
# could be deleted and the format-asserting suite above would stay green.
PATTERN_ONLY_REJECTS: tuple[tuple[str, str], ...] = (
    ("impossible-components", "2026-99-99T99:99:99Z"),
    ("month-13", "2026-13-01T12:00:00Z"),
    ("month-00", "2026-00-10T12:00:00Z"),
    ("day-32", "2026-07-32T12:00:00Z"),
    ("day-00", "2026-07-00T12:00:00Z"),
    ("hour-24", "2026-07-29T24:00:00Z"),
    ("minute-60", "2026-07-29T12:60:00Z"),
    ("second-60", "2026-07-29T12:00:60Z"),
    ("naive", "2026-07-29T12:00:00"),
    ("non-utc-offset", "2026-07-29T12:00:00+02:00"),
    ("garbage", "not-a-date"),
)


@pytest.mark.parametrize(
    ("label", "timestamp"),
    PATTERN_ONLY_REJECTS,
    ids=[entry[0] for entry in PATTERN_ONLY_REJECTS],
)
def test_pattern_alone_rejects_bad_timestamps(label: str, timestamp: str) -> None:
    document = _row(timestamp=timestamp)
    assert not _schema_accepts_without_format(document), (
        f"{label}: accepted with format assertion disabled, so the generated pattern "
        f"is not carrying its share of the contract"
    )
    assert not _model_accepts(document), f"{label}: model unexpectedly accepts"


def test_year_zero_needs_format_assertion() -> None:
    """Documented residue: the pattern cannot express a minimum year."""

    document = _row(timestamp="0000-07-29T12:00:00Z")
    assert not _model_accepts(document)
    assert _schema_accepts_without_format(document), (
        "if this now fails the pattern gained a year constraint - delete this test"
    )
    assert not _schema_accepts(document)
