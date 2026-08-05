"""Compatibility and discriminating tests for agent-authority observation v2."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from synthworld.agent_authority.cases import (
    L06RevocationPropagationObservationV1,
    L06RevocationPropagationStimulusV1,
)
from synthworld.agent_authority.common import (
    AgentAuthorityControlId,
    AttributionKind,
    FindingStatus,
    ObservationAttributionV1,
    ObservedDecision,
    ObservedSideEffect,
)
from synthworld.agent_authority.models import (
    AgentAuthorityLabReportV1,
    AgentAuthorityLabTruthV1,
    CoverageLimitationKind,
    CoverageLimitationV1,
)
from synthworld.agent_authority.models_v2 import (
    AgentAuthorityObservationV2,
    AgentAuthorityRunObservationsV2,
    L06RevocationPropagationObservationV2,
    RevocationPointResultV2,
    TimedAttemptV2,
    validate_observation_references_v2,
    validate_revocation_observation_v2,
)
from synthworld.agent_authority.reference import (
    reference_metadata,
    reference_observations,
    reference_plan,
    reference_stimuli,
    reference_systems,
    reference_truth,
)
from synthworld.agent_authority.scoring_v2 import evaluate_agent_authority_lab_v2
from synthworld.assurance.agent_authority import (
    AGENT_AUTHORITY_SCORING_VERSION_V2,
    OBSERVATIONS_PATH,
    AgentAuthorityPreExecutionArtifactsV1,
    build_agent_authority_run_receipt,
    validate_agent_authority_run_receipt,
)
from synthworld.assurance.models_v2 import RunReceiptManifestV2
from synthworld.assurance.receipt import (
    MANIFEST_PATH,
    ReceiptIntegrityError,
    canonical_json_bytes,
)
from synthworld.assurance.receipt_v2 import digest_bytes_v2

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_V1_SCHEMA_DIGESTS = {
    "agent-authority-run-plan.schema.json": (
        "15787d271ef05c8dc93d4f55bb5b3bc14fcfb8b6a8c3c7642273f1417db6f157"
    ),
    "agent-authority-observations.schema.json": (
        "97b717c5ba379c53b48f0a9f56b0ff9146619b8496ec8505c25ab7b5c47d3e3c"
    ),
    "agent-authority-lab-truth.schema.json": (
        "2e8e2dad3cd142e409cfb07e535eb680c6acfab378e2032f32cba0ff34b31a95"
    ),
    "agent-authority-lab-report.schema.json": (
        "c36f570cfb3870f35139ec48c6efc2e1d4a749daa5d8c2fe5358006da995d4a7"
    ),
}


def _v2_observations() -> AgentAuthorityRunObservationsV2:
    document = reference_observations().model_dump(mode="json")
    document["schema_version"] = "2.0.0"
    row = next(
        item
        for item in document["observations"]
        if item["stimulus_id"] == "stimulus-l06"
    )
    row["elapsed_ns"] = 112_000_000
    row["payload"] = {
        "variant": "l06_revocation_propagation",
        "revocation_epoch_monotonic_ns": 100_000_000,
        "point_results": [
            {
                "component_id": "component-gateway",
                "ack_offset_ns": 5_000_000,
                "evidence_refs": ["evidence:target"],
            }
        ],
        "timed_attempts": [
            {
                "enforcement_point_id": "component-gateway",
                "credential_or_child_handle": "synthetic-secret:credential-1",
                "sent_offset_ns": -1_000_000,
                "completed_offset_ns": 1_000_000,
                "decision": "allow",
                "side_effect": "occurred",
                "evidence_refs": ["evidence:target"],
            },
            {
                "enforcement_point_id": "component-gateway",
                "credential_or_child_handle": "synthetic-secret:credential-1",
                "sent_offset_ns": 11_000_000,
                "completed_offset_ns": 12_000_000,
                "decision": "deny",
                "side_effect": "not_observed",
                "evidence_refs": ["evidence:target"],
            },
        ],
    }
    return AgentAuthorityRunObservationsV2.model_validate(document)


def _replace_l06(
    observations: AgentAuthorityRunObservationsV2,
    **updates: object,
) -> AgentAuthorityRunObservationsV2:
    document = observations.model_dump(mode="json")
    row = next(
        item
        for item in document["observations"]
        if item["stimulus_id"] == "stimulus-l06"
    )
    row["payload"].update(updates)
    return AgentAuthorityRunObservationsV2.model_validate(document)


def _l06_payload(
    observations: AgentAuthorityRunObservationsV2,
) -> L06RevocationPropagationObservationV2:
    payload = next(
        item.payload
        for item in observations.observations
        if item.stimulus_id == "stimulus-l06"
    )
    assert isinstance(payload, L06RevocationPropagationObservationV2)
    return payload


def _evaluate(
    observations: AgentAuthorityRunObservationsV2,
    truth: AgentAuthorityLabTruthV1 | None = None,
) -> AgentAuthorityLabReportV1:
    return evaluate_agent_authority_lab_v2(
        reference_plan(),
        reference_stimuli(),
        observations,
        reference_truth() if truth is None else truth,
        reference_systems(),
    )


def _write_and_reindex(root: Path, path: str, payload: bytes) -> None:
    (root / path).write_bytes(payload)
    manifest = RunReceiptManifestV2.model_validate_json(
        (root / MANIFEST_PATH).read_bytes()
    )
    artifacts = tuple(
        item.model_copy(
            update={"digest": digest_bytes_v2(payload), "byte_size": len(payload)}
        )
        if item.path == path
        else item
        for item in manifest.artifacts
    )
    (root / MANIFEST_PATH).write_bytes(
        canonical_json_bytes(manifest.model_copy(update={"artifacts": artifacts}))
    )


def _canonical_document(document: object) -> bytes:
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _build_v2_receipt(root: Path) -> RunReceiptManifestV2:
    observations = _v2_observations()

    def runner(_input: Path, output: Path) -> int:
        output.write_bytes(canonical_json_bytes(observations))
        return 0

    return build_agent_authority_run_receipt(
        root,
        pre_execution_artifacts=AgentAuthorityPreExecutionArtifactsV1(
            reference_plan(), reference_stimuli()
        ),
        source_public=canonical_json_bytes(reference_stimuli()),
        adapter=lambda payload: payload,
        runner=runner,
        observation_normalizer=lambda payload, _plan, _stimuli: (
            AgentAuthorityRunObservationsV2.model_validate_json(payload)
        ),
        truth_loader=reference_truth,
        metadata=reference_metadata(),
    )


def test_v1_generated_protocol_schemas_remain_byte_identical() -> None:
    schema_root = REPOSITORY_ROOT / "agent-authority-contract" / "schemas"
    assert {
        name: hashlib.sha256((schema_root / name).read_bytes()).hexdigest()
        for name in _V1_SCHEMA_DIGESTS
    } == _V1_SCHEMA_DIGESTS


def test_published_observation_schemas_are_explicit_and_disjoint() -> None:
    schema_root = REPOSITORY_ROOT / "agent-authority-contract" / "schemas"
    v1 = Draft202012Validator(
        json.loads(
            (schema_root / "agent-authority-observations.schema.json").read_text(
                encoding="utf-8"
            )
        )
    )
    v2 = Draft202012Validator(
        json.loads(
            (schema_root / "agent-authority-observations-v2.schema.json").read_text(
                encoding="utf-8"
            )
        )
    )
    v1_document = reference_observations().model_dump(mode="json")
    v2_document = _v2_observations().model_dump(mode="json")
    assert v1.is_valid(v1_document)
    assert v2.is_valid(v2_document)
    assert not v1.is_valid(v2_document)
    assert not v2.is_valid(v1_document)
    assert not v2.is_valid(v2_document | {"unexpected": True})


def test_v2_represents_signed_in_flight_timing_without_reinterpreting_v1() -> None:
    observations = _v2_observations()
    payload = _l06_payload(observations)
    assert payload.timed_attempts[0].sent_offset_ns == -1_000_000
    assert observations.schema_version == "2.0.0"
    assert reference_observations().schema_version == "1.0.0"
    legacy = reference_observations().observations[-1].payload
    assert isinstance(legacy, L06RevocationPropagationObservationV1)
    assert legacy.revocation_epoch_ns == 100_000_000

    with pytest.raises(ValidationError, match="cannot precede send"):
        TimedAttemptV2(
            enforcement_point_id="point",
            credential_or_child_handle="credential",
            sent_offset_ns=1,
            completed_offset_ns=0,
            decision=ObservedDecision.DENY,
            side_effect=ObservedSideEffect.NOT_OBSERVED,
        )
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        RevocationPointResultV2(component_id="point", ack_offset_ns=-1)
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        _replace_l06(observations, revocation_epoch_monotonic_ns=-1)


def test_v2_timing_inventories_are_canonical_and_unique() -> None:
    payload = _l06_payload(_v2_observations())
    alpha = RevocationPointResultV2(component_id="component-alpha")
    with pytest.raises(ValidationError, match="canonically ordered"):
        L06RevocationPropagationObservationV2(
            revocation_epoch_monotonic_ns=1,
            point_results=(*payload.point_results, alpha),
            timed_attempts=payload.timed_attempts,
        )
    with pytest.raises(ValidationError, match="point-result components"):
        L06RevocationPropagationObservationV2(
            revocation_epoch_monotonic_ns=1,
            point_results=(payload.point_results[0],) * 2,
            timed_attempts=payload.timed_attempts,
        )
    with pytest.raises(ValidationError, match="timed attempts must be unique"):
        L06RevocationPropagationObservationV2(
            revocation_epoch_monotonic_ns=1,
            point_results=payload.point_results,
            timed_attempts=(payload.timed_attempts[0],) * 2,
        )
    with pytest.raises(ValidationError, match="timed attempts must be canonically"):
        L06RevocationPropagationObservationV2(
            revocation_epoch_monotonic_ns=1,
            point_results=payload.point_results,
            timed_attempts=tuple(reversed(payload.timed_attempts)),
        )


def test_v2_observation_envelope_preserves_time_and_inventory_invariants() -> None:
    observations = _v2_observations()
    first = observations.observations[0]
    timestamped = AgentAuthorityObservationV2.model_validate(
        first.model_dump(mode="json")
        | {"observed_at": datetime(2026, 8, 5, tzinfo=UTC).isoformat()}
    )
    assert timestamped.observed_at == datetime(2026, 8, 5, tzinfo=UTC)
    with pytest.raises(ValidationError, match="UTC"):
        AgentAuthorityObservationV2.model_validate(
            first.model_dump(mode="json") | {"observed_at": "2026-08-05T00:00:00"}
        )
    with pytest.raises(ValidationError, match="sorted and unique"):
        AgentAuthorityObservationV2.model_validate(
            first.model_dump(mode="json") | {"evidence_handle_refs": ["z", "a"]}
        )
    with pytest.raises(ValidationError, match="observation stimulus identifiers"):
        AgentAuthorityRunObservationsV2.model_validate(
            observations.model_dump(mode="json")
            | {"observations": [first.model_dump(mode="json")] * 2}
        )


def test_v2_reference_validation_uses_signed_offsets_and_v1_non_l06_rules() -> None:
    observations = _v2_observations()
    validate_observation_references_v2(
        reference_plan(), reference_stimuli(), observations, reference_systems()
    )
    capped = observations.model_copy(
        update={
            "coverage_limitations": (
                CoverageLimitationV1(
                    control_id=AgentAuthorityControlId.L01,
                    kind=CoverageLimitationKind.CAPPED,
                    reason="bounded channel collection",
                ),
            )
        }
    )
    validate_observation_references_v2(
        reference_plan(), reference_stimuli(), capped, reference_systems()
    )
    payload = _l06_payload(observations)
    no_post = _replace_l06(observations, timed_attempts=[payload.timed_attempts[0]])
    with pytest.raises(ValueError, match="requires a post-bound attempt"):
        validate_observation_references_v2(
            reference_plan(), reference_stimuli(), no_post, reference_systems()
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"run_id": "wrong"}, "run identifier differs"),
        ({"unknown_stimulus": True}, "undeclared stimulus"),
        ({"wrong_variant": True}, "variants differ"),
        ({"unknown_component": True}, "unknown component"),
        ({"missing_evidence": True}, "undeclared evidence handle"),
        ({"non_selected_limitation": True}, "non-applicable controls"),
        ({"wrong_l06_type": True}, "wrong typed payload"),
    ],
)
def test_v2_reference_validation_rejects_invalid_relationships(
    mutation: dict[str, object], message: str
) -> None:
    observations = _v2_observations()
    document = observations.model_dump(mode="json")
    if "run_id" in mutation:
        document["run_id"] = mutation["run_id"]
        changed = AgentAuthorityRunObservationsV2.model_validate(document)
    elif mutation.get("unknown_stimulus"):
        document["observations"][0]["stimulus_id"] = "stimulus-l00-unknown"
        changed = AgentAuthorityRunObservationsV2.model_validate(document)
    elif mutation.get("wrong_variant"):
        rows = list(observations.observations)
        rows[0] = rows[0].model_copy(update={"payload": rows[1].payload})
        changed = observations.model_copy(update={"observations": tuple(rows)})
    elif mutation.get("unknown_component"):
        rows = list(observations.observations)
        rows[0] = rows[0].model_copy(
            update={
                "attribution": ObservationAttributionV1(
                    kind=AttributionKind.SPECIFIC,
                    component_ids=("component-unknown",),
                )
            }
        )
        changed = observations.model_copy(update={"observations": tuple(rows)})
    elif mutation.get("missing_evidence"):
        rows = list(observations.observations)
        rows[0] = rows[0].model_copy(
            update={"evidence_handle_refs": ("evidence:unknown",)}
        )
        changed = observations.model_copy(update={"observations": tuple(rows)})
    elif mutation.get("non_selected_limitation"):
        changed = observations.model_copy(
            update={
                "coverage_limitations": (
                    CoverageLimitationV1(
                        control_id=AgentAuthorityControlId.C01,
                        kind=CoverageLimitationKind.SKIPPED,
                        reason="not selected",
                    ),
                )
            }
        )
    else:
        rows = list(observations.observations)
        v1_payload = reference_observations().observations[-1].payload
        assert isinstance(v1_payload, L06RevocationPropagationObservationV1)
        rows[-1] = rows[-1].model_copy(update={"payload": v1_payload})
        changed = observations.model_copy(update={"observations": tuple(rows)})
    with pytest.raises(ValueError, match=message):
        validate_observation_references_v2(
            reference_plan(), reference_stimuli(), changed, reference_systems()
        )


def test_v2_l06_validation_rejects_incomplete_and_undeclared_coverage() -> None:
    observations = _v2_observations()
    payload = _l06_payload(observations)
    stimulus = reference_stimuli().stimuli[-1].payload
    assert isinstance(stimulus, L06RevocationPropagationStimulusV1)
    with pytest.raises(ValueError, match="point-result inventory"):
        validate_revocation_observation_v2(
            stimulus,
            payload.model_copy(
                update={
                    "point_results": (
                        RevocationPointResultV2(component_id="component-other"),
                    )
                }
            ),
            reference_plan(),
        )

    no_post = payload.model_copy(
        update={"timed_attempts": (payload.timed_attempts[0],)}
    )
    with pytest.raises(ValueError, match="per enforcement point"):
        validate_revocation_observation_v2(stimulus, no_post, reference_plan())

    missing_handle = payload.model_copy(
        update={
            "timed_attempts": (
                payload.timed_attempts[-1].model_copy(
                    update={"credential_or_child_handle": "another-handle"}
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="per declared handle"):
        validate_revocation_observation_v2(stimulus, missing_handle, reference_plan())

    undeclared = TimedAttemptV2(
        enforcement_point_id="component-gateway",
        credential_or_child_handle="aaa-undeclared",
        sent_offset_ns=-2_000_000,
        completed_offset_ns=-1_000_000,
        decision=ObservedDecision.DENY,
        side_effect=ObservedSideEffect.NOT_OBSERVED,
    )
    extra = payload.model_copy(
        update={"timed_attempts": (undeclared, *payload.timed_attempts)}
    )
    with pytest.raises(ValueError, match="undeclared reference"):
        validate_revocation_observation_v2(stimulus, extra, reference_plan())

    stimulus_data = stimulus.model_dump()
    stimulus_data.update(
        {"issued_credential_handles": (), "child_delegation_handles": ()}
    )
    empty_handles = L06RevocationPropagationStimulusV1.model_construct(**stimulus_data)
    with pytest.raises(ValueError, match="credential or child-delegation"):
        validate_revocation_observation_v2(empty_handles, payload, reference_plan())


def test_v2_scoring_ignores_pre_revocation_send_for_post_bound_metric() -> None:
    report = _evaluate(_v2_observations())
    assert {item.status for item in report.findings} == {FindingStatus.PASS}
    metric = next(
        item
        for item in report.security_metrics
        if item.name == "post_bound_false_allow_rate"
    )
    assert (metric.numerator, metric.denominator, metric.value) == (0, 1, 0.0)


@pytest.mark.parametrize(
    ("kind", "status", "code"),
    [
        ("false_allow", FindingStatus.FAIL, "revocation_bound_violated"),
        ("late_ack", FindingStatus.FAIL, "revocation_bound_violated"),
        (
            "missing_ack",
            FindingStatus.INCONCLUSIVE,
            "revocation_acknowledgement_missing",
        ),
        (
            "unobserved",
            FindingStatus.INCONCLUSIVE,
            "post_bound_outcome_unobserved",
        ),
        (
            "missing_evidence_kind",
            FindingStatus.INCONCLUSIVE,
            "required_evidence_missing",
        ),
    ],
)
def test_v2_l06_scoring_fail_and_inconclusive_paths(
    kind: str, status: FindingStatus, code: str
) -> None:
    observations = _v2_observations()
    payload = _l06_payload(observations)
    truth = reference_truth()
    if kind == "false_allow":
        attempts = (
            payload.timed_attempts[0],
            payload.timed_attempts[1].model_copy(
                update={"decision": ObservedDecision.ALLOW}
            ),
        )
        observations = _replace_l06(observations, timed_attempts=attempts)
    elif kind == "late_ack":
        points = (
            payload.point_results[0].model_copy(update={"ack_offset_ns": 11_000_000}),
        )
        observations = _replace_l06(observations, point_results=points)
    elif kind == "missing_ack":
        points = (payload.point_results[0].model_copy(update={"ack_offset_ns": None}),)
        observations = _replace_l06(observations, point_results=points)
    elif kind == "unobserved":
        attempts = (
            payload.timed_attempts[0],
            payload.timed_attempts[1].model_copy(
                update={"decision": ObservedDecision.UNOBSERVED}
            ),
        )
        observations = _replace_l06(observations, timed_attempts=attempts)
    else:
        document = truth.model_dump(mode="json")
        row = next(
            item
            for item in document["stimuli"]
            if item["stimulus_id"] == "stimulus-l06"
        )
        row["payload"]["required_evidence_kinds"] = ["memory"]
        truth = AgentAuthorityLabTruthV1.model_validate(document)
    finding = next(
        item
        for item in _evaluate(observations, truth).findings
        if item.control_id is AgentAuthorityControlId.L06
    )
    assert (finding.status, finding.failure_code) == (status, code)


def test_v2_scoring_records_missing_observation_without_empty_false_pass() -> None:
    observations = _v2_observations()
    observations = observations.model_copy(
        update={
            "observations": tuple(
                item
                for item in observations.observations
                if item.stimulus_id != "stimulus-l06"
            )
        }
    )
    report = _evaluate(observations)
    finding = next(
        item
        for item in report.findings
        if item.control_id is AgentAuthorityControlId.L06
    )
    metric = next(
        item
        for item in report.security_metrics
        if item.name == "post_bound_false_allow_rate"
    )
    assert finding.status is FindingStatus.NOT_EXECUTED
    assert metric.denominator == 0 and metric.value is None


def test_v2_receipt_binds_observation_and_scoring_versions(tmp_path: Path) -> None:
    root = tmp_path / "run"
    manifest = _build_v2_receipt(root)
    assert {item.role: item.version for item in manifest.schema_versions}[
        "agent_authority_observations"
    ] == "2.0.0"
    assert {item.role: item.version for item in manifest.scoring_formula_versions} == {
        "agent_authority_lab": AGENT_AUTHORITY_SCORING_VERSION_V2
    }
    assert validate_agent_authority_run_receipt(root) == manifest


def test_v2_receipt_rejects_payload_binding_and_scoring_tampering(
    tmp_path: Path,
) -> None:
    template = tmp_path / "template"
    _build_v2_receipt(template)

    binding_root = tmp_path / "binding"
    shutil.copytree(template, binding_root)
    manifest = RunReceiptManifestV2.model_validate_json(
        (binding_root / MANIFEST_PATH).read_bytes()
    )
    artifacts = tuple(
        item.model_copy(update={"schema_version": "1.0.0"})
        if item.role == "agent_authority_observations"
        else item
        for item in manifest.artifacts
    )
    schemas = tuple(
        item.model_copy(update={"version": "1.0.0"})
        if item.role == "agent_authority_observations"
        else item
        for item in manifest.schema_versions
    )
    (binding_root / MANIFEST_PATH).write_bytes(
        canonical_json_bytes(
            manifest.model_copy(
                update={"artifacts": artifacts, "schema_versions": schemas}
            )
        )
    )
    with pytest.raises(ReceiptIntegrityError, match="differs from its payload"):
        validate_agent_authority_run_receipt(binding_root)

    scoring_root = tmp_path / "scoring"
    shutil.copytree(template, scoring_root)
    manifest = RunReceiptManifestV2.model_validate_json(
        (scoring_root / MANIFEST_PATH).read_bytes()
    )
    scoring = tuple(
        item.model_copy(update={"version": "1.0.0"})
        for item in manifest.scoring_formula_versions
    )
    (scoring_root / MANIFEST_PATH).write_bytes(
        canonical_json_bytes(
            manifest.model_copy(update={"scoring_formula_versions": scoring})
        )
    )
    with pytest.raises(ReceiptIntegrityError, match="scoring formula"):
        validate_agent_authority_run_receipt(scoring_root)


@pytest.mark.parametrize("document", [[], {"schema_version": "9.9.9"}])
def test_receipt_rejects_non_object_or_unknown_observation_schema(
    tmp_path: Path, document: list[object] | dict[str, str]
) -> None:
    root = tmp_path / str(type(document).__name__)
    _build_v2_receipt(root)
    _write_and_reindex(root, OBSERVATIONS_PATH, _canonical_document(document))
    with pytest.raises(ReceiptIntegrityError, match="supported schema"):
        validate_agent_authority_run_receipt(root)
