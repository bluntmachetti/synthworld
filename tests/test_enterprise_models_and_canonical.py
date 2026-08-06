"""Contract invariants for enterprise identity/access input and generated records."""

from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import pytest
from pydantic import ValidationError

from synthworld.enterprise.canonical import (
    blueprint_namespace_uuid,
    blueprint_semantic_digest,
    build_private_compilation_receipt,
    canonical_json_value_bytes,
    encode_parts,
    source_artifact_set_digest,
    stable_enterprise_id,
)
from synthworld.enterprise.models import (
    AccountObservationV1,
    AdministrativeState,
    CountSelectorV1,
    DirectEntitlementV1,
    EnterpriseCompileOuterSafetyV1,
    EnterpriseDirectoryRbacStateInputV1,
    EnterpriseIdentityAccessBlueprintV1,
    EnterpriseIdentityAccessCompileBudgetV1,
    EnterpriseIdentityAccessImportLimitsV1,
    EnterpriseIdentityAccessValidationReportV1,
    EnterpriseImportDiagnosticV1,
    FractionSelectorV1,
    TenantTemplateV1,
)
from synthworld.enterprise.reference import (
    REFERENCE_NAMESPACE_SALT,
    reference_enterprise_identity_access_import,
)


@pytest.mark.parametrize(
    "value",
    [42, "", " padded", "padded ", "a" * 257, "person@example.com"],
)
def test_logical_keys_reject_non_structural_or_person_level_values(
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        TenantTemplateV1(key=value)  # type: ignore[arg-type]


def test_logical_keys_are_nfc_normalized_and_models_are_frozen_and_strict() -> None:
    tenant = TenantTemplateV1(key="Cafe\u0301")
    assert tenant.key == "Café"
    with pytest.raises(ValidationError, match="Extra inputs"):
        TenantTemplateV1.model_validate({"key": "tenant", "extra": True})
    with pytest.raises(ValidationError):
        TenantTemplateV1.model_validate({"key": 7})
    with pytest.raises(ValidationError):
        tenant.key = "changed"


def test_fraction_selectors_are_reduced_and_bounded() -> None:
    assert FractionSelectorV1(numerator=2, denominator=3).numerator == 2
    with pytest.raises(ValidationError, match="out_of_range"):
        FractionSelectorV1(numerator=4, denominator=3)
    with pytest.raises(ValidationError, match="not_reduced"):
        FractionSelectorV1(numerator=2, denominator=4)
    with pytest.raises(ValidationError):
        CountSelectorV1(count=0)


@pytest.mark.parametrize(
    "field",
    [
        "tenants",
        "organisations",
        "units",
        "populations",
        "groups",
        "roles",
        "resource_sets",
        "principal_access_atom_rules",
    ],
)
def test_blueprint_collections_reject_normalized_duplicate_keys(field: str) -> None:
    blueprint = reference_enterprise_identity_access_import().blueprint
    item = getattr(blueprint, field)[0]
    document = blueprint.model_dump(mode="json")
    document[field] = [item.model_dump(mode="json"), item.model_dump(mode="json")]
    with pytest.raises(ValidationError, match="duplicate_"):
        EnterpriseIdentityAccessBlueprintV1.model_validate_json(
            canonical_json_value_bytes(document)
        )


def test_resource_actions_and_input_component_collections_are_canonical() -> None:
    imported = reference_enterprise_identity_access_import()
    resource = imported.blueprint.resource_sets[0]
    changed_resource = resource.model_copy(update={"actions": ("write", "read")})
    changed_blueprint = imported.blueprint.model_copy(
        update={
            "roles": tuple(reversed(imported.blueprint.roles)),
            "resource_sets": (changed_resource,),
        }
    )
    reparsed = EnterpriseIdentityAccessBlueprintV1.model_validate_json(
        canonical_json_value_bytes(changed_blueprint.model_dump(mode="json"))
    )
    assert tuple(item.key for item in reparsed.roles) == (
        "role-api-admin",
        "role-api-reader",
    )
    assert reparsed.resource_sets[0].actions == ("read", "write")
    duplicate_actions = resource.model_dump(mode="json")
    duplicate_actions["actions"] = ["read", "read"]
    with pytest.raises(ValidationError, match="duplicate_resource_action"):
        type(resource).model_validate_json(
            canonical_json_value_bytes(duplicate_actions)
        )

    extension = imported.iam_universe_extension
    allocation = extension.account_allocations[0]
    duplicate_extension = extension.model_dump(mode="json")
    duplicate_extension["account_allocations"] = [
        allocation.model_dump(mode="json"),
        allocation.model_dump(mode="json"),
    ]
    with pytest.raises(ValidationError, match="duplicate_account_allocation_key"):
        type(extension).model_validate_json(
            canonical_json_value_bytes(duplicate_extension)
        )
    atom_rule = extension.account_access_atom_rules[0]
    duplicate_extension = extension.model_dump(mode="json")
    duplicate_extension["account_access_atom_rules"] = [
        atom_rule.model_dump(mode="json"),
        atom_rule.model_dump(mode="json"),
    ]
    with pytest.raises(ValidationError, match="duplicate_account_access_atom"):
        type(extension).model_validate_json(
            canonical_json_value_bytes(duplicate_extension)
        )


def test_account_and_entitlement_intervals_are_half_open() -> None:
    account = AccountObservationV1(
        account_id="account",
        administrative_state=AdministrativeState.ACTIVE,
        valid_from_tick=1,
        revision_id="revision-1",
    )
    assert account.valid_until_tick is None
    with pytest.raises(ValidationError, match="validity_interval_invalid"):
        account.model_copy(update={"valid_until_tick": 1}).__class__.model_validate(
            account.model_copy(update={"valid_until_tick": 1}).model_dump()
        )
    entitlement = DirectEntitlementV1(
        subject_id="subject",
        authorization_target_id="target",
        action="read",
        valid_from_tick=2,
        valid_until_tick=3,
        revision_id="revision-2",
    )
    assert entitlement.valid_until_tick == 3
    with pytest.raises(ValidationError, match="validity_interval_invalid"):
        DirectEntitlementV1.model_validate(
            entitlement.model_copy(update={"valid_until_tick": 2}).model_dump()
        )


@pytest.mark.parametrize(
    "field",
    [
        "account_observations",
        "memberships",
        "group_nesting",
        "group_role_assignments",
        "population_role_assignments",
        "role_hierarchy",
        "role_grants",
        "direct_entitlements",
    ],
)
def test_directory_state_rejects_duplicate_semantic_records(field: str) -> None:
    reference = reference_enterprise_identity_access_import().directory_rbac_state
    account = AccountObservationV1(
        account_id="account",
        administrative_state=AdministrativeState.ACTIVE,
        valid_from_tick=0,
        revision_id="revision-account",
    )
    entitlement = DirectEntitlementV1(
        subject_id="subject",
        authorization_target_id="target",
        action="read",
        valid_from_tick=0,
        revision_id="revision-entitlement",
    )
    synthetic_items = {
        "account_observations": account,
        "direct_entitlements": entitlement,
    }
    item = (
        synthetic_items[field]
        if field in synthetic_items
        else getattr(reference, field)[0]
    )
    document = reference.model_dump(mode="json")
    document[field] = [item.model_dump(mode="json"), item.model_dump(mode="json")]
    with pytest.raises(ValidationError, match="duplicate_"):
        EnterpriseDirectoryRbacStateInputV1.model_validate_json(
            canonical_json_value_bytes(document)
        )


@pytest.mark.parametrize(
    ("model", "field", "ceiling"),
    [
        *(
            (EnterpriseIdentityAccessCompileBudgetV1, name, value)
            for name, value in {
                "max_principals": 1_000_000,
                "max_accounts": 1_000_000,
                "max_groups": 100_000,
                "max_roles": 100_000,
                "max_authorization_targets": 250_000,
                "max_declared_actions": 1_000_000,
                "max_access_atoms": 5_000_000,
                "max_native_contexts": 100_000,
                "max_session_state_slots": 1_000_000,
                "max_evaluation_cells": 5_000_000,
                "max_role_activation_requests": 1_000_000,
                "max_access_requests": 5_000_000,
                "max_evaluator_cases": 5_000_000,
                "max_directory_rbac_relations": 500_000,
                "max_group_depth": 256,
                "max_role_depth": 256,
                "max_attribute_facts": 5_000_000,
                "max_total_abac_rules": 100_000,
                "max_total_abac_predicates": 1_000_000,
                "max_rebac_tuples": 5_000_000,
                "max_rebac_rules": 100_000,
                "max_rebac_paths_per_cell": 256,
                "max_rebac_path_expansions": 2_000_000,
                "max_sod_constraints": 100_000,
                "max_sod_role_set_width": 256,
                "max_sod_evaluations": 5_000_000,
                "max_derivations_per_cell": 256,
                "max_total_derivations": 10_000_000,
                "max_scenario_deltas": 5_000_000,
                "max_temporal_events": 5_000_000,
            }.items()
        ),
        *(
            (EnterpriseCompileOuterSafetyV1, name, value)
            for name, value in {
                "max_serialized_records": 25_000_000,
                "max_relations": 25_000_000,
                "max_expanded_steps": 100_000_000,
                "max_canonical_bytes": 25 * 1024 * 1024 * 1024,
                "max_work_units": 500_000_000,
            }.items()
        ),
    ],
)
def test_compile_and_outer_budgets_cannot_exceed_hard_ceilings(
    model: type[EnterpriseIdentityAccessCompileBudgetV1]
    | type[EnterpriseCompileOuterSafetyV1],
    field: str,
    ceiling: int,
) -> None:
    with pytest.raises(ValidationError, match="hard_ceiling"):
        model(**{field: ceiling + 1})


def test_import_limits_and_validation_report_status_are_strict() -> None:
    with pytest.raises(ValidationError):
        EnterpriseIdentityAccessImportLimitsV1(max_csv_files=21)
    diagnostic = EnterpriseImportDiagnosticV1(
        code="problem", message="problem", remediation_hint="fix it"
    )
    assert (
        EnterpriseIdentityAccessValidationReportV1(
            valid=False, diagnostics=(diagnostic,)
        ).valid
        is False
    )
    with pytest.raises(ValidationError, match="status_mismatch"):
        EnterpriseIdentityAccessValidationReportV1(
            valid=True, diagnostics=(diagnostic,)
        )
    with pytest.raises(ValidationError, match="status_mismatch"):
        EnterpriseIdentityAccessValidationReportV1(valid=False, diagnostics=())


def test_length_prefixed_ids_and_private_digests_are_stable_and_separate() -> None:
    assert encode_parts(("a:1", "b")) != encode_parts(("a", "1:b"))
    assert encode_parts(("Café",)) == encode_parts(("Cafe\u0301",))
    with pytest.raises(ValueError, match="nonempty"):
        encode_parts(("",))
    namespace = blueprint_namespace_uuid(REFERENCE_NAMESPACE_SALT)
    assert str(namespace) == "52e8db47-d905-508a-918c-868f67e77f94"
    first = stable_enterprise_id(namespace, namespace, "a:1", "b")
    second = stable_enterprise_id(namespace, namespace, "a", "1:b")
    assert first != second

    blueprint = reference_enterprise_identity_access_import().blueprint
    semantic = blueprint_semantic_digest(blueprint)
    assert (
        semantic == "79f0cfd803ffd4f9ac4aa74b490023abe5f84ccd3a960bc32a662c62a8e9f301"
    )
    sources_a = {"b.csv": b"two", "a.csv": b"one"}
    sources_b = {"a.csv": b"one", "b.csv": b"two"}
    assert source_artifact_set_digest(sources_a) == source_artifact_set_digest(
        sources_b
    )
    assert source_artifact_set_digest(sources_a) != source_artifact_set_digest(
        {"a.csv": b"one", "b.csv": b"changed"}
    )
    with pytest.raises(ValueError, match="explicit publication consent"):
        build_private_compilation_receipt(
            blueprint=blueprint,
            source_files=sources_a,
            publication_consent=False,
        )
    receipt = build_private_compilation_receipt(
        blueprint=blueprint,
        source_files=sources_a,
        publication_consent=True,
    )
    assert receipt.publication_consent is True
    assert receipt.blueprint_semantic_digest == semantic


def test_canonical_json_rejects_nonfinite_values_and_compile_result_is_frozen() -> None:
    with pytest.raises(ValueError):
        canonical_json_value_bytes({"bad": math.nan})
    from synthworld.enterprise.compiler import (
        compile_enterprise_identity_access_universe,
    )

    result = compile_enterprise_identity_access_universe(
        import_model=reference_enterprise_identity_access_import(), seed=1
    )
    with pytest.raises(FrozenInstanceError):
        result.public_universe = result.public_universe  # type: ignore[misc]
