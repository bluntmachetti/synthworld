"""Public-cell keyed composed enterprise authorization scoring."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
from pydantic import ValidationError

from synthworld.enterprise.authorization.metrics import (
    AuthorizationScoredDimension,
    EnterpriseAuthorizationCellPredictionV1,
    EnterpriseAuthorizationEvaluationScopeV1,
    EnterpriseAuthorizationExecutionMetadataV1,
    EnterpriseAuthorizationMechanismPredictionV1,
    EnterpriseAuthorizationMetricsV1,
    EnterpriseAuthorizationPredictionV1,
    EnterpriseAuthorizationScopeCellV1,
    _accuracy,
    evaluate_enterprise_authorization,
    perfect_enterprise_authorization_prediction,
)
from synthworld.enterprise.authorization.reference import (
    reference_enterprise_authorization_inputs,
)
from synthworld.enterprise.authorization_common import MechanismOutcome
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.rbac.common import AuthorizationDecision, BindingStatus


def _execution() -> EnterpriseAuthorizationExecutionMetadataV1:
    return EnterpriseAuthorizationExecutionMetadataV1(
        synthworld_package_version="0.15.0",
        adapter_name="reference-adapter",
        adapter_version="1.0.0",
        system_name="reference-authorizer",
        system_version="1.0.0",
        policy_name="reference-composition",
        policy_version="1.0.0",
        policy_sha256="0" * 64,
    )


def _prediction() -> EnterpriseAuthorizationPredictionV1:
    reference = reference_enterprise_authorization_inputs()
    return perfect_enterprise_authorization_prediction(
        reference.access_state,
        scope=reference.evaluation_scope,
        execution=_execution(),
    )


def _evaluate(
    prediction: EnterpriseAuthorizationPredictionV1,
    *,
    scope: EnterpriseAuthorizationEvaluationScopeV1 | None = None,
) -> EnterpriseAuthorizationMetricsV1:
    reference = reference_enterprise_authorization_inputs()
    return evaluate_enterprise_authorization(
        scope=scope or reference.evaluation_scope,
        truth=reference.access_state,
        predictions=prediction,
    )


def _scope_with_dimension(
    scope: EnterpriseAuthorizationEvaluationScopeV1,
    cell_id: str,
    dimension: AuthorizationScoredDimension,
) -> EnterpriseAuthorizationEvaluationScopeV1:
    return scope.model_copy(
        update={
            "cells": tuple(
                item.model_copy(
                    update={"scored_dimensions": (*item.scored_dimensions, dimension)}
                )
                if item.cell_id == cell_id
                else item
                for item in scope.cells
            )
        }
    )


def _metrics(report: EnterpriseAuthorizationMetricsV1) -> dict[str, float | None]:
    return {f"{item.family}.{item.name}": item.value for item in report.metrics}


def _required_value(values: dict[str, float | None], name: str) -> float:
    value = values[name]
    assert value is not None
    return value


def _replace_cell(
    prediction: EnterpriseAuthorizationPredictionV1,
    cell_id: str,
    transform: Callable[
        [EnterpriseAuthorizationCellPredictionV1],
        EnterpriseAuthorizationCellPredictionV1,
    ],
) -> EnterpriseAuthorizationPredictionV1:
    return prediction.model_copy(
        update={
            "cells": tuple(
                transform(item) if item.cell_id == cell_id else item
                for item in prediction.cells
            )
        }
    )


def _opposite(decision: AuthorizationDecision) -> AuthorizationDecision:
    return (
        AuthorizationDecision.DENY
        if decision is AuthorizationDecision.ALLOW
        else AuthorizationDecision.ALLOW
    )


def _opposite_outcome(outcome: MechanismOutcome) -> MechanismOutcome:
    return (
        MechanismOutcome.DENY
        if outcome is MechanismOutcome.ALLOW
        else MechanismOutcome.ALLOW
    )


def test_perfect_composed_prediction_reports_independent_metrics_and_bindings() -> None:
    truth = reference_enterprise_authorization_inputs().access_state
    prediction = _prediction()
    report = _evaluate(prediction)
    values = _metrics(report)

    assert set(values) == {
        "abac.abac_outcome_accuracy",
        "binding.binding_status_accuracy",
        "composed.effective_decision_accuracy",
        "composed.final_decision_accuracy",
        "conflict.conflict_resolution_accuracy",
        "conflict.policy_conflict_detection_accuracy",
        "lifecycle.lifecycle_status_accuracy",
        "mechanism.mechanism_outcome_exact_match_rate",
        "mechanism.profile_mechanism_inventory_exact_match_rate",
        "rbac.rbac_outcome_accuracy",
        "rebac.rebac_outcome_accuracy",
        "runtime_gate.runtime_gate_decision_accuracy",
    }
    assert all(
        value == 1.0
        for name, value in values.items()
        if name
        not in {
            "binding.binding_status_accuracy",
            "runtime_gate.runtime_gate_decision_accuracy",
        }
    )
    assert values["binding.binding_status_accuracy"] is None
    assert values["runtime_gate.runtime_gate_decision_accuracy"] is None
    metric_by_name = {f"{item.family}.{item.name}": item for item in report.metrics}
    assert metric_by_name["composed.final_decision_accuracy"].denominator == 14
    assert metric_by_name["binding.binding_status_accuracy"].denominator == 0
    assert (
        report.identity_access_universe_digest == truth.identity_access_universe_digest
    )
    assert report.evaluation_corpus_digest == truth.evaluation_corpus_digest
    assert report.composition_digest == truth.composition_digest
    assert report.authorization_kernel_digest == truth.authorization_kernel_digest
    assert report.access_state_digest == synthetic_digest(canonical_json_bytes(truth))
    assert report.prediction_digest == synthetic_digest(
        canonical_json_bytes(prediction)
    )
    assert report.evaluated_system.system_name == "reference-authorizer"
    assert report.evaluation_scope_schema_version == "1.0.0"
    assert report.access_state_schema_version == "1.0.0"
    assert report.prediction_schema_version == "1.0.0"
    assert "aggregate" not in EnterpriseAuthorizationMetricsV1.model_fields
    metric_names = {item.name for item in report.metrics}
    assert not any(
        marker in name
        for name in metric_names
        for marker in ("intended", "path", "predicate", "ssd", "dsd")
    )
    assert canonical_json_bytes(_evaluate(prediction)) == canonical_json_bytes(report)


def test_mechanism_and_composed_failures_remain_independently_visible() -> None:
    prediction = _prediction()
    rbac_cell = next(
        item for item in prediction.cells if item.mechanism_outcomes.rbac is not None
    )
    assert rbac_cell.mechanism_outcomes.rbac is not None
    wrong_rbac = _replace_cell(
        prediction,
        rbac_cell.cell_id,
        lambda item: item.model_copy(
            update={
                "mechanism_outcomes": item.mechanism_outcomes.model_copy(
                    update={
                        "rbac": _opposite_outcome(
                            cast(MechanismOutcome, rbac_cell.mechanism_outcomes.rbac)
                        )
                    }
                )
            }
        ),
    )
    values = _metrics(_evaluate(wrong_rbac))
    assert _required_value(values, "rbac.rbac_outcome_accuracy") < 1.0
    assert _required_value(values, "mechanism.mechanism_outcome_exact_match_rate") < 1.0
    assert values["composed.effective_decision_accuracy"] == 1.0
    assert values["composed.final_decision_accuracy"] == 1.0

    composed_cell = prediction.cells[0]
    assert composed_cell.effective_decision is not None
    wrong_effective = _replace_cell(
        prediction,
        composed_cell.cell_id,
        lambda item: item.model_copy(
            update={
                "effective_decision": _opposite(
                    cast(AuthorizationDecision, composed_cell.effective_decision)
                )
            }
        ),
    )
    effective_values = _metrics(_evaluate(wrong_effective))
    assert (
        _required_value(effective_values, "composed.effective_decision_accuracy") < 1.0
    )
    assert effective_values["composed.final_decision_accuracy"] == 1.0
    assert effective_values["mechanism.mechanism_outcome_exact_match_rate"] == 1.0

    final_cell = next(
        item for item in prediction.cells if item.final_decision is not None
    )
    wrong_final = _replace_cell(
        prediction,
        final_cell.cell_id,
        lambda item: item.model_copy(
            update={
                "final_decision": _opposite(
                    cast(AuthorizationDecision, final_cell.final_decision)
                )
            }
        ),
    )
    final_values = _metrics(_evaluate(wrong_final))
    assert _required_value(final_values, "composed.final_decision_accuracy") < 1.0
    assert final_values["composed.effective_decision_accuracy"] == 1.0


def test_rbac_only_submission_can_pass_rbac_but_fail_composed_authorization() -> None:
    prediction = _prediction()
    composed_deny = next(
        item
        for item in prediction.cells
        if item.mechanism_outcomes.rbac is MechanismOutcome.ALLOW
        and item.effective_decision is AuthorizationDecision.DENY
    )
    rbac_only = _replace_cell(
        prediction,
        composed_deny.cell_id,
        lambda item: item.model_copy(
            update={"effective_decision": AuthorizationDecision.ALLOW}
        ),
    )

    values = _metrics(_evaluate(rbac_only))
    assert values["rbac.rbac_outcome_accuracy"] == 1.0
    assert values["mechanism.mechanism_outcome_exact_match_rate"] == 1.0
    assert _required_value(values, "composed.effective_decision_accuracy") < 1.0


def test_conflict_inventory_binding_and_lifecycle_fail_independently() -> None:
    reference = reference_enterprise_authorization_inputs()
    truth = reference.access_state
    prediction = _prediction()
    conflicts = {item.cell_id: item for item in truth.policy_conflicts}
    conflict_cell = next(
        item for item in prediction.cells if conflicts[item.cell_id].actual_conflict
    )
    assert conflict_cell.policy_conflict is not None
    wrong_conflict = _replace_cell(
        prediction,
        conflict_cell.cell_id,
        lambda item: item.model_copy(
            update={"policy_conflict": not conflict_cell.policy_conflict}
        ),
    )
    conflict_values = _metrics(_evaluate(wrong_conflict))
    assert (
        _required_value(conflict_values, "conflict.policy_conflict_detection_accuracy")
        < 1.0
    )
    assert conflict_values["conflict.conflict_resolution_accuracy"] == 1.0

    rbac_only = next(
        item
        for item in prediction.cells
        if item.mechanism_outcomes.rbac is not None
        and item.mechanism_outcomes.abac is None
        and item.mechanism_outcomes.rebac is None
    )
    extra_mechanism = _replace_cell(
        prediction,
        rbac_only.cell_id,
        lambda item: item.model_copy(
            update={
                "mechanism_outcomes": item.mechanism_outcomes.model_copy(
                    update={"abac": MechanismOutcome.ALLOW}
                )
            }
        ),
    )
    inventory_values = _metrics(_evaluate(extra_mechanism))
    assert (
        _required_value(
            inventory_values,
            "mechanism.profile_mechanism_inventory_exact_match_rate",
        )
        < 1.0
    )
    assert inventory_values["composed.final_decision_accuracy"] == 1.0

    binding_truth_cell = next(
        item
        for item in truth.cells
        if item.binding_status is not BindingStatus.NOT_APPLICABLE
    )
    binding_cell = next(
        item for item in prediction.cells if item.cell_id == binding_truth_cell.cell_id
    )
    binding_scope = _scope_with_dimension(
        reference.evaluation_scope,
        binding_cell.cell_id,
        AuthorizationScoredDimension.BINDING_STATUS,
    )
    wrong_binding = _replace_cell(
        prediction.model_copy(
            update={
                "evaluation_scope_digest": synthetic_digest(
                    canonical_json_bytes(binding_scope)
                )
            }
        ),
        binding_cell.cell_id,
        lambda item: item.model_copy(update={"binding_status": None}),
    )
    binding_values = _metrics(_evaluate(wrong_binding, scope=binding_scope))
    assert _required_value(binding_values, "binding.binding_status_accuracy") < 1.0
    assert binding_values["composed.final_decision_accuracy"] == 1.0

    lifecycle_cell = next(
        item for item in prediction.cells if item.lifecycle_status is not None
    )
    wrong_lifecycle = _replace_cell(
        prediction,
        lifecycle_cell.cell_id,
        lambda item: item.model_copy(update={"lifecycle_status": None}),
    )
    lifecycle_values = _metrics(_evaluate(wrong_lifecycle))
    assert (
        _required_value(lifecycle_values, "lifecycle.lifecycle_status_accuracy") < 1.0
    )
    assert lifecycle_values["composed.final_decision_accuracy"] == 1.0


def test_binding_blind_counterfactual_fails_only_binding_dimension() -> None:
    """Exercise the scorer contract; issue #138 supplies the public case profile."""

    reference = reference_enterprise_authorization_inputs()
    binding_cell = next(
        item
        for item in reference.access_state.cells
        if item.binding_status is BindingStatus.MISMATCH
        and item.actual_mechanism_outcomes.rbac is MechanismOutcome.ALLOW
    )
    allowed_mechanisms = binding_cell.actual_mechanism_outcomes.model_copy(
        update={"abac": MechanismOutcome.ALLOW}
    )
    counterfactual_cell = binding_cell.model_copy(
        update={
            "actual_mechanism_outcomes": allowed_mechanisms,
            "effective_decision": AuthorizationDecision.ALLOW,
            "final_decision": AuthorizationDecision.DENY,
        }
    )
    counterfactual_truth = reference.access_state.model_copy(
        update={
            "cells": tuple(
                counterfactual_cell if item.cell_id == binding_cell.cell_id else item
                for item in reference.access_state.cells
            )
        }
    )
    scope = _scope_with_dimension(
        _scope_with_dimension(
            reference.evaluation_scope,
            binding_cell.cell_id,
            AuthorizationScoredDimension.FINAL_DECISION,
        ),
        binding_cell.cell_id,
        AuthorizationScoredDimension.BINDING_STATUS,
    )
    prediction = perfect_enterprise_authorization_prediction(
        counterfactual_truth,
        scope=scope,
        execution=_execution(),
    )
    binding_blind = _replace_cell(
        prediction,
        binding_cell.cell_id,
        lambda item: item.model_copy(
            update={"binding_status": BindingStatus.MATCHES_CANONICAL}
        ),
    )

    report = evaluate_enterprise_authorization(
        scope=scope,
        truth=counterfactual_truth,
        predictions=binding_blind,
    )
    values = _metrics(report)
    assert counterfactual_cell.effective_decision is AuthorizationDecision.ALLOW
    assert counterfactual_cell.final_decision is AuthorizationDecision.DENY
    assert _required_value(values, "binding.binding_status_accuracy") < 1.0
    assert values["composed.effective_decision_accuracy"] == 1.0
    assert values["composed.final_decision_accuracy"] == 1.0
    assert values["mechanism.mechanism_outcome_exact_match_rate"] == 1.0


