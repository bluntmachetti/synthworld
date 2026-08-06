"""Strict cell-bound ABAC overlays and independently versioned truth."""

from __future__ import annotations

from typing import Annotated, Literal, Self, cast

from pydantic import Field, ValidationInfo, field_validator, model_validator

from synthworld.enterprise.abac.common import (
    ENTERPRISE_ABAC_COMPILER_VERSION,
    ENTERPRISE_ABAC_INTENT_SCHEMA_VERSION,
    ENTERPRISE_ABAC_STATE_SCHEMA_VERSION,
    ENTERPRISE_ABAC_TRUTH_SCHEMA_VERSION,
    AbacEmploymentType,
    ActionClass,
    AssuranceLevel,
    AttributeCategory,
    AttributeValueState,
    InformationClassification,
    NetworkZone,
)
from synthworld.enterprise.authorization_common import (
    AuthorizationSourceLayer,
    FlatRuleOperator,
    MechanismOutcome,
    PredicateOutcome,
    RuleEffect,
)
from synthworld.enterprise.models import (
    EnterpriseOperatorModel,
    LogicalKey,
    PrincipalKind,
    SyntheticDigestV1,
    TargetKind,
)
from synthworld.enterprise.rbac.common import (
    canonical_operator_records,
    canonical_strings,
    canonical_synthetic_records,
)
from synthworld.models import SyntheticModel


class AttributeFactBaseV1(EnterpriseOperatorModel):
    """One revision of one attribute bound to an already frozen cell."""

    kind: str
    category: AttributeCategory
    attribute_key: Literal[
        "principal_kind",
        "employment_type",
        "tenant_id",
        "unit_id",
        "clearance",
        "target_kind",
        "owner_unit_id",
        "classification",
        "action_id",
        "action_class",
        "assurance_level",
        "network_zone",
    ]
    fact_id: LogicalKey
    cell_id: str = Field(min_length=1)
    value_state: AttributeValueState
    value: object
    revision_id: LogicalKey
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def coherent_value_and_interval(self) -> Self:
        value = self.value
        if self.value_state is AttributeValueState.KNOWN and value is None:
            raise ValueError("known_attribute_value_missing")
        if self.value_state is AttributeValueState.UNKNOWN and value is not None:
            raise ValueError("unknown_attribute_value_present")
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.valid_from_tick
        ):
            raise ValueError("attribute_fact_validity_interval_invalid")
        return self


class SubjectPrincipalKindFactV1(AttributeFactBaseV1):
    kind: Literal["subject_principal_kind"] = "subject_principal_kind"
    category: Literal[AttributeCategory.SUBJECT] = AttributeCategory.SUBJECT
    attribute_key: Literal["principal_kind"] = "principal_kind"
    value: PrincipalKind | None


class SubjectEmploymentTypeFactV1(AttributeFactBaseV1):
    kind: Literal["subject_employment_type"] = "subject_employment_type"
    category: Literal[AttributeCategory.SUBJECT] = AttributeCategory.SUBJECT
    attribute_key: Literal["employment_type"] = "employment_type"
    value: AbacEmploymentType | None


class SubjectTenantIdFactV1(AttributeFactBaseV1):
    kind: Literal["subject_tenant_id"] = "subject_tenant_id"
    category: Literal[AttributeCategory.SUBJECT] = AttributeCategory.SUBJECT
    attribute_key: Literal["tenant_id"] = "tenant_id"
    value: str | None = Field(min_length=1)


class SubjectUnitIdFactV1(AttributeFactBaseV1):
    kind: Literal["subject_unit_id"] = "subject_unit_id"
    category: Literal[AttributeCategory.SUBJECT] = AttributeCategory.SUBJECT
    attribute_key: Literal["unit_id"] = "unit_id"
    value: str | None = Field(min_length=1)


class SubjectClearanceFactV1(AttributeFactBaseV1):
    kind: Literal["subject_clearance"] = "subject_clearance"
    category: Literal[AttributeCategory.SUBJECT] = AttributeCategory.SUBJECT
    attribute_key: Literal["clearance"] = "clearance"
    value: InformationClassification | None


class ResourceTargetKindFactV1(AttributeFactBaseV1):
    kind: Literal["resource_target_kind"] = "resource_target_kind"
    category: Literal[AttributeCategory.RESOURCE] = AttributeCategory.RESOURCE
    attribute_key: Literal["target_kind"] = "target_kind"
    value: TargetKind | None


