#!/usr/bin/env python3
"""Generate and check the enterprise C08 v2 JSON schemas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from synthworld.agentic.enterprise.c08_v2.models import (
    C08EvaluationReportV2,
    C08EvaluatorTruthV2,
    C08PublicInputV2,
    C08SubmissionV2,
)

ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SCHEMA_MODELS: Final[dict[str, type[BaseModel]]] = {
    "c08-enterprise-public-v2.schema.json": C08PublicInputV2,
    "c08-enterprise-evaluator-v2.schema.json": C08EvaluatorTruthV2,
    "c08-enterprise-submission-v2.schema.json": C08SubmissionV2,
    "c08-enterprise-report-v2.schema.json": C08EvaluationReportV2,
}


class C08SchemaDriftError(RuntimeError):
    """Raised when generated C08 schemas are missing or stale."""


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def expected_schema_files(root: Path = ROOT) -> dict[Path, bytes]:
    """Return deterministic schema bytes keyed by their expected paths."""

    schema_dir = root / "schemas"
    return {
        schema_dir / filename: _json_bytes(model.model_json_schema())
        for filename, model in SCHEMA_MODELS.items()
    }


def write_schema_files(root: Path = ROOT) -> None:
    """Write all C08 v2 schemas from the authoritative models."""

    for path, payload in expected_schema_files(root).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def check_schema_files(root: Path = ROOT) -> None:
    """Fail without writing when any expected C08 v2 schema is missing or stale."""

    problems: list[str] = []
    expected_files = expected_schema_files(root)
    expected_names = {path.name for path in expected_files}
    schema_dir = root / "schemas"
    problems.extend(
        f"unexpected {path}"
        for path in sorted(schema_dir.glob("c08-enterprise-*-v2.schema.json"))
        if path.is_file() and path.name not in expected_names
    )
    for path, expected in expected_files.items():
        if not path.is_file():
            problems.append(f"missing {path}")
        elif path.read_bytes() != expected:
            problems.append(f"drifted {path}")
    if problems:
        raise C08SchemaDriftError(
            "C08 v2 schemas do not match the models: " + "; ".join(problems)
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="check generated schemas without writing files",
    )
    args = parser.parse_args(argv)
    try:
        if args.check:
            check_schema_files()
            print("C08 v2 schemas match the models")
        else:
            write_schema_files()
            print("Generated C08 v2 schemas")
    except C08SchemaDriftError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
