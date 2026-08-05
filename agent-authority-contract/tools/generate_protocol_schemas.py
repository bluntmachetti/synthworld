"""Generate receipt-v2 and agent-authority protocol JSON Schemas.

Usage::

    uv run python agent-authority-contract/tools/generate_protocol_schemas.py

Use ``--check`` in CI to fail without rewriting stale committed schemas.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from synthworld.agent_authority.models import (
    AgentAuthorityLabReportV1,
    AgentAuthorityLabTruthV1,
    AgentAuthorityRunObservationsV1,
    AgentAuthorityRunPlanV1,
)
from synthworld.agent_authority.models_v2 import AgentAuthorityRunObservationsV2
from synthworld.assurance.models_v2 import ExecutionReceiptV2, RunReceiptManifestV2

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
BASE_ID = "https://github.com/bluntmachetti/synthworld/agent-authority-contract/schemas"
_UTC_TIMESTAMP_PATTERN = (
    r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])"
    r"T([01]\d|2[0-3]):[0-5]\d:[0-5]\d(\.\d+)?(Z|[+-]00:00)$"
)

MODELS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("agent-authority-run-plan", AgentAuthorityRunPlanV1),
    ("agent-authority-observations", AgentAuthorityRunObservationsV1),
    ("agent-authority-observations-v2", AgentAuthorityRunObservationsV2),
    ("agent-authority-lab-truth", AgentAuthorityLabTruthV1),
    ("agent-authority-lab-report", AgentAuthorityLabReportV1),
    ("execution-receipt-v2", ExecutionReceiptV2),
    ("run-receipt-manifest-v2", RunReceiptManifestV2),
)


def _assert_utc_timestamps(value: object) -> None:
    if isinstance(value, dict):
        if value.get("type") == "string" and value.get("format") == "date-time":
            value["pattern"] = _UTC_TIMESTAMP_PATTERN
        for child in value.values():
            _assert_utc_timestamps(child)
    elif isinstance(value, list):
        for child in value:
            _assert_utc_timestamps(child)


def build() -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for stem, model in MODELS:
        schema = model.model_json_schema()
        _assert_utc_timestamps(schema)
        decorated: dict[str, Any] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"{BASE_ID}/{stem}.schema.json",
            "x-generated-from": f"{model.__module__}.{model.__name__}",
            "x-generated-by": (
                "agent-authority-contract/tools/generate_protocol_schemas.py"
            ),
            "x-regenerate-with": (
                "uv run python "
                "agent-authority-contract/tools/generate_protocol_schemas.py"
            ),
        }
        decorated.update(schema)
        schemas[stem] = decorated
    return schemas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when committed schemas differ from the models",
    )
    args = parser.parse_args()
    stale: list[str] = []
    for stem, schema in build().items():
        target = SCHEMAS_DIR / f"{stem}.schema.json"
        rendered = json.dumps(schema, indent=2) + "\n"
        if args.check:
            if not target.exists() or target.read_text(encoding="utf-8") != rendered:
                stale.append(str(target))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        print(f"wrote {target}")
    if stale:
        for path in stale:
            print(f"STALE: {path} does not match the model", file=sys.stderr)
        print("re-run without --check to regenerate", file=sys.stderr)
        return 1
    if args.check:
        print("protocol schemas match the models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
