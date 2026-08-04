#!/usr/bin/env python3
"""Generate contextual-access schemas and deterministic smoke examples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from synthworld.contextual_access.metrics import (
    evaluate_contextual_access_prediction,
    perfect_contextual_access_prediction,
)
from synthworld.contextual_access.models import (
    ContextualAccessConfigV1,
    ContextualAccessEvaluatorV1,
    ContextualAccessMetricsV1,
    ContextualAccessPredictionV1,
    ContextualAccessPublicV1,
    ContextualObjectRegistryV1,
)
from synthworld.contextual_access.protocol import (
    ContextualAccessObservationsV1,
    ContextualAccessReportV1,
    ContextualAccessRunPlanV1,
    ContextualAccessRunTruthV1,
)
from synthworld.contextual_access.protocol_reference import (
    reference_contextual_access_run,
)
from synthworld.contextual_access.reference import reference_contextual_access
from synthworld.contextual_access.shared_signals import (
    ContextualSharedSignalsMappingProfileV1,
    ContextualSharedSignalsProjectionV1,
    contextual_shared_signals_mapping_profile_v1,
    project_contextual_shared_signals,
)
from synthworld.enterprise.canonical import canonical_json_bytes
from synthworld.temporal_schedule import TemporalEventEnvelopeV1, TemporalScheduleV1

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schemas"
EXAMPLE_DIR = ROOT / "examples"
BASE_ID = (
    "https://github.com/bluntmachetti/synthworld/contextual-access-contract/schemas"
)

MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("temporal-event-envelope-v1", TemporalEventEnvelopeV1),
    ("temporal-schedule-v1", TemporalScheduleV1),
    ("contextual-access-config", ContextualAccessConfigV1),
    ("contextual-object-registry", ContextualObjectRegistryV1),
    ("contextual-access-public", ContextualAccessPublicV1),
    ("contextual-access-evaluator", ContextualAccessEvaluatorV1),
    ("contextual-access-prediction", ContextualAccessPredictionV1),
    ("contextual-access-metrics", ContextualAccessMetricsV1),
    ("contextual-access-run-plan", ContextualAccessRunPlanV1),
    ("contextual-access-observations", ContextualAccessObservationsV1),
    ("contextual-access-run-truth", ContextualAccessRunTruthV1),
    ("contextual-access-report", ContextualAccessReportV1),
    (
        "contextual-shared-signals-mapping-profile",
        ContextualSharedSignalsMappingProfileV1,
    ),
    ("contextual-shared-signals-projection", ContextualSharedSignalsProjectionV1),
)


def expected_files() -> dict[Path, bytes]:
    """Return every generated schema and example as exact committed bytes."""

    files: dict[Path, bytes] = {}
    for stem, model in MODELS:
        schema: dict[str, Any] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{BASE_ID}/{stem}.schema.json",
            "x-generated-from": f"{model.__module__}.{model.__name__}",
            "x-generated-by": "contextual-access-contract/tools/generate_contract.py",
            "x-regenerate-with": (
                "uv run python contextual-access-contract/tools/generate_contract.py"
            ),
        }
        schema.update(model.model_json_schema())
        files[SCHEMA_DIR / f"{stem}.schema.json"] = (
            json.dumps(schema, indent=2) + "\n"
        ).encode("utf-8")

    benchmark = reference_contextual_access()
    prediction = perfect_contextual_access_prediction(
        public=benchmark.public,
        evaluator=benchmark.evaluator,
    )
    metrics = evaluate_contextual_access_prediction(
        public=benchmark.public,
        evaluator=benchmark.evaluator,
        prediction=prediction,
    )
    run = reference_contextual_access_run()
    shared_signals_profile = contextual_shared_signals_mapping_profile_v1()
    shared_signals_projection = project_contextual_shared_signals(
        benchmark.public,
        profile=shared_signals_profile,
    )
    examples: tuple[tuple[str, BaseModel], ...] = (
        ("contextual-access-config.json", benchmark.config),
        ("contextual-access-public.json", benchmark.public),
        ("contextual-access-evaluator.json", benchmark.evaluator),
        ("contextual-access-prediction.json", prediction),
        ("contextual-access-metrics.json", metrics),
        ("contextual-access-run-plan.json", run.plan),
        ("contextual-access-observations.json", run.observations),
        ("contextual-access-run-truth.json", run.truth),
        ("contextual-access-report.json", run.report),
        (
            "contextual-shared-signals-mapping-profile.json",
            shared_signals_profile,
        ),
        ("contextual-shared-signals-projection.json", shared_signals_projection),
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
                "contextual-access contract drift: "
                + ", ".join(str(item) for item in stale),
                file=sys.stderr,
            )
            return 1
        print("contextual-access schemas and examples match the models")
        return 0
    for path, payload in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(f"wrote {len(files)} contextual-access contract files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
