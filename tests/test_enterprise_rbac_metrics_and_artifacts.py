"""Directory/RBAC metric and physical artifact boundary tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import EnterpriseArtifactManifestV1
from synthworld.enterprise.rbac.common import MetricEmptyBehaviour
from synthworld.enterprise.rbac.compiler import compile_enterprise_directory_rbac_truth
from synthworld.enterprise.rbac.metrics import (
    DirectoryRbacCellPredictionV1,
    EnterpriseAuthorizationMetricV1,
    EnterpriseDirectoryRbacPredictionV1,
    evaluate_enterprise_directory_rbac,
    perfect_enterprise_directory_rbac_prediction,
)
from synthworld.enterprise.rbac.models import CompiledEnterpriseDirectoryRbacTruthV1
from synthworld.enterprise.rbac.reference import (
    ReferenceEnterpriseRbacInputsV1,
    reference_enterprise_evaluation_corpus_config,
    reference_enterprise_rbac_inputs,
)
from synthworld.enterprise.rbac.serialization import (
    EnterpriseRbacArtifactError,
    export_enterprise_directory_rbac,
    export_enterprise_evaluation_corpus,
    load_evaluator_enterprise_case_inventory,
    load_evaluator_enterprise_directory_rbac_truth,
    load_public_enterprise_directory_rbac_kernel,
    load_public_enterprise_evaluation_corpus,
)

CONTRACT_ROOT = Path("enterprise-identity-access-contract")


def _compiled() -> tuple[
    ReferenceEnterpriseRbacInputsV1, CompiledEnterpriseDirectoryRbacTruthV1
]:
    reference = reference_enterprise_rbac_inputs()
    truth = compile_enterprise_directory_rbac_truth(
        universe=reference.universe_result.public_universe,
        canonical_binding_truth=reference.universe_result.evaluator_canonical_binding_truth,
        corpus=reference.corpus_result.public_corpus,
        directory_rbac_kernel=reference.kernel,
        session_state=reference.session_state,
        directory_rbac_intent=reference.intent,
    )
    return reference, truth


def _rewrite_artifact(
    root: Path,
    *,
    visibility: str,
    name: str,
    model: BaseModel,
) -> None:
    payload = canonical_json_bytes(model)
    (root / visibility / name).write_bytes(payload)
    manifest_path = root / visibility / "manifest.json"
    manifest = EnterpriseArtifactManifestV1.model_validate_json(
        manifest_path.read_bytes()
    )
    descriptor = manifest.artifacts[0].model_copy(
        update={
            "schema_version": str(model.model_dump()["schema_version"]),
            "digest": synthetic_digest(payload),
            "byte_size": len(payload),
        }
    )
    manifest_path.write_bytes(
        canonical_json_bytes(manifest.model_copy(update={"artifacts": (descriptor,)}))
    )


def test_perfect_predictions_score_each_family_without_an_aggregate() -> None:
    _reference, truth = _compiled()
    prediction = perfect_enterprise_directory_rbac_prediction(truth)
    report = evaluate_enterprise_directory_rbac(truth=truth, predictions=prediction)
    metrics = {item.name: item for item in report.metrics}
    accuracy_names = {
        "birthright_decision_accuracy",
        "intended_decision_accuracy",
        "effective_decision_accuracy",
        "rbac_decision_accuracy",
        "rbac_derivation_path_exact_match_rate",
        "authorized_role_exact_match_rate",
        "activated_role_exact_match_rate",
        "activation_decision_accuracy",
        "dsd_constraint_outcome_accuracy",
        "birthright_assignment_exact_match_rate",
        "ssd_violation_detection_rate",
        "unauthorized_activation_detection_rate",
    }
    assert all(metrics[name].value == 1.0 for name in accuracy_names)
    assert metrics["ssd_violation_false_positive_rate"].value == 0.0
    assert metrics["unauthorized_activation_false_positive_rate"].value == 0.0
    assert metrics["effective_outside_intent_rate"].numerator == 3
    assert metrics["missing_intended_access_rate"].numerator == 1
    assert metrics["redundant_derivation_cell_rate"].numerator > 0
    assert "aggregate" not in {item.family for item in report.metrics}
    assert all(item.support == item.denominator for item in report.metrics)
    assert all(item.denominator_meaning for item in report.metrics)


def test_missing_predictions_score_zero_and_unknown_rows_fail() -> None:
    _reference, truth = _compiled()
    empty = evaluate_enterprise_directory_rbac(
        truth=truth,
        predictions=EnterpriseDirectoryRbacPredictionV1(),
    )
    metrics = {item.name: item for item in empty.metrics}
    assert metrics["rbac_decision_accuracy"].value == 0.0
    assert metrics["activation_decision_accuracy"].value == 0.0
    unknown = EnterpriseDirectoryRbacPredictionV1(
        cells=(
            DirectoryRbacCellPredictionV1(
                cell_id="unknown",
                birthright_decision=truth.cells[0].birthright_decision,
                intended_decision=truth.cells[0].intended_decision,
                effective_decision=truth.cells[0].effective_decision,
                final_decision=truth.cells[0].final_decision,
            ),
        )
    )
    with pytest.raises(ValueError, match="unknown truth rows"):
        evaluate_enterprise_directory_rbac(truth=truth, predictions=unknown)


def test_metric_contract_enforces_exact_denominators_and_empty_behavior() -> None:
    empty = EnterpriseAuthorizationMetricV1(
        family="rbac",
        name="empty",
        numerator=0,
        denominator=0,
        support=0,
        denominator_meaning="optional rows",
        empty_behaviour=MetricEmptyBehaviour.NULL_IF_EMPTY,
        value=None,
    )
    assert empty.value is None
    with pytest.raises(ValidationError, match="support_must_equal"):
        EnterpriseAuthorizationMetricV1(
            family="rbac",
            name="bad",
            numerator=1,
            denominator=2,
            support=1,
            denominator_meaning="rows",
            empty_behaviour=MetricEmptyBehaviour.NULL_IF_EMPTY,
            value=0.5,
        )
    with pytest.raises(ValidationError, match="numerator_exceeds"):
        EnterpriseAuthorizationMetricV1(
            family="rbac",
            name="bad",
            numerator=2,
            denominator=1,
            support=1,
            denominator_meaning="rows",
            empty_behaviour=MetricEmptyBehaviour.NULL_IF_EMPTY,
            value=2.0,
        )
    with pytest.raises(ValidationError, match="empty_metric"):
        EnterpriseAuthorizationMetricV1(
            family="rbac",
            name="bad",
            numerator=0,
            denominator=0,
            support=0,
            denominator_meaning="rows",
            empty_behaviour=MetricEmptyBehaviour.NONEMPTY,
            value=None,
        )
    with pytest.raises(ValidationError, match="value_mismatch"):
        EnterpriseAuthorizationMetricV1(
            family="rbac",
            name="bad",
            numerator=1,
            denominator=2,
            support=2,
            denominator_meaning="rows",
            empty_behaviour=MetricEmptyBehaviour.NULL_IF_EMPTY,
            value=0.25,
        )


def test_metrics_handle_ineligible_assignments_and_require_selected_cells() -> None:
    _reference, truth = _compiled()
    first = truth.birthright_assignments[0].model_copy(update={"eligible": False})
    changed = truth.model_copy(
        update={"birthright_assignments": (first, *truth.birthright_assignments[1:])}
    )
    prediction = perfect_enterprise_directory_rbac_prediction(changed)
    report = evaluate_enterprise_directory_rbac(
        truth=changed,
        predictions=prediction,
    )
    metric = next(
        item
        for item in report.metrics
        if item.name == "birthright_assignment_exact_match_rate"
    )
    assert metric.value == 1.0

    empty_truth = truth.model_copy(update={"cells": ()})
    with pytest.raises(ValueError, match="requires nonempty selected coverage"):
        evaluate_enterprise_directory_rbac(
            truth=empty_truth,
            predictions=EnterpriseDirectoryRbacPredictionV1(),
        )


def test_corpus_and_rbac_artifacts_round_trip_with_physical_visibility_split(
    tmp_path: Path,
) -> None:
    reference, truth = _compiled()
    corpus_root = tmp_path / "corpus"
    export_enterprise_evaluation_corpus(corpus_root, reference.corpus_result)
    assert load_public_enterprise_evaluation_corpus(corpus_root) == (
        reference.corpus_result.public_corpus
    )
    assert load_evaluator_enterprise_case_inventory(corpus_root) == (
        reference.corpus_result.evaluator_case_inventory
    )
    public_bytes = (corpus_root / "public" / "evaluation-corpus.json").read_bytes()
    assert b'"labels"' not in public_bytes

    rbac_root = tmp_path / "rbac"
    export_enterprise_directory_rbac(rbac_root, kernel=reference.kernel, truth=truth)
    assert load_public_enterprise_directory_rbac_kernel(rbac_root) == reference.kernel
    assert load_evaluator_enterprise_directory_rbac_truth(rbac_root) == truth
    kernel_bytes = (rbac_root / "public" / "directory-rbac-kernel.json").read_bytes()
    for forbidden in (
        b'"birthright_decision"',
        b'"reconciliation"',
        b'"assignment_satisfied"',
        b'"violated"',
    ):
        assert forbidden not in kernel_bytes
    with pytest.raises(EnterpriseRbacArtifactError, match="already exists"):
        export_enterprise_directory_rbac(
            rbac_root, kernel=reference.kernel, truth=truth
        )


def test_generated_truth_canonicalizes_rows_and_rejects_duplicate_keys() -> None:
    _reference, truth = _compiled()
    document = truth.model_dump(mode="json")
    document["cells"] = list(reversed(document["cells"]))
    reparsed = CompiledEnterpriseDirectoryRbacTruthV1.model_validate(document)
    assert reparsed == truth
    document = truth.model_dump(mode="json")
    document["cells"] = [document["cells"][0]] * 2
    with pytest.raises(ValidationError, match="duplicate_cells"):
        CompiledEnterpriseDirectoryRbacTruthV1.model_validate(document)


def test_artifact_loaders_reject_inventory_manifest_and_canonical_corruption(
    tmp_path: Path,
) -> None:
    reference, truth = _compiled()
    root = tmp_path / "rbac"
    export_enterprise_directory_rbac(root, kernel=reference.kernel, truth=truth)
    (root / "public" / "unexpected.json").write_text("{}\n")
    with pytest.raises(EnterpriseRbacArtifactError, match="inventory differs"):
        load_public_enterprise_directory_rbac_kernel(root)
    (root / "public" / "unexpected.json").unlink()
    manifest_path = root / "public" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["visibility"] = "evaluator"
    manifest_path.write_bytes(
        canonical_json_bytes(EnterpriseArtifactManifestV1.model_validate(manifest))
    )
    with pytest.raises(EnterpriseRbacArtifactError, match="visibility"):
        load_public_enterprise_directory_rbac_kernel(root)


def test_pair_loaders_verify_cross_visibility_bindings_and_case_targets(
    tmp_path: Path,
) -> None:
    reference, truth = _compiled()
    corpus_binding_root = tmp_path / "corpus-binding"
    export_enterprise_evaluation_corpus(corpus_binding_root, reference.corpus_result)
    bad_inventory = reference.corpus_result.evaluator_case_inventory.model_copy(
        update={"evaluation_corpus_digest": synthetic_digest(b"different corpus\n")}
    )
    _rewrite_artifact(
        corpus_binding_root,
        visibility="evaluator",
        name="evaluation-case-inventory.json",
        model=bad_inventory,
    )
    with pytest.raises(EnterpriseRbacArtifactError, match="corpus binding"):
        load_evaluator_enterprise_case_inventory(corpus_binding_root)

    case_target_root = tmp_path / "case-target"
    export_enterprise_evaluation_corpus(case_target_root, reference.corpus_result)
    first_case = reference.corpus_result.evaluator_case_inventory.cases[0].model_copy(
        update={"target_id": "unknown"}
    )
    bad_targets = reference.corpus_result.evaluator_case_inventory.model_copy(
        update={
            "cases": (
                first_case,
                *reference.corpus_result.evaluator_case_inventory.cases[1:],
            )
        }
    )
    _rewrite_artifact(
        case_target_root,
        visibility="evaluator",
        name="evaluation-case-inventory.json",
        model=bad_targets,
    )
    with pytest.raises(EnterpriseRbacArtifactError, match="target does not resolve"):
        load_evaluator_enterprise_case_inventory(case_target_root)

    truth_root = tmp_path / "truth-binding"
    export_enterprise_directory_rbac(truth_root, kernel=reference.kernel, truth=truth)
    bad_truth = truth.model_copy(
        update={"directory_rbac_kernel_digest": synthetic_digest(b"different kernel\n")}
    )
    _rewrite_artifact(
        truth_root,
        visibility="evaluator",
        name="directory-rbac-truth.json",
        model=bad_truth,
    )
    with pytest.raises(EnterpriseRbacArtifactError, match="kernel binding"):
        load_evaluator_enterprise_directory_rbac_truth(truth_root)


@pytest.mark.parametrize(
    ("corruption", "message"),
    [
        ("missing", "unreadable"),
        ("not_directory", "not a real directory"),
        ("manifest_count", "exactly one artifact"),
        ("manifest_binding", "manifest binding differs"),
        ("invalid_json", "artifact is invalid"),
        ("noncanonical", "not canonical JSON"),
        ("nonregular", "non-regular entry"),
    ],
)
def test_artifact_loader_rejects_each_physical_corruption_class(
    tmp_path: Path,
    corruption: str,
    message: str,
) -> None:
    reference, truth = _compiled()
    root = tmp_path / corruption
    if corruption == "missing":
        with pytest.raises(EnterpriseRbacArtifactError, match=message):
            load_public_enterprise_directory_rbac_kernel(root)
        return
    if corruption == "not_directory":
        root.mkdir()
        (root / "public").write_text("not a directory\n")
        with pytest.raises(EnterpriseRbacArtifactError, match=message):
            load_public_enterprise_directory_rbac_kernel(root)
        return

    export_enterprise_directory_rbac(root, kernel=reference.kernel, truth=truth)
    manifest_path = root / "public" / "manifest.json"
    artifact_path = root / "public" / "directory-rbac-kernel.json"
    if corruption == "manifest_count":
        manifest = EnterpriseArtifactManifestV1.model_validate_json(
            manifest_path.read_bytes()
        ).model_copy(update={"artifacts": ()})
        manifest_path.write_bytes(canonical_json_bytes(manifest))
    elif corruption == "manifest_binding":
        manifest = EnterpriseArtifactManifestV1.model_validate_json(
            manifest_path.read_bytes()
        )
        descriptor = manifest.artifacts[0].model_copy(
            update={"digest": synthetic_digest(b"different\n")}
        )
        manifest_path.write_bytes(
            canonical_json_bytes(
                manifest.model_copy(update={"artifacts": (descriptor,)})
            )
        )
    elif corruption == "invalid_json":
        artifact_path.write_bytes(b"{")
    elif corruption == "noncanonical":
        artifact_path.write_bytes(b" " + artifact_path.read_bytes())
    else:
        artifact_path.unlink()
        artifact_path.symlink_to(manifest_path)
    with pytest.raises(EnterpriseRbacArtifactError, match=message):
        load_public_enterprise_directory_rbac_kernel(root)


def test_generated_rbac_schemas_accept_reference_contracts() -> None:
    reference, truth = _compiled()
    models = {
        "enterprise-evaluation-corpus-config": (
            reference_enterprise_evaluation_corpus_config()
        ),
        "enterprise-evaluation-corpus": reference.corpus_result.public_corpus,
        "enterprise-evaluation-case-inventory": (
            reference.corpus_result.evaluator_case_inventory
        ),
        "enterprise-directory-rbac-intent": reference.intent,
        "enterprise-rbac-session-state-input": reference.session_state,
        "enterprise-directory-rbac-kernel": reference.kernel,
        "compiled-enterprise-directory-rbac-truth": truth,
        "enterprise-directory-rbac-prediction": (
            perfect_enterprise_directory_rbac_prediction(truth)
        ),
        "enterprise-directory-rbac-metrics": evaluate_enterprise_directory_rbac(
            truth=truth,
            predictions=perfect_enterprise_directory_rbac_prediction(truth),
        ),
    }
    for stem, model in models.items():
        schema = json.loads(
            (CONTRACT_ROOT / "schemas" / f"{stem}.schema.json").read_text()
        )
        errors = tuple(
            Draft202012Validator(schema).iter_errors(model.model_dump(mode="json"))
        )
        assert errors == ()
