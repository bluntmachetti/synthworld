"""End-to-end tests for the bounded enterprise-agentic smoke projection."""

from __future__ import annotations

from collections import Counter

import pytest
from pydantic import BaseModel, ValidationError

from synthworld.agentic.enterprise.baselines import (
    ENTERPRISE_AGENTIC_BASELINES,
)
from synthworld.agentic.enterprise.metrics import (
    evaluate_enterprise_agentic_prediction,
    perfect_enterprise_agentic_prediction,
)
from synthworld.agentic.enterprise.models import (
    AgentAsPrincipalV1,
    AgentAuthorizationMappingKind,
    AgenticAdministrativeState,
    AgenticGateOutcome,
    EnterpriseAgentAccountV1,
    EnterpriseAgentCredentialV1,
    EnterpriseAgentDelegationV1,
    EnterpriseAgenticActionAttemptedV1,
    EnterpriseAgenticCaseKind,
    EnterpriseAgenticPredictionV1,
    EnterpriseAgenticTraceValidationIssueV1,
    EnterpriseAgenticTraceValidationReportV1,
    HumanSubjectAgentContextV1,
)
from synthworld.agentic.enterprise.reference import (
    REFERENCE_ENTERPRISE_AGENTIC_CORPUS_SHA256,
    REFERENCE_ENTERPRISE_AGENTIC_UNIVERSE_SHA256,
    ReferenceEnterpriseAgenticV1,
    reference_enterprise_agentic,
)
from synthworld.agentic.generator import generate_asteria_agentic_v1
from synthworld.agentic.serialization import agentic_artifact_checksums
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import PrincipalKind
from synthworld.enterprise.rbac.common import AuthorizationDecision


@pytest.fixture(scope="module")
def reference() -> ReferenceEnterpriseAgenticV1:
    return reference_enterprise_agentic()


def test_reference_is_deterministic_fixed_and_discriminating(
    reference: ReferenceEnterpriseAgenticV1,
) -> None:
    repeated = reference_enterprise_agentic()
    assert canonical_json_bytes(repeated.public) == canonical_json_bytes(
        reference.public
    )
    assert canonical_json_bytes(repeated.evaluator) == canonical_json_bytes(
        reference.evaluator
    )
    benchmark = reference.public.benchmark
    assert (
        benchmark.identity_access_universe_digest.value
        == REFERENCE_ENTERPRISE_AGENTIC_UNIVERSE_SHA256
    )
    assert (
        benchmark.evaluation_corpus_digest.value
        == REFERENCE_ENTERPRISE_AGENTIC_CORPUS_SHA256
    )
    universe = reference.public.access.universe
    corpus = reference.public.access.corpus
    assert len(universe.principals) == 6
    assert len(universe.access_atoms) == 16
    assert len(corpus.evaluation_cells) == 19
    assert canonical_json_bytes(universe) == canonical_json_bytes(
        reference.authorization.rbac.universe_result.public_universe
    )
    assert canonical_json_bytes(corpus) == canonical_json_bytes(
        reference.authorization.rbac.corpus_result.public_corpus
    )
    assert len(reference.evaluator.truth.cases) == 20
    assert {item.kind for item in reference.evaluator.truth.case_labels} == set(
        EnterpriseAgenticCaseKind
    )
    assert Counter(
        item.expected_decision.final_decision
        for item in reference.evaluator.truth.cases
    ) == Counter({AuthorizationDecision.DENY: 17, AuthorizationDecision.ALLOW: 3})
    assert Counter(item.mapping_kind for item in benchmark.cases) == Counter(
        {
            AgentAuthorizationMappingKind.AGENT_AS_PRINCIPAL: 10,
            AgentAuthorizationMappingKind.HUMAN_SUBJECT_AGENT_CONTEXT: 10,
        }
    )
    assert tuple((item.tick, item.id) for item in reference.public.events) == tuple(
        sorted((item.tick, item.id) for item in reference.public.events)
    )
    assert benchmark.aiim_profile_version == "0.1.0-experimental"
    assert benchmark.aiim_source_id == "openid-aiim-mcp-interop-2026-07-14"