@pytest.mark.parametrize(
    ("field", "message"),
    (
        ("identity_access_universe_digest", "prediction_universe_digest"),
        ("evaluation_corpus_digest", "prediction_corpus_digest"),
        ("composition_digest", "prediction_composition_digest"),
        ("authorization_kernel_digest", "prediction_kernel_digest"),
        ("evaluation_scope_digest", "prediction_scope_digest"),
    ),
)
def test_prediction_rejects_cross_artifact_bindings(field: str, message: str) -> None:
    truth = reference_enterprise_authorization_inputs().access_state
    prediction = _prediction().model_copy(
        update={field: synthetic_digest(b"another artifact\n")}
    )
    with pytest.raises(ValueError, match=message):
        evaluate_enterprise_authorization(
            scope=reference_enterprise_authorization_inputs().evaluation_scope,
            truth=truth,
            predictions=prediction,
        )


def test_prediction_requires_exact_unique_public_cell_inventory() -> None:
    prediction = _prediction()
    with pytest.raises(ValueError, match="cell_inventory_mismatch"):
        _evaluate(prediction.model_copy(update={"cells": prediction.cells[:-1]}))
    unknown = prediction.cells[0].model_copy(update={"cell_id": "unknown-cell"})
    with pytest.raises(ValueError, match="cell_inventory_mismatch"):
        _evaluate(
            prediction.model_copy(update={"cells": (unknown, *prediction.cells[1:])})
        )
    with pytest.raises(
        ValidationError, match="duplicate_enterprise_authorization_prediction_cell_id"
    ):
        EnterpriseAuthorizationPredictionV1(
            identity_access_universe_digest=prediction.identity_access_universe_digest,
            evaluation_corpus_digest=prediction.evaluation_corpus_digest,
            composition_digest=prediction.composition_digest,
            authorization_kernel_digest=prediction.authorization_kernel_digest,
            evaluation_scope_digest=prediction.evaluation_scope_digest,
            execution=prediction.execution,
            cells=(prediction.cells[0], prediction.cells[0]),
        )
    with pytest.raises(ValidationError, match="mechanism_prediction_empty"):
        EnterpriseAuthorizationMechanismPredictionV1()


