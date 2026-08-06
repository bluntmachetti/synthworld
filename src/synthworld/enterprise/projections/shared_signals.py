"""Shared Signals/CAEP mapping declarations; temporal emission is deferred."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import model_validator

from synthworld.enterprise.models import EnterpriseOperatorModel
from synthworld.enterprise.projections.support import (
    ProjectionMappingDefinitionV1,
    ProjectionMappingProfileV1,
    ProjectionSupportClassification,
    ProjectionSupportMatrixV1,
    ProjectionTarget,
    compile_projection_support_matrix,
)

SHARED_SIGNALS_MAPPING_PROFILE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"

SHARED_SIGNALS_NATIVE_FEATURES = (
    "account_disabled",
    "credential_change",
    "domain_policy_change_as_caep",
    "effective_access_change",
    "relationship_change",
    "temporal_coordinate_projection",
)


class SharedSignalsMappingProfileV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = SHARED_SIGNALS_MAPPING_PROFILE_SCHEMA_VERSION
    temporal_base_version: Literal["synthworld-temporal-1.1.0"] = (
        "synthworld-temporal-1.1.0"
    )
    schedule_view_status: Literal["deferred_to_pr7"] = "deferred_to_pr7"
    emitted_event_projection: Literal["deferred"] = "deferred"
    mapping_profile: ProjectionMappingProfileV1

    @model_validator(mode="after")
    def correct_target(self) -> Self:
        if self.mapping_profile.target is not ProjectionTarget.SHARED_SIGNALS:
            raise ValueError("shared_signals_profile_mapping_target_mismatch")
        return self


def shared_signals_mapping_profile_v1() -> SharedSignalsMappingProfileV1:
    """Declare mappings without constructing a temporal envelope or SET."""

    return SharedSignalsMappingProfileV1(
        mapping_profile=ProjectionMappingProfileV1(
            profile_id="synthworld-shared-signals-projection",
            target=ProjectionTarget.SHARED_SIGNALS,
            native_profile_version="enterprise-authorization-1.0.0",
            target_profile_version="ssf-1.0-caep-1.0-final",
            definitions=(
                _mapping(
                    "account_disabled",
                    "caep:session-revoked",
                    "approx",
                    "ssf-account-disabled",
                ),
                _mapping(
                    "credential_change",
                    "caep:credential-change",
                    "exact",
                    "ssf-credential-change",
                ),
                _mapping(
                    "domain_policy_change_as_caep",
                    "none",
                    "unsupported",
                    "ssf-domain-event",
                ),
                _mapping(
                    "effective_access_change",
                    "urn:synthworld:event:effective-access-change:1.0",
                    "exact",
                    "ssf-effective-access",
                ),
                _mapping(
                    "relationship_change",
                    "urn:synthworld:event:relationship-change:1.0",
                    "exact",
                    "ssf-relationship",
                ),
                _mapping(
                    "temporal_coordinate_projection",
                    "SSF event time / SET iat",
                    "unsupported",
                    "ssf-temporal-coordinates",
                ),
            ),
        )
    )


def compile_shared_signals_support_matrix(
    profile: SharedSignalsMappingProfileV1,
) -> ProjectionSupportMatrixV1:
    """Compile mapping support only; PR7 owns emitted temporal events."""

    return compile_projection_support_matrix(
        profile=profile.mapping_profile,
        exercised_native_features=SHARED_SIGNALS_NATIVE_FEATURES,
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
        "account_disabled": (
            "Account disablement is not necessarily a CAEP session revocation."
        ),
        "domain_policy_change_as_caep": (
            "No standardized CAEP event type represents this domain policy change."
        ),
        "temporal_coordinate_projection": (
            "Effective tick, projected event tick, SET issue time, delivery, "
            "acceptance, and later decision time require PR7's schedule view."
        ),
    }
    return ProjectionMappingDefinitionV1(
        mapping_id=f"shared-signals-{feature}",
        native_source_feature=feature,
        target_construct=target,
        classification=classification,
        semantic_delta=deltas.get(feature),
        conformance_vector_ids=(vector,),
    )


__all__ = [
    "SHARED_SIGNALS_NATIVE_FEATURES",
    "SharedSignalsMappingProfileV1",
    "compile_shared_signals_support_matrix",
    "shared_signals_mapping_profile_v1",
]