def test_mapping_profiles_never_union_human_and_agent_authority(
    reference: ReferenceEnterpriseAgenticV1,
) -> None:
    atoms = {
        item.access_atom_id: item
        for item in reference.public.access.universe.access_atoms
    }
    principals = {
        item.principal_id: item for item in reference.public.access.universe.principals
    }
    access_cells = {
        item.cell_id: item for item in reference.evaluator.access_state.cells
    }
    truth = {item.case_id: item for item in reference.evaluator.truth.cases}
    labels = {item.case_id: item.kind for item in reference.evaluator.truth.case_labels}
    for event in reference.public.events:
        if not isinstance(event.payload, EnterpriseAgenticActionAttemptedV1):
            continue
        attempt = event.payload.attempt
        mapping = attempt.mapping
        atom = atoms[attempt.access_atom_id]
        expected = truth[attempt.case_id].expected_decision
        assert (
            expected.enterprise_decision is access_cells[attempt.cell_id].final_decision
        )
        if labels[attempt.case_id] is EnterpriseAgenticCaseKind.WRONG_SUBJECT_AGENT:
            assert mapping.enterprise_subject_id != atom.subject_id
            assert expected.subject_gate is AgenticGateOutcome.UNSATISFIED
        else:
            assert mapping.enterprise_subject_id == atom.subject_id
        assert (
            principals[mapping.agent_principal_id].principal_kind is PrincipalKind.AGENT
        )
        if isinstance(mapping, AgentAsPrincipalV1):
            assert atom.subject_id == mapping.agent_principal_id
            assert expected.delegation_gate is AgenticGateOutcome.NOT_APPLICABLE
        else:
            assert isinstance(mapping, HumanSubjectAgentContextV1)
            assert atom.subject_id == mapping.human_principal_id
            assert mapping.human_principal_id != mapping.agent_principal_id

    non_union_case_id = next(
        case_id
        for case_id, kind in labels.items()
        if kind is EnterpriseAgenticCaseKind.HUMAN_AUTHORITY_NOT_UNIONED
    )
    non_union = truth[non_union_case_id]
    assert non_union.expected_decision.enterprise_decision is AuthorizationDecision.DENY
    assert non_union.expected_decision.final_decision is AuthorizationDecision.DENY
    assert non_union.attribution.human_principal_id is not None


def test_each_failure_family_changes_only_the_downstream_gate_expected(
    reference: ReferenceEnterpriseAgenticV1,
) -> None:
    labels = {item.case_id: item.kind for item in reference.evaluator.truth.case_labels}
    truth = {item.case_id: item for item in reference.evaluator.truth.cases}
    expected_failure_gate = {
        EnterpriseAgenticCaseKind.WRONG_RUNTIME_AGENT: "runtime_gate",
        EnterpriseAgenticCaseKind.WRONG_RUNTIME_HUMAN: "runtime_gate",
        EnterpriseAgenticCaseKind.WRONG_SUBJECT_AGENT: "subject_gate",
        EnterpriseAgenticCaseKind.INVALID_CREDENTIAL_AGENT: "credential_gate",
        EnterpriseAgenticCaseKind.SHARED_CREDENTIAL_AGENT: "credential_gate",
        EnterpriseAgenticCaseKind.WRONG_SCOPE_AGENT: "capability_gate",
        EnterpriseAgenticCaseKind.WRONG_SCOPE_HUMAN: "capability_gate",
        EnterpriseAgenticCaseKind.CROSS_TENANT_AGENT: "tenant_gate",
        EnterpriseAgenticCaseKind.CROSS_TENANT_HUMAN: "tenant_gate",
        EnterpriseAgenticCaseKind.SUSPENDED_AGENT_ACCOUNT: "agent_account_gate",
        EnterpriseAgenticCaseKind.MISSING_DELEGATION: "delegation_gate",
        EnterpriseAgenticCaseKind.REVOKED_DELEGATION: "delegation_gate",
        EnterpriseAgenticCaseKind.SAME_HUMAN_DIFFERENT_AGENT: "delegation_gate",
        EnterpriseAgenticCaseKind.SAME_AGENT_DIFFERENT_HUMAN: "delegation_gate",
    }
    gate_names = (
        "subject_gate",
        "tenant_gate",
        "agent_account_gate",
        "runtime_gate",
        "credential_gate",
        "capability_gate",
        "delegation_gate",
    )
    for case_id, kind in labels.items():
        if kind not in expected_failure_gate:
            continue
        expected = truth[case_id].expected_decision
        assert expected.enterprise_decision is AuthorizationDecision.ALLOW
        assert expected.final_decision is AuthorizationDecision.DENY
        failed = {
            name
            for name in gate_names
            if getattr(expected, name) is AgenticGateOutcome.UNSATISFIED
        }
        assert failed == {expected_failure_gate[kind]}


