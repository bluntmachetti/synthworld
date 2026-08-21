"""Versioned contracts for generated enterprise-agentic scale tiers.

The released ``enterprise-agentic-generated-1.0.0`` family is intentionally
smoke-only.  These V2 records add scale and lifecycle semantics without widening
any V1 literal or the frozen base agentic event union.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.agentic.enterprise.generated_models import (
    EnterpriseAgenticArtifactDescriptorV1,
    EnterpriseAgenticCountMetricV1,
    EnterpriseAgenticDistributionBinV1,
)
from synthworld.agentic.models import (
    AgenticBenchmark,
    AgenticEvaluatorBundle,
    AgenticPublicBundle,
    CredentialIssued,
    DelegationGranted,
)
from synthworld.enterprise.canonical import canonical_json_bytes
from synthworld.models import SyntheticModel

ENTERPRISE_AGENTIC_SCALE_CONFIG_SCHEMA_VERSION: Literal["2.0.0"] = "2.0.0"
ENTERPRISE_AGENTIC_SCALE_PROFILE_VERSION: Literal[
    "enterprise-agentic-generated-2.0.0"
] = "enterprise-agentic-generated-2.0.0"
ENTERPRISE_AGENTIC_SCALE_GENERATOR_VERSION: Literal["2.0.0"] = "2.0.0"
ENTERPRISE_AGENTIC_SCALE_SERIALIZATION_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AGENTIC_STANDARD_EVENT_SCHEDULE_VERSION: Literal["standard-2.0.0"] = (
    "standard-2.0.0"
)
ENTERPRISE_AGENTIC_LONGITUDINAL_EVENT_SCHEDULE_VERSION: Literal[
    "longitudinal-2.0.0"
] = "longitudinal-2.0.0"
ENTERPRISE_AGENTIC_SCALE_ARTIFACT_SCHEMA_VERSION: Literal["2.0.0"] = "2.0.0"
ENTERPRISE_AGENTIC_SCALE_METRICS_SCHEMA_VERSION: Literal["2.0.0"] = "2.0.0"
ENTERPRISE_AGENTIC_PERFORMANCE_RECEIPT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"


class EnterpriseAgenticScaleTierV2(StrEnum):
    """Scale tiers introduced after the frozen generated smoke V1 family."""

    STANDARD = "standard"
    LONGITUDINAL = "longitudinal"


class EnterpriseAgenticPopulationKindV2(StrEnum):
    EMPLOYEE = "employee"
    CONTRACTOR = "contractor"
    SUPPLIER = "supplier"
    EXTERNAL_PARTNER = "external_partner"


class EnterpriseAgenticLifecycleCaseKindV2(StrEnum):
    AUTHORISED_ACTION = "authorised_action"
    EXCESSIVE_CAPABILITY = "excessive_capability"
    OVERPRIVILEGED_CHILD_DELEGATION = "overprivileged_child_delegation"
    WRONG_RUNTIME = "wrong_runtime"
    SHARED_CREDENTIAL_REUSE = "shared_credential_reuse"
    CROSS_TENANT_CONFUSION = "cross_tenant_confusion"
    VALID_THEN_REVOKED = "valid_then_revoked"
    INVALID_THEN_LATER_GRANTED = "invalid_then_later_granted"
    EVIDENCE_LOSS = "evidence_loss"
    INCORRECT_ATTRIBUTION = "incorrect_attribution"
    EXPIRED_CREDENTIAL = "expired_credential"
    POLICY_VERSION_DRIFT = "policy_version_drift"
    ROTATED_CREDENTIAL_REUSE = "rotated_credential_reuse"
    SUSPENDED_CREDENTIAL = "suspended_credential"
    AGENT_OFFBOARDING_ACTIVE_CREDENTIAL = "agent_offboarding_active_credential"
    REVOCATION_PROPAGATION_FAILURE = "revocation_propagation_failure"


class EnterpriseAgenticCredentialLifecycleStateV2(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class EnterpriseAgenticAgentLifecycleStateV2(StrEnum):
    ACTIVE = "active"
    OFFBOARDED = "offboarded"


class EnterpriseAgenticPersonLifecycleStateV2(StrEnum):
    JOINED = "joined"
    MOVED = "moved"
    LEFT = "left"


class EnterpriseAgenticScaleTopologyV2(SyntheticModel):
    """Resolved organisation and identity counts for a generated scale world."""

    organisation_count: int = Field(default=2, strict=True, ge=1, le=3)
    departments_per_organisation: int = Field(default=4, strict=True, ge=2, le=12)
    teams_per_department: int = Field(default=2, strict=True, ge=1, le=6)
    employee_count: int = Field(default=220, strict=True, ge=12, le=5_000)
    contractor_count: int = Field(default=20, strict=True, ge=0, le=1_000)
    supplier_count: int = Field(default=6, strict=True, ge=0, le=500)
    external_partner_count: int = Field(default=4, strict=True, ge=0, le=500)
    logical_agent_count: int = Field(default=36, strict=True, ge=10, le=500)
    runtime_count: int = Field(default=72, strict=True, ge=10, le=1_500)
    resource_count: int = Field(default=36, strict=True, ge=6, le=1_000)

    @property
    def human_principal_count(self) -> int:
        return (
            self.employee_count
            + self.contractor_count
            + self.supplier_count
            + self.external_partner_count
        )

    @model_validator(mode="after")
    def require_representable_topology(self) -> Self:
        if self.human_principal_count < self.logical_agent_count:
            raise ValueError("logical agents cannot outnumber accountable humans")
        if self.runtime_count < self.logical_agent_count:
            raise ValueError("every logical agent requires at least one runtime")
        if self.resource_count < self.organisation_count * 3:
            raise ValueError("every organisation requires at least three resources")
        return self


class EnterpriseAgenticAuthorityTopologyV2(SyntheticModel):
    direct_human_delegation_ratio: float = Field(
        default=0.55, strict=True, ge=0.0, le=1.0
    )
    organisation_delegation_ratio: float = Field(
        default=0.20, strict=True, ge=0.0, le=1.0
    )
    agent_subdelegation_ratio: float = Field(default=0.25, strict=True, ge=0.0, le=1.0)
    maximum_delegation_depth: int = Field(default=3, strict=True, ge=2, le=4)
    capability_resource_breadth: int = Field(default=2, strict=True, ge=1, le=8)
    capability_scope_density: int = Field(default=2, strict=True, ge=1, le=6)

    @model_validator(mode="after")
    def require_complete_delegation_mix(self) -> Self:
        total = (
            self.direct_human_delegation_ratio
            + self.organisation_delegation_ratio
            + self.agent_subdelegation_ratio
        )
        if abs(total - 1.0) > 1e-12:
            raise ValueError("delegation ratios must sum to one")
        return self


class EnterpriseAgenticCredentialTopologyV2(SyntheticModel):
    validity_days: int = Field(default=365, strict=True, ge=30, le=2_000)
    shared_identity_prevalence: float = Field(default=0.10, strict=True, ge=0.0, le=0.5)
    allowed_runtimes_per_shared_credential: int = Field(
        default=2, strict=True, ge=2, le=32
    )


class EnterpriseAgenticScenarioPrevalenceV2(SyntheticModel):
    authorised_action: int = Field(default=4, strict=True, ge=1, le=1_000)
    excessive_capability: int = Field(default=3, strict=True, ge=0, le=1_000)
    overprivileged_child_delegation: int = Field(default=2, strict=True, ge=0, le=1_000)
    wrong_runtime: int = Field(default=2, strict=True, ge=0, le=1_000)
    shared_credential_reuse: int = Field(default=2, strict=True, ge=0, le=1_000)
    cross_tenant_confusion: int = Field(default=2, strict=True, ge=0, le=1_000)
    valid_then_revoked: int = Field(default=2, strict=True, ge=0, le=1_000)
    invalid_then_later_granted: int = Field(default=1, strict=True, ge=0, le=1_000)
    evidence_loss: int = Field(default=1, strict=True, ge=0, le=1_000)
    incorrect_attribution: int = Field(default=1, strict=True, ge=0, le=1_000)
    expired_credential: int = Field(default=2, strict=True, ge=0, le=1_000)
    policy_version_drift: int = Field(default=1, strict=True, ge=0, le=1_000)
    rotated_credential_reuse: int = Field(default=0, strict=True, ge=0, le=1_000)
    suspended_credential: int = Field(default=0, strict=True, ge=0, le=1_000)
    agent_offboarding_active_credential: int = Field(
        default=0, strict=True, ge=0, le=1_000
    )
    revocation_propagation_failure: int = Field(default=0, strict=True, ge=0, le=1_000)

    @property
    def total(self) -> int:
        return sum(
            (
                self.authorised_action,
                self.excessive_capability,
                self.overprivileged_child_delegation,
                self.wrong_runtime,
                self.shared_credential_reuse,
                self.cross_tenant_confusion,
                self.valid_then_revoked,
                self.invalid_then_later_granted,
                self.evidence_loss,
                self.incorrect_attribution,
                self.expired_credential,
                self.policy_version_drift,
                self.rotated_credential_reuse,
                self.suspended_credential,
                self.agent_offboarding_active_credential,
                self.revocation_propagation_failure,
            )
        )


class EnterpriseAgenticLongitudinalScheduleV2(SyntheticModel):
    virtual_duration_days: int = Field(default=180, strict=True, ge=30, le=2_000)
    credential_rotation_interval_days: int = Field(
        default=45, strict=True, ge=7, le=365
    )
    evidence_retention_days: int = Field(default=90, strict=True, ge=7, le=1_000)
    policy_change_day: int = Field(default=90, strict=True, ge=2, le=1_999)
    agent_offboarding_day: int = Field(default=120, strict=True, ge=3, le=1_999)

    @model_validator(mode="after")
    def require_events_within_duration(self) -> Self:
        if self.credential_rotation_interval_days >= self.virtual_duration_days:
            raise ValueError("credential rotation must occur within virtual duration")
        if self.evidence_retention_days >= self.virtual_duration_days:
            raise ValueError("evidence retention must expire within virtual duration")
        if self.policy_change_day >= self.virtual_duration_days:
            raise ValueError("policy change must occur within virtual duration")
        if self.agent_offboarding_day >= self.virtual_duration_days:
            raise ValueError("agent offboarding must occur within virtual duration")
        if self.credential_rotation_interval_days + 10 >= self.virtual_duration_days:
            raise ValueError("credential suspension must occur within virtual duration")
        if self.policy_change_day >= self.agent_offboarding_day:
            raise ValueError("policy change must precede agent offboarding")
        if self.agent_offboarding_day + 10 >= self.virtual_duration_days:
            raise ValueError(
                "revocation propagation must occur within virtual duration"
            )
        return self


class EnterpriseAgenticGenerationLimitsV2(SyntheticModel):
    max_principals: int = Field(default=10_000, strict=True, ge=1, le=100_000)
    max_events: int = Field(default=30_000, strict=True, ge=1, le=200_000)
    max_cases: int = Field(default=5_000, strict=True, ge=1, le=50_000)


class EnterpriseAgenticGenerationConfigV2(SyntheticModel):
    """Explicit benchmark identity inputs for standard or longitudinal worlds."""

    schema_version: Literal["2.0.0"] = ENTERPRISE_AGENTIC_SCALE_CONFIG_SCHEMA_VERSION
    profile_version: Literal["enterprise-agentic-generated-2.0.0"] = (
        ENTERPRISE_AGENTIC_SCALE_PROFILE_VERSION
    )
    generator_version: Literal["2.0.0"] = ENTERPRISE_AGENTIC_SCALE_GENERATOR_VERSION
    canonical_serialization_version: Literal["1.0.0"] = (
        ENTERPRISE_AGENTIC_SCALE_SERIALIZATION_VERSION
    )
    event_schedule_version: Literal["standard-2.0.0", "longitudinal-2.0.0"] = (
        ENTERPRISE_AGENTIC_STANDARD_EVENT_SCHEDULE_VERSION
    )
    seed: int = Field(default=20_260_821, strict=True, ge=0, le=2**63 - 1)
    tier: EnterpriseAgenticScaleTierV2 = EnterpriseAgenticScaleTierV2.STANDARD
    topology: EnterpriseAgenticScaleTopologyV2 = Field(
        default_factory=EnterpriseAgenticScaleTopologyV2
    )
    authority: EnterpriseAgenticAuthorityTopologyV2 = Field(
        default_factory=EnterpriseAgenticAuthorityTopologyV2
    )
    credentials: EnterpriseAgenticCredentialTopologyV2 = Field(
        default_factory=EnterpriseAgenticCredentialTopologyV2
    )
    prevalence: EnterpriseAgenticScenarioPrevalenceV2 = Field(
        default_factory=EnterpriseAgenticScenarioPrevalenceV2
    )
    longitudinal: EnterpriseAgenticLongitudinalScheduleV2 | None = None
    limits: EnterpriseAgenticGenerationLimitsV2 = Field(
        default_factory=EnterpriseAgenticGenerationLimitsV2
    )

    @model_validator(mode="after")
    def require_tier_contract(self) -> Self:
        lifecycle_counts = (
            self.prevalence.rotated_credential_reuse,
            self.prevalence.suspended_credential,
            self.prevalence.agent_offboarding_active_credential,
            self.prevalence.revocation_propagation_failure,
        )
        if self.tier is EnterpriseAgenticScaleTierV2.STANDARD:
            if self.event_schedule_version != (
                ENTERPRISE_AGENTIC_STANDARD_EVENT_SCHEDULE_VERSION
            ):
                raise ValueError("standard tier requires the standard event schedule")
            if self.longitudinal is not None or any(lifecycle_counts):
                raise ValueError("standard tier cannot declare longitudinal controls")
        else:
            if self.event_schedule_version != (
                ENTERPRISE_AGENTIC_LONGITUDINAL_EVENT_SCHEDULE_VERSION
            ):
                raise ValueError(
                    "longitudinal tier requires the longitudinal event schedule"
                )
            if self.longitudinal is None or not all(lifecycle_counts):
                raise ValueError(
                    "longitudinal tier requires its schedule and every lifecycle case"
                )
        if self.topology.organisation_count < 2 and (
            self.prevalence.cross_tenant_confusion
        ):
            raise ValueError("cross-tenant cases require at least two organisations")
        if (
            self.credentials.allowed_runtimes_per_shared_credential
            > self.topology.runtime_count
        ):
            raise ValueError("shared credential runtime breadth exceeds topology")
        if (
            self.credentials.shared_identity_prevalence > 0.0
            or self.prevalence.shared_credential_reuse > 0
        ) and (
            self.credentials.allowed_runtimes_per_shared_credential
            > self.topology.runtime_count // self.topology.logical_agent_count
        ):
            raise ValueError(
                "shared credential runtime breadth exceeds per-agent runtimes"
            )
        if self.longitudinal is not None and (
            self.prevalence.rotated_credential_reuse
            > (self.longitudinal.virtual_duration_days - 1)
            // self.longitudinal.credential_rotation_interval_days
        ):
            raise ValueError("rotated credential cases exceed scheduled rotations")
        if self.prevalence.total > self.limits.max_cases:
            raise ValueError("configured cases exceed the generation limit")
        principal_count = (
            self.topology.organisation_count
            + self.topology.human_principal_count
            + self.topology.logical_agent_count
            + self.topology.runtime_count
        )
        if principal_count > self.limits.max_principals:
            raise ValueError("configured principals exceed the generation limit")
        minimum_events = (
            self.topology.logical_agent_count
            + (2 * self.topology.runtime_count)
            + self.prevalence.total
            + 1
        )
        if minimum_events > self.limits.max_events:
            raise ValueError("configured events exceed the generation limit")
        return self


class EnterpriseAgenticScaleIdentityV2(SyntheticModel):
    profile_version: Literal["enterprise-agentic-generated-2.0.0"] = (
        ENTERPRISE_AGENTIC_SCALE_PROFILE_VERSION
    )
    generator_version: Literal["2.0.0"] = ENTERPRISE_AGENTIC_SCALE_GENERATOR_VERSION
    canonical_serialization_version: Literal["1.0.0"] = (
        ENTERPRISE_AGENTIC_SCALE_SERIALIZATION_VERSION
    )
    event_schedule_version: Literal["standard-2.0.0", "longitudinal-2.0.0"]
    tier: EnterpriseAgenticScaleTierV2
    seed: int = Field(strict=True, ge=0, le=2**63 - 1)
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    world_id: str


class EnterpriseAgenticTeamV2(SyntheticModel):
    id: str
    department_id: str
    display_name: str


class EnterpriseAgenticPersonProfileV2(SyntheticModel):
    principal_id: str
    population_kind: EnterpriseAgenticPopulationKindV2
    team_ids: tuple[str, ...] = Field(min_length=1)


class EnterpriseAgenticResourceProfileV2(SyntheticModel):
    resource_id: str
    category: Literal["application", "tool", "environment", "protected_data"]
    criticality: Literal["ordinary", "sensitive", "critical"]


class EnterpriseAgenticCredentialProfileV2(SyntheticModel):
    credential_id: str
    credential_kind: Literal[
        "workload_handle", "shared_workload_handle", "lifecycle_control_handle"
    ]
    opaque_synthetic_handle: Literal[True] = True


class EnterpriseAgenticTopologyMetadataV2(SyntheticModel):
    teams: tuple[EnterpriseAgenticTeamV2, ...]
    people: tuple[EnterpriseAgenticPersonProfileV2, ...]
    resources: tuple[EnterpriseAgenticResourceProfileV2, ...]
    credentials: tuple[EnterpriseAgenticCredentialProfileV2, ...]
    isolated_tenant_ids: tuple[str, ...]


class EnterpriseAgenticCredentialRotatedV2(SyntheticModel):
    event_type: Literal["credential_rotated"] = "credential_rotated"
    old_credential_id: str
    new_credential_id: str

    @model_validator(mode="after")
    def require_distinct_credentials(self) -> Self:
        if self.old_credential_id == self.new_credential_id:
            raise ValueError("credential rotation requires distinct credentials")
        return self


class EnterpriseAgenticCredentialStatusChangedV2(SyntheticModel):
    event_type: Literal["credential_status_changed"] = "credential_status_changed"
    credential_id: str
    state: EnterpriseAgenticCredentialLifecycleStateV2


class EnterpriseAgenticAgentStatusChangedV2(SyntheticModel):
    event_type: Literal["agent_status_changed"] = "agent_status_changed"
    agent_id: str
    state: EnterpriseAgenticAgentLifecycleStateV2
    active_credential_ids: tuple[str, ...] = Field(min_length=1)


class EnterpriseAgenticPersonStatusChangedV2(SyntheticModel):
    event_type: Literal["person_status_changed"] = "person_status_changed"
    principal_id: str
    state: EnterpriseAgenticPersonLifecycleStateV2
    previous_department_id: str | None = None
    department_id: str | None = None

    @model_validator(mode="after")
    def require_state_shape(self) -> Self:
        if self.state is EnterpriseAgenticPersonLifecycleStateV2.JOINED:
            valid = (
                self.previous_department_id is None and self.department_id is not None
            )
        elif self.state is EnterpriseAgenticPersonLifecycleStateV2.MOVED:
            valid = (
                self.previous_department_id is not None
                and self.department_id is not None
                and self.previous_department_id != self.department_id
            )
        else:
            valid = (
                self.previous_department_id is not None and self.department_id is None
            )
        if not valid:
            raise ValueError("person lifecycle state has inconsistent departments")
        return self


class EnterpriseAgenticPolicyActivatedV2(SyntheticModel):
    event_type: Literal["policy_activated"] = "policy_activated"
    previous_policy_version: str
    policy_version: str

    @model_validator(mode="after")
    def require_changed_policy(self) -> Self:
        if self.previous_policy_version == self.policy_version:
            raise ValueError("policy activation requires a version change")
        return self


class EnterpriseAgenticDelegationPropagationV2(SyntheticModel):
    event_type: Literal["delegation_revocation_propagated"] = (
        "delegation_revocation_propagated"
    )
    parent_delegation_id: str
    descendant_delegation_ids: tuple[str, ...] = Field(min_length=1)


EnterpriseAgenticLifecyclePayloadV2 = Annotated[
    EnterpriseAgenticCredentialRotatedV2
    | EnterpriseAgenticCredentialStatusChangedV2
    | EnterpriseAgenticAgentStatusChangedV2
    | EnterpriseAgenticPersonStatusChangedV2
    | EnterpriseAgenticPolicyActivatedV2
    | EnterpriseAgenticDelegationPropagationV2,
    Field(discriminator="event_type"),
]


class EnterpriseAgenticLifecycleEventV2(SyntheticModel):
    schema_version: Literal["2.0.0"] = "2.0.0"
    id: str
    sequence_index: int = Field(ge=1)
    occurred_at: datetime
    related_agentic_event_id: str | None = None
    payload: EnterpriseAgenticLifecyclePayloadV2

    @field_validator("occurred_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("lifecycle event timestamp must be UTC")
        return value


class EnterpriseAgenticLifecycleStreamV2(SyntheticModel):
    schema_version: Literal["2.0.0"] = "2.0.0"
    events: tuple[EnterpriseAgenticLifecycleEventV2, ...]


class EnterpriseAgenticLifecycleCaseV2(SyntheticModel):
    action_event_id: str
    kind: EnterpriseAgenticLifecycleCaseKindV2


class EnterpriseAgenticIntegrityMetricsV2(SyntheticModel):
    schema_version: Literal["2.0.0"] = ENTERPRISE_AGENTIC_SCALE_METRICS_SCHEMA_VERSION
    counts: tuple[EnterpriseAgenticCountMetricV1, ...]
    owner_chain_depth_distribution: tuple[EnterpriseAgenticDistributionBinV1, ...]
    runtimes_per_agent_distribution: tuple[EnterpriseAgenticDistributionBinV1, ...]
    credential_runtime_binding_distribution: tuple[
        EnterpriseAgenticDistributionBinV1, ...
    ]
    delegation_depth_distribution: tuple[EnterpriseAgenticDistributionBinV1, ...]
    delegation_branching_distribution: tuple[EnterpriseAgenticDistributionBinV1, ...]
    case_kind_distribution: tuple[EnterpriseAgenticDistributionBinV1, ...]
    population_kind_distribution: tuple[EnterpriseAgenticDistributionBinV1, ...]
    lifecycle_event_kind_distribution: tuple[EnterpriseAgenticDistributionBinV1, ...]
    principal_graph_component_count: int = Field(ge=0)
    referential_integrity: Literal[True] = True
    canonical_binding_integrity: Literal[True] = True


class EnterpriseAgenticGeneratedBenchmarkV2(SyntheticModel):
    config: EnterpriseAgenticGenerationConfigV2
    identity: EnterpriseAgenticScaleIdentityV2
    public: AgenticPublicBundle
    topology: EnterpriseAgenticTopologyMetadataV2
    lifecycle_events: tuple[EnterpriseAgenticLifecycleEventV2, ...]
    evaluator: AgenticEvaluatorBundle
    lifecycle_cases: tuple[EnterpriseAgenticLifecycleCaseV2, ...]
    metrics: EnterpriseAgenticIntegrityMetricsV2

    @model_validator(mode="after")
    def require_bindings(self) -> Self:
        _require_scale_config_identity(self.config, self.identity)
        AgenticBenchmark(public=self.public, evaluator=self.evaluator)
        if (self.public.snapshot.world_id, self.public.snapshot.seed) != (
            self.identity.world_id,
            self.identity.seed,
        ):
            raise ValueError("generated scale world identity differs")
        _require_scale_public_integrity(
            self.public, self.topology, self.lifecycle_events
        )
        action_ids = set(self.public.scenario.action_event_ids)
        case_ids = tuple(item.action_event_id for item in self.lifecycle_cases)
        if len(case_ids) != len(set(case_ids)) or set(case_ids) != action_ids:
            raise ValueError("lifecycle cases must cover every action exactly once")
        return self


class EnterpriseAgenticGeneratedPublicV2(SyntheticModel):
    schema_version: Literal["2.0.0"] = ENTERPRISE_AGENTIC_SCALE_ARTIFACT_SCHEMA_VERSION
    config: EnterpriseAgenticGenerationConfigV2
    identity: EnterpriseAgenticScaleIdentityV2
    benchmark: AgenticPublicBundle
    topology: EnterpriseAgenticTopologyMetadataV2
    lifecycle_events: tuple[EnterpriseAgenticLifecycleEventV2, ...]

    @model_validator(mode="after")
    def require_identity_binding(self) -> Self:
        _require_scale_config_identity(self.config, self.identity)
        if (self.benchmark.snapshot.world_id, self.benchmark.snapshot.seed) != (
            self.identity.world_id,
            self.identity.seed,
        ):
            raise ValueError("generated scale world identity differs")
        _require_scale_public_integrity(
            self.benchmark, self.topology, self.lifecycle_events
        )
        return self


class EnterpriseAgenticGeneratedEvaluatorV2(SyntheticModel):
    schema_version: Literal["2.0.0"] = ENTERPRISE_AGENTIC_SCALE_ARTIFACT_SCHEMA_VERSION
    identity: EnterpriseAgenticScaleIdentityV2
    public_artifact_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    benchmark: AgenticEvaluatorBundle
    lifecycle_cases: tuple[EnterpriseAgenticLifecycleCaseV2, ...]
    metrics: EnterpriseAgenticIntegrityMetricsV2

    @model_validator(mode="after")
    def require_identity_binding(self) -> Self:
        if (self.benchmark.world_id, self.benchmark.seed) != (
            self.identity.world_id,
            self.identity.seed,
        ):
            raise ValueError("generated scale evaluator identity differs")
        case_ids = tuple(item.action_event_id for item in self.lifecycle_cases)
        if len(case_ids) != len(set(case_ids)) or set(case_ids) != {
            item.action_event_id for item in self.benchmark.cases
        }:
            raise ValueError("evaluator lifecycle cases must cover every action")
        return self


class EnterpriseAgenticGeneratedPublicManifestV2(SyntheticModel):
    schema_version: Literal["2.0.0"] = ENTERPRISE_AGENTIC_SCALE_ARTIFACT_SCHEMA_VERSION
    visibility: Literal["public"] = "public"
    artifact_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifacts: tuple[EnterpriseAgenticArtifactDescriptorV1, ...]
    oracle_free: Literal[True] = True


class EnterpriseAgenticGeneratedEvaluatorManifestV2(SyntheticModel):
    schema_version: Literal["2.0.0"] = ENTERPRISE_AGENTIC_SCALE_ARTIFACT_SCHEMA_VERSION
    visibility: Literal["evaluator"] = "evaluator"
    artifact_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_artifact_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifacts: tuple[EnterpriseAgenticArtifactDescriptorV1, ...]


class EnterpriseAgenticTierMeasurementV1(SyntheticModel):
    tier: EnterpriseAgenticScaleTierV2
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_artifact_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    iterations: int = Field(strict=True, gt=0)
    generation_seconds_median: float = Field(ge=0.0)
    serialization_seconds_median: float = Field(ge=0.0)
    replay_seconds_median: float = Field(ge=0.0)
    scoring_seconds_median: float = Field(ge=0.0)
    peak_memory_bytes: int = Field(ge=0)


class EnterpriseAgenticPerformanceReceiptV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = (
        ENTERPRISE_AGENTIC_PERFORMANCE_RECEIPT_SCHEMA_VERSION
    )
    source_revision: str
    dependency_lock_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    python_version: str
    platform: str
    measurements: tuple[EnterpriseAgenticTierMeasurementV1, ...]


def _require_scale_config_identity(
    config: EnterpriseAgenticGenerationConfigV2,
    identity: EnterpriseAgenticScaleIdentityV2,
) -> None:
    expected = (
        config.profile_version,
        config.generator_version,
        config.canonical_serialization_version,
        config.event_schedule_version,
        config.tier,
        config.seed,
        hashlib.sha256(canonical_json_bytes(config)).hexdigest(),
    )
    actual = (
        identity.profile_version,
        identity.generator_version,
        identity.canonical_serialization_version,
        identity.event_schedule_version,
        identity.tier,
        identity.seed,
        identity.configuration_sha256,
    )
    if actual != expected:
        raise ValueError("generated scale configuration identity differs")


def _require_scale_public_integrity(
    public: AgenticPublicBundle,
    topology: EnterpriseAgenticTopologyMetadataV2,
    lifecycle_events: tuple[EnterpriseAgenticLifecycleEventV2, ...],
) -> None:
    snapshot = public.snapshot
    department_ids = {item.id for item in snapshot.departments}
    human_ids = {item.id for item in snapshot.principals if item.kind.value == "human"}
    resource_ids = {item.id for item in snapshot.resources}
    agent_ids = {item.id for item in snapshot.agents}
    principal_ids = {item.id for item in snapshot.principals}
    policy_versions = {item.version for item in snapshot.policies}
    tenant_ids = {item.tenant_id for item in snapshot.organisations}
    team_ids = tuple(item.id for item in topology.teams)
    if len(team_ids) != len(set(team_ids)) or any(
        item.department_id not in department_ids for item in topology.teams
    ):
        raise ValueError("scale teams have invalid identities or departments")
    person_ids = tuple(item.principal_id for item in topology.people)
    if len(person_ids) != len(set(person_ids)) or set(person_ids) != human_ids:
        raise ValueError("scale people must cover every human exactly once")
    if any(not set(item.team_ids) <= set(team_ids) for item in topology.people):
        raise ValueError("scale people reference unknown teams")
    profiled_resource_ids = tuple(item.resource_id for item in topology.resources)
    if (
        len(profiled_resource_ids) != len(set(profiled_resource_ids))
        or set(profiled_resource_ids) != resource_ids
    ):
        raise ValueError("scale resources must be profiled exactly once")
    if not set(topology.isolated_tenant_ids) <= tenant_ids:
        raise ValueError("scale isolated controls reference unknown tenants")
    public_event_ids = {item.id for item in public.events}
    credential_ids = {
        event.payload.credential.id
        for event in public.events
        if isinstance(event.payload, CredentialIssued)
    }
    profiled_credential_ids = tuple(item.credential_id for item in topology.credentials)
    if (
        len(profiled_credential_ids) != len(set(profiled_credential_ids))
        or set(profiled_credential_ids) != credential_ids
    ):
        raise ValueError("scale credentials must be profiled exactly once")
    delegation_ids = {
        event.payload.delegation.id
        for event in public.events
        if isinstance(event.payload, DelegationGranted)
    }
    lifecycle_ids = tuple(item.id for item in lifecycle_events)
    if len(lifecycle_ids) != len(set(lifecycle_ids)):
        raise ValueError("lifecycle event IDs must be unique")
    if tuple(item.sequence_index for item in lifecycle_events) != tuple(
        range(1, len(lifecycle_events) + 1)
    ) or any(
        current.occurred_at < previous.occurred_at
        for previous, current in pairwise(lifecycle_events)
    ):
        raise ValueError("lifecycle event ordering is invalid")
    for event in lifecycle_events:
        if (
            event.related_agentic_event_id is not None
            and event.related_agentic_event_id not in public_event_ids
        ):
            raise ValueError("lifecycle event references an unknown agentic event")
        payload = event.payload
        if isinstance(payload, EnterpriseAgenticCredentialRotatedV2):
            valid = {
                payload.old_credential_id,
                payload.new_credential_id,
            } <= credential_ids
        elif isinstance(payload, EnterpriseAgenticCredentialStatusChangedV2):
            valid = payload.credential_id in credential_ids
        elif isinstance(payload, EnterpriseAgenticAgentStatusChangedV2):
            valid = (
                payload.agent_id in agent_ids
                and set(payload.active_credential_ids) <= credential_ids
            )
        elif isinstance(payload, EnterpriseAgenticPersonStatusChangedV2):
            referenced_departments = {
                item
                for item in (
                    payload.previous_department_id,
                    payload.department_id,
                )
                if item is not None
            }
            valid = (
                payload.principal_id in principal_ids
                and referenced_departments <= department_ids
            )
        elif isinstance(payload, EnterpriseAgenticPolicyActivatedV2):
            valid = {
                payload.previous_policy_version,
                payload.policy_version,
            } <= policy_versions
        else:
            valid = (
                payload.parent_delegation_id in delegation_ids
                and set(payload.descendant_delegation_ids) <= delegation_ids
            )
        if not valid:
            raise ValueError("lifecycle event has broken references")


__all__ = [name for name in globals() if name.startswith("EnterpriseAgentic")]