def test_public_evaluation_scope_rejects_stale_ambiguous_or_duplicate_rows() -> None:
    reference = reference_enterprise_authorization_inputs()
    scope = reference.evaluation_scope
    prediction = _prediction()
    assert all(
        AuthorizationScoredDimension.BINDING_STATUS not in item.scored_dimensions
        for item in scope.cells
    )

    with pytest.raises(ValueError, match="scope_corpus_digest_mismatch"):
        evaluate_enterprise_authorization(
            scope=scope.model_copy(
                update={"evaluation_corpus_digest": synthetic_digest(b"stale\n")}
            ),
            truth=reference.access_state,
            predictions=prediction,
        )
    with pytest.raises(ValueError, match="scope_kernel_digest_mismatch"):
        evaluate_enterprise_authorization(
            scope=scope.model_copy(
                update={"authorization_kernel_digest": synthetic_digest(b"stale\n")}
            ),
            truth=reference.access_state,
            predictions=prediction,
        )
    with pytest.raises(ValueError, match="scope_cell_inventory_mismatch"):
        evaluate_enterprise_authorization(
            scope=scope.model_copy(update={"cells": scope.cells[:-1]}),
            truth=reference.access_state,
            predictions=prediction,
        )
    with pytest.raises(
        ValidationError, match="duplicate_authorization_scored_dimension"
    ):
        EnterpriseAuthorizationScopeCellV1(
            cell_id="cell",
            scored_dimensions=(
                AuthorizationScoredDimension.EFFECTIVE_DECISION,
                AuthorizationScoredDimension.EFFECTIVE_DECISION,
            ),
        )
    with pytest.raises(
        ValidationError, match="duplicate_enterprise_authorization_scope_cell_id"
    ):
        EnterpriseAuthorizationEvaluationScopeV1(
            evaluation_corpus_digest=scope.evaluation_corpus_digest,
            authorization_kernel_digest=scope.authorization_kernel_digest,
            cells=(scope.cells[0], scope.cells[0]),
        )