class ResourceTenantIdFactV1(AttributeFactBaseV1):
    kind: Literal["resource_tenant_id"] = "resource_tenant_id"
    category: Literal[AttributeCategory.RESOURCE] = AttributeCategory.RESOURCE
    attribute_key: Literal["tenant_id"] = "tenant_id"
    value: str | None = Field(min_length=1)


class ResourceOwnerUnitIdFactV1(AttributeFactBaseV1):
    kind: Literal["resource_owner_unit_id"] = "resource_owner_unit_id"
    category: Literal[AttributeCategory.RESOURCE] = AttributeCategory.RESOURCE
    attribute_key: Literal["owner_unit_id"] = "owner_unit_id"
    value: str | None = Field(min_length=1)


class ResourceClassificationFactV1(AttributeFactBaseV1):
    kind: Literal["resource_classification"] = "resource_classification"
    category: Literal[AttributeCategory.RESOURCE] = AttributeCategory.RESOURCE
    attribute_key: Literal["classification"] = "classification"
    value: InformationClassification | None


class ActionIdFactV1(AttributeFactBaseV1):
    kind: Literal["action_id"] = "action_id"
    category: Literal[AttributeCategory.ACTION] = AttributeCategory.ACTION
    attribute_key: Literal["action_id"] = "action_id"
    value: str | None = Field(min_length=1)


class ActionClassFactV1(AttributeFactBaseV1):
    kind: Literal["action_class"] = "action_class"
    category: Literal[AttributeCategory.ACTION] = AttributeCategory.ACTION
    attribute_key: Literal["action_class"] = "action_class"
    value: ActionClass | None


class EnvironmentAssuranceLevelFactV1(AttributeFactBaseV1):
    kind: Literal["environment_assurance_level"] = "environment_assurance_level"
    category: Literal[AttributeCategory.ENVIRONMENT] = AttributeCategory.ENVIRONMENT
    attribute_key: Literal["assurance_level"] = "assurance_level"
    value: AssuranceLevel | None


class EnvironmentNetworkZoneFactV1(AttributeFactBaseV1):
    kind: Literal["environment_network_zone"] = "environment_network_zone"
    category: Literal[AttributeCategory.ENVIRONMENT] = AttributeCategory.ENVIRONMENT
    attribute_key: Literal["network_zone"] = "network_zone"
    value: NetworkZone | None


AttributeFactV1 = Annotated[
    SubjectPrincipalKindFactV1
    | SubjectEmploymentTypeFactV1
    | SubjectTenantIdFactV1
    | SubjectUnitIdFactV1
    | SubjectClearanceFactV1
    | ResourceTargetKindFactV1
    | ResourceTenantIdFactV1
    | ResourceOwnerUnitIdFactV1
    | ResourceClassificationFactV1
    | ActionIdFactV1
    | ActionClassFactV1
    | EnvironmentAssuranceLevelFactV1
    | EnvironmentNetworkZoneFactV1,
    Field(discriminator="kind"),
]


class SubjectKindIsV1(EnterpriseOperatorModel):
    kind: Literal["subject_kind_is"] = "subject_kind_is"
    values: tuple[PrincipalKind, ...] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def canonical_values(
        cls, value: tuple[PrincipalKind, ...]
    ) -> tuple[PrincipalKind, ...]:
        return _canonical_enum_values(value, "abac_subject_kind")


class EmploymentTypeIsV1(EnterpriseOperatorModel):
    kind: Literal["employment_type_is"] = "employment_type_is"
    values: tuple[AbacEmploymentType, ...] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def canonical_values(
        cls, value: tuple[AbacEmploymentType, ...]
    ) -> tuple[AbacEmploymentType, ...]:
        return _canonical_enum_values(value, "abac_employment_type")


class SameTenantV1(EnterpriseOperatorModel):
    kind: Literal["same_tenant"] = "same_tenant"


class SubjectUnitIsV1(EnterpriseOperatorModel):
    kind: Literal["subject_unit_is"] = "subject_unit_is"
    unit_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("unit_ids")
    @classmethod
    def canonical_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "abac_subject_unit_id")


class SubjectUnitOwnsTargetV1(EnterpriseOperatorModel):
    kind: Literal["subject_unit_owns_target"] = "subject_unit_owns_target"


class TargetKindIsV1(EnterpriseOperatorModel):
    kind: Literal["target_kind_is"] = "target_kind_is"
    values: tuple[TargetKind, ...] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def canonical_values(cls, value: tuple[TargetKind, ...]) -> tuple[TargetKind, ...]:
        return _canonical_enum_values(value, "abac_target_kind")


