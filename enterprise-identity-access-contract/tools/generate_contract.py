#!/usr/bin/env python3
"""Generate enterprise identity/access schemas and cross-format examples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel

from synthworld.enterprise.models import (
    EnterpriseCanonicalBindingTruthV1,
    EnterpriseDirectoryRbacStateInputV1,
    EnterpriseIamUniverseExtensionV1,
    EnterpriseIdentityAccessBlueprintV1,
    EnterpriseIdentityAccessImportV1,
    EnterpriseIdentityAccessUniverseV1,
)
from synthworld.enterprise.reference import (
    reference_enterprise_csv_bundle,
    reference_enterprise_json,
    reference_enterprise_yaml,
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