def test_nonempty_metric_guard_fails_closed() -> None:
    with pytest.raises(ValueError, match="requires nonempty selected coverage"):
        _accuracy(
            family="composed",
            name="required_accuracy",
            truth=(),
            predictions={},
            matches=lambda _expected, _observed: True,
            denominator_meaning="required rows",
            nonempty=True,
        )


def test_execution_metadata_and_result_metrics_remain_strict_and_canonical() -> None:
    with pytest.raises(ValidationError, match="policy_sha256"):
        EnterpriseAuthorizationExecutionMetadataV1(
            **{
                **_execution().model_dump(),
                "policy_sha256": "not-a-digest",
            }
        )
    report = _evaluate(_prediction())
    with pytest.raises(
        ValidationError, match="duplicate_composed_enterprise_authorization_metric_name"
    ):
        EnterpriseAuthorizationMetricsV1(
            evaluation_scope_schema_version=report.evaluation_scope_schema_version,
            access_state_schema_version=report.access_state_schema_version,
            prediction_schema_version=report.prediction_schema_version,
            identity_access_universe_digest=report.identity_access_universe_digest,
            evaluation_corpus_digest=report.evaluation_corpus_digest,
            composition_digest=report.composition_digest,
            authorization_kernel_digest=report.authorization_kernel_digest,
            evaluation_scope_digest=report.evaluation_scope_digest,
            access_state_digest=report.access_state_digest,
            prediction_digest=report.prediction_digest,
            evaluated_system=report.evaluated_system,
            metrics=(report.metrics[0], report.metrics[0]),
        )
