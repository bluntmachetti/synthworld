"""End-to-end tests for the bounded enterprise identity-fabric smoke pack."""

from __future__ import annotations

from collections import Counter

import pytest
from pydantic import ValidationError

from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.identity_fabric.baselines import (
    all_non_birthright_is_sprawl_baseline,
    direct_only_membership_baseline,
    latest_state_only_baseline,
    no_hierarchy_or_nesting_role_baseline,
    trust_recorded_state_baseline,
)
from synthworld.enterprise.identity_fabric.metrics import (
    evaluate_enterprise_identity_fabric,
    perfect_enterprise_identity_fabric_prediction,
)
from synthworld.enterprise.identity_fabric.models import (
    EnterpriseIdentityFabricBenchmarkV1,
    EnterpriseIdentityFabricMetricsV1,
    EnterpriseIdentityFabricPredictionV1,
    EnterpriseIdentityFabricProjectionLimitsV1,
    IdentityFabricAccumulationPredictionV1,
    IdentityFabricCheckpointPredictionV1,
    IdentityFabricMembershipPredictionV1,
)
from synthworld.enterprise.identity_fabric.projection import (
    compile_enterprise_identity_fabric_truth,
    project_enterprise_identity_fabric_public,
)
from synthworld.enterprise.identity_fabric.reference import (
    REFERENCE_ACCUMULATION_CELL_ID,
    REFERENCE_APPROVED_EXCEPTION_CELL_ID,
    REFERENCE_CORPUS_SHA256,
    REFERENCE_IDENTITY_FABRIC_ACCUMULATED_CHECKPOINT,
    REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT,
    REFERENCE_UNIVERSE_SHA256,
    ReferenceEnterpriseIdentityFabricV1,
    reference_enterprise_identity_fabric,
)
from synthworld.enterprise.rbac.common import AuthorizationDecision
from synthworld.enterprise.rbac.metrics import EnterpriseAuthorizationMetricV1


@pytest.fixture(scope="module")
def reference() -> ReferenceEnterpriseIdentityFabricV1:
    return reference_enterprise_identity_fabric()


def _checkpoint_metrics(
    report: EnterpriseIdentityFabricMetricsV1, checkpoint_id: str
) -> dict[str, EnterpriseAuthorizationMetricV1]:
    checkpoint = next(
        item for item in report.checkpoints if item.checkpoint_id == checkpoint_id
    )
    return {item.name: item for item in checkpoint.identity_fabric_metrics}


