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
        "serialized string form. Tolerated because the scorer only ever reads "
        "model-serialized output, so the coercion is unreachable in practice, and "
        "imitating it in the schema would let a non-Python adapter emit a form the "
        "published contract calls valid but no serializer produces.",
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