class ClassificationWithinClearanceV1(EnterpriseOperatorModel):
    kind: Literal["classification_within_clearance"] = "classification_within_clearance"


class ActionIsV1(EnterpriseOperatorModel):
    kind: Literal["action_is"] = "action_is"
    action_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("action_ids")
    @classmethod
    def canonical_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "abac_action_id")


class ActionClassIsV1(EnterpriseOperatorModel):
    kind: Literal["action_class_is"] = "action_class_is"
    values: tuple[ActionClass, ...] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def canonical_values(
        cls, value: tuple[ActionClass, ...]
    ) -> tuple[ActionClass, ...]:
        return _canonical_enum_values(value, "abac_action_class")


class AssuranceAtLeastV1(EnterpriseOperatorModel):
    kind: Literal["assurance_at_least"] = "assurance_at_least"
    minimum: AssuranceLevel


class NetworkZoneIsV1(EnterpriseOperatorModel):
    kind: Literal["network_zone_is"] = "network_zone_is"
    values: tuple[NetworkZone, ...] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def canonical_values(
        cls, value: tuple[NetworkZone, ...]
    ) -> tuple[NetworkZone, ...]:
        return _canonical_enum_values(value, "abac_network_zone")


AbacPredicateV1 = Annotated[
    SubjectKindIsV1
    | EmploymentTypeIsV1
    | SameTenantV1
    | SubjectUnitIsV1
    | SubjectUnitOwnsTargetV1
    | TargetKindIsV1
    | ClassificationWithinClearanceV1
    | ActionIsV1
    | ActionClassIsV1
    | AssuranceAtLeastV1
    | NetworkZoneIsV1,
    Field(discriminator="kind"),
]


class AbacRuleV1(EnterpriseOperatorModel):
    rule_id: LogicalKey
    revision_id: LogicalKey
    effect: RuleEffect
    operator: FlatRuleOperator
    cell_ids: tuple[str, ...] = Field(min_length=1)
    predicates: tuple[AbacPredicateV1, ...] = Field(min_length=1, max_length=64)
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)

    @field_validator("cell_ids")
    @classmethod
    def canonical_cells(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "abac_rule_cell_id")

    @field_validator("predicates")
    @classmethod
    def canonical_predicates(
        cls, value: tuple[AbacPredicateV1, ...]
    ) -> tuple[AbacPredicateV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple(
                (item.kind, item.model_dump_json(exclude_defaults=False))
                for item in value
            ),
            description="abac_rule_predicate",
        )

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.valid_from_tick
        ):
            raise ValueError("abac_rule_validity_interval_invalid")
        return self


class EnterpriseAbacCompileLimitsV1(EnterpriseOperatorModel):
    max_rules_per_overlay: int = Field(default=64, gt=0, le=256)
    max_predicates_per_rule: int = Field(default=16, gt=0, le=64)


class EnterpriseAbacStateOverlayV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_ABAC_STATE_SCHEMA_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    attribute_facts: tuple[AttributeFactV1, ...] = ()
    rules: tuple[AbacRuleV1, ...] = ()

    @field_validator("attribute_facts")
    @classmethod
    def canonical_facts(
        cls, value: tuple[AttributeFactV1, ...]
    ) -> tuple[AttributeFactV1, ...]:
        return _canonical_facts(value, "actual")

    @field_validator("rules")
    @classmethod
    def canonical_rules(cls, value: tuple[AbacRuleV1, ...]) -> tuple[AbacRuleV1, ...]:
        return _canonical_rules(value, "actual")


class EnterpriseAbacIntentOverlayV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_ABAC_INTENT_SCHEMA_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    attribute_facts: tuple[AttributeFactV1, ...] = ()
    rules: tuple[AbacRuleV1, ...] = ()

    @field_validator("attribute_facts")
    @classmethod
    def canonical_facts(
        cls, value: tuple[AttributeFactV1, ...]
    ) -> tuple[AttributeFactV1, ...]:
        return _canonical_facts(value, "intended")

    @field_validator("rules")
    @classmethod
    def canonical_rules(cls, value: tuple[AbacRuleV1, ...]) -> tuple[AbacRuleV1, ...]:
        return _canonical_rules(value, "intended")


