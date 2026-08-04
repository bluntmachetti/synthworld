#!/usr/bin/env python3
"""Generate enterprise identity/access schemas and cross-format examples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from synthworld.enterprise.canonical import canonical_json_bytes
from synthworld.enterprise.models import (
    EnterpriseCanonicalBindingTruthV1,
    EnterpriseDirectoryRbacStateInputV1,
    EnterpriseIamUniverseExtensionV1,
    EnterpriseIdentityAccessBlueprintV1,
    EnterpriseIdentityAccessImportV1,
    EnterpriseIdentityAccessUniverseV1,
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
