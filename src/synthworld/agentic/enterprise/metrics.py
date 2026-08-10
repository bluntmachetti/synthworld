"""Independent denominator-bearing metrics for enterprise-agentic traces."""

from __future__ import annotations

from collections.abc import Callable, Collection
from functools import partial

from synthworld.agentic.enterprise.errors import EnterpriseAgenticEvaluationError
from synthworld.agentic.enterprise.models import (
    AgentAuthorizationMappingKind,
    AgenticGateOutcome,
    AgenticGatePredictionV1,
    EnterpriseAgenticCaseTruthV1,
    EnterpriseAgenticEvaluatorArtifactsV1,
    EnterpriseAgenticMetricsV1,
    EnterpriseAgenticPredictionV1,
    EnterpriseAgenticPublicInputV1,
    EnterpriseAgenticTraceRowV1,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.rbac.common import MetricEmptyBehaviour
from synthworld.enterprise.rbac.metrics import EnterpriseAuthorizationMetricV1


def perfect_enterprise_agentic_prediction(
    evaluator: EnterpriseAgenticEvaluatorArtifactsV1,
) -> EnterpriseAgenticPredictionV1:
    """Return a full-fidelity reference trace for schema and scorer checks."""

    benchmark_digest = evaluator.truth.benchmark_digest
    rows = tuple(
        EnterpriseAgenticTraceRowV1(
            benchmark_digest=benchmark_digest,
            case_id=item.case_id,
            enterprise_decision=item.expected_decision.enterprise_decision,
            gates=AgenticGatePredictionV1(
                subject_gate=item.expected_decision.subject_gate,
                tenant_gate=item.expected_decision.tenant_gate,
                agent_account_gate=item.expected_decision.agent_account_gate,
                runtime_gate=item.expected_decision.runtime_gate,
                credential_gate=item.expected_decision.credential_gate,
                capability_gate=item.expected_decision.capability_gate,
                delegation_gate=item.expected_decision.delegation_gate,
            ),
            final_decision=item.expected_decision.final_decision,
            failure_reasons=item.expected_decision.failure_reasons,
            human_principal_id=item.attribution.human_principal_id,
            agent_principal_id=item.attribution.agent_principal_id,
            agent_account_id=item.attribution.agent_account_id,
            runtime_id=item.attribution.runtime_id,
            evidence_refs=item.required_evidence_refs,
            reconstructable_at_audit=item.reconstructable_at_audit,
        )
        for item in evaluator.truth.cases
    )
    return EnterpriseAgenticPredictionV1(
        benchmark_digest=benchmark_digest,
        rows=rows,
    )


def evaluate_enterprise_agentic_prediction(
    *,
    public: EnterpriseAgenticPublicInputV1,
    evaluator: EnterpriseAgenticEvaluatorArtifactsV1,
    prediction: EnterpriseAgenticPredictionV1,
) -> EnterpriseAgenticMetricsV1:
    """Score enterprise truth, each downstream gate, and evidence independently."""

    expected_digest = evaluator.truth.benchmark_digest
    if prediction.benchmark_digest != expected_digest or any(
        item.benchmark_digest != expected_digest for item in prediction.rows
    ):
        raise EnterpriseAgenticEvaluationError(
            "enterprise agentic prediction benchmark digest differs"
        )
    truth = {item.case_id: item for item in evaluator.truth.cases}
    rows = {item.case_id: item for item in prediction.rows}
    if set(rows) != set(truth):
        raise EnterpriseAgenticEvaluationError(
            "enterprise agentic prediction must cover every case exactly once"
        )
    mapping_by_case = {
        event.payload.attempt.case_id: event.payload.attempt.mapping.mapping_kind
        for event in public.events
        if event.payload.event_type == "action_attempted"
    }
    if set(mapping_by_case) != set(truth):
        raise EnterpriseAgenticEvaluationError(
            "enterprise agentic public case inventory differs from truth"
        )
    case_ids = tuple(sorted(truth))
    metrics = [
        _accuracy(
            family="enterprise_authorization",
            name="enterprise_decision_accuracy",
            case_ids=case_ids,
            check=lambda case_id: (
                rows[case_id].enterprise_decision
                == truth[case_id].expected_decision.enterprise_decision
            ),
            meaning="enterprise-agentic cases with immutable enterprise F truth",
        ),
        _accuracy(
            family="downstream_authorization",
            name="final_decision_accuracy",
            case_ids=case_ids,
            check=lambda case_id: (
                rows[case_id].final_decision
                == truth[case_id].expected_decision.final_decision
            ),
            meaning="enterprise-agentic cases with a downstream expected decision",
        ),
        _accuracy(
            family="downstream_authorization",
            name="failure_reason_exact_match",
            case_ids=case_ids,
            check=lambda case_id: (
                rows[case_id].failure_reasons
                == truth[case_id].expected_decision.failure_reasons
            ),
            meaning="enterprise-agentic cases with ordered failure-reason truth",
        ),
    ]
    gate_fields = (
        "subject_gate",
        "tenant_gate",
        "agent_account_gate",
        "runtime_gate",
        "credential_gate",
        "capability_gate",
        "delegation_gate",
    )
    for field_name in gate_fields:
        applicable = tuple(
            case_id
            for case_id in case_ids
            if getattr(truth[case_id].expected_decision, field_name)
            is not AgenticGateOutcome.NOT_APPLICABLE
        )
        metrics.append(
            _accuracy(
                family="agentic_gate",
                name=f"{field_name}_accuracy",
                case_ids=applicable,
                check=partial(
                    _gate_field_matches,
                    rows=rows,
                    truth=truth,
                    field_name=field_name,
                ),
                meaning=(f"enterprise-agentic cases where {field_name} is applicable"),
            )
        )
    attribution_fields = (
        "human_principal_id",
        "agent_principal_id",
        "agent_account_id",
        "runtime_id",
    )
    for field_name in attribution_fields:
        metrics.append(
            _accuracy(
                family="identity_attribution",
                name=f"{field_name}_accuracy",
                case_ids=case_ids,
                check=partial(
                    _attribution_field_matches,
                    rows=rows,
                    truth=truth,
                    field_name=field_name,
                ),
                meaning=f"enterprise-agentic cases with {field_name} truth",
            )
        )
    metrics.extend(_evidence_metrics(case_ids, rows, truth))
    for mapping_kind in AgentAuthorizationMappingKind:
        profile_cases = tuple(
            case_id for case_id in case_ids if mapping_by_case[case_id] is mapping_kind
        )
        metrics.append(
            _accuracy(
                family="mapping_profile",
                name=f"{mapping_kind.value}_final_decision_accuracy",
                case_ids=profile_cases,
                check=lambda case_id: (
                    rows[case_id].final_decision
                    == truth[case_id].expected_decision.final_decision
                ),
                meaning=f"cases using the {mapping_kind.value} mapping profile",
            )
        )
    return EnterpriseAgenticMetricsV1(
        benchmark_digest=expected_digest,
        truth_digest=synthetic_digest(canonical_json_bytes(evaluator.truth)),
        metrics=tuple(metrics),
    )


def _evidence_metrics(
    case_ids: tuple[str, ...],
    rows: dict[str, EnterpriseAgenticTraceRowV1],
    truth: dict[str, EnterpriseAgenticCaseTruthV1],
) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
    completeness = _accuracy(
        family="observability",
        name="evidence_completeness",
        case_ids=case_ids,
        check=lambda case_id: (
            set(truth[case_id].required_evidence_refs)
            <= set(rows[case_id].evidence_refs)
        ),
        meaning=(
            "enterprise-agentic cases; compares reported evidence-reference labels "
            "to evaluator requirements, without checking underlying evidence retention"
        ),
    )
    exact = _accuracy(
        family="observability",
        name="evidence_exact_match",
        case_ids=case_ids,
        check=lambda case_id: (
            set(rows[case_id].evidence_refs)
            == set(truth[case_id].required_evidence_refs)
        ),
        meaning=(
            "enterprise-agentic cases; compares reported evidence-reference labels "
            "to evaluator requirements, without checking underlying evidence retention"
        ),
    )
    reconstructability = _accuracy(
        family="observability",
        name="audit_reconstructability_accuracy",
        case_ids=case_ids,
        check=lambda case_id: (
            rows[case_id].reconstructable_at_audit
            == truth[case_id].reconstructable_at_audit
        ),
        meaning=(
            "enterprise-agentic cases; compares the reported reconstructability "
            "claim to evaluator truth, without reconstructing or inspecting retained "
            "evidence"
        ),
    )
    submitted = sum(len(set(rows[case_id].evidence_refs)) for case_id in case_ids)
    correct: int = sum(
        len(
            set(rows[case_id].evidence_refs)
            & set(truth[case_id].required_evidence_refs)
        )
        for case_id in case_ids
    )
    precision = _ratio(
        family="observability",
        name="evidence_precision",
        numerator=correct,
        denominator=submitted,
        meaning=(
            "distinct reported evidence references across all cases; compares labels "
            "to evaluator requirements, without checking underlying evidence retention"
        ),
    )
    return completeness, exact, reconstructability, precision


def _gate_field_matches(
    case_id: str,
    *,
    rows: dict[str, EnterpriseAgenticTraceRowV1],
    truth: dict[str, EnterpriseAgenticCaseTruthV1],
    field_name: str,
) -> bool:
    return bool(
        getattr(rows[case_id].gates, field_name)
        == getattr(truth[case_id].expected_decision, field_name)
    )


def _attribution_field_matches(
    case_id: str,
    *,
    rows: dict[str, EnterpriseAgenticTraceRowV1],
    truth: dict[str, EnterpriseAgenticCaseTruthV1],
    field_name: str,
) -> bool:
    return bool(
        getattr(rows[case_id], field_name)
        == getattr(truth[case_id].attribution, field_name)
    )


def _accuracy(
    *,
    family: str,
    name: str,
    case_ids: Collection[str],
    check: Callable[[str], bool],
    meaning: str,
) -> EnterpriseAuthorizationMetricV1:
    return _ratio(
        family=family,
        name=name,
        numerator=sum(check(case_id) for case_id in case_ids),
        denominator=len(case_ids),
        meaning=meaning,
    )


def _ratio(
    *,
    family: str,
    name: str,
    numerator: int,
    denominator: int,
    meaning: str,
) -> EnterpriseAuthorizationMetricV1:
    return EnterpriseAuthorizationMetricV1(
        family=family,
        name=name,
        numerator=numerator,
        denominator=denominator,
        support=denominator,
        denominator_meaning=meaning,
        empty_behaviour=MetricEmptyBehaviour.NULL_IF_EMPTY,
        value=numerator / denominator if denominator else None,
    )


__all__ = [
    "evaluate_enterprise_agentic_prediction",
    "perfect_enterprise_agentic_prediction",
]
