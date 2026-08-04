"""Hold the control catalogue's vocabulary claims to the models it cites.

``agent-authority-contract/README.md`` states that the catalogue and
``synthworld.agentic.models`` are "in exact correspondence": every emitted metric,
every case kind and every failure reason cited by at least one control, and every
control's identifiers resolving. That was a prose claim, checked by hand, and it
went stale the moment ``AgenticCaseKind`` gained two members - the catalogue still
said its eleven labelled cases were "one per AgenticCaseKind member" while the enum
had thirteen. Nothing failed, because nothing was checking.

The claim is the kind that has to be executable. A drifting vocabulary is not a
cosmetic docs problem: a control citing a slice or reason that no longer exists
reads as covered while scoring nothing, which is precisely the failure mode the
catalogue exists to disclose.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from synthworld.agent_authority.common import (
    AGENT_AUTHORITY_PROTOCOL_VERSION,
    LAB_CONTROL_IDS,
    OPERATIONAL_CONTROL_IDS,
)
from synthworld.agentic import (
    AGENTIC_SCORING_PROTOCOL_VERSION,
    evaluate_agentic_trace,
    generate_asteria_agentic_v1,
)
from synthworld.agentic.baselines import reference_agentic_trace
from synthworld.agentic.models import (
    AGENTIC_SCHEMA_VERSION,
    AgenticCaseKind,
    AuthorityFailureReason,
)

CATALOGUE = Path("agent-authority-contract/control-catalogue.yaml")


def _catalogue() -> dict[str, object]:
    loaded = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _controls() -> list[dict[str, object]]:
    controls = _catalogue()["controls"]
    assert isinstance(controls, list)
    return controls


def _cited(field: str) -> set[str]:
    found: set[str] = set()
    for control in _controls():
        values = control.get(field) or []
        assert isinstance(values, list)
        found |= set(values)
    return found


def _fixture_shape() -> dict[str, object]:
    meta = _catalogue()["meta"]
    assert isinstance(meta, dict)
    shape = meta["fixture_shape"]
    assert isinstance(shape, dict)
    return shape


def test_declared_fixture_shape_matches_the_generated_benchmark() -> None:
    benchmark = generate_asteria_agentic_v1()
    shape = _fixture_shape()
    attempts = [
        event
        for event in benchmark.public.events
        if event.payload.event_type == "action_attempted"
    ]

    assert shape["events"] == len(benchmark.public.events)
    assert shape["action_attempts"] == len(attempts)
    assert shape["labelled_cases"] == len(benchmark.evaluator.cases)


def test_every_case_kind_is_cited_or_declared_unexercised() -> None:
    """The claim that broke. Cited and unexercised must partition the enum.

    Requiring the two sets to be disjoint matters as much as requiring them to
    cover: a kind listed as unexercised while some control claims it as a failure
    slice is the same defect in the opposite direction.
    """

    declared = _fixture_shape()["unexercised_case_kinds"]
    assert isinstance(declared, list)
    unexercised = set(declared)
    cited = _cited("failure_slices")
    members = {member.value for member in AgenticCaseKind}

    assert not (cited & unexercised), (
        f"declared unexercised but cited as a failure slice: "
        f"{sorted(cited & unexercised)}"
    )
    assert cited | unexercised == members, (
        f"case kinds neither cited nor declared unexercised: "
        f"{sorted(members - cited - unexercised)}; "
        f"named in the catalogue but not in the enum: "
        f"{sorted((cited | unexercised) - members)}"
    )


def test_every_authority_failure_reason_is_cited() -> None:
    cited = _cited("authority_failure_reasons")
    members = {member.value for member in AuthorityFailureReason}

    assert cited == members, (
        f"uncited: {sorted(members - cited)}; unresolvable: {sorted(cited - members)}"
    )


def test_every_emitted_metric_is_cited_and_every_cited_metric_exists() -> None:
    """Both directions. An uncited metric is an undisclosed capability; a cited
    metric that no longer exists is a control that reads as covered and is not.
    """

    benchmark = generate_asteria_agentic_v1()
    report = evaluate_agentic_trace(
        reference_agentic_trace(benchmark), benchmark=benchmark
    )
    emitted = {metric.name for metric in report.metrics}
    cited = _cited("metrics")

    assert cited == emitted, (
        f"emitted but cited by no control: {sorted(emitted - cited)}; "
        f"cited but not emitted: {sorted(cited - emitted)}"
    )


def test_declared_versions_track_the_code_they_describe() -> None:
    """The catalogue pins two versions by hand, and nothing was checking them.

    `scoring_protocol_version` is the number a reader uses to know which rule
    produced their truth. If it drifts from the constant the scorer actually
    stamps, the catalogue is describing a protocol that no longer exists - the
    same failure as the case-kind count, which claimed eleven kinds while the
    enum had thirteen and stayed wrong until an external review caught it.
    """

    meta = _catalogue()["meta"]
    assert isinstance(meta, dict)

    assert meta["scoring_protocol_version"] == AGENTIC_SCORING_PROTOCOL_VERSION
    assert meta["agentic_schema_version"] == AGENTIC_SCHEMA_VERSION
    assert meta["agent_authority_protocol_version"] == (
        AGENT_AUTHORITY_PROTOCOL_VERSION
    )


def test_agent_authority_protocol_coverage_is_explicit_without_live_claim() -> None:
    meta = _catalogue()["meta"]
    assert isinstance(meta, dict)
    coverage = meta["agent_authority_protocol_coverage"]
    assert isinstance(coverage, dict)
    assert coverage["status"] == "modeled-not-live-evidence"
    assert coverage["controls"] == [
        control.value for control in (*LAB_CONTROL_IDS, *OPERATIONAL_CONTROL_IDS)
    ]
