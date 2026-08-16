#!/usr/bin/env python3
"""Generate enterprise identity/access schemas and cross-format examples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from synthworld.agentic.enterprise.metrics import (
    evaluate_enterprise_agentic_prediction,
    perfect_enterprise_agentic_prediction,
)
from synthworld.agentic.enterprise.models import (
    EnterpriseAgenticBenchmarkV1,
    EnterpriseAgenticEvaluatorArtifactsV1,
    EnterpriseAgenticMetricsV1,
    EnterpriseAgenticPredictionV1,
    EnterpriseAgenticPublicInputV1,
    EnterpriseAgenticTruthV1,
)
from synthworld.agentic.enterprise.reference import reference_enterprise_agentic
from synthworld.enterprise.abac.metrics import (
    EnterpriseAbacMetricsV1,
    EnterpriseAbacPredictionV1,
)
from synthworld.enterprise.abac.models import (
    CompiledEnterpriseAbacTruthV1,
    EnterpriseAbacIntentOverlayV1,
    EnterpriseAbacStateOverlayV1,
)
from synthworld.enterprise.authorization.adversarial.metrics import (
    evaluate_enterprise_adversarial_authorization,
    perfect_enterprise_adversarial_authorization_prediction,
)
from synthworld.enterprise.authorization.adversarial.models import (
    EnterpriseAdversarialAuthorizationEvaluatorV1,
    EnterpriseAdversarialAuthorizationMetricsV1,
    EnterpriseAdversarialAuthorizationPredictionV1,
    EnterpriseAdversarialAuthorizationPublicV1,
)
from synthworld.enterprise.authorization.adversarial.reference import (
    reference_enterprise_adversarial_authorization,
)
from synthworld.enterprise.authorization.metrics import (
    EnterpriseAuthorizationEvaluationScopeV1,
    EnterpriseAuthorizationExecutionMetadataV1,
    EnterpriseAuthorizationMetricsV1,
    EnterpriseAuthorizationPredictionV1,
    evaluate_enterprise_authorization,
    perfect_enterprise_authorization_prediction,
)
from synthworld.enterprise.authorization.models import (
    AuthorizationEvaluationProfileV1,
    CompiledEnterpriseAccessStateV1,
    EnterpriseAuthorizationCompositionV1,
    EnterpriseAuthorizationKernelV1,
)
from synthworld.enterprise.authorization.reference import (
    reference_enterprise_authorization_inputs,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.conformance.models import (
    AuthorizationConformanceVectorV1,
    PolicyCoverageManifestV1,
)
from synthworld.enterprise.identity_fabric.metrics import (
    evaluate_enterprise_identity_fabric,
    perfect_enterprise_identity_fabric_prediction,
)
from synthworld.enterprise.identity_fabric.models import (
    EnterpriseIdentityFabricBenchmarkV1,
    EnterpriseIdentityFabricEvaluatorArtifactsV1,
    EnterpriseIdentityFabricMetricsV1,
    EnterpriseIdentityFabricPredictionV1,
    EnterpriseIdentityFabricPublicInputV1,
    EnterpriseIdentityFabricTruthV1,
)
from synthworld.enterprise.identity_fabric.reference import (
    reference_enterprise_identity_fabric,
)
from synthworld.enterprise.models import (
    EnterpriseCanonicalBindingTruthV1,
    EnterpriseDirectoryRbacStateInputV1,
    EnterpriseIamUniverseExtensionV1,
    EnterpriseIdentityAccessBlueprintV1,
    EnterpriseIdentityAccessImportV1,
    EnterpriseIdentityAccessUniverseV1,
)
from synthworld.enterprise.projections.authzen import (
    AuthZenDecisionObservationV1,
    AuthZenMappingProfileV1,
    AuthZenNormalizedObservationV1,
    AuthZenRequestProjectionV1,
)
from synthworld.enterprise.projections.openfga import (
    OpenFgaMappingProfileV1,
    OpenFgaProjectionV1,
)
from synthworld.enterprise.projections.scim import (
    ScimProjectionProfileV1,
    ScimProjectionV1,
)
from synthworld.enterprise.projections.shared_signals import (
    SharedSignalsMappingProfileV1,
)
from synthworld.enterprise.projections.support import (
    ProjectionFidelityMetricsV1,
    ProjectionMappingProfileV1,
    ProjectionSupportMatrixV1,
)
from synthworld.enterprise.rbac.corpus_models import (
    EnterpriseEvaluationCaseInventoryV1,
    EnterpriseEvaluationCorpusConfigV1,
    EnterpriseEvaluationCorpusV1,
)
from synthworld.enterprise.rbac.metrics import (
    EnterpriseDirectoryRbacMetricsV1,
    EnterpriseDirectoryRbacPredictionV1,
)
from synthworld.enterprise.rbac.models import (
    CompiledEnterpriseDirectoryRbacTruthV1,
    EnterpriseDirectoryRbacIntentOverlayV1,
    EnterpriseDirectoryRbacKernelV1,
    EnterpriseRbacSessionStateInputV1,
)
from synthworld.enterprise.rbac.reference import (
    reference_enterprise_evaluation_corpus_config,
    reference_enterprise_rbac_inputs,
)
from synthworld.enterprise.rebac.metrics import (
    EnterpriseRebacMetricsV1,
    EnterpriseRebacPredictionV1,
)
from synthworld.enterprise.rebac.models import (
    CompiledEnterpriseRebacTruthV1,
    EnterpriseRebacIntentOverlayV1,
    EnterpriseRebacStateOverlayV1,
)
from synthworld.enterprise.reference import (
    reference_enterprise_csv_bundle,
    reference_enterprise_json,
    reference_enterprise_yaml,
)
from synthworld.enterprise.standards import (
    StandardsProfileLedgerV1,
    standards_profile_ledger_v1,
)

ROOT = Path("enterprise-identity-access-contract")
SCHEMA_DIR = ROOT / "schemas"
EXAMPLE_DIR = ROOT / "examples"

SCHEMAS: dict[str, type[BaseModel]] = {
    "enterprise-identity-access-import.schema.json": EnterpriseIdentityAccessImportV1,
    "enterprise-identity-access-blueprint.schema.json": (
        EnterpriseIdentityAccessBlueprintV1
    ),
    "enterprise-iam-universe-extension.schema.json": EnterpriseIamUniverseExtensionV1,
    "enterprise-directory-rbac-state-input.schema.json": (
        EnterpriseDirectoryRbacStateInputV1
    ),
    "enterprise-identity-access-universe.schema.json": (
        EnterpriseIdentityAccessUniverseV1
    ),
    "enterprise-canonical-binding-truth.schema.json": EnterpriseCanonicalBindingTruthV1,
    "standards-profile-ledger.schema.json": StandardsProfileLedgerV1,
    "enterprise-evaluation-corpus-config.schema.json": (
        EnterpriseEvaluationCorpusConfigV1
    ),
    "enterprise-evaluation-corpus.schema.json": EnterpriseEvaluationCorpusV1,
    "enterprise-evaluation-case-inventory.schema.json": (
        EnterpriseEvaluationCaseInventoryV1
    ),
    "enterprise-directory-rbac-intent.schema.json": (
        EnterpriseDirectoryRbacIntentOverlayV1
    ),
    "enterprise-rbac-session-state-input.schema.json": (
        EnterpriseRbacSessionStateInputV1
    ),
    "enterprise-directory-rbac-kernel.schema.json": EnterpriseDirectoryRbacKernelV1,
    "compiled-enterprise-directory-rbac-truth.schema.json": (
        CompiledEnterpriseDirectoryRbacTruthV1
    ),
    "enterprise-directory-rbac-prediction.schema.json": (
        EnterpriseDirectoryRbacPredictionV1
    ),
    "enterprise-directory-rbac-metrics.schema.json": EnterpriseDirectoryRbacMetricsV1,
    "enterprise-abac-state.schema.json": EnterpriseAbacStateOverlayV1,
    "enterprise-abac-intent.schema.json": EnterpriseAbacIntentOverlayV1,
    "compiled-enterprise-abac-truth.schema.json": CompiledEnterpriseAbacTruthV1,
    "enterprise-abac-prediction.schema.json": EnterpriseAbacPredictionV1,
    "enterprise-abac-metrics.schema.json": EnterpriseAbacMetricsV1,
    "enterprise-rebac-state.schema.json": EnterpriseRebacStateOverlayV1,
    "enterprise-rebac-intent.schema.json": EnterpriseRebacIntentOverlayV1,
    "compiled-enterprise-rebac-truth.schema.json": CompiledEnterpriseRebacTruthV1,
    "enterprise-rebac-prediction.schema.json": EnterpriseRebacPredictionV1,
    "enterprise-rebac-metrics.schema.json": EnterpriseRebacMetricsV1,
    "enterprise-authorization-composition.schema.json": (
        EnterpriseAuthorizationCompositionV1
    ),
    "enterprise-authorization-evaluation-profile.schema.json": (
        AuthorizationEvaluationProfileV1
    ),
    "enterprise-authorization-kernel.schema.json": EnterpriseAuthorizationKernelV1,
    "compiled-enterprise-access-state.schema.json": CompiledEnterpriseAccessStateV1,
    "enterprise-authorization-evaluation-scope.schema.json": (
        EnterpriseAuthorizationEvaluationScopeV1
    ),
    "enterprise-authorization-prediction.schema.json": (
        EnterpriseAuthorizationPredictionV1
    ),
    "enterprise-authorization-metrics.schema.json": EnterpriseAuthorizationMetricsV1,
    "enterprise-adversarial-authorization-public.schema.json": (
        EnterpriseAdversarialAuthorizationPublicV1
    ),
    "enterprise-adversarial-authorization-evaluator.schema.json": (
        EnterpriseAdversarialAuthorizationEvaluatorV1
    ),
    "enterprise-adversarial-authorization-prediction.schema.json": (
        EnterpriseAdversarialAuthorizationPredictionV1
    ),
    "enterprise-adversarial-authorization-metrics.schema.json": (
        EnterpriseAdversarialAuthorizationMetricsV1
    ),
    "projection-mapping-profile.schema.json": ProjectionMappingProfileV1,
    "projection-support-matrix.schema.json": ProjectionSupportMatrixV1,
    "projection-fidelity-metrics.schema.json": ProjectionFidelityMetricsV1,
    "authorization-conformance-vector.schema.json": AuthorizationConformanceVectorV1,
    "policy-coverage-manifest.schema.json": PolicyCoverageManifestV1,
    "scim-projection-profile.schema.json": ScimProjectionProfileV1,
    "scim-projection.schema.json": ScimProjectionV1,
    "authzen-mapping-profile.schema.json": AuthZenMappingProfileV1,
    "authzen-request-projection.schema.json": AuthZenRequestProjectionV1,
    "authzen-decision-observation.schema.json": AuthZenDecisionObservationV1,
    "authzen-normalized-observation.schema.json": AuthZenNormalizedObservationV1,
    "openfga-mapping-profile.schema.json": OpenFgaMappingProfileV1,
    "openfga-projection.schema.json": OpenFgaProjectionV1,
    "shared-signals-mapping-profile.schema.json": SharedSignalsMappingProfileV1,
    "enterprise-identity-fabric-benchmark.schema.json": (
        EnterpriseIdentityFabricBenchmarkV1
    ),
    "enterprise-identity-fabric-public-input.schema.json": (
        EnterpriseIdentityFabricPublicInputV1
    ),
    "enterprise-identity-fabric-truth.schema.json": EnterpriseIdentityFabricTruthV1,
    "enterprise-identity-fabric-evaluator.schema.json": (
        EnterpriseIdentityFabricEvaluatorArtifactsV1
    ),
    "enterprise-identity-fabric-prediction.schema.json": (
        EnterpriseIdentityFabricPredictionV1
    ),
    "enterprise-identity-fabric-metrics.schema.json": (
        EnterpriseIdentityFabricMetricsV1
    ),
    "enterprise-agentic-benchmark.schema.json": EnterpriseAgenticBenchmarkV1,
    "enterprise-agentic-public-input.schema.json": EnterpriseAgenticPublicInputV1,
    "enterprise-agentic-truth.schema.json": EnterpriseAgenticTruthV1,
    "enterprise-agentic-evaluator.schema.json": (EnterpriseAgenticEvaluatorArtifactsV1),
    "enterprise-agentic-prediction.schema.json": EnterpriseAgenticPredictionV1,
    "enterprise-agentic-metrics.schema.json": EnterpriseAgenticMetricsV1,
}


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()


def expected_files() -> dict[Path, bytes]:
    files = {
        SCHEMA_DIR / name: _json_bytes(model.model_json_schema())
        for name, model in SCHEMAS.items()
    }
    files[EXAMPLE_DIR / "enterprise-access-smoke.json"] = (
        reference_enterprise_json().encode()
    )
    files[EXAMPLE_DIR / "enterprise-access-smoke.yaml"] = (
        reference_enterprise_yaml().encode()
    )
    for name, payload in reference_enterprise_csv_bundle().items():
        files[EXAMPLE_DIR / "csv" / name] = payload.encode()
    files[ROOT / "standards-profile-ledger.json"] = canonical_json_bytes(
        standards_profile_ledger_v1()
    )
    reference_rbac = reference_enterprise_rbac_inputs()
    files[EXAMPLE_DIR / "enterprise-rbac-corpus-config.json"] = _json_bytes(
        reference_enterprise_evaluation_corpus_config().model_dump(mode="json")
    )
    files[EXAMPLE_DIR / "enterprise-directory-rbac-intent.json"] = _json_bytes(
        reference_rbac.intent.model_dump(mode="json")
    )
    files[EXAMPLE_DIR / "enterprise-rbac-session-state.json"] = _json_bytes(
        reference_rbac.session_state.model_dump(mode="json")
    )
    reference_authorization = reference_enterprise_authorization_inputs()
    files[EXAMPLE_DIR / "enterprise-abac-state.json"] = _json_bytes(
        reference_authorization.abac_state.model_dump(mode="json")
    )
    files[EXAMPLE_DIR / "enterprise-abac-intent.json"] = _json_bytes(
        reference_authorization.abac_intent.model_dump(mode="json")
    )
    files[EXAMPLE_DIR / "enterprise-rebac-state.json"] = _json_bytes(
        reference_authorization.rebac_state.model_dump(mode="json")
    )
    files[EXAMPLE_DIR / "enterprise-rebac-intent.json"] = _json_bytes(
        reference_authorization.rebac_intent.model_dump(mode="json")
    )
    files[EXAMPLE_DIR / "enterprise-authorization-evaluation-profile.json"] = (
        _json_bytes(reference_authorization.evaluation_profile.model_dump(mode="json"))
    )
    files[EXAMPLE_DIR / "enterprise-authorization-evaluation-scope.json"] = (
        canonical_json_bytes(reference_authorization.evaluation_scope)
    )
    authorization_prediction = perfect_enterprise_authorization_prediction(
        reference_authorization.access_state,
        scope=reference_authorization.evaluation_scope,
        execution=EnterpriseAuthorizationExecutionMetadataV1(
            synthworld_package_version="development",
            adapter_name="reference-adapter",
            adapter_version="1.0.0",
            system_name="reference-authorizer",
            system_version="1.0.0",
            policy_name="reference-composition",
            policy_version="1.0.0",
            policy_sha256=synthetic_digest(
                canonical_json_bytes(reference_authorization.composition)
            ).value,
        ),
    )
    authorization_metrics = evaluate_enterprise_authorization(
        scope=reference_authorization.evaluation_scope,
        truth=reference_authorization.access_state,
        predictions=authorization_prediction,
    )
    files[EXAMPLE_DIR / "enterprise-authorization-prediction.json"] = (
        canonical_json_bytes(authorization_prediction)
    )
    files[EXAMPLE_DIR / "enterprise-authorization-metrics.json"] = canonical_json_bytes(
        authorization_metrics
    )
    reference_adversarial = reference_enterprise_adversarial_authorization()
    adversarial_prediction = perfect_enterprise_adversarial_authorization_prediction(
        reference_adversarial.evaluator
    )
    adversarial_metrics = evaluate_enterprise_adversarial_authorization(
        public=reference_adversarial.public,
        evaluator=reference_adversarial.evaluator,
        prediction=adversarial_prediction,
    )
    files[EXAMPLE_DIR / "enterprise-adversarial-authorization-public.json"] = (
        canonical_json_bytes(reference_adversarial.public)
    )
    files[EXAMPLE_DIR / "enterprise-adversarial-authorization-evaluator.json"] = (
        canonical_json_bytes(reference_adversarial.evaluator)
    )
    files[EXAMPLE_DIR / "enterprise-adversarial-authorization-prediction.json"] = (
        canonical_json_bytes(adversarial_prediction)
    )
    files[EXAMPLE_DIR / "enterprise-adversarial-authorization-metrics.json"] = (
        canonical_json_bytes(adversarial_metrics)
    )
    reference_identity_fabric = reference_enterprise_identity_fabric()
    perfect_identity_fabric_prediction = perfect_enterprise_identity_fabric_prediction(
        reference_identity_fabric.evaluator
    )
    perfect_identity_fabric_metrics = evaluate_enterprise_identity_fabric(
        artifacts=reference_identity_fabric.evaluator,
        predictions=perfect_identity_fabric_prediction,
    )
    files[EXAMPLE_DIR / "enterprise-identity-fabric-public-input.json"] = (
        canonical_json_bytes(reference_identity_fabric.public)
    )
    files[EXAMPLE_DIR / "enterprise-identity-fabric-evaluator.json"] = (
        canonical_json_bytes(reference_identity_fabric.evaluator)
    )
    files[EXAMPLE_DIR / "enterprise-identity-fabric-prediction.json"] = (
        canonical_json_bytes(perfect_identity_fabric_prediction)
    )
    files[EXAMPLE_DIR / "enterprise-identity-fabric-metrics.json"] = (
        canonical_json_bytes(perfect_identity_fabric_metrics)
    )
    reference_agentic = reference_enterprise_agentic()
    perfect_agentic_prediction = perfect_enterprise_agentic_prediction(
        reference_agentic.evaluator
    )
    perfect_agentic_metrics = evaluate_enterprise_agentic_prediction(
        public=reference_agentic.public,
        evaluator=reference_agentic.evaluator,
        prediction=perfect_agentic_prediction,
    )
    files[EXAMPLE_DIR / "enterprise-agentic-public-input.json"] = canonical_json_bytes(
        reference_agentic.public
    )
    files[EXAMPLE_DIR / "enterprise-agentic-evaluator.json"] = canonical_json_bytes(
        reference_agentic.evaluator
    )
    files[EXAMPLE_DIR / "enterprise-agentic-prediction.json"] = canonical_json_bytes(
        perfect_agentic_prediction
    )
    files[EXAMPLE_DIR / "enterprise-agentic-metrics.json"] = canonical_json_bytes(
        perfect_agentic_metrics
    )
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = expected_files()
    if args.check:
        mismatches = [
            path
            for path, payload in files.items()
            if not path.is_file() or path.read_bytes() != payload
        ]
        if mismatches:
            print(
                "enterprise contract drift: "
                + ", ".join(str(path) for path in mismatches),
                file=sys.stderr,
            )
            return 1
        print("enterprise identity/access schemas and examples match the models")
        return 0
    for path, payload in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(f"wrote {len(files)} enterprise contract files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