def test_reference_labels_cover_the_named_smoke_risks(
    reference: ReferenceEnterpriseAgenticV1,
) -> None:
    tags = {
        tag
        for label in reference.evaluator.truth.case_labels
        for tag in label.scenario_tags
    }
    assert {
        "excessive-capability",
        "ownerless-nhi",
        "policy-mismatch",
        "shared-credential",
    } <= tags


def test_audit_evidence_is_independent_of_the_action_decision(
    reference: ReferenceEnterpriseAgenticV1,
) -> None:
    labels = {item.case_id: item.kind for item in reference.evaluator.truth.case_labels}
    evidence_truth = next(
        item
        for item in reference.evaluator.truth.cases
        if labels[item.case_id] is EnterpriseAgenticCaseKind.EVIDENCE_DISCARDED
    )
    assert (
        evidence_truth.expected_decision.enterprise_decision
        is AuthorizationDecision.ALLOW
    )
    assert (
        evidence_truth.expected_decision.final_decision is AuthorizationDecision.ALLOW
    )
    assert not evidence_truth.reconstructable_at_audit
    assert all(
        item.reconstructable_at_audit
        for item in reference.evaluator.truth.cases
        if item.case_id != evidence_truth.case_id
    )


def test_public_input_contains_no_answer_key_fields(
    reference: ReferenceEnterpriseAgenticV1,
) -> None:
    public_bytes = canonical_json_bytes(reference.public)
    evaluator_bytes = canonical_json_bytes(reference.evaluator)
    for forbidden in (
        b'"expected_decision"',
        b'"case_labels"',
        b'"canonical_binding_truth"',
        b'"failure_reasons"',
        b'"reconstructable_at_audit"',
        b'"access_state"',
    ):
        assert forbidden not in public_bytes
    assert b'"expected_decision"' in evaluator_bytes
    assert b'"case_labels"' in evaluator_bytes
    assert b'"canonical_binding_truth"' in evaluator_bytes
    assert b'"opaque_handle"' in public_bytes
    assert b'"secret"' not in public_bytes.lower()
    assert b'"token"' not in public_bytes.lower()


def test_perfect_prediction_and_all_shortcut_baselines_discriminate(
    reference: ReferenceEnterpriseAgenticV1,
) -> None:
    perfect = perfect_enterprise_agentic_prediction(reference.evaluator)
    report = evaluate_enterprise_agentic_prediction(
        public=reference.public,
        evaluator=reference.evaluator,
        prediction=perfect,
    )
    assert report.truth_digest == synthetic_digest(
        canonical_json_bytes(reference.evaluator.truth)
    )
    assert len(report.metrics) == 20
    assert all(item.value == 1.0 for item in report.metrics)
    assert all(item.support == item.denominator for item in report.metrics)
    assert "aggregate" not in {item.family for item in report.metrics}
    metrics_by_name = {item.name: item for item in report.metrics}
    assert metrics_by_name["delegation_gate_accuracy"].denominator == 10
    assert (
        metrics_by_name["agent_as_principal_final_decision_accuracy"].denominator == 10
    )
    assert (
        metrics_by_name[
            "human_subject_agent_context_final_decision_accuracy"
        ].denominator
        == 10
    )

    expected_failures = {
        "Enterprise decision only": "final_decision_accuracy",
        "Union owner authority": "agent_as_principal_final_decision_accuracy",
        "Ignore lifecycle and revocation": "failure_reason_exact_match",
        "Discard retained evidence": "evidence_completeness",
    }
    for name, baseline in ENTERPRISE_AGENTIC_BASELINES:
        baseline_report = evaluate_enterprise_agentic_prediction(
            public=reference.public,
            evaluator=reference.evaluator,
            prediction=baseline(reference.evaluator),
        )
        values = {item.name: item.value for item in baseline_report.metrics}
        assert values[expected_failures[name]] != 1.0


