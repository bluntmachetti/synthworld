"""Public consumer facade, canonical digests, and operator provenance."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from synthworld.enterprise import consumer
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import (
    AccountObservationV1,
    AdministrativeState,
    DirectEntitlementV1,
    EnterpriseDirectoryRbacStateInputV1,
    EnterpriseIdentityAccessCompileResultV1,
    EnterpriseIdentityAccessImportV1,
    SyntheticDigestV1,
)
from synthworld.enterprise.provenance import (
    EnterpriseCompiledObjectKind,
    EnterpriseCompiledObjectReferenceV1,
    EnterpriseCompilerProvenanceEntryV1,
    EnterpriseCompilerProvenanceV1,
    EnterpriseCompilerSourceKind,
)
from synthworld.enterprise.rbac.kernel import (
    compile_enterprise_directory_rbac_kernel,
)
from synthworld.enterprise.rbac.models import EnterpriseDirectoryRbacKernelV1
from synthworld.enterprise.reference import reference_enterprise_identity_access_import


def _compile_with_every_provenance_source() -> tuple[
    EnterpriseIdentityAccessImportV1,
    EnterpriseIdentityAccessCompileResultV1,
    EnterpriseDirectoryRbacKernelV1,
]:
    imported = reference_enterprise_identity_access_import()
    baseline = consumer.compile_enterprise_identity_access_universe(
        import_model=imported, seed=20260804
    )
    account = baseline.public_universe.accounts[0]
    binding = next(
        item
        for item in baseline.evaluator_canonical_binding_truth.bindings
        if item.account_id == account.account_id
    )
    target = baseline.public_universe.authorization_targets[0]
    state = imported.directory_rbac_state
    expanded_state = EnterpriseDirectoryRbacStateInputV1(
        account_observations=(
            AccountObservationV1(
                account_id=account.account_id,
                observed_principal_id=binding.principal_id,
                administrative_state=AdministrativeState.ACTIVE,
                valid_from_tick=0,
                revision_id="observed-v1",
            ),
        ),
        memberships=state.memberships,
        group_nesting=state.group_nesting,
        group_role_assignments=state.group_role_assignments,
        population_role_assignments=state.population_role_assignments,
        role_hierarchy=state.role_hierarchy,
        role_grants=state.role_grants,
        direct_entitlements=(
            DirectEntitlementV1(
                subject_id=binding.principal_id,
                authorization_target_id=target.authorization_target_id,
                action=target.actions[0],
                valid_from_tick=0,
                revision_id="direct-v1",
            ),
        ),
    )
    expanded = imported.model_copy(update={"directory_rbac_state": expanded_state})
    result = consumer.compile_enterprise_identity_access_universe(
        import_model=expanded, seed=20260804
    )
    kernel = compile_enterprise_directory_rbac_kernel(
        import_model=expanded, universe=result.public_universe
    )
    return expanded, result, kernel


def test_consumer_namespace_exposes_authoring_and_result_contracts() -> None:
    required = {
        "TenantTemplateV1",
        "AllSelectorV1",
        "EnterpriseIdentityAccessImportLimitsV1",
        "EnterpriseIdentityAccessCompileBudgetV1",
        "AccessEvaluationCellTemplateV1",
        "AbacCellPredictionV1",
        "RebacCellPredictionV1",
        "DirectoryRbacCellPredictionV1",
        "EnterpriseAuthorizationCellPredictionV1",
        "EnterpriseAuthorizationPublicArtifactsV1",
        "EnterpriseAuthorizationEvaluatorArtifactsV1",
        "EnterpriseEvaluationCorpusCompileResultV1",
        "EnterpriseIdentityAccessValidationReportV1",
        "build_enterprise_model",
        "digest_enterprise_model",
        "build_enterprise_compiler_provenance",
    }
    assert required <= set(consumer.__all__)
    assert (
        consumer.AbacEmploymentTypeIsV1.__module__
        != consumer.RbacEmploymentTypeIsV1.__module__
    )


def test_json_shaped_builder_is_the_permissive_constructor_boundary() -> None:
    data = {
        "blueprint_key": "consumer",
        "id_namespace_salt": "1" * 64,
        "tenants": [{"key": "tenant"}],
        "organisations": [{"key": "org", "tenant_key": "tenant"}],
        "units": [],
        "populations": [],
        "groups": [],
        "roles": [],
        "resource_sets": [],
        "principal_access_atom_rules": [],
    }
    with pytest.raises(ValidationError):
        consumer.EnterpriseIdentityAccessBlueprintV1(**data)  # type: ignore[arg-type]

    built = consumer.build_enterprise_model(
        consumer.EnterpriseIdentityAccessBlueprintV1, data
    )
    assert isinstance(built.tenants, tuple)
    assert built.tenants[0].key == "tenant"


def test_public_digest_helpers_match_exporter_serialization() -> None:
    imported = reference_enterprise_identity_access_import()
    result = consumer.compile_enterprise_identity_access_universe(
        import_model=imported, seed=7
    )
    universe = result.public_universe
    payload = consumer.canonical_enterprise_model_bytes(universe)

    assert payload == canonical_json_bytes(universe)
    assert consumer.digest_enterprise_model(universe) == synthetic_digest(payload)
    assert consumer.digest_enterprise_artifact(payload) == synthetic_digest(payload)


def test_provenance_maps_every_source_family_and_ignores_input_order() -> None:
    imported, result, kernel = _compile_with_every_provenance_source()
    provenance = consumer.build_enterprise_compiler_provenance(
        import_model=imported,
        compile_result=result,
        directory_rbac_kernel=kernel,
    )

    assert {item.source_kind for item in provenance.entries} == set(
        EnterpriseCompilerSourceKind
    )
    assert provenance.public_universe_digest == consumer.digest_enterprise_model(
        result.public_universe
    )
    assert provenance.directory_rbac_kernel_digest == consumer.digest_enterprise_model(
        kernel
    )
    assert "synthetic" not in provenance.model_dump(mode="json")

    document: dict[str, Any] = imported.model_dump(mode="json")
    document["blueprint"]["roles"].reverse()
    document["directory_rbac_state"]["role_grants"].reverse()
    reordered = consumer.build_enterprise_model(
        consumer.EnterpriseIdentityAccessImportV1, document
    )
    reordered_result = consumer.compile_enterprise_identity_access_universe(
        import_model=reordered, seed=result.public_universe.seed
    )
    reordered_kernel = consumer.compile_enterprise_directory_rbac_kernel(
        import_model=reordered, universe=reordered_result.public_universe
    )
    repeated = consumer.build_enterprise_compiler_provenance(
        import_model=reordered,
        compile_result=reordered_result,
        directory_rbac_kernel=reordered_kernel,
    )
    assert repeated == provenance


def test_provenance_rejects_stale_or_unresolvable_inputs() -> None:
    imported, result, kernel = _compile_with_every_provenance_source()
    changed = SyntheticDigestV1(value="0" * 64)

    with pytest.raises(
        ValueError, match="compiler_provenance_kernel_universe_digest_mismatch"
    ):
        consumer.build_enterprise_compiler_provenance(
            import_model=imported,
            compile_result=result,
            directory_rbac_kernel=kernel.model_copy(
                update={"identity_access_universe_digest": changed}
            ),
        )
    with pytest.raises(
        ValueError, match="compiler_provenance_kernel_source_digest_mismatch"
    ):
        consumer.build_enterprise_compiler_provenance(
            import_model=imported,
            compile_result=result,
            directory_rbac_kernel=kernel.model_copy(
                update={"directory_rbac_state_input_digest": changed}
            ),
        )

    incomplete_universe = result.public_universe.model_copy(update={"tenants": ()})
    incomplete_result = EnterpriseIdentityAccessCompileResultV1(
        public_universe=incomplete_universe,
        evaluator_canonical_binding_truth=result.evaluator_canonical_binding_truth,
    )
    rebound_kernel = kernel.model_copy(
        update={
            "identity_access_universe_digest": consumer.digest_enterprise_model(
                incomplete_universe
            )
        }
    )
    with pytest.raises(
        ValueError, match="compiler_provenance_compiled_reference_missing"
    ):
        consumer.build_enterprise_compiler_provenance(
            import_model=imported,
            compile_result=incomplete_result,
            directory_rbac_kernel=rebound_kernel,
        )


def test_provenance_contracts_reject_duplicate_keys_paths_and_outputs() -> None:
    reference = EnterpriseCompiledObjectReferenceV1(
        object_kind=EnterpriseCompiledObjectKind.TENANT,
        stable_id="opaque",
    )
    with pytest.raises(
        ValidationError, match="duplicate_compiler_provenance_compiled_object"
    ):
        EnterpriseCompilerProvenanceEntryV1(
            source_kind=EnterpriseCompilerSourceKind.TENANT,
            logical_key=("tenant",),
            source_path="/blueprint/tenants/0",
            compiled_objects=(reference, reference),
        )

    first = EnterpriseCompilerProvenanceEntryV1(
        source_kind=EnterpriseCompilerSourceKind.TENANT,
        logical_key=("tenant",),
        source_path="/blueprint/tenants/0",
        compiled_objects=(reference,),
    )
    second_key_collision = EnterpriseCompilerProvenanceEntryV1(
        source_kind=EnterpriseCompilerSourceKind.TENANT,
        logical_key=("tenant",),
        source_path="/blueprint/tenants/1",
        compiled_objects=(reference,),
    )
    with pytest.raises(
        ValidationError, match="duplicate_compiler_provenance_source_key"
    ):
        EnterpriseCompilerProvenanceV1(
            seed=1,
            source_import_digest=SyntheticDigestV1(value="1" * 64),
            public_universe_digest=SyntheticDigestV1(value="2" * 64),
            directory_rbac_kernel_digest=SyntheticDigestV1(value="3" * 64),
            entries=(first, second_key_collision),
        )
    with pytest.raises(
        ValidationError, match="duplicate_compiler_provenance_source_path"
    ):
        EnterpriseCompilerProvenanceV1(
            seed=1,
            source_import_digest=SyntheticDigestV1(value="1" * 64),
            public_universe_digest=SyntheticDigestV1(value="2" * 64),
            directory_rbac_kernel_digest=SyntheticDigestV1(value="3" * 64),
            entries=(first, first),
        )
