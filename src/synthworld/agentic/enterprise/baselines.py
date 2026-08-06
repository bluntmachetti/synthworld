"""Deliberately weak enterprise-agentic baselines for discriminating tests."""

from __future__ import annotations

from collections.abc import Callable

from synthworld.agentic.enterprise.metrics import perfect_enterprise_agentic_prediction
from synthworld.agentic.enterprise.models import (
    AgenticFailureReason,
    AgenticGateOutcome,
    EnterpriseAgenticCaseKind,
    EnterpriseAgenticEvaluatorArtifactsV1,
    EnterpriseAgenticPredictionV1,
    EnterpriseAgenticTraceRowV1,
)
from synthworld.enterprise.rbac.common import AuthorizationDecision


def enterprise_only_agentic_prediction(
    evaluator: EnterpriseAgenticEvaluatorArtifactsV1,
) -> EnterpriseAgenticPredictionV1:
    """Treat enterprise ``F`` as final and ignore every downstream agent gate."""

    perfect = perfect_enterprise_agentic_prediction(evaluator)
    return _replace_rows(
        perfect,
        lambda row: row.model_copy(
            update={
                "gates": row.gates.model_copy(
                    update={
                        name: (
                            AgenticGateOutcome.NOT_APPLICABLE
                            if value is AgenticGateOutcome.NOT_APPLICABLE
                            else AgenticGateOutcome.SATISFIED
                        )
                        for name, value in row.gates
                    }
                ),
                "final_decision": row.enterprise_decision,
                "failure_reasons": (
                    (AgenticFailureReason.ENTERPRISE_DENIED,)
                    if row.enterprise_decision is AuthorizationDecision.DENY
                    else ()
                ),
            }
        ),
    )


def union_owner_authority_prediction(
    evaluator: EnterpriseAgenticEvaluatorArtifactsV1,
) -> EnterpriseAgenticPredictionV1:
    """Incorrectly let a human owner's authority override an agent denial."""

    labels = {item.case_id: item.kind for item in evaluator.truth.case_labels}
    perfect = perfect_enterprise_agentic_prediction(evaluator)
    return _replace_rows(
        perfect,
        lambda row: (
            row.model_copy(
                update={
                    "final_decision": AuthorizationDecision.ALLOW,
                    "failure_reasons": (),
                }
            )
            if labels[row.case_id]
            is EnterpriseAgenticCaseKind.HUMAN_AUTHORITY_NOT_UNIONED
            else row
        ),
    )


def ignore_agent_lifecycle_prediction(
    evaluator: EnterpriseAgenticEvaluatorArtifactsV1,
) -> EnterpriseAgenticPredictionV1:
    """Ignore suspension, credential revocation, and delegation revocation."""

    labels = {item.case_id: item.kind for item in evaluator.truth.case_labels}
    affected = {
        EnterpriseAgenticCaseKind.SUSPENDED_AGENT_ACCOUNT,
        EnterpriseAgenticCaseKind.INVALID_CREDENTIAL_AGENT,
        EnterpriseAgenticCaseKind.REVOKED_DELEGATION,
    }
    perfect = perfect_enterprise_agentic_prediction(evaluator)

    def transform(row: EnterpriseAgenticTraceRowV1) -> EnterpriseAgenticTraceRowV1:
        if labels[row.case_id] not in affected:
            return row
        updates: dict[str, AgenticGateOutcome] = {}
        if labels[row.case_id] is EnterpriseAgenticCaseKind.SUSPENDED_AGENT_ACCOUNT:
            updates["agent_account_gate"] = AgenticGateOutcome.SATISFIED
        elif labels[row.case_id] is EnterpriseAgenticCaseKind.INVALID_CREDENTIAL_AGENT:
            updates["credential_gate"] = AgenticGateOutcome.SATISFIED
        else:
            updates["delegation_gate"] = AgenticGateOutcome.SATISFIED
        return row.model_copy(
            update={
                "gates": row.gates.model_copy(update=updates),
                "final_decision": AuthorizationDecision.ALLOW,
                "failure_reasons": (),
            }
        )

    return _replace_rows(perfect, transform)


def discard_agentic_evidence_prediction(
    evaluator: EnterpriseAgenticEvaluatorArtifactsV1,
) -> EnterpriseAgenticPredictionV1:
    """Get decisions right while retaining no evidence references."""

    perfect = perfect_enterprise_agentic_prediction(evaluator)
    return _replace_rows(
        perfect,
        lambda row: row.model_copy(
            update={
                "evidence_refs": (),
                "reconstructable_at_audit": False,
            }
        ),
    )


ENTERPRISE_AGENTIC_BASELINES: tuple[
    tuple[
        str,
        Callable[
            [EnterpriseAgenticEvaluatorArtifactsV1], EnterpriseAgenticPredictionV1
        ],
    ],
    ...,
] = (
    ("Enterprise decision only", enterprise_only_agentic_prediction),
    ("Union owner authority", union_owner_authority_prediction),
    ("Ignore lifecycle and revocation", ignore_agent_lifecycle_prediction),
    ("Discard retained evidence", discard_agentic_evidence_prediction),
)


def _replace_rows(
    prediction: EnterpriseAgenticPredictionV1,
    transform: Callable[[EnterpriseAgenticTraceRowV1], EnterpriseAgenticTraceRowV1],
) -> EnterpriseAgenticPredictionV1:
    return EnterpriseAgenticPredictionV1(
        benchmark_digest=prediction.benchmark_digest,
        rows=tuple(transform(item) for item in prediction.rows),
    )


__all__ = [
    "ENTERPRISE_AGENTIC_BASELINES",
    "discard_agentic_evidence_prediction",
    "enterprise_only_agentic_prediction",
    "ignore_agent_lifecycle_prediction",
    "union_owner_authority_prediction",
]