def test_seed_changes_selection_without_remapping_same_overlay_entity() -> None:
    first = reference_enterprise_agentic(seed=20_260_804)
    second = reference_enterprise_agentic(seed=20_260_805)
    assert canonical_json_bytes(first.public) != canonical_json_bytes(second.public)
    assert first.public.benchmark.config_digest != second.public.benchmark.config_digest
    first_accounts = {
        (item.agent_principal_id, item.administrative_state, item.tenant_id): item.id
        for item in first.public.snapshot.accounts
    }
    second_accounts = {
        (item.agent_principal_id, item.administrative_state, item.tenant_id): item.id
        for item in second.public.snapshot.accounts
    }
    assert first_accounts == second_accounts
    assert canonical_json_bytes(first.public.access.universe) == canonical_json_bytes(
        second.public.access.universe
    )
    assert canonical_json_bytes(first.public.access.corpus) == canonical_json_bytes(
        second.public.access.corpus
    )


def test_frozen_asteria_output_is_byte_identical() -> None:
    assert dict(agentic_artifact_checksums(generate_asteria_agentic_v1())) == {
        "public": "9ef217b5d604f42a68b7c97596c550698293f1a44f402dbc3d39a2cef19c4594",
        "evaluator": "3d856f39a5c34ca891ec61298a40ee5bfcb134feae5db7b8a20f6ce9078b2b3f",
    }


@pytest.mark.parametrize(
    "model",
    (
        EnterpriseAgentAccountV1(
            id="account",
            tenant_id="tenant",
            agent_principal_id="agent",
            administrative_state=AgenticAdministrativeState.ACTIVE,
            valid_from_tick=0,
            valid_until_tick=1,
        ),
        EnterpriseAgentCredentialV1(
            id="credential",
            opaque_handle="opaque",
            tenant_id="tenant",
            agent_principal_id="agent",
            agent_account_id="account",
            allowed_runtime_ids=("runtime",),
            valid_from_tick=0,
            valid_until_tick=1,
        ),
        EnterpriseAgentDelegationV1(
            id="delegation",
            tenant_id="tenant",
            human_principal_id="human",
            agent_principal_id="agent",
            agent_account_id="account",
            capability_id="capability",
            valid_from_tick=0,
            valid_until_tick=1,
        ),
    ),
)
def test_overlay_validity_intervals_are_half_open(model: BaseModel) -> None:
    document = model.model_dump(mode="python")
    document["valid_until_tick"] = document["valid_from_tick"]
    with pytest.raises(ValidationError, match="validity_interval_invalid"):
        type(model).model_validate(document)


def test_prediction_and_validation_report_bind_their_own_status(
    reference: ReferenceEnterpriseAgenticV1,
) -> None:
    prediction = perfect_enterprise_agentic_prediction(reference.evaluator)
    wrong_row = prediction.rows[0].model_copy(
        update={"benchmark_digest": synthetic_digest(b"wrong\n")}
    )
    with pytest.raises(ValidationError, match="row_digest_mismatch"):
        EnterpriseAgenticPredictionV1(
            benchmark_digest=prediction.benchmark_digest,
            rows=(wrong_row, *prediction.rows[1:]),
        )
    issue = EnterpriseAgenticTraceValidationIssueV1(
        severity="error", code="bad", message="bad"
    )
    with pytest.raises(ValidationError, match="validity_mismatch"):
        EnterpriseAgenticTraceValidationReportV1(
            valid=True,
            row_count=0,
            expected_case_count=0,
            issues=(issue,),
        )
