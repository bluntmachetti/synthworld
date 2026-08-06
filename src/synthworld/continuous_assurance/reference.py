"""Reference composition for the continuous-assurance benchmark family."""

from __future__ import annotations

from typing import Literal

from synthworld.agentic.enterprise.reference import reference_enterprise_agentic
from synthworld.authority_governance.reference import reference_authority_governance
from synthworld.contextual_access.reference import reference_contextual_access
from synthworld.continuous_assurance.generator import (
    ContinuousAssuranceBenchmarkV1,
    ContinuousAssuranceSourceInputsV1,
    generate_continuous_assurance,
)
from synthworld.continuous_assurance.models import (
    ContinuousAssuranceConfigV1,
    ContinuousAssuranceTier,
)
from synthworld.enterprise.identity_fabric.reference import (
    reference_enterprise_identity_fabric,
)

REFERENCE_CONTINUOUS_ASSURANCE_SEED = 20_260_804


def reference_continuous_assurance_sources() -> ContinuousAssuranceSourceInputsV1:
    """Build the four concrete deterministic source-family inputs."""

    identity_fabric = reference_enterprise_identity_fabric()
    enterprise_agentic = reference_enterprise_agentic()
    contextual_access = reference_contextual_access()
    authority_governance = reference_authority_governance()
    return ContinuousAssuranceSourceInputsV1(
        identity_fabric_public=identity_fabric.public,
        identity_fabric_evaluator=identity_fabric.evaluator,
        enterprise_agentic_public=enterprise_agentic.public,
        enterprise_agentic_evaluator=enterprise_agentic.evaluator,
        contextual_access_public=contextual_access.public,
        contextual_access_evaluator=contextual_access.evaluator,
        authority_governance_public=authority_governance.public,
        authority_governance_evaluator=authority_governance.evaluator,
    )


def reference_continuous_assurance(
    *,
    tier: ContinuousAssuranceTier = ContinuousAssuranceTier.SMOKE,
    seed: int = REFERENCE_CONTINUOUS_ASSURANCE_SEED,
    risk_threshold: int = 70,
    justification_kind: Literal[
        "business_need", "case_assignment", "emergency_access"
    ] = "business_need",
) -> ContinuousAssuranceBenchmarkV1:
    """Generate a reference tier from fixed consumers and explicit inputs."""

    config = ContinuousAssuranceConfigV1(
        tier=tier,
        seed=seed,
        risk_threshold=risk_threshold,
        justification_kind=justification_kind,
    )
    return generate_continuous_assurance(
        sources=reference_continuous_assurance_sources(),
        config=config,
    )


__all__ = [
    "REFERENCE_CONTINUOUS_ASSURANCE_SEED",
    "reference_continuous_assurance",
    "reference_continuous_assurance_sources",
]
