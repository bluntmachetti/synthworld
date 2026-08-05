#!/usr/bin/env python3
"""Generate continuous-assurance schemas and deterministic smoke examples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from synthworld.continuous_assurance import (
    ContinuousAssuranceConfigV1,
    ContinuousAssuranceEvaluatorV1,
    ContinuousAssurancePredictionV1,
    ContinuousAssurancePublicV1,
    ContinuousAssuranceReportV1,
    evaluate_continuous_assurance_prediction,
    perfect_continuous_assurance_prediction,
    reference_continuous_assurance,
)
from synthworld.enterprise.canonical import canonical_json_bytes

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schemas"
EXAMPLE_DIR = ROOT / "examples"
BASE_ID = (
    "https://github.com/bluntmachetti/synthworld/continuous-assurance-contract/schemas"
)

MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("continuous-assurance-config", ContinuousAssuranceConfigV1),
    ("continuous-assurance-public", ContinuousAssurancePublicV1),
    ("continuous-assurance-evaluator", ContinuousAssuranceEvaluatorV1),
    ("continuous-assurance-prediction", ContinuousAssurancePredictionV1),
    ("continuous-assurance-report", ContinuousAssuranceReportV1),
)


def expected_files() -> dict[Path, bytes]:
    """Return every generated file as its exact committed bytes."""

    files: dict[Path, bytes] = {}
    for stem, schema_model in MODELS:
        schema: dict[str, Any] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{BASE_ID}/{stem}.schema.json",
            "x-generated-from": (f"{schema_model.__module__}.{schema_model.__name__}"),
            "x-generated-by": (
                "continuous-assurance-contract/tools/generate_contract.py"
            ),
            "x-regenerate-with": (
                "uv run python continuous-assurance-contract/tools/generate_contract.py"
            ),
        }
        schema.update(schema_model.model_json_schema())
        files[SCHEMA_DIR / f"{stem}.schema.json"] = (
            json.dumps(schema, indent=2) + "\n"
        ).encode("utf-8")

    benchmark = reference_continuous_assurance()
    prediction = perfect_continuous_assurance_prediction(benchmark.evaluator)
    report = evaluate_continuous_assurance_prediction(
        public=benchmark.public,
        evaluator=benchmark.evaluator,
        prediction=prediction,
    )
    examples: tuple[tuple[str, BaseModel], ...] = (
        ("continuous-assurance-config.json", benchmark.config),
        ("continuous-assurance-public.json", benchmark.public),
        ("continuous-assurance-evaluator.json", benchmark.evaluator),
        ("continuous-assurance-prediction.json", prediction),
        ("continuous-assurance-report.json", report),
    )
    for name, example_model in examples:
        files[EXAMPLE_DIR / name] = canonical_json_bytes(example_model)
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
                "continuous-assurance contract drift: "
                + ", ".join(str(item) for item in stale),
                file=sys.stderr,
            )
            return 1
        print("continuous-assurance schemas and examples match the models")
        return 0
    for path, payload in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(f"wrote {len(files)} continuous-assurance contract files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