def test_reference_is_deterministic_cell_preserving_and_discriminating(
    reference: ReferenceEnterpriseIdentityFabricV1,
) -> None:
    repeated = reference_enterprise_identity_fabric()
    assert canonical_json_bytes(repeated.public) == canonical_json_bytes(
        reference.public
    )
    assert canonical_json_bytes(repeated.evaluator) == canonical_json_bytes(
        reference.evaluator
    )
    benchmark = reference.public.benchmark
    assert benchmark.identity_access_universe_digest.value == REFERENCE_UNIVERSE_SHA256
    assert benchmark.evaluation_corpus_digest.value == REFERENCE_CORPUS_SHA256
    assert canonical_json_bytes(
        reference.public.invariant.universe
    ) == canonical_json_bytes(
        reference.authorization.rbac.universe_result.public_universe
    )
    assert canonical_json_bytes(
        reference.public.invariant.corpus
    ) == canonical_json_bytes(reference.authorization.rbac.corpus_result.public_corpus)
    assert len(reference.public.invariant.universe.access_atoms) == 16
    assert len(reference.public.invariant.corpus.evaluation_cells) == 19
    assert (
        len(benchmark.membership_queries),
        len(benchmark.role_queries),
        len(benchmark.account_queries),
        len(benchmark.access_queries),
        len(benchmark.accumulation_queries),
    ) == (40, 40, 24, 38, 10)
    all_query_ids = {
        item.query_id
        for rows in (
            benchmark.membership_queries,
            benchmark.role_queries,
            benchmark.account_queries,
            benchmark.access_queries,
            benchmark.accumulation_queries,
        )
        for item in rows
    }
    assert len(all_query_ids) == 152

    baseline, accumulated = reference.evaluator.truth.checkpoints
    assert (baseline.checkpoint_id, accumulated.checkpoint_id) == (
        REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT,
        REFERENCE_IDENTITY_FABRIC_ACCUMULATED_CHECKPOINT,
    )
    assert Counter(
        (item.direct_member, item.effective_member) for item in baseline.membership
    ) == Counter({(False, False): 12, (True, True): 4, (False, True): 4})
    role_shapes = {
        (
            item.direct_role_assignment,
            item.group_derived_role,
            item.hierarchy_inherited_role,
            item.effective_role,
        )
        for item in baseline.roles
    }
    assert {
        (True, False, False, True),
        (False, True, False, True),
        (False, False, True, True),
        (False, False, False, False),
    } <= role_shapes
    assert {item.binding_status.value for item in baseline.accounts} == {
        "matches_canonical",
        "mismatch",
        "missing",
    }
    assert {item.lifecycle_status.value for item in baseline.accounts} == {
        "active",
        "inactive",
        "expired",
    }
    assert any(item.direct_entitlement for item in baseline.access)
    assert any(item.role_entitlement for item in baseline.access)
    assert any(item.redundant_derivation for item in baseline.access)
    assert any(item.policy_conflict for item in baseline.access)
    assert any(item.birthright_access for item in baseline.access)
    assert any(item.approved_exception for item in baseline.access)
    native = reference.evaluator.checkpoints[0]
    assert {item.violated for item in native.directory_rbac_truth.ssd_evaluations} == {
        False,
        True,
    }
    assert {
        (item.request_violated, item.observed_session_violated)
        for item in native.directory_rbac_truth.dsd_evaluations
    } == {(False, False), (True, True)}
    assert any(item.actual_path_ids for item in native.rebac_truth.cells)
    assert any(item.actual_rule_truth_ids for item in native.abac_truth.cells)

    access_query = {item.query_id: item for item in benchmark.access_queries}
    baseline_by_cell = {
        access_query[item.query_id].cell_id: item for item in baseline.access
    }
    accumulated_by_cell = {
        access_query[item.query_id].cell_id: item for item in accumulated.access
    }
    exception = baseline_by_cell[REFERENCE_APPROVED_EXCEPTION_CELL_ID]
    assert exception.approved_exception
    assert exception.outside_birthright
    assert not exception.outside_intent
    assert exception.intended_decision is AuthorizationDecision.ALLOW
    assert exception.effective_decision is AuthorizationDecision.ALLOW
    assert not baseline_by_cell[REFERENCE_ACCUMULATION_CELL_ID].outside_intent
    assert accumulated_by_cell[REFERENCE_ACCUMULATION_CELL_ID].outside_intent
    positives = tuple(
        item
        for item in reference.evaluator.truth.accumulation
        if item.accumulated_cell_ids
    )
    assert len(positives) == 1
    assert positives[0].accumulated_cell_ids == (REFERENCE_ACCUMULATION_CELL_ID,)


def test_public_projection_contains_no_evaluator_answers(
    reference: ReferenceEnterpriseIdentityFabricV1,
) -> None:
    public_bytes = canonical_json_bytes(reference.public)
    evaluator_bytes = canonical_json_bytes(reference.evaluator)
    for forbidden in (
        b'"case_labels"',
        b'"canonical_binding_truth"',
        b'"membership_path_ids"',
        b'"authorized_role_path_ids"',
        b'"outside_intent"',
        b'"redundant_derivation"',
        b'"expected_verdict"',
    ):
        assert forbidden not in public_bytes
    assert b'"case_labels"' in evaluator_bytes
    assert b'"canonical_binding_truth"' in evaluator_bytes
    assert b'"outside_intent"' in evaluator_bytes


