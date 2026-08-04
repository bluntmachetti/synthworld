#!/usr/bin/env python3
"""Generate enterprise identity/access schemas and cross-format examples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from synthworld.enterprise.abac.metrics import (
    EnterpriseAbacMetricsV1,
    EnterpriseAbacPredictionV1,
)
from synthworld.enterprise.abac.models import (
    CompiledEnterpriseAbacTruthV1,
    EnterpriseAbacIntentOverlayV1,
    EnterpriseAbacStateOverlayV1,
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
from synthworld.enterprise.canonical import canonical_json_bytes
from synthworld.enterprise.conformance.models import (
    AuthorizationConformanceVectorV1,
    PolicyCoverageManifestV1,
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
