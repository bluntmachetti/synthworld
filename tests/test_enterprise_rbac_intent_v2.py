"""Versioned intended direct-entitlement semantics and artifact boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from synthworld.enterprise.authorization.compiler import (
    compile_enterprise_access_state,
    compose_enterprise_authorization_v2,
)
from synthworld.enterprise.authorization.models import (
    AuthorizationCellProfileV1,
    AuthorizationEvaluationProfileV1,
    CompiledEnterpriseAccessStateV1,
    EnterpriseAuthorizationCompositionV2,
)
from synthworld.enterprise.authorization_common import (
    AuthorizationEvaluationProfileKind,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.compiler import EnterpriseCompileError
from synthworld.enterprise.models import EnterpriseArtifactManifestV1
from synthworld.enterprise.rbac.common import (
    AuthorizationDecision,
    DerivationMechanism,
    ReconciliationOutcome,
)
from synthworld.enterprise.rbac.compiler import (
    compile_enterprise_directory_rbac_truth_v2,
)
from synthworld.enterprise.rbac.models import (
    CompiledEnterpriseDirectoryRbacTruthV2,
    EnterpriseDirectoryRbacIntentOverlayV1,
    EnterpriseDirectoryRbacIntentOverlayV2,
    IntendedDirectEntitlementV2,
)
from synthworld.enterprise.rbac.reference import (
    ReferenceEnterpriseRbacInputsV1,
    reference_enterprise_rbac_inputs,
)
from synthworld.enterprise.rbac.serialization import (
    EnterpriseRbacArtifactError,
    export_enterprise_directory_rbac_v2,
    load_evaluator_enterprise_directory_rbac_truth_v2,
    load_public_enterprise_directory_rbac_intent_v2,
    load_public_enterprise_directory_rbac_kernel_v2,
)

CONTRACT_ROOT = Path("enterprise-identity-access-contract")


def _v2_intent(
    reference: ReferenceEnterpriseRbacInputsV1,
    direct: tuple[IntendedDirectEntitlementV2, ...] = (),
) -> EnterpriseDirectoryRbacIntentOverlayV2:
    document = reference.intent.model_dump(mode="json")
    document["schema_version"] = "2.0.0"
    document["intended_direct_entitlements"] = [
        item.model_dump(mode="json") for item in direct
    ]
    return EnterpriseDirectoryRbacIntentOverlayV2.model_validate_json(
        json.dumps(document)
    )


def _compile_v2(
    reference: ReferenceEnterpriseRbacInputsV1,
    intent: EnterpriseDirectoryRbacIntentOverlayV2,
) -> CompiledEnterpriseDirectoryRbacTruthV2:
    return compile_enterprise_directory_rbac_truth_v2(
        universe=reference.universe_result.public_universe,
        canonical_binding_truth=(
            reference.universe_result.evaluator_canonical_binding_truth
        ),
        corpus=reference.corpus_result.public_corpus,
        directory_rbac_kernel=reference.kernel,
        session_state=reference.session_state,
        directory_rbac_intent=intent,
    )


def _excessive_direct_target(
    reference: ReferenceEnterpriseRbacInputsV1,
    truth: CompiledEnterpriseDirectoryRbacTruthV2,
) -> tuple[str, IntendedDirectEntitlementV2]:
    paths = {item.path_id: item for item in truth.access_derivation_paths}
    cell = next(
        item
        for item in truth.cells
        if item.reconciliation is ReconciliationOutcome.EXCESSIVE
        and any(
            paths[path_id].mechanism is DerivationMechanism.DIRECT_ENTITLEMENT
            for path_id in item.effective_path_ids
        )
    )
    direct_path = next(
        paths[path_id]
        for path_id in cell.effective_path_ids
        if paths[path_id].mechanism is DerivationMechanism.DIRECT_ENTITLEMENT
    )
    actual = next(
        item
        for item in reference.kernel.direct_entitlements
        if item.entitlement_id == direct_path.source_record_id
    )
    return cell.cell_id, IntendedDirectEntitlementV2(
        entitlement_id="approved-direct-reference",
        subject_id=actual.subject_id,
        permission_id=actual.permission_id,
        valid_from_tick=actual.valid_from_tick,
        valid_until_tick=actual.valid_until_tick,
        revision_id="approved-direct-reference-r1",
    )


def _rewrite_model_and_descriptor(
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
    descriptors = tuple(
        item.model_copy(
            update={
                "schema_version": str(model.model_dump()["schema_version"]),
                "digest": synthetic_digest(payload),
                "byte_size": len(payload),
            }
        )
        if item.path == name
        else item
        for item in manifest.artifacts
    )
    manifest_path.write_bytes(
        canonical_json_bytes(manifest.model_copy(update={"artifacts": descriptors}))
    )


def test_v2_direct_intent_changes_reconciliation_not_effective_authority() -> None:
    reference = reference_enterprise_rbac_inputs()
    empty_intent = _v2_intent(reference)
    before = _compile_v2(reference, empty_intent)
    cell_id, direct = _excessive_direct_target(reference, before)

    approved_intent = _v2_intent(reference, (direct,))
    approved = _compile_v2(reference, approved_intent)
    repeated = _compile_v2(reference, approved_intent)
    changed_window = _compile_v2(
        reference,
        _v2_intent(
            reference,
            (direct.model_copy(update={"valid_from_tick": 1}),),
        ),
    )

    before_cell = next(item for item in before.cells if item.cell_id == cell_id)
    approved_cell = next(item for item in approved.cells if item.cell_id == cell_id)
    changed_cell = next(
        item for item in changed_window.cells if item.cell_id == cell_id
    )
    intended_paths = {item.path_id: item for item in approved.intended_derivation_paths}

    assert before.schema_version == "2.0.0"
    assert before.compiler_version == "2.0.0"
    assert before_cell.intended_decision is AuthorizationDecision.DENY
    assert before_cell.effective_decision is AuthorizationDecision.ALLOW
    assert before_cell.reconciliation is ReconciliationOutcome.EXCESSIVE
    assert approved_cell.intended_decision is AuthorizationDecision.ALLOW
    assert approved_cell.effective_decision is AuthorizationDecision.ALLOW
    assert approved_cell.reconciliation is ReconciliationOutcome.ALIGNED_ALLOW
    assert approved_cell.effective_path_ids == before_cell.effective_path_ids
    assert len(approved_cell.intended_path_ids) > len(before_cell.intended_path_ids)
    assert any(
        intended_paths[path_id].mechanism is DerivationMechanism.DIRECT_ENTITLEMENT
        for path_id in approved_cell.intended_path_ids
    )
    assert changed_cell.effective_path_ids == before_cell.effective_path_ids
    assert changed_cell.reconciliation is ReconciliationOutcome.EXCESSIVE
    assert canonical_json_bytes(repeated) == canonical_json_bytes(approved)

    document = approved.model_dump(mode="json")
    document["cells"] = list(reversed(document["cells"]))
    assert (
        CompiledEnterpriseDirectoryRbacTruthV2.model_validate_json(json.dumps(document))
        == approved
    )
    document["cells"] = [document["cells"][0]] * 2
    with pytest.raises(ValidationError, match="duplicate_cells"):
        CompiledEnterpriseDirectoryRbacTruthV2.model_validate_json(json.dumps(document))


def test_v2_truth_reaches_composed_authorization_without_widening_v1() -> None:
    reference = reference_enterprise_rbac_inputs()
    empty_truth = _compile_v2(reference, _v2_intent(reference))
    cell_id, direct = _excessive_direct_target(reference, empty_truth)
    approved_truth = _compile_v2(reference, _v2_intent(reference, (direct,)))
    corpus = reference.corpus_result.public_corpus
    profile = AuthorizationEvaluationProfileV1(
        evaluation_corpus_digest=synthetic_digest(canonical_json_bytes(corpus)),
        cells=tuple(
            AuthorizationCellProfileV1(
                cell_id=item.cell_id,
                profile=AuthorizationEvaluationProfileKind.RBAC,
            )
            for item in corpus.evaluation_cells
        ),
    )

    def compose_and_compile(
        truth: CompiledEnterpriseDirectoryRbacTruthV2,
    ) -> tuple[EnterpriseAuthorizationCompositionV2, CompiledEnterpriseAccessStateV1]:
        composition = compose_enterprise_authorization_v2(directory_rbac_truth=truth)
        access_state = compile_enterprise_access_state(
            universe=reference.universe_result.public_universe,
            canonical_binding_truth=(
                reference.universe_result.evaluator_canonical_binding_truth
            ),
            corpus=corpus,
            composition=composition,
            directory_rbac_truth=truth,
            evaluation_profile=profile,
        )
        return composition, access_state

    before_composition, before = compose_and_compile(empty_truth)
    approved_composition, approved = compose_and_compile(approved_truth)
    before_cell = next(item for item in before.cells if item.cell_id == cell_id)
    approved_cell = next(item for item in approved.cells if item.cell_id == cell_id)

    assert before_composition.schema_version == "2.0.0"
    assert approved_composition.directory_rbac.component_schema_version == "2.0.0"
    assert before_cell.reconciliation is ReconciliationOutcome.EXCESSIVE
    assert approved_cell.reconciliation is ReconciliationOutcome.ALIGNED_ALLOW
    assert approved_cell.effective_decision is before_cell.effective_decision


def test_v2_model_is_independent_strict_canonical_and_validates_windows() -> None:
    reference = reference_enterprise_rbac_inputs()
    empty = _v2_intent(reference)
    _cell_id, direct = _excessive_direct_target(
        reference, _compile_v2(reference, empty)
    )

    assert "intended_direct_entitlements" not in (
        EnterpriseDirectoryRbacIntentOverlayV1.model_fields
    )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EnterpriseDirectoryRbacIntentOverlayV1.model_validate_json(
            canonical_json_bytes(_v2_intent(reference, (direct,)))
        )
    with pytest.raises(ValidationError, match="validity_interval_invalid"):
        IntendedDirectEntitlementV2(
            entitlement_id="invalid-window",
            subject_id=direct.subject_id,
            permission_id=direct.permission_id,
            valid_from_tick=1,
            valid_until_tick=1,
            revision_id="invalid-window-r1",
        )
    with pytest.raises(
        ValidationError, match="duplicate_intended_direct_entitlement_id"
    ):
        _v2_intent(reference, (direct, direct))
    with pytest.raises(
        ValidationError, match="duplicate_intended_direct_entitlement_scope"
    ):
        _v2_intent(
            reference,
            (
                direct,
                direct.model_copy(update={"entitlement_id": "same-scope-second-id"}),
            ),
        )


@pytest.mark.parametrize("unknown_field", ["subject_id", "permission_id"])
def test_v2_compile_rejects_unknown_direct_intent_references(
    unknown_field: str,
) -> None:
    reference = reference_enterprise_rbac_inputs()
    empty = _v2_intent(reference)
    _cell_id, direct = _excessive_direct_target(
        reference, _compile_v2(reference, empty)
    )
    invalid = direct.model_copy(update={unknown_field: "unknown"})

    with pytest.raises(
        EnterpriseCompileError,
        match="unknown_intended_direct_entitlement_reference",
    ):
        _compile_v2(reference, _v2_intent(reference, (invalid,)))


def test_v2_compile_rejects_cross_tenant_and_digest_mismatches() -> None:
    reference = reference_enterprise_rbac_inputs()
    empty = _v2_intent(reference)
    _cell_id, direct = _excessive_direct_target(
        reference, _compile_v2(reference, empty)
    )
    universe = reference.universe_result.public_universe
    other_target = universe.authorization_targets[0].model_copy(
        update={
            "authorization_target_id": "other-tenant-target",
            "tenant_id": "other-tenant",
        }
    )
    other_permission = universe.permissions[0].model_copy(
        update={
            "permission_id": "other-tenant-permission",
            "authorization_target_id": other_target.authorization_target_id,
        }
    )
    universe = universe.model_copy(
        update={
            "authorization_targets": (*universe.authorization_targets, other_target),
            "permissions": (*universe.permissions, other_permission),
        }
    )
    universe_digest = synthetic_digest(canonical_json_bytes(universe))
    binding = reference.universe_result.evaluator_canonical_binding_truth.model_copy(
        update={"identity_access_universe_digest": universe_digest}
    )
    corpus = reference.corpus_result.public_corpus.model_copy(
        update={"identity_access_universe_digest": universe_digest}
    )
    corpus_digest = synthetic_digest(canonical_json_bytes(corpus))
    kernel = reference.kernel.model_copy(
        update={"identity_access_universe_digest": universe_digest}
    )
    session = reference.session_state.model_copy(
        update={"evaluation_corpus_digest": corpus_digest}
    )
    cross_tenant = direct.model_copy(
        update={"permission_id": other_permission.permission_id}
    )
    cross_tenant_intent = _v2_intent(reference, (cross_tenant,)).model_copy(
        update={
            "identity_access_universe_digest": universe_digest,
            "evaluation_corpus_digest": corpus_digest,
        }
    )
    with pytest.raises(
        EnterpriseCompileError,
        match="cross_tenant_intended_direct_entitlement",
    ):
        compile_enterprise_directory_rbac_truth_v2(
            universe=universe,
            canonical_binding_truth=binding,
            corpus=corpus,
            directory_rbac_kernel=kernel,
            session_state=session,
            directory_rbac_intent=cross_tenant_intent,
        )

    digest_mismatch = empty.model_copy(
        update={"identity_access_universe_digest": synthetic_digest(b"other\n")}
    )
    with pytest.raises(EnterpriseCompileError, match="rbac_intent_universe_digest"):
        _compile_v2(reference, digest_mismatch)


def test_v2_artifacts_are_exact_split_canonical_and_schema_valid(
    tmp_path: Path,
) -> None:
    reference = reference_enterprise_rbac_inputs()
    empty = _v2_intent(reference)
    _cell_id, direct = _excessive_direct_target(
        reference, _compile_v2(reference, empty)
    )
    intent = _v2_intent(reference, (direct,))
    truth = _compile_v2(reference, intent)
    root = tmp_path / "v2"

    export_enterprise_directory_rbac_v2(
        root,
        kernel=reference.kernel,
        intent=intent,
        truth=truth,
    )

    assert load_public_enterprise_directory_rbac_kernel_v2(root) == reference.kernel
    assert load_public_enterprise_directory_rbac_intent_v2(root) == intent
    assert load_evaluator_enterprise_directory_rbac_truth_v2(root) == truth
    assert {item.name for item in (root / "public").iterdir()} == {
        "directory-rbac-intent-v2.json",
        "directory-rbac-kernel.json",
        "manifest.json",
    }
    assert {item.name for item in (root / "evaluator").iterdir()} == {
        "directory-rbac-truth-v2.json",
        "manifest.json",
    }
    intent_bytes = (root / "public" / "directory-rbac-intent-v2.json").read_bytes()
    kernel_bytes = (root / "public" / "directory-rbac-kernel.json").read_bytes()
    truth_bytes = (root / "evaluator" / "directory-rbac-truth-v2.json").read_bytes()
    assert intent_bytes == canonical_json_bytes(intent)
    assert kernel_bytes == canonical_json_bytes(reference.kernel)
    assert truth_bytes == canonical_json_bytes(truth)
    assert b'"reconciliation"' not in intent_bytes + kernel_bytes
    assert b'"intended_decision"' not in intent_bytes + kernel_bytes
    assert b'"reconciliation"' in truth_bytes

    schema_models = {
        "enterprise-directory-rbac-intent-v2": intent,
        "compiled-enterprise-directory-rbac-truth-v2": truth,
        "enterprise-authorization-composition-v2": (
            compose_enterprise_authorization_v2(directory_rbac_truth=truth)
        ),
    }
    for stem, model in schema_models.items():
        schema = json.loads(
            (CONTRACT_ROOT / "schemas" / f"{stem}.schema.json").read_text()
        )
        assert (
            tuple(
                Draft202012Validator(schema).iter_errors(model.model_dump(mode="json"))
            )
            == ()
        )

    with pytest.raises(EnterpriseRbacArtifactError, match="already exists"):
        export_enterprise_directory_rbac_v2(
            root,
            kernel=reference.kernel,
            intent=intent,
            truth=truth,
        )


@pytest.mark.parametrize(
    ("corruption", "message"),
    [
        ("visibility", "visibility differs"),
        ("inventory", "inventory differs"),
        ("descriptor", "manifest binding differs"),
        ("truth_binding", "truth public binding differs"),
        ("truth_corpus_binding", "truth public binding differs"),
        ("public_universe_binding", "public universe binding differs"),
    ],
)
def test_v2_artifact_loaders_reject_manifest_and_public_binding_corruption(
    tmp_path: Path,
    corruption: str,
    message: str,
) -> None:
    reference = reference_enterprise_rbac_inputs()
    intent = _v2_intent(reference)
    truth = _compile_v2(reference, intent)
    root = tmp_path / corruption
    export_enterprise_directory_rbac_v2(
        root,
        kernel=reference.kernel,
        intent=intent,
        truth=truth,
    )

    if corruption in {"truth_binding", "truth_corpus_binding"}:
        invalid_truth = truth.model_copy(
            update={
                (
                    "directory_rbac_intent_digest"
                    if corruption == "truth_binding"
                    else "evaluation_corpus_digest"
                ): synthetic_digest(b"other\n")
            }
        )
        _rewrite_model_and_descriptor(
            root,
            visibility="evaluator",
            name="directory-rbac-truth-v2.json",
            model=invalid_truth,
        )
        with pytest.raises(EnterpriseRbacArtifactError, match=message):
            load_evaluator_enterprise_directory_rbac_truth_v2(root)
        return
    if corruption == "public_universe_binding":
        invalid_kernel = reference.kernel.model_copy(
            update={"identity_access_universe_digest": synthetic_digest(b"other\n")}
        )
        _rewrite_model_and_descriptor(
            root,
            visibility="public",
            name="directory-rbac-kernel.json",
            model=invalid_kernel,
        )
        with pytest.raises(EnterpriseRbacArtifactError, match=message):
            load_public_enterprise_directory_rbac_kernel_v2(root)
        with pytest.raises(EnterpriseRbacArtifactError, match=message):
            load_public_enterprise_directory_rbac_intent_v2(root)
        return
    else:
        manifest_path = root / "public" / "manifest.json"
        manifest = EnterpriseArtifactManifestV1.model_validate_json(
            manifest_path.read_bytes()
        )
        if corruption == "visibility":
            manifest = manifest.model_copy(update={"visibility": "evaluator"})
        elif corruption == "inventory":
            manifest = manifest.model_copy(update={"artifacts": manifest.artifacts[:1]})
        else:
            first = manifest.artifacts[0].model_copy(
                update={"digest": synthetic_digest(b"other\n")}
            )
            manifest = manifest.model_copy(
                update={"artifacts": (first, *manifest.artifacts[1:])}
            )
        manifest_path.write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(EnterpriseRbacArtifactError, match=message):
        load_public_enterprise_directory_rbac_intent_v2(root)
