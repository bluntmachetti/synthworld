"""Pure AuthZEN 1.0 request projection and observation normalization."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import field_validator, model_validator

from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.compiler import EnterpriseCompileError
from synthworld.enterprise.models import (
    AccessSubjectKind,
    EnterpriseIdentityAccessUniverseV1,
    EnterpriseOperatorModel,
    SyntheticDigestV1,
    TargetKind,
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
    AuthorizationDecision,
    canonical_synthetic_records,
)
from synthworld.enterprise.rbac.corpus_models import (
    EnterpriseAccessRequestV1,
    EnterpriseEvaluationCorpusV1,
)
from synthworld.models import SyntheticModel

AUTHZEN_MAPPING_PROFILE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
AUTHZEN_REQUEST_PROJECTION_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
AUTHZEN_OBSERVATION_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
AUTHZEN_PROJECTION_COMPILER_VERSION: Literal["1.0.0"] = "1.0.0"

AUTHZEN_NATIVE_FEATURES = (
    "action_identity",
    "context_slot",
    "logical_tick",
    "native_four_outcome_semantics",
    "resource_identity",
    "subject_identity",
)


class AuthZenMappingProfileV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = AUTHZEN_MAPPING_PROFILE_SCHEMA_VERSION
    mapping_profile: ProjectionMappingProfileV1

    @model_validator(mode="after")
    def correct_target(self) -> Self:
        if self.mapping_profile.target is not ProjectionTarget.AUTHZEN:
            raise ValueError("authzen_profile_mapping_target_mismatch")
        return self


class AuthZenSubjectV1(SyntheticModel):
    type: AccessSubjectKind
    id: str


class AuthZenActionV1(SyntheticModel):
    id: str


class AuthZenResourceV1(SyntheticModel):
    type: TargetKind
    id: str


class AuthZenContextV1(SyntheticModel):
    context_id: str
    logical_tick: int
    session_state_id: str | None


class AuthZenFieldProvenanceV1(SyntheticModel):
    target_field: str
    native_source: str


class AuthZenRequestProjectionV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = AUTHZEN_REQUEST_PROJECTION_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = AUTHZEN_PROJECTION_COMPILER_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    access_request_id: str
    cell_id: str
    subject: AuthZenSubjectV1
    action: AuthZenActionV1
    resource: AuthZenResourceV1
    context: AuthZenContextV1
    field_provenance: tuple[AuthZenFieldProvenanceV1, ...]
    mapping_digest: SyntheticDigestV1
    support_matrix: ProjectionSupportMatrixV1

    @field_validator("field_provenance")
    @classmethod
    def canonical_provenance(
        cls, value: tuple[AuthZenFieldProvenanceV1, ...]
    ) -> tuple[AuthZenFieldProvenanceV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.target_field,) for item in value),
            description="authzen_target_field",
        )

    @model_validator(mode="after")
    def mapping_matches_matrix(self) -> Self:
        if (
            self.support_matrix.target is not ProjectionTarget.AUTHZEN
            or self.support_matrix.mapping_digest != self.mapping_digest
        ):
            raise ValueError("authzen_support_matrix_binding_mismatch")
        return self


class AuthZenRawOutcome(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    INDETERMINATE = "indeterminate"
    TRANSPORT_ERROR = "transport_error"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"


class AuthZenDecisionObservationV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = AUTHZEN_OBSERVATION_SCHEMA_VERSION
    access_request_id: str
    raw_outcome: AuthZenRawOutcome
    boolean_decision: bool | None
    transport_evidence_digest: SyntheticDigestV1 | None = None

    @model_validator(mode="after")
    def outcome_matches_boolean(self) -> Self:
        expected = {
            AuthZenRawOutcome.ALLOW: True,
            AuthZenRawOutcome.DENY: False,
        }.get(self.raw_outcome)
        if self.boolean_decision is not expected:
            raise ValueError("authzen_raw_outcome_boolean_mismatch")
        return self


class AuthZenNormalizedObservationV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = AUTHZEN_OBSERVATION_SCHEMA_VERSION
    access_request_id: str
    raw_outcome: AuthZenRawOutcome
    raw_boolean_decision: bool | None
    normalized_decision: AuthorizationDecision | None
    transport_evidence_digest: SyntheticDigestV1 | None


def authzen_mapping_profile_v1() -> AuthZenMappingProfileV1:
    return AuthZenMappingProfileV1(
        mapping_profile=ProjectionMappingProfileV1(
            profile_id="synthworld-authzen-projection",
            target=ProjectionTarget.AUTHZEN,
            native_profile_version="enterprise-authorization-1.0.0",
            target_profile_version="authzen-authorization-api-1.0-final",
            definitions=(
                _mapping("action_identity", "Action.id", "exact", "authzen-action"),
                _mapping(
                    "context_slot", "Context.context_id", "exact", "authzen-context"
                ),
                _mapping(
                    "logical_tick", "Context.logical_tick", "approx", "authzen-tick"
                ),
                _mapping(
                    "native_four_outcome_semantics",
                    "boolean decision",
                    "unsupported",
                    "authzen-outcome",
                ),
                _mapping(
                    "resource_identity", "Resource.type/id", "exact", "authzen-resource"
                ),
                _mapping(
                    "subject_identity", "Subject.type/id", "exact", "authzen-subject"
                ),
            ),
        )
    )


def project_authzen(
    *,
    universe: EnterpriseIdentityAccessUniverseV1,
    corpus: EnterpriseEvaluationCorpusV1,
    request: EnterpriseAccessRequestV1,
    mapping_profile: AuthZenMappingProfileV1,
) -> AuthZenRequestProjectionV1:
    """Project one frozen request without embedding an expected decision."""

    universe_digest = synthetic_digest(canonical_json_bytes(universe))
    corpus_digest = synthetic_digest(canonical_json_bytes(corpus))
    if corpus.identity_access_universe_digest != universe_digest:
        raise EnterpriseCompileError(
            "authzen_corpus_universe_digest_mismatch",
            "evaluation corpus does not bind the supplied universe",
        )
    known_request = next(
        (
            item
            for item in corpus.access_requests
            if item.access_request_id == request.access_request_id
        ),
        None,
    )
    if known_request != request:
        raise EnterpriseCompileError(
            "authzen_unknown_or_mismatched_request",
            "AuthZEN request must exactly match one frozen corpus request",
        )
    cell = next(
        item for item in corpus.evaluation_cells if item.cell_id == request.cell_id
    )
    atom = next(
        item
        for item in universe.access_atoms
        if item.access_atom_id == cell.access_atom_id
    )
    subject = next(
        item for item in universe.access_subjects if item.subject_id == atom.subject_id
    )
    target = next(
        item
        for item in universe.authorization_targets
        if item.authorization_target_id == atom.authorization_target_id
    )
    matrix = compile_projection_support_matrix(
        profile=mapping_profile.mapping_profile,
        exercised_native_features=AUTHZEN_NATIVE_FEATURES,
    )
    return AuthZenRequestProjectionV1(
        identity_access_universe_digest=universe_digest,
        evaluation_corpus_digest=corpus_digest,
        access_request_id=request.access_request_id,
        cell_id=cell.cell_id,
        subject=AuthZenSubjectV1(type=subject.subject_kind, id=subject.subject_id),
        action=AuthZenActionV1(id=atom.action),
        resource=AuthZenResourceV1(
            type=target.target_kind, id=target.authorization_target_id
        ),
        context=AuthZenContextV1(
            context_id=cell.context_id,
            logical_tick=cell.tick,
            session_state_id=cell.session_state_id,
        ),
        field_provenance=(
            AuthZenFieldProvenanceV1(
                target_field="Action.id", native_source="AccessAtomV1.action"
            ),
            AuthZenFieldProvenanceV1(
                target_field="Context.context_id",
                native_source="AccessEvaluationCellV1.context_id",
            ),
            AuthZenFieldProvenanceV1(
                target_field="Context.logical_tick",
                native_source="AccessEvaluationCellV1.tick",
            ),
            AuthZenFieldProvenanceV1(
                target_field="Context.session_state_id",
                native_source="AccessEvaluationCellV1.session_state_id",
            ),
            AuthZenFieldProvenanceV1(
                target_field="Resource.id",
                native_source="AccessAtomV1.authorization_target_id",
            ),
            AuthZenFieldProvenanceV1(
                target_field="Resource.type",
                native_source="EnterpriseAuthorizationTargetV1.target_kind",
            ),
            AuthZenFieldProvenanceV1(
                target_field="Subject.id", native_source="AccessAtomV1.subject_id"
            ),
            AuthZenFieldProvenanceV1(
                target_field="Subject.type",
                native_source="EnterpriseAccessSubjectV1.subject_kind",
            ),
        ),
        mapping_digest=matrix.mapping_digest,
        support_matrix=matrix,
    )


def normalize_authzen_observation(
    observation: AuthZenDecisionObservationV1,
) -> AuthZenNormalizedObservationV1:
    normalized = {
        AuthZenRawOutcome.ALLOW: AuthorizationDecision.ALLOW,
        AuthZenRawOutcome.DENY: AuthorizationDecision.DENY,
    }.get(observation.raw_outcome)
    return AuthZenNormalizedObservationV1(
        access_request_id=observation.access_request_id,
        raw_outcome=observation.raw_outcome,
        raw_boolean_decision=observation.boolean_decision,
        normalized_decision=normalized,
        transport_evidence_digest=observation.transport_evidence_digest,
    )


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
        "logical_tick": (
            "AuthZEN Context carries the integer as data but defines no "
            "SynthWorld clock."
        ),
        "native_four_outcome_semantics": (
            "The AuthZEN response is boolean; unknown and not-applicable remain "
            "native truth only."
        ),
    }
    return ProjectionMappingDefinitionV1(
        mapping_id=f"authzen-{feature}",
        native_source_feature=feature,
        target_construct=target,
        classification=classification,
        semantic_delta=deltas.get(feature),
        conformance_vector_ids=(vector,),
    )


__all__ = [
    "AUTHZEN_NATIVE_FEATURES",
    "AuthZenDecisionObservationV1",
    "AuthZenMappingProfileV1",
    "AuthZenNormalizedObservationV1",
    "AuthZenRawOutcome",
    "AuthZenRequestProjectionV1",
    "authzen_mapping_profile_v1",
    "normalize_authzen_observation",
    "project_authzen",
]