def test_perfect_prediction_scores_every_independent_family(
    reference: ReferenceEnterpriseIdentityFabricV1,
) -> None:
    prediction = perfect_enterprise_identity_fabric_prediction(reference.evaluator)
    report = evaluate_enterprise_identity_fabric(
        artifacts=reference.evaluator, predictions=prediction
    )
    assert report.benchmark_digest == reference.evaluator.truth.benchmark_digest
    assert report.truth_digest == synthetic_digest(
        canonical_json_bytes(reference.evaluator.truth)
    )
    for checkpoint in report.checkpoints:
        assert all(
            item.value in {1.0, None} for item in checkpoint.identity_fabric_metrics
        )
        assert all(
            item.support == item.denominator
            for item in checkpoint.identity_fabric_metrics
        )
        assert "aggregate" not in {
            item.family for item in checkpoint.identity_fabric_metrics
        }
        rbac_metrics = {item.name: item for item in checkpoint.directory_rbac.metrics}
        for name in (
            "birthright_decision_accuracy",
            "intended_decision_accuracy",
            "effective_decision_accuracy",
            "rbac_decision_accuracy",
            "rbac_derivation_path_exact_match_rate",
            "authorized_role_exact_match_rate",
            "activation_decision_accuracy",
            "activated_role_exact_match_rate",
            "ssd_violation_detection_rate",
            "dsd_constraint_outcome_accuracy",
            "birthright_assignment_exact_match_rate",
            "unauthorized_activation_detection_rate",
        ):
            assert rbac_metrics[name].value == 1.0
        assert all(
            item.value == 1.0 for item in checkpoint.abac.metrics if item.denominator
        )
        assert all(
            item.value == 1.0 for item in checkpoint.rebac.metrics if item.denominator
        )
    cross = {item.name: item for item in report.cross_checkpoint_metrics}
    assert cross["privilege_accumulation_exact_match_rate"].value == 1.0
    assert cross["privilege_accumulation_detection_recall"].value == 1.0
    assert cross["privilege_accumulation_detection_precision"].value == 1.0


def test_missing_and_false_positive_predictions_have_explicit_denominators(
    reference: ReferenceEnterpriseIdentityFabricV1,
) -> None:
    empty = EnterpriseIdentityFabricPredictionV1(
        benchmark_digest=reference.evaluator.truth.benchmark_digest
    )
    report = evaluate_enterprise_identity_fabric(
        artifacts=reference.evaluator, predictions=empty
    )
    baseline_metrics = _checkpoint_metrics(
        report, REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT
    )
    assert baseline_metrics["direct_membership_accuracy"].value == 0.0
    assert baseline_metrics["effective_access_accuracy"].value == 0.0
    cross = {item.name: item for item in report.cross_checkpoint_metrics}
    assert cross["privilege_accumulation_detection_recall"].value == 0.0
    assert cross["privilege_accumulation_detection_precision"].value is None

    positive_query = next(
        item
        for item in reference.evaluator.truth.accumulation
        if item.accumulated_cell_ids
    )
    wrong_cell = next(
        item.cell_id
        for item in (
            reference.authorization.rbac.corpus_result.public_corpus.evaluation_cells
        )
        if item.cell_id != REFERENCE_ACCUMULATION_CELL_ID
    )
    false_positive = empty.model_copy(
        update={
            "accumulation": (
                IdentityFabricAccumulationPredictionV1(
                    query_id=positive_query.query_id,
                    accumulated_cell_ids=(wrong_cell,),
                ),
            )
        }
    )
    false_report = evaluate_enterprise_identity_fabric(
        artifacts=reference.evaluator, predictions=false_positive
    )
    false_cross = {item.name: item for item in false_report.cross_checkpoint_metrics}
    assert false_cross["privilege_accumulation_detection_recall"].value == 0.0
    assert false_cross["privilege_accumulation_detection_precision"].value == 0.0


