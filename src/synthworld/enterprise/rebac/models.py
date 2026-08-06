"""Strict bounded relationship overlays and independently versioned truth."""

from __future__ import annotations

from typing import Annotated, Literal, Self, cast

from pydantic import Field, ValidationInfo, field_validator, model_validator

from synthworld.enterprise.authorization_common import (
    AuthorizationSourceLayer,
    MechanismOutcome,
    RuleEffect,
)
from synthworld.enterprise.models import (
    EnterpriseOperatorModel,
    LogicalKey,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.common import (
    canonical_operator_records,
    canonical_strings,
    canonical_synthetic_records,
)
from synthworld.enterprise.rebac.common import (
    ENTERPRISE_REBAC_COMPILER_VERSION,
    ENTERPRISE_REBAC_INTENT_SCHEMA_VERSION,
    ENTERPRISE_REBAC_STATE_SCHEMA_VERSION,
    ENTERPRISE_REBAC_TRUTH_SCHEMA_VERSION,
    RebacRelation,
    RebacTemplateKind,
)
from synthworld.models import SyntheticModel


class RelationTupleV1(EnterpriseOperatorModel):
    tuple_id: LogicalKey
    tenant_id: str = Field(min_length=1)
    subject_entity_id: str = Field(min_length=1)
    relation: RebacRelation
    object_entity_id: str = Field(min_length=1)
    snapshot_id: LogicalKey
    revision_id: LogicalKey
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.valid_from_tick
        ):
            raise ValueError("rebac_tuple_validity_interval_invalid")
        return self


class RebacRuleBaseV1(EnterpriseOperatorModel):
    template: RebacTemplateKind
    rule_id: LogicalKey
    revision_id: LogicalKey
    effect: RuleEffect
    cell_ids: tuple[str, ...] = Field(min_length=1)
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)

    @field_validator("cell_ids")
    @classmethod
    def canonical_cells(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "rebac_rule_cell_id")

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.valid_from_tick
        ):
            raise ValueError("rebac_rule_validity_interval_invalid")
        return self


class DirectSubjectRelationV1(RebacRuleBaseV1):
    template: Literal[RebacTemplateKind.DIRECT_SUBJECT_RELATION] = (
        RebacTemplateKind.DIRECT_SUBJECT_RELATION
    )
    relation: Literal[RebacRelation.OWNS, RebacRelation.COLLABORATES_ON]


class GroupCollaborationV1(RebacRuleBaseV1):
    template: Literal[RebacTemplateKind.GROUP_COLLABORATION] = (
        RebacTemplateKind.GROUP_COLLABORATION
    )


class ManagerOfOwnerV1(RebacRuleBaseV1):
    template: Literal[RebacTemplateKind.MANAGER_OF_OWNER] = (
        RebacTemplateKind.MANAGER_OF_OWNER
    )


RebacRuleV1 = Annotated[
    DirectSubjectRelationV1 | GroupCollaborationV1 | ManagerOfOwnerV1,
    Field(discriminator="template"),
]


class EnterpriseRebacStateOverlayV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_REBAC_STATE_SCHEMA_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    relation_tuples: tuple[RelationTupleV1, ...] = ()
    rules: tuple[RebacRuleV1, ...] = ()
    unknown_evidence_cell_ids: tuple[str, ...] = ()

    @field_validator("relation_tuples")
    @classmethod
    def canonical_tuples(
        cls, value: tuple[RelationTupleV1, ...]
    ) -> tuple[RelationTupleV1, ...]:
        return _canonical_tuples(value, "actual")

    @field_validator("rules")
    @classmethod
    def canonical_rules(cls, value: tuple[RebacRuleV1, ...]) -> tuple[RebacRuleV1, ...]:
        return _canonical_rules(value, "actual")

    @field_validator("unknown_evidence_cell_ids")
    @classmethod
    def canonical_unknown_cells(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "actual_rebac_unknown_cell_id")


