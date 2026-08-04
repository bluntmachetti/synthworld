"""Pure standards projections, support matrices, and coverage manifests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.enterprise.authorization.reference import (
    reference_enterprise_authorization_inputs,
)
from synthworld.enterprise.authorization_common import AuthorizationSourceLayer
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.compiler import EnterpriseCompileError
from synthworld.enterprise.conformance.models import (
    AuthorizationConformanceVectorV1,
    CoverageConstraintV1,
    CoverageFactorV1,
    CoverageFactorValueV1,
    CoverageTupleV1,
    PolicyCoverageManifestV1,
    validate_conformance_vectors,
)
from synthworld.enterprise.projections.authzen import (
    AuthZenDecisionObservationV1,
    AuthZenMappingProfileV1,
    AuthZenRawOutcome,
    AuthZenRequestProjectionV1,
    authzen_mapping_profile_v1,
    normalize_authzen_observation,
    project_authzen,
)
from synthworld.enterprise.projections.openfga import (
    OpenFgaMappingProfileV1,
    OpenFgaProjectionV1,
    openfga_mapping_profile_v1,
    project_openfga,
)
from synthworld.enterprise.projections.scim import (
    ScimGroupMemberProjectionV1,
    ScimGroupProjectionV1,
    ScimMembershipKind,
    ScimProjectionProfileV1,
    ScimProjectionV1,
    ScimProviderCapability,
    _ancestors,
    project_scim,
    scim_projection_profile_v1,
)
from synthworld.enterprise.projections.shared_signals import (
    SharedSignalsMappingProfileV1,
    compile_shared_signals_support_matrix,
    shared_signals_mapping_profile_v1,
)
from synthworld.enterprise.projections.support import (
    ProjectionMappingDefinitionV1,
    ProjectionMappingProfileV1,
    ProjectionSupportClassification,
    ProjectionSupportMatrixV1,
    ProjectionSupportRowV1,
    ProjectionTarget,
    compile_projection_support_matrix,
    evaluate_projection_fidelity,
)
from synthworld.enterprise.rbac.common import AuthorizationDecision
from synthworld.enterprise.rbac.models import DirectoryMembershipEdgeV1


def test_each_projection_declares_exact_approximated_and_unsupported_features() -> None:
    reference = reference_enterprise_authorization_inputs()
    universe = reference.rbac.universe_result.public_universe
    corpus = reference.rbac.corpus_result.public_corpus
    scim = project_scim(
        universe=universe,
        directory_rbac_kernel=reference.rbac.kernel,
        profile=scim_projection_profile_v1(snapshot_tick=0),
    )
    authzen = project_authzen(
        universe=universe,
        corpus=corpus,
        request=corpus.access_requests[0],
        mapping_profile=authzen_mapping_profile_v1(),
    )
    openfga = project_openfga(
        universe=universe,
        rebac_truth=reference.rebac_truth,
        mapping_profile=openfga_mapping_profile_v1(
            source_layer=AuthorizationSourceLayer.ACTUAL
        ),
    )
    shared = compile_shared_signals_support_matrix(shared_signals_mapping_profile_v1())
    matrices = (
        scim.support_matrix,
        authzen.support_matrix,
        openfga.support_matrix,
        shared,
    )
    assert {item.target for item in matrices} == set(ProjectionTarget)
    for matrix in matrices:
        assert {item.classification for item in matrix.rows} == set(
            ProjectionSupportClassification
        )
        assert all(item.mapping_digest == matrix.mapping_digest for item in matrix.rows)
        metrics = evaluate_projection_fidelity(matrix)
        assert {item.name for item in metrics.metrics} == {
            "approximated_feature_rate",
            "exact_feature_rate",
            "unsupported_feature_rate",
        }
        assert sum(item.value or 0.0 for item in metrics.metrics) == pytest.approx(1.0)


def test_support_matrix_preflight_is_complete_canonical_and_loss_explicit() -> None:
    exact = ProjectionMappingDefinitionV1(
        mapping_id="exact",
        native_source_feature="feature-a",
        target_construct="Target.a",
        classification=ProjectionSupportClassification.EXACT,
        conformance_vector_ids=("vector-a",),
    )
    unsupported = ProjectionMappingDefinitionV1(
        mapping_id="unsupported",
        native_source_feature="feature-b",
        target_construct="none",
        classification=ProjectionSupportClassification.UNSUPPORTED,
        semantic_delta="The target has no equivalent construct.",
        conformance_vector_ids=("vector-b",),
    )
    profile = ProjectionMappingProfileV1(
        profile_id="test-profile",
        target=ProjectionTarget.AUTHZEN,
        native_profile_version="1",
        target_profile_version="1",
        definitions=(unsupported, exact),
    )
    matrix = compile_projection_support_matrix(
        profile=profile, exercised_native_features=("feature-b", "feature-a")
    )
    assert matrix.exercised_native_features == ("feature-a", "feature-b")
    assert tuple(item.native_source_feature for item in matrix.rows) == (
        "feature-a",
        "feature-b",
    )
    with pytest.raises(ValueError, match="preflight_mismatch"):
        compile_projection_support_matrix(
            profile=profile, exercised_native_features=("feature-a",)
        )
    with pytest.raises(ValueError, match="preflight_mismatch"):
        compile_projection_support_matrix(
            profile=profile,
            exercised_native_features=("feature-a", "feature-b", "feature-c"),
        )
    with pytest.raises(ValidationError, match="exact_projection_has_semantic_delta"):
        exact.model_copy(update={"semantic_delta": "loss"}).model_validate(
            {**exact.model_dump(), "semantic_delta": "loss"}
        )
    with pytest.raises(
        ValidationError, match="nonexact_projection_requires_semantic_delta"
    ):
        ProjectionMappingDefinitionV1(
            mapping_id="bad",
            native_source_feature="bad",
            target_construct="none",
            classification=ProjectionSupportClassification.APPROXIMATED,
            conformance_vector_ids=("vector",),
        )
    with pytest.raises(ValidationError, match="duplicate_projection_native_source"):
        ProjectionMappingProfileV1(
            profile_id="duplicate",
            target=ProjectionTarget.AUTHZEN,
            native_profile_version="1",
            target_profile_version="1",
            definitions=(exact, exact.model_copy(update={"mapping_id": "other"})),
        )
    with pytest.raises(ValidationError, match="duplicate_projection_mapping_id"):
        ProjectionMappingProfileV1(
            profile_id="duplicate-id",
            target=ProjectionTarget.AUTHZEN,
            native_profile_version="1",
            target_profile_version="1",
            definitions=(
                exact,
                unsupported.model_copy(update={"mapping_id": exact.mapping_id}),
            ),
        )


def test_support_matrix_model_rejects_inventory_digest_and_version_drift() -> None:
    matrix = compile_shared_signals_support_matrix(shared_signals_mapping_profile_v1())
    document = matrix.model_dump()
    document["exercised_native_features"] = document["exercised_native_features"][:-1]
    with pytest.raises(ValidationError, match="support_inventory_mismatch"):
        ProjectionSupportMatrixV1.model_validate(document)
    document = matrix.model_dump()
    rows = list(matrix.rows)
    rows[0] = matrix.rows[0].model_copy(
        update={"mapping_digest": synthetic_digest(b"changed\n")}
    )
    document["rows"] = tuple(rows)
    with pytest.raises(ValidationError, match="mapping_digest_mismatch"):
        ProjectionSupportMatrixV1.model_validate(document)
    document = matrix.model_dump()
    rows = list(matrix.rows)
    rows[0] = matrix.rows[0].model_copy(update={"target_profile_version": "changed"})
    document["rows"] = tuple(rows)
    with pytest.raises(ValidationError, match="profile_version_mismatch"):
        ProjectionSupportMatrixV1.model_validate(document)

    exact = next(
        item
        for item in matrix.rows
        if item.classification is ProjectionSupportClassification.EXACT
    )
    document = exact.model_dump()
    document["semantic_delta"] = "unexpected loss"
    with pytest.raises(ValidationError, match="exact_support_row_has_semantic_delta"):
        ProjectionSupportRowV1.model_validate(document)
    nonexact = next(
        item
        for item in matrix.rows
        if item.classification is not ProjectionSupportClassification.EXACT
    )
    document = nonexact.model_dump()
    document["semantic_delta"] = None
    with pytest.raises(
        ValidationError, match="nonexact_support_row_requires_semantic_delta"
    ):
        ProjectionSupportRowV1.model_validate(document)


def test_scim_maps_accounts_only_and_never_imports_authorization_semantics() -> None:
    reference = reference_enterprise_authorization_inputs()
    universe = reference.rbac.universe_result.public_universe
    profile = scim_projection_profile_v1(snapshot_tick=0)
    projection = project_scim(
        universe=universe,
        directory_rbac_kernel=reference.rbac.kernel,
        profile=profile,
    )
    assert {item.source_account_id for item in projection.users} == {
        item.account_id for item in universe.accounts
    }
    assert len(projection.users) == len(universe.accounts)
    assert all(
        item.user_name.endswith("@accounts.example.invalid")
        for item in projection.users
    )
    assert all(
        item.roles == ()
        and item.entitlements == ()
        and item.authorization_semantics == "none"
        for item in projection.users
    )
    assert any(item.active for item in projection.users)
    expired = project_scim(
        universe=universe,
        directory_rbac_kernel=reference.rbac.kernel,
        profile=scim_projection_profile_v1(snapshot_tick=20),
    )
    assert not any(item.active for item in expired.users)

    observations = reference.rbac.kernel.account_observations
    omitted = observations[0].account_id
    without_observation = reference.rbac.kernel.model_copy(
        update={"account_observations": observations[1:]}
    )
    missing = project_scim(
        universe=universe,
        directory_rbac_kernel=without_observation,
        profile=profile,
    )
    assert not next(item for item in missing.users if item.user_id == omitted).active


def test_scim_ancestor_walk_is_cycle_safe_for_converging_paths() -> None:
    assert _ancestors(
        "child",
        {
            "child": {"parent-a", "parent-b"},
            "parent-a": {"root"},
            "parent-b": {"root"},
            "root": set(),
        },
    ) == ("child", "parent-a", "parent-b", "root")


def test_scim_distinguishes_direct_and_indirect_account_membership() -> None:
    reference = reference_enterprise_authorization_inputs()
    universe = reference.rbac.universe_result.public_universe
    child = reference.rbac.kernel.group_nesting[0].child_group_id
    account = universe.accounts[0]
    edge = DirectoryMembershipEdgeV1(
        edge_id="scim-account-membership",
        subject_id=account.account_id,
        group_id=child,
    )
    kernel = reference.rbac.kernel.model_copy(
        update={"memberships": (*reference.rbac.kernel.memberships, edge)}
    )
    projection = project_scim(
        universe=universe,
        directory_rbac_kernel=kernel,
        profile=scim_projection_profile_v1(snapshot_tick=0),
    )
    memberships = {
        item.membership_kind
        for group in projection.groups
        for item in group.members
        if item.user_id == account.account_id
    }
    assert memberships == {ScimMembershipKind.DIRECT, ScimMembershipKind.INDIRECT}
    duplicate = ScimGroupMemberProjectionV1(
        user_id=account.account_id,
        membership_kind=ScimMembershipKind.DIRECT,
    )
    with pytest.raises(ValidationError, match="duplicate_scim_group_member"):
        ScimGroupProjectionV1(
            group_id="group",
            display_name="Example Group",
            members=(duplicate, duplicate),
        )


def test_scim_profile_and_universe_bindings_fail_closed() -> None:
    reference = reference_enterprise_authorization_inputs()
    wrong_mapping = scim_projection_profile_v1(
        snapshot_tick=0
    ).mapping_profile.model_copy(update={"target": ProjectionTarget.AUTHZEN})
    with pytest.raises(ValidationError, match="scim_profile_mapping_target"):
        ScimProjectionProfileV1(
            snapshot_tick=0,
            provider_capabilities=(ScimProviderCapability.CORE_USER,),
            mapping_profile=wrong_mapping,
        )
    with pytest.raises(ValidationError, match="duplicate_scim_provider_capability"):
        ScimProjectionProfileV1(
            snapshot_tick=0,
            provider_capabilities=(
                ScimProviderCapability.CORE_USER,
                ScimProviderCapability.CORE_USER,
            ),
            mapping_profile=scim_projection_profile_v1(snapshot_tick=0).mapping_profile,
        )
    changed_kernel = reference.rbac.kernel.model_copy(
        update={"identity_access_universe_digest": synthetic_digest(b"changed\n")}
    )
    with pytest.raises(EnterpriseCompileError, match="scim_kernel_universe"):
        project_scim(
            universe=reference.rbac.universe_result.public_universe,
            directory_rbac_kernel=changed_kernel,
            profile=scim_projection_profile_v1(snapshot_tick=0),
        )


def test_authzen_projection_has_exact_field_provenance_and_no_oracle_answer() -> None:
    reference = reference_enterprise_authorization_inputs()
    universe = reference.rbac.universe_result.public_universe
    corpus = reference.rbac.corpus_result.public_corpus
    request = corpus.access_requests[0]
    projection = project_authzen(
        universe=universe,
        corpus=corpus,
        request=request,
        mapping_profile=authzen_mapping_profile_v1(),
    )
    assert projection.access_request_id == request.access_request_id
    assert {item.target_field for item in projection.field_provenance} == {
        "Action.id",
        "Context.context_id",
        "Context.logical_tick",
        "Context.session_state_id",
        "Resource.id",
        "Resource.type",
        "Subject.id",
        "Subject.type",
    }
    payload = canonical_json_bytes(projection)
    assert b"expected" not in payload
    assert b"final_decision" not in payload


@pytest.mark.parametrize(
    ("raw", "boolean", "normalized"),
    (
        (AuthZenRawOutcome.ALLOW, True, AuthorizationDecision.ALLOW),
        (AuthZenRawOutcome.DENY, False, AuthorizationDecision.DENY),
        (AuthZenRawOutcome.INDETERMINATE, None, None),
        (AuthZenRawOutcome.TRANSPORT_ERROR, None, None),
        (AuthZenRawOutcome.TIMEOUT, None, None),
        (AuthZenRawOutcome.UNAVAILABLE, None, None),
    ),
)
def test_authzen_raw_outcomes_are_retained_before_normalization(
    raw: AuthZenRawOutcome,
    boolean: bool | None,
    normalized: AuthorizationDecision | None,
) -> None:
    observation = AuthZenDecisionObservationV1(
        access_request_id="request",
        raw_outcome=raw,
        boolean_decision=boolean,
    )
    result = normalize_authzen_observation(observation)
    assert result.raw_outcome is raw
    assert result.raw_boolean_decision is boolean
    assert result.normalized_decision is normalized


def test_authzen_observation_and_mapping_fail_closed() -> None:
    with pytest.raises(ValidationError, match="raw_outcome_boolean_mismatch"):
        AuthZenDecisionObservationV1(
            access_request_id="request",
            raw_outcome=AuthZenRawOutcome.ALLOW,
            boolean_decision=False,
        )
    with pytest.raises(ValidationError, match="raw_outcome_boolean_mismatch"):
        AuthZenDecisionObservationV1(
            access_request_id="request",
            raw_outcome=AuthZenRawOutcome.TIMEOUT,
            boolean_decision=True,
        )
    profile = authzen_mapping_profile_v1()
    with pytest.raises(ValidationError, match="authzen_profile_mapping_target"):
        AuthZenMappingProfileV1(
            mapping_profile=profile.mapping_profile.model_copy(
                update={"target": ProjectionTarget.SCIM}
            )
        )
    reference = reference_enterprise_authorization_inputs()
    corpus = reference.rbac.corpus_result.public_corpus
    request = corpus.access_requests[0].model_copy(update={"cell_id": "absent"})
    with pytest.raises(EnterpriseCompileError, match="unknown_or_mismatched_request"):
        project_authzen(
            universe=reference.rbac.universe_result.public_universe,
            corpus=corpus,
            request=request,
            mapping_profile=profile,
        )
    changed_corpus = corpus.model_copy(
        update={"identity_access_universe_digest": synthetic_digest(b"changed\n")}
    )
    with pytest.raises(EnterpriseCompileError, match="authzen_corpus_universe"):
        project_authzen(
            universe=reference.rbac.universe_result.public_universe,
            corpus=changed_corpus,
            request=changed_corpus.access_requests[0],
            mapping_profile=profile,
        )

    valid = project_authzen(
        universe=reference.rbac.universe_result.public_universe,
        corpus=corpus,
        request=corpus.access_requests[0],
        mapping_profile=profile,
    )
    document = valid.model_dump()
    document["mapping_digest"] = synthetic_digest(b"changed\n")
    with pytest.raises(ValidationError, match="authzen_support_matrix_binding"):
        AuthZenRequestProjectionV1.model_validate(document)


def test_openfga_projection_uses_usersets_only_at_the_projection_boundary() -> None:
    reference = reference_enterprise_authorization_inputs()
    universe = reference.rbac.universe_result.public_universe
    actual = project_openfga(
        universe=universe,
        rebac_truth=reference.rebac_truth,
        mapping_profile=openfga_mapping_profile_v1(
            source_layer=AuthorizationSourceLayer.ACTUAL
        ),
    )
    intended = project_openfga(
        universe=universe,
        rebac_truth=reference.rebac_truth,
        mapping_profile=openfga_mapping_profile_v1(
            source_layer=AuthorizationSourceLayer.INTENDED
        ),
    )
    assert actual.source_layer is AuthorizationSourceLayer.ACTUAL
    assert intended.source_layer is AuthorizationSourceLayer.INTENDED
    assert len(actual.tuples) > len(intended.tuples)
    assert any(item.user.endswith("#member") for item in actual.tuples)
    assert all(
        "#member" not in item.subject_entity_id
        for item in reference.rebac_state.relation_tuples
    )
    assert {item.native_template for item in actual.rules} == set(
        reference_path.template for reference_path in reference.rebac_truth.paths
    )
    manager = next(
        item
        for item in actual.rules
        if item.native_template.value == "manager_of_owner"
    )
    assert manager.classification is ProjectionSupportClassification.APPROXIMATED
    assert manager.emitted


def test_openfga_profile_and_compiled_entity_bindings_fail_closed() -> None:
    reference = reference_enterprise_authorization_inputs()
    profile = openfga_mapping_profile_v1(source_layer=AuthorizationSourceLayer.ACTUAL)
    with pytest.raises(ValidationError, match="openfga_profile_mapping_target"):
        OpenFgaMappingProfileV1(
            source_layer=AuthorizationSourceLayer.ACTUAL,
            mapping_profile=profile.mapping_profile.model_copy(
                update={"target": ProjectionTarget.SCIM}
            ),
        )
    changed_truth = reference.rebac_truth.model_copy(
        update={"identity_access_universe_digest": synthetic_digest(b"changed\n")}
    )
    with pytest.raises(EnterpriseCompileError, match="openfga_truth_universe"):
        project_openfga(
            universe=reference.rbac.universe_result.public_universe,
            rebac_truth=changed_truth,
            mapping_profile=profile,
        )
    source_tuple = next(
        item
        for item in reference.rebac_truth.relation_tuples
        if item.source_layer is AuthorizationSourceLayer.ACTUAL
    )
    tuple_row = source_tuple.model_copy(update={"subject_entity_id": "absent"})
    broken = reference.rebac_truth.model_copy(
        update={
            "relation_tuples": tuple(
                tuple_row if item.tuple_id == tuple_row.tuple_id else item
                for item in reference.rebac_truth.relation_tuples
            )
        }
    )
    with pytest.raises(EnterpriseCompileError, match="openfga_unknown_entity"):
        project_openfga(
            universe=reference.rbac.universe_result.public_universe,
            rebac_truth=broken,
            mapping_profile=profile,
        )

    valid = project_openfga(
        universe=reference.rbac.universe_result.public_universe,
        rebac_truth=reference.rebac_truth,
        mapping_profile=profile,
    )
    document = valid.model_dump()
    document["mapping_digest"] = synthetic_digest(b"changed\n")
    with pytest.raises(ValidationError, match="openfga_support_matrix_binding"):
        OpenFgaProjectionV1.model_validate(document)


def test_projection_payloads_bind_their_support_matrices() -> None:
    reference = reference_enterprise_authorization_inputs()
    projection = project_scim(
        universe=reference.rbac.universe_result.public_universe,
        directory_rbac_kernel=reference.rbac.kernel,
        profile=scim_projection_profile_v1(snapshot_tick=0),
    )
    document = projection.model_dump()
    document["mapping_digest"] = synthetic_digest(b"changed\n")
    with pytest.raises(ValidationError, match="scim_support_matrix_binding"):
        ScimProjectionV1.model_validate(document)


def test_shared_signals_profile_defers_temporal_emission_to_pr7() -> None:
    profile = shared_signals_mapping_profile_v1()
    assert profile.temporal_base_version == "synthworld-temporal-1.1.0"
    assert profile.schedule_view_status == "deferred_to_pr7"
    assert profile.emitted_event_projection == "deferred"
    matrix = compile_shared_signals_support_matrix(profile)
    domain = next(
        item
        for item in matrix.rows
        if item.native_source_feature == "domain_policy_change_as_caep"
    )
    assert domain.classification is ProjectionSupportClassification.UNSUPPORTED
    with pytest.raises(ValidationError, match="shared_signals_profile_mapping_target"):
        SharedSignalsMappingProfileV1(
            mapping_profile=profile.mapping_profile.model_copy(
                update={"target": ProjectionTarget.AUTHZEN}
            )
        )


def _coverage_manifest() -> PolicyCoverageManifestV1:
    covered = CoverageTupleV1(
        tuple_id="covered",
        factor_values=(
            CoverageFactorValueV1(factor="effect", value="allow"),
            CoverageFactorValueV1(factor="outcome", value="true"),
        ),
    )
    unreachable = CoverageTupleV1(
        tuple_id="unreachable",
        factor_values=(
            CoverageFactorValueV1(factor="effect", value="deny"),
            CoverageFactorValueV1(factor="outcome", value="unknown"),
        ),
    )
    return PolicyCoverageManifestV1(
        suite_id="abac-pairwise",
        seed=20260804,
        interaction_strength=2,
        factors=(
            CoverageFactorV1(name="effect", levels=("allow", "deny")),
            CoverageFactorV1(name="outcome", levels=("true", "unknown")),
        ),
        constraints=(
            CoverageConstraintV1(
                constraint_id="unreachable-combination",
                unreachable_tuple_ids=(unreachable.tuple_id,),
                rationale="The selected mutation cannot produce this pair.",
            ),
        ),
        covered_tuples=(covered,),
        unreachable_tuples=(unreachable,),
        conformance_vector_ids=("abac-effect-outcome",),
    )


def test_coverage_manifest_records_factors_constraints_seed_and_nonexhaustion() -> None:
    manifest = _coverage_manifest()
    assert manifest.seed == 20260804
    assert manifest.interaction_strength == 2
    assert not manifest.exhaustive
    assert manifest.covered_tuples[0].tuple_id == "covered"
    assert manifest.unreachable_tuples[0].tuple_id == "unreachable"


@pytest.mark.parametrize(
    ("update", "match"),
    (
        ({"interaction_strength": 3}, "strength_exceeds_factor_count"),
        ({"covered_tuples": ()}, "constraint_inventory_mismatch"),
    ),
)
def test_coverage_manifest_rejects_incoherent_claims(
    update: dict[str, object], match: str
) -> None:
    manifest = _coverage_manifest()
    document = manifest.model_dump()
    document.update(update)
    if match == "constraint_inventory_mismatch":
        document["unreachable_tuples"] = ()
    with pytest.raises(ValidationError, match=match):
        PolicyCoverageManifestV1.model_validate(document)


def test_coverage_manifest_rejects_overlap_strength_unknown_factor_and_level() -> None:
    manifest = _coverage_manifest()
    document = manifest.model_dump()
    document["unreachable_tuples"] = document["covered_tuples"]
    document["constraints"] = (
        CoverageConstraintV1(
            constraint_id="overlap",
            unreachable_tuple_ids=("covered",),
            rationale="invalid overlap",
        ),
    )
    with pytest.raises(ValidationError, match="both_covered_and_unreachable"):
        PolicyCoverageManifestV1.model_validate(document)

    for pair, match in (
        ((CoverageFactorValueV1(factor="effect", value="allow"),), "strength_mismatch"),
        (
            (
                CoverageFactorValueV1(factor="absent", value="allow"),
                CoverageFactorValueV1(factor="outcome", value="true"),
            ),
            "unknown_factor",
        ),
        (
            (
                CoverageFactorValueV1(factor="effect", value="other"),
                CoverageFactorValueV1(factor="outcome", value="true"),
            ),
            "unknown_level",
        ),
    ):
        document = manifest.model_dump()
        document["covered_tuples"] = (
            CoverageTupleV1(tuple_id="changed", factor_values=pair),
        )
        with pytest.raises(ValidationError, match=match):
            PolicyCoverageManifestV1.model_validate(document)


def test_conformance_vectors_bind_the_pinned_standards_ledger() -> None:
    vector = AuthorizationConformanceVectorV1(
        vector_id="authzen-subject",
        standards_source_id="authzen-authorization-api-1.0",
        native_feature="subject_identity",
        expected_semantics="Subject type and ID preserve exact provenance.",
    )
    assert validate_conformance_vectors(
        (vector,), standards_source_ids={vector.standards_source_id}
    ) == (vector,)
    with pytest.raises(ValueError, match="unknown_standards_source"):
        validate_conformance_vectors((vector,), standards_source_ids=set())
    with pytest.raises(ValueError, match="duplicate_authorization_conformance"):
        validate_conformance_vectors(
            (vector, vector), standards_source_ids={vector.standards_source_id}
        )


def test_generated_projection_contracts_are_checked_in() -> None:
    root = Path("enterprise-identity-access-contract/schemas")
    expected = {
        "authzen-request-projection.schema.json",
        "openfga-projection.schema.json",
        "projection-support-matrix.schema.json",
        "scim-projection.schema.json",
        "shared-signals-mapping-profile.schema.json",
    }
    assert expected <= {item.name for item in root.iterdir()}