def test_metrics_reject_mismatched_or_unknown_prediction_coordinates(
    reference: ReferenceEnterpriseIdentityFabricV1,
) -> None:
    digest = reference.evaluator.truth.benchmark_digest
    with pytest.raises(ValueError, match="benchmark_digest_mismatch"):
        evaluate_enterprise_identity_fabric(
            artifacts=reference.evaluator,
            predictions=EnterpriseIdentityFabricPredictionV1(
                benchmark_digest=synthetic_digest(b"wrong benchmark\n")
            ),
        )
    with pytest.raises(ValueError, match=r"unknown.*checkpoint"):
        evaluate_enterprise_identity_fabric(
            artifacts=reference.evaluator,
            predictions=EnterpriseIdentityFabricPredictionV1(
                benchmark_digest=digest,
                checkpoints=(
                    IdentityFabricCheckpointPredictionV1(
                        checkpoint_id="unknown-checkpoint"
                    ),
                ),
            ),
        )
    with pytest.raises(ValueError, match=r"unknown.*query"):
        evaluate_enterprise_identity_fabric(
            artifacts=reference.evaluator,
            predictions=EnterpriseIdentityFabricPredictionV1(
                benchmark_digest=digest,
                checkpoints=(
                    IdentityFabricCheckpointPredictionV1(
                        checkpoint_id=REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT,
                        membership=(
                            IdentityFabricMembershipPredictionV1(
                                query_id="unknown-query",
                                direct_member=False,
                                effective_member=False,
                            ),
                        ),
                    ),
                ),
            ),
        )
    with pytest.raises(ValueError, match=r"unknown.*accumulation"):
        evaluate_enterprise_identity_fabric(
            artifacts=reference.evaluator,
            predictions=EnterpriseIdentityFabricPredictionV1(
                benchmark_digest=digest,
                accumulation=(
                    IdentityFabricAccumulationPredictionV1(query_id="unknown-query"),
                ),
            ),
        )
    known_query = reference.evaluator.truth.accumulation[0].query_id
    with pytest.raises(ValueError, match=r"unknown.*accumulation"):
        evaluate_enterprise_identity_fabric(
            artifacts=reference.evaluator,
            predictions=EnterpriseIdentityFabricPredictionV1(
                benchmark_digest=digest,
                accumulation=(
                    IdentityFabricAccumulationPredictionV1(
                        query_id=known_query,
                        accumulated_cell_ids=("unknown-cell",),
                    ),
                ),
            ),
        )


def test_baselines_are_discriminating_on_their_named_dimensions(
    reference: ReferenceEnterpriseIdentityFabricV1,
) -> None:
    direct_report = evaluate_enterprise_identity_fabric(
        artifacts=reference.evaluator,
        predictions=direct_only_membership_baseline(reference.public),
    )
    direct_metrics = _checkpoint_metrics(
        direct_report, REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT
    )
    assert direct_metrics["direct_membership_accuracy"].value == 1.0
    assert direct_metrics["effective_membership_accuracy"].value is not None
    assert direct_metrics["effective_membership_accuracy"].value < 1.0
    assert direct_metrics["nested_membership_detection_recall"].value == 0.0

    role_report = evaluate_enterprise_identity_fabric(
        artifacts=reference.evaluator,
        predictions=no_hierarchy_or_nesting_role_baseline(reference.public),
    )
    role_metrics = _checkpoint_metrics(
        role_report, REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT
    )
    assert role_metrics["direct_role_assignment_accuracy"].value == 1.0
    assert role_metrics["hierarchy_inherited_role_accuracy"].value is not None
    assert role_metrics["hierarchy_inherited_role_accuracy"].value < 1.0
    assert role_metrics["effective_role_accuracy"].value is not None
    assert role_metrics["effective_role_accuracy"].value < 1.0

    trust_report = evaluate_enterprise_identity_fabric(
        artifacts=reference.evaluator,
        predictions=trust_recorded_state_baseline(reference.public),
    )
    trust_metrics = _checkpoint_metrics(
        trust_report, REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT
    )
    assert trust_metrics["account_lifecycle_status_accuracy"].value == 1.0
    assert trust_metrics["canonical_account_owner_accuracy"].value is not None
    assert trust_metrics["canonical_account_owner_accuracy"].value < 1.0
    assert trust_metrics["account_binding_status_accuracy"].value is not None
    assert trust_metrics["account_binding_status_accuracy"].value < 1.0

    perfect = perfect_enterprise_identity_fabric_prediction(reference.evaluator)
    latest_report = evaluate_enterprise_identity_fabric(
        artifacts=reference.evaluator,
        predictions=latest_state_only_baseline(public=reference.public, source=perfect),
    )
    latest_metrics = _checkpoint_metrics(
        latest_report, REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT
    )
    assert latest_metrics["outside_intent_accuracy"].value is not None
    assert latest_metrics["outside_intent_accuracy"].value < 1.0
    latest_cross = {item.name: item for item in latest_report.cross_checkpoint_metrics}
    assert latest_cross["privilege_accumulation_detection_recall"].value == 0.0

    shortcut_report = evaluate_enterprise_identity_fabric(
        artifacts=reference.evaluator,
        predictions=all_non_birthright_is_sprawl_baseline(perfect),
    )
    shortcut_metrics = _checkpoint_metrics(
        shortcut_report, REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT
    )
    assert shortcut_metrics["outside_birthright_accuracy"].value == 1.0
    assert shortcut_metrics["outside_intent_accuracy"].value is not None
    assert shortcut_metrics["outside_intent_accuracy"].value < 1.0


