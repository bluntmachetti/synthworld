"""Adversarial reference, replay, projection, and scorer vectors for PR6."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

import synthworld.agentic.enterprise.projection as projection_module
import synthworld.agentic.enterprise.serialization as serialization_module
from synthworld.agentic.enterprise.errors import (
    EnterpriseAgenticArtifactError,
    EnterpriseAgenticEvaluationError,
    EnterpriseAgenticIntegrityError,
)
from synthworld.agentic.enterprise.metrics import (
    _ratio,
    evaluate_enterprise_agentic_prediction,
    perfect_enterprise_agentic_prediction,
)
from synthworld.agentic.enterprise.models import (
    AgentAsPrincipalV1,
    EnterpriseAgentCapabilityV1,
    EnterpriseAgentCredentialV1,
    EnterpriseAgenticAccessPublicInputV1,
    EnterpriseAgenticActionAttemptedV1,
    EnterpriseAgenticAuditPerformedV1,
    EnterpriseAgenticDelegationRevokedV1,
    EnterpriseAgenticEvaluatorArtifactsV1,
    EnterpriseAgenticEventV1,
    EnterpriseAgenticEvidenceDiscardedV1,
    EnterpriseAgenticPredictionV1,
    EnterpriseAgenticProjectionConfigV1,
    EnterpriseAgenticProjectionLimitsV1,
    EnterpriseAgenticPublicInputV1,
    EnterpriseAgenticReplayStateV1,
    EnterpriseAgenticSnapshotV1,
    canonical_json_bytes_value,
)
from synthworld.agentic.enterprise.projection import (
    _action_payload,
    _evaluate_attempt,
    _validate_public_reprojection,
    compile_enterprise_agentic_truth,
    project_enterprise_agentic_public,
)
from synthworld.agentic.enterprise.reference import (
    ReferenceEnterpriseAgenticV1,
    _require_case_inventory,
    _require_frozen_access_inputs,
    _select_cell,
    reference_enterprise_agentic,
)
from synthworld.agentic.enterprise.replay import (
    materialize_enterprise_agentic_overlay,
)
from synthworld.agentic.enterprise.serialization import (
    export_enterprise_agentic_benchmark,
    load_public_enterprise_agentic_benchmark,
)
from synthworld.agentic.enterprise.trace import (
    enterprise_agentic_trace_to_jsonl,
    validate_enterprise_agentic_trace_jsonl,
)
from synthworld.enterprise.canonical import synthetic_digest
from synthworld.enterprise.rbac.common import (
    AuthorizationDecision,
    MetricEmptyBehaviour,
)


def _first_action(reference: ReferenceEnterpriseAgenticV1) -> EnterpriseAgenticEventV1:
    return next(
        event
        for event in reference.public.events
        if isinstance(event.payload, EnterpriseAgenticActionAttemptedV1)
    )


def _replace_event(
    events: tuple[EnterpriseAgenticEventV1, ...],
    event_id: str,
    replacement: EnterpriseAgenticEventV1,
) -> tuple[EnterpriseAgenticEventV1, ...]:
    return tuple(
        sorted(
            (replacement if item.id == event_id else item for item in events),
            key=lambda item: (item.tick, item.id),
        )
    )


def _project(
    reference: ReferenceEnterpriseAgenticV1,
    *,
    access: EnterpriseAgenticAccessPublicInputV1 | None = None,
    snapshot: EnterpriseAgenticSnapshotV1 | None = None,
    events: tuple[EnterpriseAgenticEventV1, ...] | None = None,
    config: EnterpriseAgenticProjectionConfigV1 | None = None,
) -> EnterpriseAgenticPublicInputV1:
    return project_enterprise_agentic_public(
        access=access or reference.public.access,
        snapshot=snapshot or reference.public.snapshot,
        events=events or reference.public.events,
        config=config or reference.public.config,
    )


def _compile(
    reference: ReferenceEnterpriseAgenticV1,
    public: EnterpriseAgenticPublicInputV1,
) -> EnterpriseAgenticEvaluatorArtifactsV1:
    return compile_enterprise_agentic_truth(
        public=public,
        canonical_binding_truth=reference.evaluator.canonical_binding_truth,
        directory_rbac_truth=reference.evaluator.directory_rbac_truth,
        abac_truth=reference.evaluator.abac_truth,
        rebac_truth=reference.evaluator.rebac_truth,
        access_state=reference.evaluator.access_state,
    )


def test_replay_rejects_order_duplicates_and_unknown_boundary() -> None:
    reference = reference_enterprise_agentic()
    events = reference.public.events
    with pytest.raises(EnterpriseAgenticIntegrityError, match="ordered"):
        materialize_enterprise_agentic_overlay(
            reference.public.snapshot, tuple(reversed(events))
        )
    duplicate = tuple(
        sorted((*events, events[0]), key=lambda item: (item.tick, item.id))
    )
    with pytest.raises(EnterpriseAgenticIntegrityError, match="unique"):
        materialize_enterprise_agentic_overlay(reference.public.snapshot, duplicate)
    with pytest.raises(EnterpriseAgenticIntegrityError, match="boundary event"):
        materialize_enterprise_agentic_overlay(
            reference.public.snapshot, events, before_event_id="unknown"
        )


@pytest.mark.parametrize(
    ("event_type", "message"),
    (
        ("unknown_credential", "unknown credential"),
        ("duplicate_credential", "credential is revoked more than once"),
        ("unknown_delegation", "unknown delegation"),
        ("duplicate_delegation", "delegation is revoked more than once"),
        ("unknown_evidence", "unknown evidence"),
    ),
)
def test_replay_rejects_invalid_mutation_events(event_type: str, message: str) -> None:
    reference = reference_enterprise_agentic()
    events = list(reference.public.events)
    if event_type == "unknown_credential":
        target = next(
            item for item in events if item.payload.event_type == "credential_revoked"
        )
        replacement = target.model_copy(
            update={
                "payload": target.payload.model_copy(
                    update={"credential_id": "unknown"}
                )
            }
        )
        events[events.index(target)] = replacement
    elif event_type == "duplicate_credential":
        target = next(
            item for item in events if item.payload.event_type == "credential_revoked"
        )
        events.append(target.model_copy(update={"id": "000-duplicate", "tick": 1}))
    elif event_type == "unknown_delegation":
        target = next(
            item for item in events if item.payload.event_type == "delegation_revoked"
        )
        replacement = target.model_copy(
            update={
                "payload": EnterpriseAgenticDelegationRevokedV1(delegation_id="unknown")
            }
        )
        events[events.index(target)] = replacement
    elif event_type == "duplicate_delegation":
        target = next(
            item for item in events if item.payload.event_type == "delegation_revoked"
        )
        events.append(target.model_copy(update={"id": "001-duplicate", "tick": 1}))
    else:
        target = next(
            item for item in events if item.payload.event_type == "evidence_discarded"
        )
        replacement = target.model_copy(
            update={
                "payload": EnterpriseAgenticEvidenceDiscardedV1(
                    evidence_refs=("unknown",)
                )
            }
        )
        events[events.index(target)] = replacement
    with pytest.raises(EnterpriseAgenticIntegrityError, match=message):
        materialize_enterprise_agentic_overlay(
            reference.public.snapshot,
            tuple(sorted(events, key=lambda item: (item.tick, item.id))),
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("runtime", "runtime references"),
        ("credential_account", "credential references"),
        ("credential_runtime", "credential references"),
        ("delegation_account", "delegation references"),
        ("delegation_capability", "delegation references"),
    ),
)
def test_replay_rejects_broken_snapshot_references(mutation: str, message: str) -> None:
    reference = reference_enterprise_agentic()
    snapshot = reference.public.snapshot
    updates: dict[str, object]
    if mutation == "runtime":
        updates = {
            "runtimes": (
                snapshot.runtimes[0].model_copy(update={"agent_account_id": "unknown"}),
                *snapshot.runtimes[1:],
            )
        }
    elif mutation.startswith("credential"):
        changed_credential = snapshot.credentials[0].model_copy(
            update=(
                {"agent_account_id": "unknown"}
                if mutation == "credential_account"
                else {"allowed_runtime_ids": ("unknown",)}
            )
        )
        updates = {"credentials": (changed_credential, *snapshot.credentials[1:])}
    else:
        changed_delegation = snapshot.delegations[0].model_copy(
            update=(
                {"agent_account_id": "unknown"}
                if mutation == "delegation_account"
                else {"capability_id": "unknown"}
            )
        )
        updates = {"delegations": (changed_delegation, *snapshot.delegations[1:])}
    changed_snapshot = snapshot.model_copy(update=updates)
    with pytest.raises(EnterpriseAgenticIntegrityError, match=message):
        materialize_enterprise_agentic_overlay(
            changed_snapshot, snapshot_events(reference)
        )


def snapshot_events(
    reference: ReferenceEnterpriseAgenticV1,
) -> tuple[EnterpriseAgenticEventV1, ...]:
    return reference.public.events


@pytest.mark.parametrize(
    "condition",
    (
        "no_audit",
        "two_audits",
        "action_after_audit",
        "duplicate_case",
        "access_digest",
    ),
)
def test_public_projection_rejects_invalid_inventories(condition: str) -> None:
    reference = reference_enterprise_agentic()
    events = list(reference.public.events)
    access = reference.public.access
    message = ""
    if condition == "no_audit":
        events = [
            item for item in events if item.payload.event_type != "audit_performed"
        ]
        message = "exactly one audit"
    elif condition == "two_audits":
        audit = next(
            item for item in events if item.payload.event_type == "audit_performed"
        )
        events.append(audit.model_copy(update={"id": "second-audit", "tick": 41}))
        message = "exactly one audit"
    elif condition == "action_after_audit":
        audit = next(
            item for item in events if item.payload.event_type == "audit_performed"
        )
        events[events.index(audit)] = audit.model_copy(update={"tick": 4})
        message = "must precede"
    elif condition == "duplicate_case":
        action = _first_action(reference)
        events.append(action.model_copy(update={"id": "duplicate-action", "tick": 39}))
        message = "repeat a case"
    else:
        access = access.model_copy(
            update={
                "authorization_kernel": access.authorization_kernel.model_copy(
                    update={
                        "identity_access_universe_digest": synthetic_digest(b"wrong\n")
                    }
                )
            }
        )
        message = "digest bindings"
    with pytest.raises(EnterpriseAgenticIntegrityError, match=message):
        _project(
            reference,
            access=access,
            events=tuple(sorted(events, key=lambda item: (item.tick, item.id))),
        )


@pytest.mark.parametrize(
    ("limit_field", "inventory_field"),
    (
        ("max_accounts", "accounts"),
        ("max_runtimes", "runtimes"),
        ("max_credentials", "credentials"),
        ("max_capabilities", "capabilities"),
        ("max_delegations", "delegations"),
        ("max_events", "events"),
        ("max_cases", "cases"),
    ),
)
def test_every_projection_limit_fails_before_projection(
    limit_field: str, inventory_field: str
) -> None:
    reference = reference_enterprise_agentic()
    measured = {
        "accounts": len(reference.public.snapshot.accounts),
        "runtimes": len(reference.public.snapshot.runtimes),
        "credentials": len(reference.public.snapshot.credentials),
        "capabilities": len(reference.public.snapshot.capabilities),
        "delegations": len(reference.public.snapshot.delegations),
        "events": len(reference.public.events),
        "cases": len(reference.public.benchmark.cases),
    }
    limits = reference.public.config.limits.model_dump(mode="python")
    limits[limit_field] = measured[inventory_field] - 1
    config = EnterpriseAgenticProjectionConfigV1(
        seed=reference.public.config.seed,
        limits=EnterpriseAgenticProjectionLimitsV1.model_validate(limits),
    )
    with pytest.raises(EnterpriseAgenticIntegrityError, match=inventory_field):
        _project(reference, config=config)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("account_principal", "account references an unknown principal"),
        ("unknown_object", "action references an unknown object"),
        ("optional_object", "mapping references an unknown optional object"),
        ("atom_cell", "does not bind one frozen atom and cell"),
        ("evidence", "references unknown evidence"),
    ),
)
def test_public_projection_rejects_broken_action_references(
    mutation: str, message: str
) -> None:
    reference = reference_enterprise_agentic()
    snapshot = reference.public.snapshot
    events = reference.public.events
    action = _first_action(reference)
    assert isinstance(action.payload, EnterpriseAgenticActionAttemptedV1)
    attempt = action.payload.attempt
    if mutation == "account_principal":
        changed_account = snapshot.accounts[0].model_copy(
            update={"agent_principal_id": "unknown"}
        )
        snapshot = snapshot.model_copy(
            update={"accounts": (changed_account, *snapshot.accounts[1:])}
        )
    else:
        if mutation == "unknown_object":
            changed_attempt = attempt.model_copy(update={"credential_id": "unknown"})
        elif mutation == "optional_object":
            assert isinstance(attempt.mapping, AgentAsPrincipalV1)
            mapping = attempt.mapping.model_copy(
                update={"owner_human_principal_id": "unknown"}
            )
            changed_attempt = attempt.model_copy(update={"mapping": mapping})
        elif mutation == "atom_cell":
            other_atom = next(
                item
                for item in reference.public.access.universe.access_atoms
                if item.access_atom_id != attempt.access_atom_id
            )
            changed_attempt = attempt.model_copy(
                update={"access_atom_id": other_atom.access_atom_id}
            )
        else:
            changed_attempt = attempt.model_copy(update={"evidence_refs": ("unknown",)})
        changed_action = action.model_copy(
            update={
                "payload": action.payload.model_copy(
                    update={"attempt": changed_attempt}
                )
            }
        )
        events = _replace_event(events, action.id, changed_action)
    with pytest.raises(EnterpriseAgenticIntegrityError, match=message):
        _project(reference, snapshot=snapshot, events=events)


def test_semantic_subject_and_account_binding_failures_are_scoreable() -> None:
    reference = reference_enterprise_agentic()
    action = _first_action(reference)
    assert isinstance(action.payload, EnterpriseAgenticActionAttemptedV1)
    attempt = action.payload.attempt
    assert isinstance(attempt.mapping, AgentAsPrincipalV1)
    other_principal = next(
        item.principal_id
        for item in reference.public.access.universe.principals
        if item.principal_id != attempt.mapping.enterprise_subject_id
    )
    mapping = attempt.mapping.model_copy(
        update={"enterprise_subject_id": other_principal}
    )
    changed_attempt = attempt.model_copy(update={"mapping": mapping})
    changed_action = action.model_copy(
        update={
            "payload": action.payload.model_copy(update={"attempt": changed_attempt})
        }
    )
    public = _project(
        reference,
        events=_replace_event(reference.public.events, action.id, changed_action),
    )
    evaluator = _compile(reference, public)
    changed_truth = next(
        item for item in evaluator.truth.cases if item.case_id == attempt.case_id
    )
    assert "subject_mismatch" in {
        item.value for item in changed_truth.expected_decision.failure_reasons
    }

    account_id = attempt.mapping.agent_account_id
    account = next(
        item for item in reference.public.snapshot.accounts if item.id == account_id
    )
    changed_account = account.model_copy(update={"agent_principal_id": other_principal})
    snapshot = reference.public.snapshot.model_copy(
        update={
            "accounts": tuple(
                changed_account if item.id == account_id else item
                for item in reference.public.snapshot.accounts
            )
        }
    )
    public = _project(reference, snapshot=snapshot)
    evaluator = _compile(reference, public)
    changed_truth = next(
        item for item in evaluator.truth.cases if item.case_id == attempt.case_id
    )
    assert "agent_account_binding_mismatch" in {
        item.value for item in changed_truth.expected_decision.failure_reasons
    }


def test_evaluator_rejects_component_and_aggregate_truth_drift() -> None:
    reference = reference_enterprise_agentic()
    changed_rbac = reference.evaluator.directory_rbac_truth.model_copy(
        update={"compiler_version": "changed"}
    )
    with pytest.raises(EnterpriseAgenticIntegrityError, match="component truth"):
        compile_enterprise_agentic_truth(
            public=reference.public,
            canonical_binding_truth=reference.evaluator.canonical_binding_truth,
            directory_rbac_truth=changed_rbac,
            abac_truth=reference.evaluator.abac_truth,
            rebac_truth=reference.evaluator.rebac_truth,
            access_state=reference.evaluator.access_state,
        )
    changed_access = reference.evaluator.access_state.model_copy(
        update={
            "policy_conflicts": reference.evaluator.access_state.policy_conflicts[1:]
        }
    )
    with pytest.raises(EnterpriseAgenticIntegrityError, match="aggregate access"):
        compile_enterprise_agentic_truth(
            public=reference.public,
            canonical_binding_truth=reference.evaluator.canonical_binding_truth,
            directory_rbac_truth=reference.evaluator.directory_rbac_truth,
            abac_truth=reference.evaluator.abac_truth,
            rebac_truth=reference.evaluator.rebac_truth,
            access_state=changed_access,
        )


def test_private_projection_defenses_are_discriminating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = reference_enterprise_agentic()
    audit = next(
        item
        for item in reference.public.events
        if isinstance(item.payload, EnterpriseAgenticAuditPerformedV1)
    )
    with pytest.raises(EnterpriseAgenticIntegrityError, match="expected an action"):
        _action_payload(audit)
    with pytest.raises(EnterpriseAgenticIntegrityError, match="expected an action"):
        _evaluate_attempt(
            public=reference.public,
            event=audit,
            access_cell=reference.evaluator.access_state.cells[0],
            revoked_credentials=set(),
            revoked_delegations=set(),
        )
    monkeypatch.setattr(
        projection_module,
        "project_enterprise_agentic_public",
        lambda **_: reference.public.model_copy(update={"schema_version": "changed"}),
    )
    with pytest.raises(EnterpriseAgenticIntegrityError, match="projection differs"):
        _validate_public_reprojection(reference.public)


def test_metrics_reject_wrong_digest_case_inventory_and_public_inventory() -> None:
    reference = reference_enterprise_agentic()
    perfect = perfect_enterprise_agentic_prediction(reference.evaluator)
    wrong_digest = synthetic_digest(b"wrong\n")
    rows = tuple(
        item.model_copy(update={"benchmark_digest": wrong_digest})
        for item in perfect.rows
    )
    prediction = EnterpriseAgenticPredictionV1(
        benchmark_digest=wrong_digest,
        rows=rows,
    )
    with pytest.raises(EnterpriseAgenticEvaluationError, match="digest differs"):
        evaluate_enterprise_agentic_prediction(
            public=reference.public,
            evaluator=reference.evaluator,
            prediction=prediction,
        )
    prediction = EnterpriseAgenticPredictionV1(
        benchmark_digest=perfect.benchmark_digest,
        rows=perfect.rows[:-1],
    )
    with pytest.raises(EnterpriseAgenticEvaluationError, match="cover every case"):
        evaluate_enterprise_agentic_prediction(
            public=reference.public,
            evaluator=reference.evaluator,
            prediction=prediction,
        )
    removed_action = _first_action(reference)
    public = _project(
        reference,
        events=tuple(
            item for item in reference.public.events if item.id != removed_action.id
        ),
    )
    with pytest.raises(EnterpriseAgenticEvaluationError, match="public case inventory"):
        evaluate_enterprise_agentic_prediction(
            public=public,
            evaluator=reference.evaluator,
            prediction=perfect,
        )
    metric = _ratio(
        family="empty",
        name="empty",
        numerator=0,
        denominator=0,
        meaning="no applicable cases",
    )
    assert metric.value is None
    assert metric.empty_behaviour is MetricEmptyBehaviour.NULL_IF_EMPTY


def test_model_canonical_and_digest_guards() -> None:
    reference = reference_enterprise_agentic()
    snapshot = reference.public.snapshot
    duplicate_snapshot = snapshot.model_dump(mode="python")
    duplicate_snapshot["accounts"] = (snapshot.accounts[0], snapshot.accounts[0])
    with pytest.raises(
        ValidationError, match="duplicate_enterprise_agentic_accounts_id"
    ):
        EnterpriseAgenticSnapshotV1.model_validate(duplicate_snapshot)
    with pytest.raises(ValidationError, match="duplicate_enterprise_agentic_event_id"):
        reference.public.model_validate(
            {
                **reference.public.model_dump(mode="python"),
                "events": (reference.public.events[0], reference.public.events[0]),
            }
        )
    with pytest.raises(ValidationError, match="public_digest_binding"):
        reference.public.model_validate(
            {
                **reference.public.model_dump(mode="python"),
                "benchmark": reference.public.benchmark.model_copy(
                    update={"config_digest": synthetic_digest(b"wrong\n")}
                ),
            }
        )
    with pytest.raises(ValidationError, match=r"duplicate.*capability_member"):
        EnterpriseAgentCapabilityV1(
            id="capability",
            tenant_id="tenant",
            agent_principal_id="agent",
            authorization_target_ids=("target", "target"),
            actions=("read",),
            scopes=("scope",),
        )
    with pytest.raises(ValidationError, match=r"duplicate.*credential_runtime"):
        EnterpriseAgentCredentialV1(
            id="credential",
            opaque_handle="handle",
            tenant_id="tenant",
            agent_principal_id="agent",
            agent_account_id="account",
            allowed_runtime_ids=("runtime", "runtime"),
            valid_from_tick=0,
        )
    assert canonical_json_bytes_value(
        (reference.public.snapshot.accounts[0],)
    ).endswith(b"\n")
    state = EnterpriseAgenticReplayStateV1(
        processed_event_ids=("event-b", "event-a"),
        revoked_credential_ids=(),
        revoked_delegation_ids=(),
        discarded_evidence_refs=(),
        action_event_ids=(),
        audit_event_ids=(),
    )
    assert state.processed_event_ids == ("event-b", "event-a")


def test_reference_tripwires_fail_closed() -> None:
    reference = reference_enterprise_agentic()
    with pytest.raises(RuntimeError, match="cell selection is empty"):
        _select_cell(
            reference.authorization,
            subject_id="unknown",
            decision=AuthorizationDecision.ALLOW,
        )
    with pytest.raises(RuntimeError, match="reference inputs changed"):
        _require_frozen_access_inputs(
            reference.public.access.universe.model_copy(update={"seed": 1}),
            reference.public.access.corpus,
        )
    changed_evaluator = reference.evaluator.model_copy(
        update={
            "truth": reference.evaluator.truth.model_copy(
                update={"case_labels": reference.evaluator.truth.case_labels[:-1]}
            )
        }
    )
    with pytest.raises(RuntimeError, match="inventory is incomplete"):
        _require_case_inventory(changed_evaluator)


def test_public_loader_wraps_projection_failure_and_detects_reprojection_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = reference_enterprise_agentic()
    root = tmp_path / "world"
    export_enterprise_agentic_benchmark(
        root, public=reference.public, evaluator=reference.evaluator
    )
    monkeypatch.setattr(
        serialization_module,
        "project_enterprise_agentic_public",
        lambda **_: (_ for _ in ()).throw(ValueError("broken")),
    )
    with pytest.raises(EnterpriseAgenticArtifactError, match="bindings are invalid"):
        load_public_enterprise_agentic_benchmark(root)
    monkeypatch.setattr(
        serialization_module,
        "project_enterprise_agentic_public",
        lambda **_: reference.public.model_copy(update={"schema_version": "changed"}),
    )
    with pytest.raises(EnterpriseAgenticArtifactError, match="projection differs"):
        load_public_enterprise_agentic_benchmark(root)


def test_trace_validator_skips_blanks_and_handles_non_object_json() -> None:
    reference = reference_enterprise_agentic()
    perfect = perfect_enterprise_agentic_prediction(reference.evaluator)
    serialized = "\n[]\n" + enterprise_agentic_trace_to_jsonl(perfect)
    report = validate_enterprise_agentic_trace_jsonl(
        serialized, public=reference.public
    )
    assert not report.valid
    assert any(item.code == "invalid_row" for item in report.issues)


def test_cli_generate_rejects_existing_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from synthworld.cli import main

    output = tmp_path / "existing"
    output.mkdir()
    assert main(["generate-enterprise-agentic", "--output", str(output)]) == 1
    assert "already exists" in capsys.readouterr().err
