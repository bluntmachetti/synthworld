"""Fixed native evaluation-corpus contracts."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.enterprise.canonical import canonical_json_value_bytes, synthetic_digest
from synthworld.enterprise.models import (
    EnterpriseIdentityAccessCompileConfigV1,
    EnterpriseOperatorModel,
    LogicalKey,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.common import (
    ENTERPRISE_CORPUS_COMPILER_VERSION,
    ENTERPRISE_CORPUS_CONFIG_SCHEMA_VERSION,
    ENTERPRISE_CORPUS_SCHEMA_VERSION,
    ENTERPRISE_EVALUATOR_CASE_SCHEMA_VERSION,
    EvaluationCaseTargetKind,
    canonical_operator_records,
    canonical_strings,
    canonical_synthetic_records,
)
from synthworld.models import SyntheticModel


class EnterpriseContextTemplateV1(EnterpriseOperatorModel):
    """An opaque context slot; later mechanisms attach typed facts by ID."""

    context_key: LogicalKey


class AuthorizationSessionSlotTemplateV1(EnterpriseOperatorModel):
    session_state_key: LogicalKey
    session_key: LogicalKey
    subject_id: str = Field(min_length=1)
    activation_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)


class RoleActivationRequestTemplateV1(EnterpriseOperatorModel):
    request_key: LogicalKey
    session_state_key: LogicalKey
    requested_role_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("requested_role_ids")
    @classmethod
    def canonical_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "requested_role_id")


class AccessEvaluationCellTemplateV1(EnterpriseOperatorModel):
    cell_key: LogicalKey
    access_atom_id: str = Field(min_length=1)
    context_key: LogicalKey
    session_state_key: LogicalKey | None = None
    tick: int = Field(ge=0)


class EnterpriseAccessRequestTemplateV1(EnterpriseOperatorModel):
    request_key: LogicalKey
    cell_key: LogicalKey


class EnterpriseEvaluatorCaseTemplateV1(EnterpriseOperatorModel):
    case_key: LogicalKey
    target_kind: EvaluationCaseTargetKind
    target_key: LogicalKey
    labels: tuple[LogicalKey, ...] = Field(min_length=1)

    @field_validator("labels")
    @classmethod
    def canonical_labels(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "evaluator_case_label")


class EnterpriseEvaluationCorpusConfigV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_CORPUS_CONFIG_SCHEMA_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    compile_config: EnterpriseIdentityAccessCompileConfigV1 = Field(
        default_factory=EnterpriseIdentityAccessCompileConfigV1
    )
    contexts: tuple[EnterpriseContextTemplateV1, ...] = Field(min_length=1)
    session_slots: tuple[AuthorizationSessionSlotTemplateV1, ...] = ()
    role_activation_requests: tuple[RoleActivationRequestTemplateV1, ...] = ()
    evaluation_cells: tuple[AccessEvaluationCellTemplateV1, ...] = Field(min_length=1)
    access_requests: tuple[EnterpriseAccessRequestTemplateV1, ...] = Field(min_length=1)
    evaluator_cases: tuple[EnterpriseEvaluatorCaseTemplateV1, ...] = ()

    @field_validator("contexts")
    @classmethod
    def canonical_contexts(
        cls, value: tuple[EnterpriseContextTemplateV1, ...]
    ) -> tuple[EnterpriseContextTemplateV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.context_key,) for item in value),
            description="context_key",
        )

    @field_validator("session_slots")
    @classmethod
    def canonical_session_slots(
        cls, value: tuple[AuthorizationSessionSlotTemplateV1, ...]
    ) -> tuple[AuthorizationSessionSlotTemplateV1, ...]:
        ordered = canonical_operator_records(
            value,
            keys=tuple((item.session_state_key,) for item in value),
            description="session_state_key",
        )
        session_keys = tuple(item.session_key for item in ordered)
        if len(session_keys) != len(set(session_keys)):
            raise ValueError("duplicate_session_key")
        return ordered

    @field_validator("role_activation_requests")
    @classmethod
    def canonical_activation_requests(
        cls, value: tuple[RoleActivationRequestTemplateV1, ...]
    ) -> tuple[RoleActivationRequestTemplateV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.request_key,) for item in value),
            description="activation_request_key",
        )

    @field_validator("evaluation_cells")
    @classmethod
    def canonical_cells(
        cls, value: tuple[AccessEvaluationCellTemplateV1, ...]
    ) -> tuple[AccessEvaluationCellTemplateV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.cell_key,) for item in value),
            description="evaluation_cell_key",
        )

    @field_validator("access_requests")
    @classmethod
    def canonical_access_requests(
        cls, value: tuple[EnterpriseAccessRequestTemplateV1, ...]
    ) -> tuple[EnterpriseAccessRequestTemplateV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.request_key,) for item in value),
            description="access_request_key",
        )

    @field_validator("evaluator_cases")
    @classmethod
    def canonical_cases(
        cls, value: tuple[EnterpriseEvaluatorCaseTemplateV1, ...]
    ) -> tuple[EnterpriseEvaluatorCaseTemplateV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.case_key,) for item in value),
            description="evaluator_case_key",
        )


class EnterpriseContextV1(SyntheticModel):
    context_id: str


class AuthorizationSessionSlotV1(SyntheticModel):
    session_state_id: str
    session_id: str
    subject_id: str
    activation_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.activation_tick
        ):
            raise ValueError("generated_session_validity_interval_invalid")
        return self


class RoleActivationRequestV1(SyntheticModel):
    activation_request_id: str
    session_state_id: str
    session_id: str
    subject_id: str
    request_tick: int = Field(ge=0)
    requested_role_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("requested_role_ids")
    @classmethod
    def canonical_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "generated_requested_role_id")


class AccessEvaluationCellV1(SyntheticModel):
    cell_id: str
    access_atom_id: str
    context_id: str
    session_state_id: str | None
    tick: int = Field(ge=0)


class EnterpriseAccessRequestV1(SyntheticModel):
    access_request_id: str
    cell_id: str


class EnterpriseEvaluationCorpusV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_CORPUS_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = ENTERPRISE_CORPUS_COMPILER_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    corpus_config_digest: SyntheticDigestV1
    compile_config_digest: SyntheticDigestV1
    evaluation_cell_digest: SyntheticDigestV1
    contexts: tuple[EnterpriseContextV1, ...] = Field(min_length=1)
    session_slots: tuple[AuthorizationSessionSlotV1, ...]
    role_activation_requests: tuple[RoleActivationRequestV1, ...]
    evaluation_cells: tuple[AccessEvaluationCellV1, ...] = Field(min_length=1)
    access_requests: tuple[EnterpriseAccessRequestV1, ...] = Field(min_length=1)

    @field_validator("contexts")
    @classmethod
    def canonical_contexts(
        cls, value: tuple[EnterpriseContextV1, ...]
    ) -> tuple[EnterpriseContextV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.context_id,) for item in value),
            description="context_id",
        )

    @field_validator("session_slots")
    @classmethod
    def canonical_sessions(
        cls, value: tuple[AuthorizationSessionSlotV1, ...]
    ) -> tuple[AuthorizationSessionSlotV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.session_state_id,) for item in value),
            description="session_state_id",
        )

    @field_validator("role_activation_requests")
    @classmethod
    def canonical_activations(
        cls, value: tuple[RoleActivationRequestV1, ...]
    ) -> tuple[RoleActivationRequestV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.activation_request_id,) for item in value),
            description="activation_request_id",
        )

    @field_validator("evaluation_cells")
    @classmethod
    def canonical_cells(
        cls, value: tuple[AccessEvaluationCellV1, ...]
    ) -> tuple[AccessEvaluationCellV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.cell_id,) for item in value),
            description="evaluation_cell_id",
        )

    @field_validator("access_requests")
    @classmethod
    def canonical_requests(
        cls, value: tuple[EnterpriseAccessRequestV1, ...]
    ) -> tuple[EnterpriseAccessRequestV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.access_request_id,) for item in value),
            description="access_request_id",
        )

    @model_validator(mode="after")
    def internally_consistent(self) -> Self:
        contexts = {item.context_id for item in self.contexts}
        slots = {item.session_state_id: item for item in self.session_slots}
        if len({item.session_id for item in self.session_slots}) != len(
            self.session_slots
        ):
            raise ValueError("duplicate_generated_session_id")

        activation_counts = Counter(
            item.session_state_id for item in self.role_activation_requests
        )
        if set(activation_counts) != set(slots) or any(
            count != 1 for count in activation_counts.values()
        ):
            raise ValueError("generated_session_activation_cardinality")
        for request in self.role_activation_requests:
            slot = slots[request.session_state_id]
            if (
                request.session_id != slot.session_id
                or request.subject_id != slot.subject_id
                or request.request_tick != slot.activation_tick
            ):
                raise ValueError("generated_activation_slot_binding_differs")

        semantic_cells: set[tuple[str, str, str | None, int]] = set()
        for cell in self.evaluation_cells:
            if cell.context_id not in contexts:
                raise ValueError("unknown_generated_cell_context")
            if cell.session_state_id is not None:
                cell_slot = slots.get(cell.session_state_id)
                if cell_slot is None:
                    raise ValueError("unknown_generated_cell_session")
                if cell.tick < cell_slot.activation_tick:
                    raise ValueError("generated_cell_before_session_activation")
                if (
                    cell_slot.valid_until_tick is not None
                    and cell.tick >= cell_slot.valid_until_tick
                ):
                    raise ValueError("generated_cell_at_or_after_session_expiry")
            semantic_key = (
                cell.access_atom_id,
                cell.context_id,
                cell.session_state_id,
                cell.tick,
            )
            if semantic_key in semantic_cells:
                raise ValueError("duplicate_generated_evaluation_cell_tuple")
            semantic_cells.add(semantic_key)

        cell_ids = {item.cell_id for item in self.evaluation_cells}
        request_counts = Counter(item.cell_id for item in self.access_requests)
        if set(request_counts) != cell_ids or any(
            count != 1 for count in request_counts.values()
        ):
            raise ValueError("generated_cell_access_request_cardinality")
        expected_cell_digest = synthetic_digest(
            canonical_json_value_bytes(
                {
                    "schema_version": self.schema_version,
                    "evaluation_cells": [
                        item.model_dump(mode="json") for item in self.evaluation_cells
                    ],
                }
            )
        )
        if self.evaluation_cell_digest != expected_cell_digest:
            raise ValueError("generated_evaluation_cell_digest_mismatch")
        return self


class EnterpriseEvaluationCaseV1(SyntheticModel):
    case_id: str
    target_kind: EvaluationCaseTargetKind
    target_id: str
    labels: tuple[str, ...] = Field(min_length=1)

    @field_validator("labels")
    @classmethod
    def canonical_labels(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "generated_evaluator_case_label")


class EnterpriseEvaluationCaseInventoryV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_EVALUATOR_CASE_SCHEMA_VERSION
    evaluation_corpus_digest: SyntheticDigestV1
    cases: tuple[EnterpriseEvaluationCaseV1, ...]

    @field_validator("cases")
    @classmethod
    def canonical_cases(
        cls, value: tuple[EnterpriseEvaluationCaseV1, ...]
    ) -> tuple[EnterpriseEvaluationCaseV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.case_id,) for item in value),
            description="evaluation_case_id",
        )


@dataclass(frozen=True, slots=True)
class EnterpriseEvaluationCorpusCompileResultV1:
    """Typed in-memory public/evaluator split; never serialized as one object."""

    public_corpus: EnterpriseEvaluationCorpusV1
    evaluator_case_inventory: EnterpriseEvaluationCaseInventoryV1


__all__ = [name for name in globals() if name.startswith("Enterprise")]
__all__ += [
    "AccessEvaluationCellTemplateV1",
    "AccessEvaluationCellV1",
    "AuthorizationSessionSlotTemplateV1",
    "AuthorizationSessionSlotV1",
    "RoleActivationRequestTemplateV1",
    "RoleActivationRequestV1",
]