class AbacPredicateTruthV1(SyntheticModel):
    truth_id: str
    source_layer: AuthorizationSourceLayer
    rule_id: str
    revision_id: str
    cell_id: str
    predicate_index: int = Field(ge=0)
    outcome: PredicateOutcome
    supporting_fact_ids: tuple[str, ...]

    @field_validator("supporting_fact_ids")
    @classmethod
    def canonical_facts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "abac_supporting_fact_id")


class AbacAttributeFactTruthV1(SyntheticModel):
    fact_id: str
    revision_id: str
    source_layer: AuthorizationSourceLayer
    cell_id: str
    category: AttributeCategory
    attribute_key: Literal[
        "principal_kind",
        "employment_type",
        "tenant_id",
        "unit_id",
        "clearance",
        "target_kind",
        "owner_unit_id",
        "classification",
        "action_id",
        "action_class",
        "assurance_level",
        "network_zone",
    ]
    value_state: AttributeValueState
    value: str | None
    active_at_cell_tick: bool

    @model_validator(mode="after")
    def coherent_value(self) -> Self:
        if self.value_state is AttributeValueState.KNOWN and self.value is None:
            raise ValueError("known_truth_attribute_value_missing")
        if self.value_state is AttributeValueState.UNKNOWN and self.value is not None:
            raise ValueError("unknown_truth_attribute_value_present")
        return self


class AbacRuleTruthV1(SyntheticModel):
    truth_id: str
    source_layer: AuthorizationSourceLayer
    rule_id: str
    revision_id: str
    cell_id: str
    effect: RuleEffect
    predicate_outcome: PredicateOutcome
    outcome: MechanismOutcome


class AbacCellTruthV1(SyntheticModel):
    cell_id: str
    actual_outcome: MechanismOutcome
    intended_outcome: MechanismOutcome
    actual_conflict: bool
    intended_conflict: bool
    actual_rule_truth_ids: tuple[str, ...]
    intended_rule_truth_ids: tuple[str, ...]

    @field_validator("actual_rule_truth_ids", "intended_rule_truth_ids")
    @classmethod
    def canonical_rules(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return canonical_strings(value, cast(str, info.field_name))


class CompiledEnterpriseAbacTruthV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_ABAC_TRUTH_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = ENTERPRISE_ABAC_COMPILER_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    abac_state_digest: SyntheticDigestV1
    abac_intent_digest: SyntheticDigestV1
    attribute_facts: tuple[AbacAttributeFactTruthV1, ...]
    predicate_truth: tuple[AbacPredicateTruthV1, ...]
    rule_truth: tuple[AbacRuleTruthV1, ...]
    cells: tuple[AbacCellTruthV1, ...]

    @field_validator("attribute_facts", "predicate_truth", "rule_truth", "cells")
    @classmethod
    def canonical_truth(
        cls, value: tuple[SyntheticModel, ...], info: ValidationInfo
    ) -> tuple[SyntheticModel, ...]:
        field_name = cast(str, info.field_name)
        return canonical_synthetic_records(
            value,
            keys=tuple(
                (
                    str(item.cell_id)
                    if isinstance(item, AbacCellTruthV1)
                    else str(
                        item.fact_id
                        if isinstance(item, AbacAttributeFactTruthV1)
                        else item.truth_id
                    ),
                )
                for item in value
                if isinstance(
                    item,
                    AbacAttributeFactTruthV1
                    | AbacPredicateTruthV1
                    | AbacRuleTruthV1
                    | AbacCellTruthV1,
                )
            ),
            description=f"abac_{field_name}",
        )


def _canonical_enum_values[EnumT](
    value: tuple[EnumT, ...], description: str
) -> tuple[EnumT, ...]:
    ordered = tuple(sorted(value, key=str))
    if len(ordered) != len(set(ordered)):
        raise ValueError(f"duplicate_{description}")
    return ordered


def _canonical_facts(
    value: tuple[AttributeFactV1, ...], layer: str
) -> tuple[AttributeFactV1, ...]:
    return canonical_operator_records(
        value,
        keys=tuple((item.fact_id,) for item in value),
        description=f"{layer}_abac_fact_id",
    )


def _canonical_rules(
    value: tuple[AbacRuleV1, ...], layer: str
) -> tuple[AbacRuleV1, ...]:
    return canonical_operator_records(
        value,
        keys=tuple((item.rule_id, item.revision_id) for item in value),
        description=f"{layer}_abac_rule_revision",
    )


__all__ = [name for name in globals() if name.endswith("V1")]
__all__ += ["AbacPredicateV1", "AttributeFactV1"]