class EnterpriseRebacIntentOverlayV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_REBAC_INTENT_SCHEMA_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    relation_tuples: tuple[RelationTupleV1, ...] = ()
    rules: tuple[RebacRuleV1, ...] = ()
    unknown_evidence_cell_ids: tuple[str, ...] = ()

    @field_validator("relation_tuples")
    @classmethod
    def canonical_tuples(
        cls, value: tuple[RelationTupleV1, ...]
    ) -> tuple[RelationTupleV1, ...]:
        return _canonical_tuples(value, "intended")

    @field_validator("rules")
    @classmethod
    def canonical_rules(cls, value: tuple[RebacRuleV1, ...]) -> tuple[RebacRuleV1, ...]:
        return _canonical_rules(value, "intended")

    @field_validator("unknown_evidence_cell_ids")
    @classmethod
    def canonical_unknown_cells(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "intended_rebac_unknown_cell_id")


class RebacTupleTruthV1(SyntheticModel):
    tuple_id: str
    revision_id: str
    source_layer: AuthorizationSourceLayer
    tenant_id: str
    subject_entity_id: str
    relation: RebacRelation
    object_entity_id: str
    snapshot_id: str
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)


class RebacPathTruthV1(SyntheticModel):
    path_id: str
    source_layer: AuthorizationSourceLayer
    rule_id: str
    revision_id: str
    cell_id: str
    template: RebacTemplateKind
    subject_id: str
    authorization_target_id: str
    tuple_ids: tuple[str, ...] = Field(min_length=1, max_length=2)


class RebacRuleTruthV1(SyntheticModel):
    truth_id: str
    source_layer: AuthorizationSourceLayer
    rule_id: str
    revision_id: str
    cell_id: str
    template: RebacTemplateKind
    effect: RuleEffect
    outcome: MechanismOutcome
    path_ids: tuple[str, ...]

    @field_validator("path_ids")
    @classmethod
    def canonical_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "rebac_rule_path_id")


class RebacCellTruthV1(SyntheticModel):
    cell_id: str
    actual_outcome: MechanismOutcome
    intended_outcome: MechanismOutcome
    actual_conflict: bool
    intended_conflict: bool
    actual_rule_truth_ids: tuple[str, ...]
    intended_rule_truth_ids: tuple[str, ...]
    actual_path_ids: tuple[str, ...]
    intended_path_ids: tuple[str, ...]

    @field_validator(
        "actual_rule_truth_ids",
        "intended_rule_truth_ids",
        "actual_path_ids",
        "intended_path_ids",
    )
    @classmethod
    def canonical_ids(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return canonical_strings(value, cast(str, info.field_name))


class CompiledEnterpriseRebacTruthV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_REBAC_TRUTH_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = ENTERPRISE_REBAC_COMPILER_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    rebac_state_digest: SyntheticDigestV1
    rebac_intent_digest: SyntheticDigestV1
    relation_tuples: tuple[RebacTupleTruthV1, ...]
    paths: tuple[RebacPathTruthV1, ...]
    rule_truth: tuple[RebacRuleTruthV1, ...]
    cells: tuple[RebacCellTruthV1, ...]

    @field_validator("relation_tuples", "paths", "rule_truth", "cells")
    @classmethod
    def canonical_truth(
        cls, value: tuple[SyntheticModel, ...], info: ValidationInfo
    ) -> tuple[SyntheticModel, ...]:
        field_name = cast(str, info.field_name)
        keys: tuple[tuple[str, ...], ...]
        if field_name == "relation_tuples":
            keys = tuple((cast(RebacTupleTruthV1, item).tuple_id,) for item in value)
        elif field_name == "paths":
            keys = tuple((cast(RebacPathTruthV1, item).path_id,) for item in value)
        elif field_name == "rule_truth":
            keys = tuple((cast(RebacRuleTruthV1, item).truth_id,) for item in value)
        else:
            keys = tuple((cast(RebacCellTruthV1, item).cell_id,) for item in value)
        return canonical_synthetic_records(
            value, keys=keys, description=f"rebac_{field_name}"
        )


def _canonical_tuples(
    value: tuple[RelationTupleV1, ...], layer: str
) -> tuple[RelationTupleV1, ...]:
    return canonical_operator_records(
        value,
        keys=tuple((item.tuple_id, item.revision_id) for item in value),
        description=f"{layer}_rebac_tuple_revision",
    )


def _canonical_rules(
    value: tuple[RebacRuleV1, ...], layer: str
) -> tuple[RebacRuleV1, ...]:
    return canonical_operator_records(
        value,
        keys=tuple((item.rule_id, item.revision_id) for item in value),
        description=f"{layer}_rebac_rule_revision",
    )


__all__ = [name for name in globals() if name.endswith("V1")]
__all__ += ["RebacRuleV1"]
