"""Pure public projection and evaluator compilation for enterprise-agentic cases."""

from __future__ import annotations

from synthworld.agentic.enterprise.errors import EnterpriseAgenticIntegrityError
from synthworld.agentic.enterprise.models import (
    AgentAsPrincipalV1,
    AgenticAdministrativeState,
    AgenticExpectedDecisionV1,
    AgenticFailureReason,
    AgenticGateOutcome,
    EnterpriseAgenticAccessPublicInputV1,
    EnterpriseAgenticActionAttemptedV1,
    EnterpriseAgenticAttributionTruthV1,
    EnterpriseAgenticAuditPerformedV1,
    EnterpriseAgenticBenchmarkV1,
    EnterpriseAgenticCaseKind,
    EnterpriseAgenticCaseLabelV1,
    EnterpriseAgenticCaseReferenceV1,
    EnterpriseAgenticCaseTruthV1,
    EnterpriseAgenticEvaluatorArtifactsV1,
    EnterpriseAgenticEventV1,
    EnterpriseAgenticProjectionConfigV1,
    EnterpriseAgenticPublicInputV1,
    EnterpriseAgenticSnapshotV1,
    EnterpriseAgenticTruthV1,
    HumanSubjectAgentContextV1,
    canonical_json_bytes_value,
)
from synthworld.agentic.enterprise.replay import (
    materialize_enterprise_agentic_overlay,
)
from synthworld.enterprise.abac.compiler import compile_enterprise_abac_truth
from synthworld.enterprise.abac.models import CompiledEnterpriseAbacTruthV1
from synthworld.enterprise.authorization.compiler import (
    compile_enterprise_access_state,
    compile_enterprise_authorization_kernel,
    compose_enterprise_authorization,
)
from synthworld.enterprise.authorization.models import (
    CompiledEnterpriseAccessCellV1,
    CompiledEnterpriseAccessStateV1,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import (
    EnterpriseCanonicalBindingTruthV1,
    PrincipalKind,
)
from synthworld.enterprise.rbac.common import AuthorizationDecision
from synthworld.enterprise.rbac.compiler import (
    compile_enterprise_directory_rbac_truth,
)
from synthworld.enterprise.rbac.models import CompiledEnterpriseDirectoryRbacTruthV1
from synthworld.enterprise.rebac.compiler import compile_enterprise_rebac_truth
from synthworld.enterprise.rebac.models import CompiledEnterpriseRebacTruthV1


def project_enterprise_agentic_public(
    *,
    access: EnterpriseAgenticAccessPublicInputV1,
    snapshot: EnterpriseAgenticSnapshotV1,
    events: tuple[EnterpriseAgenticEventV1, ...],
    config: EnterpriseAgenticProjectionConfigV1,
) -> EnterpriseAgenticPublicInputV1:
    """Project a bounded public pack without copying any expected outcomes."""

    _enforce_limits(snapshot, events, config)
    materialize_enterprise_agentic_overlay(snapshot, events)
    action_events = tuple(
        event
        for event in events
        if isinstance(event.payload, EnterpriseAgenticActionAttemptedV1)
    )
    audits = tuple(
        event
        for event in events
        if isinstance(event.payload, EnterpriseAgenticAuditPerformedV1)
    )
    if len(audits) != 1:
        raise EnterpriseAgenticIntegrityError(
            "enterprise agentic pack must contain exactly one audit event"
        )
    audit = audits[0]
    if any((event.tick, event.id) >= (audit.tick, audit.id) for event in action_events):
        raise EnterpriseAgenticIntegrityError(
            "enterprise agentic action events must precede the audit event"
        )
    cases = tuple(
        EnterpriseAgenticCaseReferenceV1(
            case_id=_action_payload(event).attempt.case_id,
            action_event_id=event.id,
            mapping_kind=_action_payload(event).attempt.mapping.mapping_kind,
        )
        for event in action_events
    )
    if len({item.case_id for item in cases}) != len(cases):
        raise EnterpriseAgenticIntegrityError(
            "enterprise agentic action events repeat a case id"
        )
    universe_digest = synthetic_digest(canonical_json_bytes(access.universe))
    corpus_digest = synthetic_digest(canonical_json_bytes(access.corpus))
    if (
        access.corpus.identity_access_universe_digest != universe_digest
        or access.authorization_kernel.identity_access_universe_digest
        != universe_digest
        or access.authorization_kernel.evaluation_corpus_digest != corpus_digest
    ):
        raise EnterpriseAgenticIntegrityError(
            "enterprise agentic access input digest bindings differ"
        )
    benchmark = EnterpriseAgenticBenchmarkV1(
        seed=config.seed,
        tier=config.tier,
        config_digest=synthetic_digest(canonical_json_bytes(config)),
        identity_access_universe_digest=universe_digest,
        evaluation_corpus_digest=corpus_digest,
        access_input_digest=synthetic_digest(canonical_json_bytes(access)),
        snapshot_digest=synthetic_digest(canonical_json_bytes(snapshot)),
        events_digest=synthetic_digest(canonical_json_bytes_value(events)),
        audit_event_id=audit.id,
        cases=cases,
    )
    public = EnterpriseAgenticPublicInputV1(
        config=config,
        access=access,
        snapshot=snapshot,
        events=events,
        benchmark=benchmark,
    )
    _validate_public_references(public)
    return public


def compile_enterprise_agentic_truth(
    *,
    public: EnterpriseAgenticPublicInputV1,
    canonical_binding_truth: EnterpriseCanonicalBindingTruthV1,
    directory_rbac_truth: CompiledEnterpriseDirectoryRbacTruthV1,
    abac_truth: CompiledEnterpriseAbacTruthV1,
    rebac_truth: CompiledEnterpriseRebacTruthV1,
    access_state: CompiledEnterpriseAccessStateV1,
) -> EnterpriseAgenticEvaluatorArtifactsV1:
    """Recompile enterprise ``F`` and then apply only the declared agentic gates."""

    _validate_public_reprojection(public)
    _validate_evaluator_access(
        public=public,
        canonical_binding_truth=canonical_binding_truth,
        directory_rbac_truth=directory_rbac_truth,
        abac_truth=abac_truth,
        rebac_truth=rebac_truth,
        access_state=access_state,
    )
    action_events = {
        event.id: event
        for event in public.events
        if isinstance(event.payload, EnterpriseAgenticActionAttemptedV1)
    }
    audit_state = materialize_enterprise_agentic_overlay(
        public.snapshot,
        public.events,
        before_event_id=public.benchmark.audit_event_id,
    )
    access_cells = {item.cell_id: item for item in access_state.cells}
    truths: list[EnterpriseAgenticCaseTruthV1] = []
    labels: list[EnterpriseAgenticCaseLabelV1] = []
    for case in public.benchmark.cases:
        event = action_events[case.action_event_id]
        payload = _action_payload(event)
        replay = materialize_enterprise_agentic_overlay(
            public.snapshot,
            public.events,
            before_event_id=event.id,
        )
        expected = _evaluate_attempt(
            public=public,
            event=event,
            access_cell=access_cells[payload.attempt.cell_id],
            revoked_credentials=set(replay.revoked_credential_ids),
            revoked_delegations=set(replay.revoked_delegation_ids),
        )
        mapping = payload.attempt.mapping
        human_id = (
            mapping.owner_human_principal_id
            if isinstance(mapping, AgentAsPrincipalV1)
            else mapping.human_principal_id
        )
        reconstructable = not bool(
            set(payload.attempt.evidence_refs)
            & set(audit_state.discarded_evidence_refs)
        )
        kind = _derive_case_kind(
            mapping=mapping,
            expected=expected,
            reconstructable=reconstructable,
            snapshot=public.snapshot,
            credential_id=payload.attempt.credential_id,
            revoked_credentials=set(replay.revoked_credential_ids),
            revoked_delegations=set(replay.revoked_delegation_ids),
        )
        truths.append(
            EnterpriseAgenticCaseTruthV1(
                case_id=case.case_id,
                action_event_id=event.id,
                expected_decision=expected,
                attribution=EnterpriseAgenticAttributionTruthV1(
                    human_principal_id=human_id,
                    agent_principal_id=mapping.agent_principal_id,
                    agent_account_id=mapping.agent_account_id,
                    runtime_id=mapping.runtime_id,
                ),
                required_evidence_refs=payload.attempt.evidence_refs,
                reconstructable_at_audit=reconstructable,
            )
        )
        labels.append(
            EnterpriseAgenticCaseLabelV1(
                case_id=case.case_id,
                kind=kind,
                scenario_tags=_scenario_tags(kind, mapping),
            )
        )
    truth = EnterpriseAgenticTruthV1(
        public_input_digest=synthetic_digest(canonical_json_bytes(public)),
        benchmark_digest=synthetic_digest(canonical_json_bytes(public.benchmark)),
        access_state_digest=synthetic_digest(canonical_json_bytes(access_state)),
        cases=tuple(truths),
        case_labels=tuple(labels),
    )
    return EnterpriseAgenticEvaluatorArtifactsV1(
        public_input_digest=truth.public_input_digest,
        canonical_binding_truth=canonical_binding_truth,
        directory_rbac_truth=directory_rbac_truth,
        abac_truth=abac_truth,
        rebac_truth=rebac_truth,
        access_state=access_state,
        truth=truth,
    )


def _enforce_limits(
    snapshot: EnterpriseAgenticSnapshotV1,
    events: tuple[EnterpriseAgenticEventV1, ...],
    config: EnterpriseAgenticProjectionConfigV1,
) -> None:
    measured = (
        ("accounts", len(snapshot.accounts), config.limits.max_accounts),
        ("runtimes", len(snapshot.runtimes), config.limits.max_runtimes),
        ("credentials", len(snapshot.credentials), config.limits.max_credentials),
        ("capabilities", len(snapshot.capabilities), config.limits.max_capabilities),
        ("delegations", len(snapshot.delegations), config.limits.max_delegations),
        ("events", len(events), config.limits.max_events),
        (
            "cases",
            sum(
                isinstance(item.payload, EnterpriseAgenticActionAttemptedV1)
                for item in events
            ),
            config.limits.max_cases,
        ),
    )
    for name, count, limit in measured:
        if count > limit:
            raise EnterpriseAgenticIntegrityError(
                f"enterprise agentic {name} count exceeds its declared limit"
            )


def _validate_public_reprojection(public: EnterpriseAgenticPublicInputV1) -> None:
    reprojected = project_enterprise_agentic_public(
        access=public.access,
        snapshot=public.snapshot,
        events=public.events,
        config=public.config,
    )
    if reprojected != public:
        raise EnterpriseAgenticIntegrityError(
            "enterprise agentic public projection differs"
        )


def _validate_evaluator_access(
    *,
    public: EnterpriseAgenticPublicInputV1,
    canonical_binding_truth: EnterpriseCanonicalBindingTruthV1,
    directory_rbac_truth: CompiledEnterpriseDirectoryRbacTruthV1,
    abac_truth: CompiledEnterpriseAbacTruthV1,
    rebac_truth: CompiledEnterpriseRebacTruthV1,
    access_state: CompiledEnterpriseAccessStateV1,
) -> None:
    access = public.access
    compiled_rbac = compile_enterprise_directory_rbac_truth(
        universe=access.universe,
        canonical_binding_truth=canonical_binding_truth,
        corpus=access.corpus,
        directory_rbac_kernel=access.directory_rbac_kernel,
        session_state=access.rbac_session_state,
        directory_rbac_intent=access.directory_rbac_intent,
    )
    compiled_abac = compile_enterprise_abac_truth(
        universe=access.universe,
        corpus=access.corpus,
        abac_state=access.abac_state,
        abac_intent=access.abac_intent,
    )
    compiled_rebac = compile_enterprise_rebac_truth(
        universe=access.universe,
        corpus=access.corpus,
        rebac_state=access.rebac_state,
        rebac_intent=access.rebac_intent,
    )
    if (
        compiled_rbac != directory_rbac_truth
        or compiled_abac != abac_truth
        or compiled_rebac != rebac_truth
    ):
        raise EnterpriseAgenticIntegrityError(
            "enterprise agentic component truth differs from recompiled truth"
        )
    composition = compose_enterprise_authorization(
        directory_rbac_truth=directory_rbac_truth,
        abac_truth=abac_truth,
        rebac_truth=rebac_truth,
    )
    kernel = compile_enterprise_authorization_kernel(
        universe=access.universe,
        corpus=access.corpus,
        composition=composition,
        evaluation_profile=access.evaluation_profile,
    )
    compiled_access = compile_enterprise_access_state(
        universe=access.universe,
        canonical_binding_truth=canonical_binding_truth,
        corpus=access.corpus,
        composition=composition,
        directory_rbac_truth=directory_rbac_truth,
        abac_truth=abac_truth,
        rebac_truth=rebac_truth,
        evaluation_profile=access.evaluation_profile,
    )
    if (
        composition != access.composition
        or kernel != access.authorization_kernel
        or compiled_access != access_state
    ):
        raise EnterpriseAgenticIntegrityError(
            "enterprise agentic aggregate access truth differs"
        )


def _validate_public_references(public: EnterpriseAgenticPublicInputV1) -> None:
    universe = public.access.universe
    principals = {item.principal_id: item for item in universe.principals}
    accounts = {item.id: item for item in public.snapshot.accounts}
    runtimes = {item.id: item for item in public.snapshot.runtimes}
    credentials = {item.id: item for item in public.snapshot.credentials}
    capabilities = {item.id: item for item in public.snapshot.capabilities}
    delegations = {item.id: item for item in public.snapshot.delegations}
    cells = {item.cell_id: item for item in public.access.corpus.evaluation_cells}
    atoms = {item.access_atom_id: item for item in universe.access_atoms}
    requests = {
        item.access_request_id: item for item in public.access.corpus.access_requests
    }
    targets = {
        item.authorization_target_id: item for item in universe.authorization_targets
    }
    for account in accounts.values():
        if account.agent_principal_id not in principals:
            raise EnterpriseAgenticIntegrityError(
                "enterprise agent account references an unknown principal"
            )
    for event in public.events:
        if not isinstance(event.payload, EnterpriseAgenticActionAttemptedV1):
            continue
        attempt = event.payload.attempt
        mapping = attempt.mapping
        if (
            mapping.enterprise_subject_id not in principals
            or mapping.agent_principal_id not in principals
            or mapping.agent_account_id not in accounts
            or mapping.runtime_id not in runtimes
            or attempt.credential_id not in credentials
            or attempt.capability_id not in capabilities
            or attempt.cell_id not in cells
            or attempt.access_atom_id not in atoms
            or attempt.access_request_id not in requests
            or attempt.authorization_target_id not in targets
        ):
            raise EnterpriseAgenticIntegrityError(
                "enterprise agentic action references an unknown object"
            )
        if isinstance(mapping, AgentAsPrincipalV1):
            optional_ids = (
                (mapping.owner_human_principal_id, principals),
                (mapping.provenance_delegation_id, delegations),
            )
        else:
            optional_ids = (
                (mapping.human_principal_id, principals),
                (mapping.delegation_id, delegations),
            )
        if any(
            value is not None and value not in inventory
            for value, inventory in optional_ids
        ):
            raise EnterpriseAgenticIntegrityError(
                "enterprise agentic mapping references an unknown optional object"
            )
        cell = cells[attempt.cell_id]
        atom = atoms[attempt.access_atom_id]
        request = requests[attempt.access_request_id]
        if (
            cell.access_atom_id != atom.access_atom_id
            or request.cell_id != cell.cell_id
            or attempt.authorization_target_id != atom.authorization_target_id
            or attempt.action != atom.action
        ):
            raise EnterpriseAgenticIntegrityError(
                "enterprise agentic action does not bind one frozen atom and cell"
            )
        if not set(attempt.evidence_refs) <= set(public.snapshot.initial_evidence_refs):
            raise EnterpriseAgenticIntegrityError(
                "enterprise agentic action references unknown evidence"
            )


def _evaluate_attempt(
    *,
    public: EnterpriseAgenticPublicInputV1,
    event: EnterpriseAgenticEventV1,
    access_cell: CompiledEnterpriseAccessCellV1,
    revoked_credentials: set[str],
    revoked_delegations: set[str],
) -> AgenticExpectedDecisionV1:
    payload = event.payload
    if not isinstance(payload, EnterpriseAgenticActionAttemptedV1):
        raise EnterpriseAgenticIntegrityError("expected an action event")
    attempt = payload.attempt
    mapping = attempt.mapping
    snapshot = public.snapshot
    universe = public.access.universe
    cell = access_cell
    atom = next(
        item
        for item in universe.access_atoms
        if item.access_atom_id == attempt.access_atom_id
    )
    principals = {item.principal_id: item for item in universe.principals}
    targets = {
        item.authorization_target_id: item for item in universe.authorization_targets
    }
    accounts = {item.id: item for item in snapshot.accounts}
    runtimes = {item.id: item for item in snapshot.runtimes}
    credentials = {item.id: item for item in snapshot.credentials}
    capabilities = {item.id: item for item in snapshot.capabilities}
    delegations = {item.id: item for item in snapshot.delegations}
    account = accounts[mapping.agent_account_id]
    runtime = runtimes[mapping.runtime_id]
    credential = credentials[attempt.credential_id]
    capability = capabilities[attempt.capability_id]
    agent = principals[mapping.agent_principal_id]
    subject = principals[mapping.enterprise_subject_id]
    target = targets[attempt.authorization_target_id]

    if isinstance(mapping, AgentAsPrincipalV1):
        subject_ok = (
            mapping.enterprise_subject_id == atom.subject_id
            and mapping.agent_principal_id == atom.subject_id
            and agent.principal_kind is PrincipalKind.AGENT
        )
        human_tenant = None
        delegation = None
    else:
        subject_ok = (
            mapping.enterprise_subject_id == atom.subject_id
            and mapping.human_principal_id == atom.subject_id
            and agent.principal_kind is PrincipalKind.AGENT
            and principals[mapping.human_principal_id].principal_kind
            is not PrincipalKind.AGENT
        )
        human_tenant = principals[mapping.human_principal_id].tenant_id
        delegation = (
            delegations[mapping.delegation_id]
            if mapping.delegation_id is not None
            else None
        )
    tenant_values = {
        subject.tenant_id,
        target.tenant_id,
        agent.tenant_id,
        account.tenant_id,
        runtime.tenant_id,
        credential.tenant_id,
        capability.tenant_id,
    }
    if human_tenant is not None:
        tenant_values.add(human_tenant)
    if delegation is not None:
        tenant_values.add(delegation.tenant_id)
    tenant_ok = len(tenant_values) == 1
    account_binding_ok = account.agent_principal_id == mapping.agent_principal_id
    account_active = (
        account.administrative_state is AgenticAdministrativeState.ACTIVE
        and account.valid_from_tick <= event.tick
        and (account.valid_until_tick is None or event.tick < account.valid_until_tick)
    )
    account_ok = account_binding_ok and account_active
    runtime_ok = (
        runtime.agent_principal_id == mapping.agent_principal_id
        and runtime.agent_account_id == mapping.agent_account_id
    )
    credential_ok = (
        credential.agent_principal_id == mapping.agent_principal_id
        and credential.agent_account_id == mapping.agent_account_id
        and mapping.runtime_id in credential.allowed_runtime_ids
        and credential.valid_from_tick <= event.tick
        and (
            credential.valid_until_tick is None
            or event.tick < credential.valid_until_tick
        )
        and credential.id not in revoked_credentials
    )
    capability_ok = (
        capability.agent_principal_id == mapping.agent_principal_id
        and attempt.authorization_target_id in capability.authorization_target_ids
        and attempt.action in capability.actions
        and set(attempt.requested_scopes) <= set(capability.scopes)
    )
    if isinstance(mapping, AgentAsPrincipalV1):
        delegation_outcome = AgenticGateOutcome.NOT_APPLICABLE
        delegation_ok = True
    else:
        delegation_ok = (
            delegation is not None
            and delegation.human_principal_id == mapping.human_principal_id
            and delegation.agent_principal_id == mapping.agent_principal_id
            and delegation.agent_account_id == mapping.agent_account_id
            and delegation.capability_id == attempt.capability_id
            and delegation.valid_from_tick <= event.tick
            and (
                delegation.valid_until_tick is None
                or event.tick < delegation.valid_until_tick
            )
            and delegation.id not in revoked_delegations
        )
        delegation_outcome = _gate(delegation_ok)
    failures: list[AgenticFailureReason] = []
    if cell.final_decision is AuthorizationDecision.DENY:
        failures.append(AgenticFailureReason.ENTERPRISE_DENIED)
    if not subject_ok:
        failures.append(AgenticFailureReason.SUBJECT_MISMATCH)
    if not tenant_ok:
        failures.append(AgenticFailureReason.TENANT_MISMATCH)
    if not account_ok:
        failures.append(
            AgenticFailureReason.AGENT_ACCOUNT_BINDING_MISMATCH
            if not account_binding_ok
            else AgenticFailureReason.AGENT_ACCOUNT_INACTIVE
        )
    if not runtime_ok:
        failures.append(AgenticFailureReason.WRONG_RUNTIME)
    if not credential_ok:
        failures.append(AgenticFailureReason.CREDENTIAL_INVALID)
    if not capability_ok:
        failures.append(AgenticFailureReason.CAPABILITY_EXCEEDED)
    if not delegation_ok:
        failures.append(
            AgenticFailureReason.NO_ACTIVE_DELEGATION
            if delegation is None or delegation.id in revoked_delegations
            else AgenticFailureReason.DELEGATION_MISMATCH
        )
    final = (
        AuthorizationDecision.ALLOW
        if cell.final_decision is AuthorizationDecision.ALLOW
        and subject_ok
        and tenant_ok
        and account_ok
        and runtime_ok
        and credential_ok
        and capability_ok
        and delegation_ok
        else AuthorizationDecision.DENY
    )
    return AgenticExpectedDecisionV1(
        enterprise_decision=cell.final_decision,
        subject_gate=_gate(subject_ok),
        tenant_gate=_gate(tenant_ok),
        agent_account_gate=_gate(account_ok),
        runtime_gate=_gate(runtime_ok),
        credential_gate=_gate(credential_ok),
        capability_gate=_gate(capability_ok),
        delegation_gate=delegation_outcome,
        final_decision=final,
        failure_reasons=tuple(failures),
    )


def _action_payload(
    event: EnterpriseAgenticEventV1,
) -> EnterpriseAgenticActionAttemptedV1:
    payload = event.payload
    if not isinstance(payload, EnterpriseAgenticActionAttemptedV1):
        raise EnterpriseAgenticIntegrityError("expected an action event")
    return payload


def _gate(value: bool) -> AgenticGateOutcome:
    return AgenticGateOutcome.SATISFIED if value else AgenticGateOutcome.UNSATISFIED


def _derive_case_kind(
    *,
    mapping: AgentAsPrincipalV1 | HumanSubjectAgentContextV1,
    expected: AgenticExpectedDecisionV1,
    reconstructable: bool,
    snapshot: EnterpriseAgenticSnapshotV1,
    credential_id: str,
    revoked_credentials: set[str],
    revoked_delegations: set[str],
) -> EnterpriseAgenticCaseKind:
    if isinstance(mapping, AgentAsPrincipalV1):
        if expected.tenant_gate is AgenticGateOutcome.UNSATISFIED:
            return EnterpriseAgenticCaseKind.CROSS_TENANT_AGENT
        if expected.agent_account_gate is AgenticGateOutcome.UNSATISFIED:
            return EnterpriseAgenticCaseKind.SUSPENDED_AGENT_ACCOUNT
        if expected.subject_gate is AgenticGateOutcome.UNSATISFIED:
            return EnterpriseAgenticCaseKind.WRONG_SUBJECT_AGENT
        if expected.runtime_gate is AgenticGateOutcome.UNSATISFIED:
            return EnterpriseAgenticCaseKind.WRONG_RUNTIME_AGENT
        if expected.credential_gate is AgenticGateOutcome.UNSATISFIED:
            return (
                EnterpriseAgenticCaseKind.INVALID_CREDENTIAL_AGENT
                if credential_id in revoked_credentials
                else EnterpriseAgenticCaseKind.SHARED_CREDENTIAL_AGENT
            )
        if expected.capability_gate is AgenticGateOutcome.UNSATISFIED:
            return EnterpriseAgenticCaseKind.WRONG_SCOPE_AGENT
        if expected.enterprise_decision is AuthorizationDecision.DENY:
            return (
                EnterpriseAgenticCaseKind.HUMAN_AUTHORITY_NOT_UNIONED
                if mapping.owner_human_principal_id is not None
                else EnterpriseAgenticCaseKind.ENTERPRISE_DENIED_AGENT
            )
        return EnterpriseAgenticCaseKind.VALID_AGENT_PRINCIPAL
    if expected.tenant_gate is AgenticGateOutcome.UNSATISFIED:
        return EnterpriseAgenticCaseKind.CROSS_TENANT_HUMAN
    if expected.runtime_gate is AgenticGateOutcome.UNSATISFIED:
        return EnterpriseAgenticCaseKind.WRONG_RUNTIME_HUMAN
    if expected.capability_gate is AgenticGateOutcome.UNSATISFIED:
        return EnterpriseAgenticCaseKind.WRONG_SCOPE_HUMAN
    if expected.delegation_gate is AgenticGateOutcome.UNSATISFIED:
        if mapping.delegation_id is None:
            return EnterpriseAgenticCaseKind.MISSING_DELEGATION
        if mapping.delegation_id in revoked_delegations:
            return EnterpriseAgenticCaseKind.REVOKED_DELEGATION
        delegation = next(
            item for item in snapshot.delegations if item.id == mapping.delegation_id
        )
        return (
            EnterpriseAgenticCaseKind.SAME_HUMAN_DIFFERENT_AGENT
            if delegation.human_principal_id == mapping.human_principal_id
            else EnterpriseAgenticCaseKind.SAME_AGENT_DIFFERENT_HUMAN
        )
    if expected.enterprise_decision is AuthorizationDecision.DENY:
        return EnterpriseAgenticCaseKind.ENTERPRISE_DENIED_HUMAN
    if not reconstructable:
        return EnterpriseAgenticCaseKind.EVIDENCE_DISCARDED
    return EnterpriseAgenticCaseKind.VALID_HUMAN_CONTEXT


def _scenario_tags(
    kind: EnterpriseAgenticCaseKind,
    mapping: AgentAsPrincipalV1 | HumanSubjectAgentContextV1,
) -> tuple[str, ...]:
    tags = {"agent-identity", "runtime-binding"}
    if (
        isinstance(mapping, AgentAsPrincipalV1)
        and mapping.owner_human_principal_id is None
    ):
        tags.add("ownerless-nhi")
    if kind in {
        EnterpriseAgenticCaseKind.SAME_HUMAN_DIFFERENT_AGENT,
        EnterpriseAgenticCaseKind.SAME_AGENT_DIFFERENT_HUMAN,
        EnterpriseAgenticCaseKind.MISSING_DELEGATION,
        EnterpriseAgenticCaseKind.REVOKED_DELEGATION,
        EnterpriseAgenticCaseKind.VALID_HUMAN_CONTEXT,
        EnterpriseAgenticCaseKind.ENTERPRISE_DENIED_HUMAN,
    }:
        tags.add("delegation-chain")
    if kind in {
        EnterpriseAgenticCaseKind.HUMAN_AUTHORITY_NOT_UNIONED,
        EnterpriseAgenticCaseKind.SAME_HUMAN_DIFFERENT_AGENT,
        EnterpriseAgenticCaseKind.SAME_AGENT_DIFFERENT_HUMAN,
    }:
        tags.add("ownership")
    if kind in {
        EnterpriseAgenticCaseKind.INVALID_CREDENTIAL_AGENT,
        EnterpriseAgenticCaseKind.SHARED_CREDENTIAL_AGENT,
        EnterpriseAgenticCaseKind.REVOKED_DELEGATION,
        EnterpriseAgenticCaseKind.SUSPENDED_AGENT_ACCOUNT,
    }:
        tags.add("agent-lifecycle")
    if kind is EnterpriseAgenticCaseKind.EVIDENCE_DISCARDED:
        tags.add("audit-evidence")
    if kind in {
        EnterpriseAgenticCaseKind.CROSS_TENANT_AGENT,
        EnterpriseAgenticCaseKind.CROSS_TENANT_HUMAN,
    }:
        tags.add("federated-boundary")
    if kind in {
        EnterpriseAgenticCaseKind.ENTERPRISE_DENIED_AGENT,
        EnterpriseAgenticCaseKind.ENTERPRISE_DENIED_HUMAN,
        EnterpriseAgenticCaseKind.HUMAN_AUTHORITY_NOT_UNIONED,
    }:
        tags.add("policy-mismatch")
    if kind in {
        EnterpriseAgenticCaseKind.WRONG_SCOPE_AGENT,
        EnterpriseAgenticCaseKind.WRONG_SCOPE_HUMAN,
    }:
        tags.add("excessive-capability")
    if kind is EnterpriseAgenticCaseKind.SHARED_CREDENTIAL_AGENT:
        tags.add("shared-credential")
    return tuple(tags)


__all__ = [
    "compile_enterprise_agentic_truth",
    "project_enterprise_agentic_public",
]