def test_latest_state_baseline_rejects_bad_source_bindings(
    reference: ReferenceEnterpriseIdentityFabricV1,
) -> None:
    perfect = perfect_enterprise_identity_fabric_prediction(reference.evaluator)
    with pytest.raises(ValueError, match="benchmark_digest_mismatch"):
        latest_state_only_baseline(
            public=reference.public,
            source=perfect.model_copy(
                update={"benchmark_digest": synthetic_digest(b"wrong\n")}
            ),
        )
    latest = next(
        item
        for item in perfect.checkpoints
        if item.checkpoint_id == REFERENCE_IDENTITY_FABRIC_ACCUMULATED_CHECKPOINT
    )
    without_latest = perfect.model_copy(
        update={
            "checkpoints": tuple(
                item
                for item in perfect.checkpoints
                if item.checkpoint_id != latest.checkpoint_id
            )
        }
    )
    with pytest.raises(ValueError, match="latest_checkpoint_missing"):
        latest_state_only_baseline(public=reference.public, source=without_latest)

    for field_name in ("membership", "roles", "accounts", "access"):
        changed_latest = latest.model_copy(
            update={field_name: getattr(latest, field_name)[1:]}
        )
        changed = perfect.model_copy(
            update={
                "checkpoints": tuple(
                    changed_latest
                    if item.checkpoint_id == latest.checkpoint_id
                    else item
                    for item in perfect.checkpoints
                )
            }
        )
        with pytest.raises(ValueError, match=f"{field_name.rstrip('s')}.*inventory"):
            latest_state_only_baseline(public=reference.public, source=changed)


@pytest.mark.parametrize(
    ("field_name", "allowed", "code"),
    (
        ("max_checkpoints", 1, "checkpoint_budget"),
        ("max_membership_queries", 39, "membership_query_budget"),
        ("max_role_queries", 39, "role_query_budget"),
        ("max_account_queries", 23, "account_query_budget"),
        ("max_access_queries", 37, "access_query_budget"),
        ("max_accumulation_queries", 9, "accumulation_query_budget"),
        ("max_total_queries", 151, "total_query_budget"),
    ),
)
def test_projection_enforces_independent_query_budgets(
    reference: ReferenceEnterpriseIdentityFabricV1,
    field_name: str,
    allowed: int,
    code: str,
) -> None:
    limits = EnterpriseIdentityFabricProjectionLimitsV1().model_copy(
        update={field_name: allowed}
    )
    with pytest.raises(ValueError, match=code):
        project_enterprise_identity_fabric_public(
            invariant=reference.public.invariant,
            checkpoints=reference.public.checkpoints,
            limits=limits,
        )


def test_projection_rejects_checkpoint_and_public_binding_errors(
    reference: ReferenceEnterpriseIdentityFabricV1,
) -> None:
    invariant = reference.public.invariant
    checkpoints = reference.public.checkpoints
    with pytest.raises(ValueError, match="minimum_not_met"):
        project_enterprise_identity_fabric_public(
            invariant=invariant, checkpoints=checkpoints[:1]
        )
    with pytest.raises(ValueError, match="sequence_not_contiguous"):
        project_enterprise_identity_fabric_public(
            invariant=invariant, checkpoints=tuple(reversed(checkpoints))
        )
    duplicate = checkpoints[1].model_copy(
        update={"checkpoint_id": checkpoints[0].checkpoint_id}
    )
    with pytest.raises(ValueError, match=r"duplicate.*checkpoint"):
        project_enterprise_identity_fabric_public(
            invariant=invariant, checkpoints=(checkpoints[0], duplicate)
        )

    wrong = synthetic_digest(b"wrong artifact\n")
    changed_corpus = invariant.corpus.model_copy(
        update={"identity_access_universe_digest": wrong}
    )
    with pytest.raises(ValueError, match="corpus_universe"):
        project_enterprise_identity_fabric_public(
            invariant=invariant.model_copy(update={"corpus": changed_corpus}),
            checkpoints=checkpoints,
        )
    changed_profile = invariant.evaluation_profile.model_copy(
        update={"cells": invariant.evaluation_profile.cells[1:]}
    )
    with pytest.raises(ValueError, match="profile_cell_inventory"):
        project_enterprise_identity_fabric_public(
            invariant=invariant.model_copy(
                update={"evaluation_profile": changed_profile}
            ),
            checkpoints=checkpoints,
        )
    changed_kernel = checkpoints[0].directory_rbac_kernel.model_copy(
        update={"identity_access_universe_digest": wrong}
    )
    with pytest.raises(ValueError, match="checkpoint_kernel_universe"):
        project_enterprise_identity_fabric_public(
            invariant=invariant,
            checkpoints=(
                checkpoints[0].model_copy(
                    update={"directory_rbac_kernel": changed_kernel}
                ),
                checkpoints[1],
            ),
        )
    changed_authorization_kernel = checkpoints[0].authorization_kernel.model_copy(
        update={"composition_digest": wrong}
    )
    with pytest.raises(ValueError, match="authorization_kernel_composition"):
        project_enterprise_identity_fabric_public(
            invariant=invariant,
            checkpoints=(
                checkpoints[0].model_copy(
                    update={"authorization_kernel": changed_authorization_kernel}
                ),
                checkpoints[1],
            ),
        )


