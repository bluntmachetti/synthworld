"""Pure RFC 7643-style account and group projection."""

from __future__ import annotations

from collections import defaultdict
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.compiler import EnterpriseCompileError
from synthworld.enterprise.models import (
    AdministrativeState,
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
from synthworld.enterprise.rbac.common import (
    canonical_synthetic_records,
)
from synthworld.enterprise.rbac.models import (
    DirectoryAccountObservationV1,
    EnterpriseDirectoryRbacKernelV1,
)
from synthworld.models import SyntheticModel

SCIM_PROJECTION_PROFILE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
SCIM_PROJECTION_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
SCIM_PROJECTION_COMPILER_VERSION: Literal["1.0.0"] = "1.0.0"

SCIM_NATIVE_FEATURES = (
    "account_active",
    "account_to_user",
    "direct_group_membership",
    "entitlements_authorization_semantics",
    "group_resource",
    "indirect_group_membership",
    "membership_authorization_semantics",
    "roles_authorization_semantics",
)


class ScimProviderCapability(StrEnum):
    CORE_USER = "core_user"
    CORE_GROUP = "core_group"
    PATCH = "patch"
    FILTER = "filter"
    BULK = "bulk"


class ScimMembershipKind(StrEnum):
    DIRECT = "direct"
    INDIRECT = "indirect"


class ScimProjectionProfileV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = SCIM_PROJECTION_PROFILE_SCHEMA_VERSION
    snapshot_tick: int = Field(ge=0)
    provider_capabilities: tuple[ScimProviderCapability, ...] = Field(min_length=1)
    mapping_profile: ProjectionMappingProfileV1

    @field_validator("provider_capabilities")
    @classmethod
    def canonical_capabilities(
        cls, value: tuple[ScimProviderCapability, ...]
    ) -> tuple[ScimProviderCapability, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.value))
        if len(ordered) != len(set(ordered)):
            raise ValueError("duplicate_scim_provider_capability")
        return ordered

    @model_validator(mode="after")
    def correct_target(self) -> Self:
        if self.mapping_profile.target is not ProjectionTarget.SCIM:
            raise ValueError("scim_profile_mapping_target_mismatch")
        return self


class ScimUserProjectionV1(SyntheticModel):
    user_id: str
    source_account_id: str
    user_name: str
    active: bool
    roles: tuple[str, ...] = ()
    entitlements: tuple[str, ...] = ()
    authorization_semantics: Literal["none"] = "none"


class ScimGroupMemberProjectionV1(SyntheticModel):
    user_id: str
    membership_kind: ScimMembershipKind


class ScimGroupProjectionV1(SyntheticModel):
    group_id: str
    display_name: str
    members: tuple[ScimGroupMemberProjectionV1, ...]

    @field_validator("members")
    @classmethod
    def canonical_members(
        cls, value: tuple[ScimGroupMemberProjectionV1, ...]
    ) -> tuple[ScimGroupMemberProjectionV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.user_id, item.membership_kind.value) for item in value),
            description="scim_group_member",
        )


class ScimProjectionV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = SCIM_PROJECTION_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = SCIM_PROJECTION_COMPILER_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    directory_rbac_kernel_digest: SyntheticDigestV1
    snapshot_tick: int = Field(ge=0)
    provider_capabilities: tuple[ScimProviderCapability, ...]
    mapping_digest: SyntheticDigestV1
    support_matrix: ProjectionSupportMatrixV1
    users: tuple[ScimUserProjectionV1, ...]
    groups: tuple[ScimGroupProjectionV1, ...]

    @field_validator("users", "groups")
    @classmethod
    def canonical_resources(
        cls, value: tuple[SyntheticModel, ...]
    ) -> tuple[SyntheticModel, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple(
                (
                    item.user_id
                    if isinstance(item, ScimUserProjectionV1)
                    else item.group_id,
                )
                for item in value
                if isinstance(item, ScimUserProjectionV1 | ScimGroupProjectionV1)
            ),
            description="scim_resource_id",
        )

    @model_validator(mode="after")
    def mapping_matches_matrix(self) -> Self:
        if (
            self.support_matrix.target is not ProjectionTarget.SCIM
            or self.support_matrix.mapping_digest != self.mapping_digest
        ):
            raise ValueError("scim_support_matrix_binding_mismatch")
        return self


def scim_projection_profile_v1(*, snapshot_tick: int) -> ScimProjectionProfileV1:
    return ScimProjectionProfileV1(
        snapshot_tick=snapshot_tick,
        provider_capabilities=(
            ScimProviderCapability.CORE_USER,
            ScimProviderCapability.CORE_GROUP,
            ScimProviderCapability.FILTER,
            ScimProviderCapability.PATCH,
        ),
        mapping_profile=ProjectionMappingProfileV1(
            profile_id="synthworld-scim-core-projection",
            target=ProjectionTarget.SCIM,
            native_profile_version="enterprise-authorization-1.0.0",
            target_profile_version="rfc7643-rfc7644-2015",
            definitions=(
                _mapping("account_active", "User.active", "approx", "scim-active"),
                _mapping("account_to_user", "User", "exact", "scim-user"),
                _mapping(
                    "direct_group_membership",
                    "Group.members",
                    "exact",
                    "scim-direct-group",
                ),
                _mapping(
                    "entitlements_authorization_semantics",
                    "User.entitlements",
                    "unsupported",
                    "scim-entitlements",
                ),
                _mapping("group_resource", "Group", "exact", "scim-group"),
                _mapping(
                    "indirect_group_membership",
                    "SynthWorld membership provenance",
                    "approx",
                    "scim-indirect-group",
                ),
                _mapping(
                    "membership_authorization_semantics",
                    "Group.members",
                    "unsupported",
                    "scim-membership-authz",
                ),
                _mapping(
                    "roles_authorization_semantics",
                    "User.roles",
                    "unsupported",
                    "scim-roles",
                ),
            ),
        ),
    )


