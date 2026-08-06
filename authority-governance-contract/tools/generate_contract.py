#!/usr/bin/env python3
"""Generate authority-governance schemas and deterministic examples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from synthworld.authority_governance.metrics import (
    evaluate_authority_governance_prediction,
    perfect_authority_governance_prediction,
)
from synthworld.authority_governance.models import (
    AuthorityGovernanceEvaluatorV1,
    AuthorityGovernancePredictionV1,
    AuthorityGovernancePublicV1,
    AuthorityGovernanceReportV1,
)
from synthworld.authority_governance.reference import (
    reference_authority_governance,
)
from synthworld.enterprise.canonical import canonical_json_bytes
from synthworld.temporal_schedule import TemporalEventEnvelopeV2, TemporalScheduleV2

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schemas"
EXAMPLE_DIR = ROOT / "examples"
BASE_ID = (
    "https://github.com/bluntmachetti/synthworld/authority-governance-contract/schemas"
)

MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("temporal-event-envelope-v2", TemporalEventEnvelopeV2),
    ("temporal-schedule-v2", TemporalScheduleV2),
    ("authority-governance-public", AuthorityGovernancePublicV1),
    ("authority-governance-evaluator", AuthorityGovernanceEvaluatorV1),
    ("authority-governance-prediction", AuthorityGovernancePredictionV1),
    ("authority-governance-report", AuthorityGovernanceReportV1),
)


def expected_files() -> dict[Path, bytes]:
    """Return every generated file as its exact committed bytes."""

    files: dict[Path, bytes] = {}
    for stem, model in MODELS:
        schema: dict[str, Any] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{BASE_ID}/{stem}.schema.json",
            "x-generated-from": f"{model.__module__}.{model.__name__}",
            "x-generated-by": (
                "authority-governance-contract/tools/generate_contract.py"
            ),
            "x-regenerate-with": (
                "uv run python authority-governance-contract/tools/generate_contract.py"
            ),
        }
        schema.update(model.model_json_schema())
        files[SCHEMA_DIR / f"{stem}.schema.json"] = (
            json.dumps(schema, indent=2) + "\n"
        ).encode("utf-8")

    benchmark = reference_authority_governance()
    prediction = perfect_authority_governance_prediction(benchmark.evaluator)
    report = evaluate_authority_governance_prediction(
        public=benchmark.public,
        evaluator=benchmark.evaluator,
        prediction=prediction,
    )
    examples: tuple[tuple[str, BaseModel], ...] = (
        ("authority-governance-public.json", benchmark.public),
        ("authority-governance-evaluator.json", benchmark.evaluator),
        ("authority-governance-prediction.json", prediction),
        ("authority-governance-report.json", report),
    )
    for name, model in examples:
        files[EXAMPLE_DIR / name] = canonical_json_bytes(model)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = expected_files()
    if args.check:
        stale = tuple(
            path
            for path, payload in files.items()
            if not path.is_file() or path.read_bytes() != payload
        )
        if stale:
            print(
                "authority-governance contract drift: "
                + ", ".join(str(item) for item in stale),
                file=sys.stderr,
            )
            return 1
        print("authority-governance schemas and examples match the models")
        return 0
    for path, payload in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(f"wrote {len(files)} authority-governance contract files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
