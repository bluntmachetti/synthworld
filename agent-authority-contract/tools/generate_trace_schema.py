"""Generate the ObservedActionTrace JSON Schema from the authoritative model.

The pydantic models in ``synthworld.agentic.models`` are the contract. This script
projects them into language-neutral JSON Schema so non-Python adapters can validate
their output, and it exists so the projection is reproducible rather than folklore:
if the model changes, re-run this and commit the diff.

Usage::

    uv run python agent-authority-contract/tools/generate_trace_schema.py

Add ``--check`` to fail without writing when the committed schema is stale, which is
what a future CI step should call.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from synthworld.agentic.models import AgenticTraceSubmission, ObservedActionTrace

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

BASE_ID = "https://github.com/bluntmachetti/synthworld/agent-authority-contract/schemas"

ROW_DESCRIPTION = """\
One system-under-test observation of one attempted agent action.

The wire format is JSON Lines: one object per line, one line per action event in
the benchmark's public event stream, keyed by `event_id`. The scorer requires the
submitted set of `event_id` values to equal the benchmark's action-event set
exactly - no omissions, no duplicates, no extras.

Every field except `event_id` is nullable, and null carries meaning: it asserts
that the system did not capture that value. Null is scored as a miss, never
back-filled or ignored, so emitting null is an honest answer rather than a way to
avoid being wrong. Do not substitute empty strings or empty arrays for null; for
`evidence_refs` in particular an empty array and null are scored differently.

This schema is generated from `synthworld.agentic.models.ObservedActionTrace`. It
is a projection of that model, not an independent definition: where the two
disagree, the model is correct and this file is stale.\
"""

ENVELOPE_DESCRIPTION = """\
The batch form of a trace submission, holding many observations as one document.

Provided for tooling that prefers a single JSON object over JSON Lines. The scorer's
CLI reads JSON Lines; this envelope is the in-memory equivalent and rejects
duplicate `event_id` values.\
"""


def _decorate(schema: dict[str, Any], name: str, description: str) -> dict[str, Any]:
    """Prepend JSON Schema metadata that pydantic does not emit."""
    decorated: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"{BASE_ID}/{name}.schema.json",
        "x-generated-from": f"synthworld.agentic.models.{schema.get('title', name)}",
        "x-generated-by": "agent-authority-contract/tools/generate_trace_schema.py",
        "x-regenerate-with": (
            "uv run python agent-authority-contract/tools/generate_trace_schema.py"
        ),
        "description": description,
    }
    decorated.update(schema)
    return decorated


def build() -> dict[str, dict[str, Any]]:
    """Return the schemas to write, keyed by file stem."""
    return {
        "observed-action-trace": _decorate(
            ObservedActionTrace.model_json_schema(),
            "observed-action-trace",
            ROW_DESCRIPTION,
        ),
        "agentic-trace-submission": _decorate(
            AgenticTraceSubmission.model_json_schema(),
            "agentic-trace-submission",
            ENVELOPE_DESCRIPTION,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if a committed schema differs from the model",
    )
    args = parser.parse_args()

    stale: list[str] = []
    for stem, schema in build().items():
        target = SCHEMAS_DIR / f"{stem}.schema.json"
        rendered = json.dumps(schema, indent=2, sort_keys=False) + "\n"
        if args.check:
            current = target.read_text() if target.exists() else ""
            if current != rendered:
                stale.append(str(target))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered)
        print(f"wrote {target}")

    if stale:
        for path in stale:
            print(f"STALE: {path} does not match the model", file=sys.stderr)
        print("re-run without --check to regenerate", file=sys.stderr)
        return 1
    if args.check:
        print("schemas match the models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
