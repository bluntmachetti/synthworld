"""Generate and check the deterministic Asteria C08 v2 JSON schemas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from synthworld.agentic.c08_v2.models import (
    C08ArtifactManifestV2,
    C08AsteriaEvaluatorV2,
    C08AsteriaPublicInputV2,
    C08AsteriaSubmissionV2,
    C08MetricsReportV2,
)

SCHEMA_DIRECTORY = Path(__file__).resolve().parent.parent / "schemas"
SCHEMA_SPECS: tuple[tuple[str, type[BaseModel]], ...] = (
    ("c08-asteria-public-v2.schema.json", C08AsteriaPublicInputV2),
    ("c08-asteria-evaluator-v2.schema.json", C08AsteriaEvaluatorV2),
    ("c08-asteria-submission-v2.schema.json", C08AsteriaSubmissionV2),
    ("c08-asteria-manifest-v2.schema.json", C08ArtifactManifestV2),
    ("c08-asteria-report-v2.schema.json", C08MetricsReportV2),
)


def canonical_json_bytes(value: object) -> bytes:
    """Return sorted UTF-8 JSON with LF and exactly one trailing newline."""

    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def schema_documents() -> dict[str, bytes]:
    """Build every C08 schema from its authoritative Pydantic model."""

    documents: dict[str, bytes] = {}
    for filename, model in SCHEMA_SPECS:
        document: dict[str, Any] = model.model_json_schema(mode="validation")
        document["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        document["$id"] = (
            "https://github.com/bluntmachetti/synthworld/"
            f"agent-authority-contract/schemas/{filename}"
        )
        documents[filename] = canonical_json_bytes(document)
    return documents


def write_schema_directory(directory: Path = SCHEMA_DIRECTORY) -> None:
    """Write the complete generated C08 schema set."""

    directory.mkdir(parents=True, exist_ok=True)
    for filename, payload in schema_documents().items():
        (directory / filename).write_bytes(payload)


def check_schema_directory(directory: Path = SCHEMA_DIRECTORY) -> None:
    """Fail if any generated C08 schema is missing or byte-different."""

    for filename, payload in schema_documents().items():
        path = directory / filename
        if not path.is_file():
            raise RuntimeError(f"missing generated schema: {path}")
        if path.read_bytes() != payload:
            raise RuntimeError(f"generated schema drift: {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        check_schema_directory()
    else:
        write_schema_directory()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
