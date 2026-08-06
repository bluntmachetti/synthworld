"""Pure OpenFGA model/tuple projection of the bounded native ReBAC subset."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import field_validator, model_validator

from synthworld.enterprise.authorization_common import AuthorizationSourceLayer
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.compiler import EnterpriseCompileError
from synthworld.enterprise.models import (
    EnterpriseIdentityAccessUniverseV1,
    EnterpriseOperatorModel,
    SyntheticDigestV1,
)
from synthworld.enterprise.projections.support import (
    ProjectionMappingDefinitionV1,
    ProjectionMappingProfileV1,
    ProjectionSupportClassification,
    ProjectionSupportMatrixV1,
    ProjectionTarget,
    compile_projection_support_matrix,
)
from synthworld.enterprise.rbac.common import canonical_synthetic_records
from synthworld.enterprise.rebac.common import RebacRelation, RebacTemplateKind
from synthworld.enterprise.rebac.models import CompiledEnterpriseRebacTruthV1
from synthworld.models import SyntheticModel

OPENFGA_MAPPING_PROFILE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
OPENFGA_PROJECTION_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
OPENFGA_PROJECTION_COMPILER_VERSION: Literal["1.0.0"] = "1.0.0"

OPENFGA_NATIVE_FEATURES = (
    "relation_collaborates_on",
    "relation_manages",
    "relation_member_of",
    "relation_owns",
    "snapshot_and_validity_semantics",
    "template_direct_subject_relation",
    "template_group_collaboration",
    "template_manager_of_owner",
)


class OpenFgaMappingProfileV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = OPENFGA_MAPPING_PROFILE_SCHEMA_VERSION
    source_layer: AuthorizationSourceLayer
    mapping_profile: ProjectionMappingProfileV1

    @model_validator(mode="after")
    def correct_target(self) -> Self:
        if self.mapping_profile.target is not ProjectionTarget.OPENFGA:
            raise ValueError("openfga_profile_mapping_target_mismatch")
        return self


class OpenFgaAuthorizationModelV1(SyntheticModel):
    schema_version: Literal["1.1"] = "1.1"
    type_definitions: tuple[str, ...]


class OpenFgaTupleProjectionV1(SyntheticModel):
    tuple_id: str
    user: str
    relation: str
    object: str
    native_relation: RebacRelation
    native_snapshot_id: str
    native_revision_id: str
    native_valid_from_tick: int
    native_valid_until_tick: int | None


class OpenFgaRuleProjectionV1(SyntheticModel):
    native_template: RebacTemplateKind
    target_construct: str
    classification: ProjectionSupportClassification
    emitted: bool


class OpenFgaProjectionV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = OPENFGA_PROJECTION_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = OPENFGA_PROJECTION_COMPILER_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    rebac_truth_digest: SyntheticDigestV1
    source_layer: AuthorizationSourceLayer
    mapping_digest: SyntheticDigestV1
    support_matrix: ProjectionSupportMatrixV1
    authorization_model: OpenFgaAuthorizationModelV1
    tuples: tuple[OpenFgaTupleProjectionV1, ...]
    rules: tuple[OpenFgaRuleProjectionV1, ...]

    @field_validator("tuples", "rules")
    @classmethod
    def canonical_projection_records(
        cls, value: tuple[SyntheticModel, ...]
    ) -> tuple[SyntheticModel, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple(
                (
                    item.tuple_id
                    if isinstance(item, OpenFgaTupleProjectionV1)
                    else item.native_template.value,
                )
                for item in value
                if isinstance(item, OpenFgaTupleProjectionV1 | OpenFgaRuleProjectionV1)
            ),
            description="openfga_projection_record",
        )

    @model_validator(mode="after")
    def mapping_matches_matrix(self) -> Self:
        if (
            self.support_matrix.target is not ProjectionTarget.OPENFGA
            or self.support_matrix.mapping_digest != self.mapping_digest
        ):
            raise ValueError("openfga_support_matrix_binding_mismatch")
        return self


def openfga_mapping_profile_v1(
    *, source_layer: AuthorizationSourceLayer
) -> OpenFgaMappingProfileV1:
    return OpenFgaMappingProfileV1(
        source_layer=source_layer,
        mapping_profile=ProjectionMappingProfileV1(
            profile_id="synthworld-openfga-projection",
            target=ProjectionTarget.OPENFGA,
            native_profile_version="synthworld-bounded-rebac-1.0.0",
            target_profile_version="openfga-model-schema-1.1",
            definitions=(
                _mapping(
                    "relation_collaborates_on",
                    "authorization_target#collaborates_on",
                    "exact",
                    "openfga-collaboration",
                ),
                _mapping(
                    "relation_manages",
                    "principal#manages",
                    "exact",
                    "openfga-manages",
                ),
                _mapping(
                    "relation_member_of",
                    "group#member",
                    "exact",
                    "openfga-member",
                ),
                _mapping(
                    "relation_owns",
                    "authorization_target#owner",
                    "exact",
                    "openfga-owner",
                ),
                _mapping(
                    "snapshot_and_validity_semantics",
                    "tuple metadata only",
                    "unsupported",
                    "openfga-snapshot",
                ),
                _mapping(
                    "template_direct_subject_relation",
                    "direct relation check",
                    "exact",
                    "openfga-direct",
                ),
                _mapping(
                    "template_group_collaboration",
                    "group#member userset",
                    "exact",
                    "openfga-userset",
                ),
                _mapping(
                    "template_manager_of_owner",
                    "tuple-to-userset relation chain",
                    "approx",
                    "openfga-manager-owner",
                ),
            ),
        ),
    )


def project_openfga(
    *,
    universe: EnterpriseIdentityAccessUniverseV1,
    rebac_truth: CompiledEnterpriseRebacTruthV1,
    mapping_profile: OpenFgaMappingProfileV1,
) -> OpenFgaProjectionV1:
    """Map compiled tuples and named templates; execute no external model."""

    universe_digest = synthetic_digest(canonical_json_bytes(universe))
    if rebac_truth.identity_access_universe_digest != universe_digest:
        raise EnterpriseCompileError(
            "openfga_truth_universe_digest_mismatch",
            "ReBAC truth does not bind the supplied universe",
        )
    matrix = compile_projection_support_matrix(
        profile=mapping_profile.mapping_profile,
        exercised_native_features=OPENFGA_NATIVE_FEATURES,
    )
    entity_kinds = _entity_kinds(universe)
    selected_tuples = tuple(
        item
        for item in rebac_truth.relation_tuples
        if item.source_layer is mapping_profile.source_layer
    )
    tuples = tuple(
        OpenFgaTupleProjectionV1(
            tuple_id=item.tuple_id,
            user=_project_user(
                item.subject_entity_id,
                entity_kinds,
                userset=(
                    item.relation is RebacRelation.COLLABORATES_ON
                    and entity_kinds[item.subject_entity_id] == "group"
                ),
            ),
            relation=_target_relation(item.relation),
            object=_typed_entity(item.object_entity_id, entity_kinds),
            native_relation=item.relation,
            native_snapshot_id=item.snapshot_id,
            native_revision_id=item.revision_id,
            native_valid_from_tick=item.valid_from_tick,
            native_valid_until_tick=item.valid_until_tick,
        )
        for item in selected_tuples
    )
    templates = {
        item.template
        for item in rebac_truth.rule_truth
        if item.source_layer is mapping_profile.source_layer
    }
    support_by_feature = {item.native_source_feature: item for item in matrix.rows}
    rules = tuple(
        OpenFgaRuleProjectionV1(
            native_template=template,
            target_construct=support_by_feature[
                f"template_{template.value}"
            ].target_construct,
            classification=support_by_feature[
                f"template_{template.value}"
            ].classification,
            emitted=(
                support_by_feature[f"template_{template.value}"].classification
                is not ProjectionSupportClassification.UNSUPPORTED
            ),
        )
        for template in sorted(templates, key=lambda item: item.value)
    )
    return OpenFgaProjectionV1(
        identity_access_universe_digest=universe_digest,
        rebac_truth_digest=synthetic_digest(canonical_json_bytes(rebac_truth)),
        source_layer=mapping_profile.source_layer,
        mapping_digest=matrix.mapping_digest,
        support_matrix=matrix,
        authorization_model=OpenFgaAuthorizationModelV1(
            type_definitions=(
                "account",
                "authorization_target",
                "group:member",
                "principal:manages",
                "unit",
            )
        ),
        tuples=tuples,
        rules=rules,
    )


def _entity_kinds(universe: EnterpriseIdentityAccessUniverseV1) -> dict[str, str]:
    result: dict[str, str] = {}
    result.update((item.principal_id, "principal") for item in universe.principals)
    result.update((item.account_id, "account") for item in universe.accounts)
    result.update((item.group_id, "group") for item in universe.groups)
    result.update((item.unit_id, "unit") for item in universe.units)
    result.update(
        (item.authorization_target_id, "authorization_target")
        for item in universe.authorization_targets
    )
    return result


def _project_user(
    entity_id: str, entity_kinds: dict[str, str], *, userset: bool
) -> str:
    value = _typed_entity(entity_id, entity_kinds)
    return f"{value}#member" if userset else value


def _typed_entity(entity_id: str, entity_kinds: dict[str, str]) -> str:
    try:
        return f"{entity_kinds[entity_id]}:{entity_id}"
    except KeyError as error:
        raise EnterpriseCompileError(
            "openfga_unknown_entity",
            "compiled ReBAC tuple references an absent universe entity",
        ) from error


def _target_relation(relation: RebacRelation) -> str:
    return {
        RebacRelation.MEMBER_OF: "member",
        RebacRelation.OWNS: "owner",
        RebacRelation.MANAGES: "manages",
        RebacRelation.COLLABORATES_ON: "collaborates_on",
    }[relation]


def _mapping(
    feature: str,
    target: str,
    support: Literal["exact", "approx", "unsupported"],
    vector: str,
) -> ProjectionMappingDefinitionV1:
    classification = {
        "exact": ProjectionSupportClassification.EXACT,
        "approx": ProjectionSupportClassification.APPROXIMATED,
        "unsupported": ProjectionSupportClassification.UNSUPPORTED,
    }[support]
    deltas = {
        "snapshot_and_validity_semantics": (
            "OpenFGA tuples emitted by this profile carry no native interval or "
            "snapshot enforcement."
        ),
        "template_manager_of_owner": (
            "The projected chain does not preserve the native human-principal "
            "and same-snapshot guards."
        ),
    }
    return ProjectionMappingDefinitionV1(
        mapping_id=f"openfga-{feature}",
        native_source_feature=feature,
        target_construct=target,
        classification=classification,
        semantic_delta=deltas.get(feature),
        conformance_vector_ids=(vector,),
    )


__all__ = [
    "OPENFGA_NATIVE_FEATURES",
    "OpenFgaMappingProfileV1",
    "OpenFgaProjectionV1",
    "openfga_mapping_profile_v1",
    "project_openfga",
]