def test_truth_compiler_rejects_binding_inventory_and_component_mismatches(
    reference: ReferenceEnterpriseIdentityFabricV1,
) -> None:
    public = reference.public
    binding = reference.evaluator.canonical_binding_truth
    checkpoints = reference.evaluator.checkpoints
    with pytest.raises(ValueError, match="binding_universe"):
        compile_enterprise_identity_fabric_truth(
            public=public,
            canonical_binding_truth=binding.model_copy(
                update={"identity_access_universe_digest": synthetic_digest(b"wrong\n")}
            ),
            checkpoints=checkpoints,
        )
    with pytest.raises(ValueError, match="checkpoint_inventory"):
        compile_enterprise_identity_fabric_truth(
            public=public,
            canonical_binding_truth=binding,
            checkpoints=checkpoints[:1],
        )
    wrong_truth = checkpoints[0].directory_rbac_truth.model_copy(
        update={"identity_access_universe_digest": synthetic_digest(b"wrong\n")}
    )
    with pytest.raises(ValueError, match="evaluator_directory_universe"):
        compile_enterprise_identity_fabric_truth(
            public=public,
            canonical_binding_truth=binding,
            checkpoints=(
                checkpoints[0].model_copy(update={"directory_rbac_truth": wrong_truth}),
                checkpoints[1],
            ),
        )


@pytest.mark.parametrize(
    "field_name",
    (
        "membership_queries",
        "role_queries",
        "account_queries",
        "access_queries",
        "accumulation_queries",
    ),
)
def test_truth_compiler_rejects_noncanonical_public_query_inventory(
    reference: ReferenceEnterpriseIdentityFabricV1,
    field_name: str,
) -> None:
    rows = getattr(reference.public.benchmark, field_name)
    changed_rows = (
        rows[0].model_copy(update={"query_id": "noncanonical-query-id"}),
        *rows[1:],
    )
    changed_benchmark = reference.public.benchmark.model_copy(
        update={field_name: changed_rows}
    )
    changed_public = reference.public.model_copy(
        update={"benchmark": changed_benchmark}
    )
    with pytest.raises(ValueError, match="public_query_inventory_mismatch"):
        compile_enterprise_identity_fabric_truth(
            public=changed_public,
            canonical_binding_truth=reference.evaluator.canonical_binding_truth,
            checkpoints=reference.evaluator.checkpoints,
        )


def test_models_canonicalize_and_reject_duplicate_prediction_ids(
    reference: ReferenceEnterpriseIdentityFabricV1,
) -> None:
    document = reference.public.benchmark.model_dump(mode="python")
    document["membership_queries"] = tuple(
        reversed(reference.public.benchmark.membership_queries)
    )
    reparsed = EnterpriseIdentityFabricBenchmarkV1.model_validate(document)
    assert reparsed == reference.public.benchmark
    prediction = perfect_enterprise_identity_fabric_prediction(reference.evaluator)
    checkpoint = prediction.checkpoints[0]
    with pytest.raises(ValidationError, match=r"duplicate.*prediction"):
        IdentityFabricCheckpointPredictionV1(
            checkpoint_id=checkpoint.checkpoint_id,
            membership=(checkpoint.membership[0], checkpoint.membership[0]),
        )
