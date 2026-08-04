"""Opaque directory/RBAC kernel compilation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.compiler import (
    EnterpriseCompileError,
    compile_enterprise_identity_access_universe,
)
from synthworld.enterprise.models import (
    AllSelectorV1,
    EnterpriseCompileOuterSafetyV1,
    EnterpriseIdentityAccessCompileBudgetV1,
    EnterpriseIdentityAccessCompileConfigV1,
    GroupTemplateV1,
    PopulationGroupMembershipRuleV1,
)
from synthworld.enterprise.rbac.graph import bounded_paths, canonical_adjacency
from synthworld.enterprise.rbac.kernel import compile_enterprise_directory_rbac_kernel
from synthworld.enterprise.rbac.reference import (
    REFERENCE_ENTERPRISE_SEED,
    reference_enterprise_rbac_inputs,
)
from synthworld.enterprise.reference import reference_enterprise_identity_access_import


def test_kernel_resolves_rules_without_changing_pr2_universe_or_leaking_keys() -> None:
    reference = reference_enterprise_rbac_inputs()
    base = reference_enterprise_identity_access_import()
    assert (
        synthetic_digest(
            canonical_json_bytes(reference.universe_result.public_universe)
        ).value
        == "b4eae423689ede98d98858cae004f98d07fa5b0ac4774858500a4ba257946f4a"
    )
    assert reference.kernel.directory_rbac_state_input_digest == synthetic_digest(
        canonical_json_bytes(reference.source_import.directory_rbac_state)
    )
    assert len(reference.kernel.memberships) == 4
    assert len(reference.kernel.subject_role_assignments) == 2
    assert len(reference.kernel.role_grants) == 4
    assert len(reference.kernel.direct_entitlements) == 5
    kernel_bytes = canonical_json_bytes(reference.kernel)
    for private_key in (
        base.blueprint.blueprint_key,
        "population-employees",
        "group-platform",
        "role-api-reader",
        "redundant-employee-read",
    ):
        assert private_key.encode() not in kernel_bytes
    with pytest.raises(ValidationError):
        reference.kernel.memberships = ()


def test_pr3_install_preserves_every_pr2_reference_contract_digest() -> None:
    imported = reference_enterprise_identity_access_import()
    compiled = compile_enterprise_identity_access_universe(
        import_model=imported,
        seed=REFERENCE_ENTERPRISE_SEED,
    )
    expected = {
        "blueprint": "fe6d17a918935fa57fe5389c25e535378e909312e488e97d060ffdb5c434f486",
        "extension": "a5b6e7a2fc6e26f332f24d4aac1c4476113c52243056b7027a95e6d757639097",
        "state": "43a64653b41b5d3e2243232f68a8c82105e635f98b7e7f409a5254005d5d29ee",
        "import": "759d839c5df4e3177c182393384961d3d2ef3cdd70c1ee399a1f0182b6d806c9",
        "universe": "b4eae423689ede98d98858cae004f98d07fa5b0ac4774858500a4ba257946f4a",
        "binding": "3346f26f6d00f6be29605e9b8a996e1757ed68bf5e5b088393be8ec1542c1cdc",
    }
    actual = {
        "blueprint": synthetic_digest(canonical_json_bytes(imported.blueprint)).value,
        "extension": synthetic_digest(
            canonical_json_bytes(imported.iam_universe_extension)
        ).value,
        "state": synthetic_digest(
            canonical_json_bytes(imported.directory_rbac_state)
        ).value,
        "import": synthetic_digest(canonical_json_bytes(imported)).value,
        "universe": synthetic_digest(
            canonical_json_bytes(compiled.public_universe)
        ).value,
        "binding": synthetic_digest(
            canonical_json_bytes(compiled.evaluator_canonical_binding_truth)
        ).value,
    }
    assert actual == expected


def test_kernel_is_deterministic_and_canonicalizes_generated_records() -> None:
    reference = reference_enterprise_rbac_inputs()
    second = compile_enterprise_directory_rbac_kernel(
        import_model=reference.source_import,
        universe=reference.universe_result.public_universe,
    )
    assert canonical_json_bytes(second) == canonical_json_bytes(reference.kernel)
    reordered = reference.kernel.model_copy(
        update={"memberships": tuple(reversed(reference.kernel.memberships))}
    )
    reparsed = type(reference.kernel).model_validate(reordered.model_dump())
    assert reparsed == reference.kernel


def test_kernel_rejects_a_source_import_that_does_not_match_the_universe() -> None:
    reference = reference_enterprise_rbac_inputs()
    blueprint = reference.source_import.blueprint
    changed_blueprint = blueprint.model_copy(
        update={
            "groups": (
                *blueprint.groups,
                GroupTemplateV1(
                    key="unused-extra-group",
                    tenant_key="tenant-main",
                    organisation_key="organisation-main",
                ),
            )
        }
    )
    changed = reference.source_import.model_copy(
        update={"blueprint": changed_blueprint}
    )
    with pytest.raises(
        EnterpriseCompileError, match="kernel_universe_mapping_mismatch"
    ):
        compile_enterprise_directory_rbac_kernel(
            import_model=changed,
            universe=reference.universe_result.public_universe,
        )


def test_overlapping_population_rules_cannot_collapse_into_one_kernel_edge() -> None:
    reference = reference_enterprise_rbac_inputs()
    state = reference.source_import.directory_rbac_state
    overlapping = PopulationGroupMembershipRuleV1(
        rule_key="overlapping-platform-membership",
        population_key="population-employees",
        group_key="group-platform",
        selector=AllSelectorV1(),
    )
    changed_state = state.model_copy(
        update={"memberships": (*state.memberships, overlapping)}
    )
    changed = reference.source_import.model_copy(
        update={"directory_rbac_state": changed_state}
    )
    with pytest.raises(EnterpriseCompileError, match="duplicate_compiled_membership"):
        compile_enterprise_directory_rbac_kernel(
            import_model=changed,
            universe=reference.universe_result.public_universe,
        )


def test_directory_relation_budget_is_checked_before_kernel_materialization() -> None:
    reference = reference_enterprise_rbac_inputs()
    config = EnterpriseIdentityAccessCompileConfigV1(
        budget=EnterpriseIdentityAccessCompileBudgetV1(max_directory_rbac_relations=17)
    )
    with pytest.raises(
        EnterpriseCompileError, match="directory_rbac_relation_budget_exceeded"
    ):
        compile_enterprise_directory_rbac_kernel(
            import_model=reference.source_import,
            universe=reference.universe_result.public_universe,
            compile_config=config,
        )


def test_kernel_generated_records_reject_duplicate_semantic_ids() -> None:
    reference = reference_enterprise_rbac_inputs()
    item = reference.kernel.memberships[0]
    document = reference.kernel.model_dump(mode="json")
    document["memberships"] = [item.model_dump(mode="json")] * 2
    with pytest.raises(ValidationError, match="duplicate_edge_id"):
        type(reference.kernel).model_validate_json(__import__("json").dumps(document))


def test_dag_paths_are_canonical_and_reject_cycles_before_enumeration() -> None:
    adjacency = canonical_adjacency(
        ("a", "b", "c", "d"),
        (("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")),
    )
    assert bounded_paths(
        adjacency=adjacency,
        starts=("a",),
        max_paths_per_start=10,
        max_total_paths=10,
        budget_code="path_budget",
    )["a"] == (("a",), ("a", "b"), ("a", "b", "d"), ("a", "c"), ("a", "c", "d"))
    with pytest.raises(EnterpriseCompileError, match="directory_rbac_graph_cycle"):
        canonical_adjacency(("a", "b"), (("a", "b"), ("b", "a")))


@pytest.mark.parametrize(
    ("per_start", "total"),
    [(1, 10), (10, 2)],
)
def test_dag_path_budgets_fail_before_enumeration(per_start: int, total: int) -> None:
    adjacency = canonical_adjacency(("a", "b", "c"), (("a", "b"),))
    with pytest.raises(EnterpriseCompileError, match="path_budget"):
        bounded_paths(
            adjacency=adjacency,
            starts=("a", "b"),
            max_paths_per_start=per_start,
            max_total_paths=total,
            budget_code="path_budget",
        )


@pytest.mark.parametrize(
    ("limit", "code"),
    [
        ("records", "directory_rbac_outer_record_limit_exceeded"),
        ("bytes", "directory_rbac_outer_byte_limit_exceeded"),
    ],
)
def test_expanded_kernel_has_its_own_outer_safety_limits(limit: str, code: str) -> None:
    reference = reference_enterprise_rbac_inputs()
    state = reference.source_import.directory_rbac_state
    template = state.direct_entitlements[0]
    expanded_state = state.model_copy(
        update={
            "direct_entitlements": (
                *state.direct_entitlements,
                *tuple(
                    template.model_copy(update={"revision_id": f"outer-{index:03d}"})
                    for index in range(100)
                ),
            )
        }
    )
    source_import = reference.source_import.model_copy(
        update={"directory_rbac_state": expanded_state}
    )
    compiled = compile_enterprise_identity_access_universe(
        import_model=source_import,
        seed=reference.universe_result.public_universe.seed,
    )
    assert compiled.public_universe == reference.universe_result.public_universe
    if limit == "records":
        allowed = sum(
            len(getattr(compiled.public_universe, field))
            for field in (
                "tenants",
                "organisations",
                "units",
                "principals",
                "accounts",
                "access_subjects",
                "groups",
                "roles",
                "authorization_targets",
                "permissions",
                "relationship_anchors",
                "access_atoms",
            )
        ) + len(compiled.evaluator_canonical_binding_truth.bindings)
        safety = EnterpriseCompileOuterSafetyV1(max_serialized_records=allowed)
    else:
        allowed = len(canonical_json_bytes(compiled.public_universe)) + len(
            canonical_json_bytes(compiled.evaluator_canonical_binding_truth)
        )
        safety = EnterpriseCompileOuterSafetyV1(max_canonical_bytes=allowed)
    config = EnterpriseIdentityAccessCompileConfigV1(outer_safety=safety)
    with pytest.raises(EnterpriseCompileError, match=code):
        compile_enterprise_directory_rbac_kernel(
            import_model=source_import,
            universe=compiled.public_universe,
            compile_config=config,
        )