def project_scim(
    *,
    universe: EnterpriseIdentityAccessUniverseV1,
    directory_rbac_kernel: EnterpriseDirectoryRbacKernelV1,
    profile: ScimProjectionProfileV1,
) -> ScimProjectionV1:
    """Project accounts and groups without importing SCIM authorization semantics."""

    universe_digest = synthetic_digest(canonical_json_bytes(universe))
    if directory_rbac_kernel.identity_access_universe_digest != universe_digest:
        raise EnterpriseCompileError(
            "scim_kernel_universe_digest_mismatch",
            "directory/RBAC kernel does not bind the supplied universe",
        )
    matrix = compile_projection_support_matrix(
        profile=profile.mapping_profile,
        exercised_native_features=SCIM_NATIVE_FEATURES,
    )
    observations = {
        item.account_id: item for item in directory_rbac_kernel.account_observations
    }
    users = tuple(
        ScimUserProjectionV1(
            user_id=item.account_id,
            source_account_id=item.account_id,
            user_name=f"{item.account_id}@accounts.example.invalid",
            active=_account_active(
                observations.get(item.account_id), profile.snapshot_tick
            ),
        )
        for item in universe.accounts
    )
    account_ids = {item.account_id for item in universe.accounts}
    parents: dict[str, set[str]] = defaultdict(set)
    for nesting_edge in directory_rbac_kernel.group_nesting:
        parents[nesting_edge.child_group_id].add(nesting_edge.parent_group_id)
    members: dict[str, set[tuple[str, ScimMembershipKind]]] = defaultdict(set)
    for membership_edge in directory_rbac_kernel.memberships:
        if membership_edge.subject_id not in account_ids:
            continue
        members[membership_edge.group_id].add(
            (membership_edge.subject_id, ScimMembershipKind.DIRECT)
        )
        for ancestor in _ancestors(membership_edge.group_id, parents):
            if ancestor != membership_edge.group_id:
                members[ancestor].add(
                    (membership_edge.subject_id, ScimMembershipKind.INDIRECT)
                )
    groups = tuple(
        ScimGroupProjectionV1(
            group_id=item.group_id,
            display_name=item.display_label,
            members=tuple(
                ScimGroupMemberProjectionV1(user_id=user_id, membership_kind=kind)
                for user_id, kind in sorted(
                    members[item.group_id], key=lambda pair: (pair[0], pair[1].value)
                )
            ),
        )
        for item in universe.groups
    )
    return ScimProjectionV1(
        identity_access_universe_digest=universe_digest,
        directory_rbac_kernel_digest=synthetic_digest(
            canonical_json_bytes(directory_rbac_kernel)
        ),
        snapshot_tick=profile.snapshot_tick,
        provider_capabilities=profile.provider_capabilities,
        mapping_digest=matrix.mapping_digest,
        support_matrix=matrix,
        users=users,
        groups=groups,
    )


def _account_active(
    observation: DirectoryAccountObservationV1 | None, tick: int
) -> bool:
    if observation is None:
        return False
    return bool(
        observation.administrative_state is AdministrativeState.ACTIVE
        and tick >= observation.valid_from_tick
        and (
            observation.valid_until_tick is None or tick < observation.valid_until_tick
        )
    )


def _ancestors(group_id: str, parents: dict[str, set[str]]) -> tuple[str, ...]:
    seen = {group_id}
    pending = [group_id]
    while pending:
        current = pending.pop()
        for parent in sorted(parents[current]):
            if parent not in seen:
                seen.add(parent)
                pending.append(parent)
    return tuple(sorted(seen))


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
        "account_active": (
            "A point-in-time SCIM boolean cannot carry the native revision interval."
        ),
        "indirect_group_membership": (
            "RFC 7643 Group.members does not distinguish inherited membership."
        ),
        "entitlements_authorization_semantics": (
            "SCIM entitlement values do not define native authorization truth."
        ),
        "membership_authorization_semantics": (
            "SCIM group membership is provisioning data, not kernel authorization."
        ),
        "roles_authorization_semantics": (
            "SCIM role values do not define native RBAC role semantics."
        ),
    }
    return ProjectionMappingDefinitionV1(
        mapping_id=f"scim-{feature}",
        native_source_feature=feature,
        target_construct=target,
        classification=classification,
        semantic_delta=deltas.get(feature),
        conformance_vector_ids=(vector,),
    )


__all__ = [
    "SCIM_NATIVE_FEATURES",
    "ScimProjectionProfileV1",
    "ScimProjectionV1",
    "project_scim",
    "scim_projection_profile_v1",
]
