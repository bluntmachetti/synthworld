"""Validate and emit a no-network Hugging Face publication dry run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

HF_TARGETS = frozenset({"hugging_face_raw", "hugging_face_viewer"})
REQUIRED_HF_CHECKS = frozenset(
    {
        "adversarial_review",
        "boundary_validation",
        "catalogue_hf_metadata",
        "checksums",
        "safety_review",
    }
)
KNOWN_TARGETS = frozenset(
    {
        "docs_catalog",
        "hugging_face_raw",
        "hugging_face_viewer",
        "python_package",
        "repository",
    }
)


class PublicationError(ValueError):
    """Raised when local publication controls are inconsistent."""


def canonical_json(value: object) -> str:
    """Return the repository's canonical human-readable JSON representation."""

    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def file_sha256(path: Path) -> str:
    """Hash a local file without consulting host or network state."""

    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError) as error:
        raise PublicationError(f"cannot hash local file: {path}") from error


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    """Load one JSON object and normalize read/parse failures."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise PublicationError(f"{label}: cannot read JSON from {path}") from error
    if not isinstance(value, dict):
        raise PublicationError(f"{label}: top-level JSON value must be an object")
    return value


def validate_schema(instance: object, schema: dict[str, Any], label: str) -> None:
    """Validate an object and report the first deterministic schema error."""

    try:
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema).iter_errors(instance),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except SchemaError as error:
        raise PublicationError(f"{label}: invalid JSON schema") from error
    if errors:
        location = "/".join(str(part) for part in errors[0].absolute_path) or "<root>"
        raise PublicationError(
            f"{label}: schema error at {location}: {errors[0].message}"
        )


def read_card_configs(path: Path) -> list[dict[str, Any]]:
    """Extract and normalize the historical dataset-card config inventory."""

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise PublicationError(f"dataset card: cannot read {path}") from error
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise PublicationError("dataset card: YAML frontmatter is missing")
    frontmatter = text[4:].split("\n---\n", 1)[0]
    try:
        metadata = yaml.safe_load(frontmatter)
    except yaml.YAMLError as error:
        raise PublicationError("dataset card: invalid YAML frontmatter") from error
    if not isinstance(metadata, dict) or not isinstance(metadata.get("configs"), list):
        raise PublicationError("dataset card: configs must use the expected shape")
    normalized: list[dict[str, Any]] = []
    for config in metadata["configs"]:
        if not isinstance(config, dict) or set(config) - {
            "config_name",
            "data_files",
            "default",
        }:
            raise PublicationError("dataset card: config has unexpected fields")
        if not isinstance(config.get("config_name"), str) or not isinstance(
            config.get("data_files"), list
        ):
            raise PublicationError("dataset card: config has invalid fields")
        default = config.get("default", False)
        default_explicit = "default" in config
        if not isinstance(default, bool):
            raise PublicationError("dataset card: default must be boolean")
        data_files: list[dict[str, str]] = []
        for data_file in config["data_files"]:
            if (
                not isinstance(data_file, dict)
                or set(data_file) != {"path", "split"}
                or not isinstance(data_file.get("path"), str)
                or not isinstance(data_file.get("split"), str)
            ):
                raise PublicationError("dataset card: data file has invalid fields")
            data_files.append(
                {"path": data_file["path"], "split": data_file["split"]}
            )
        normalized.append(
            {
                "config_name": config["config_name"],
                "data_files": data_files,
                "default": default,
                "default_explicit": default_explicit,
            }
        )
    return normalized


def _target_set(value: object, label: str) -> set[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) for item in value)
        or len(set(value)) != len(value)
        or not set(value).issubset(KNOWN_TARGETS)
    ):
        raise PublicationError(f"{label}: invalid publication targets")
    return set(value)


def _source_file(repository_root: Path, source_path: str) -> Path:
    root = repository_root.resolve()
    candidate = (root / source_path).resolve()
    if candidate == root or root not in candidate.parents:
        raise PublicationError(f"artifact path escapes repository: {source_path}")
    return candidate


def _approved_hf_gate(
    gate: dict[str, Any],
    benchmark_id: str,
    benchmark_version: str,
    expected_gate_id: str,
) -> set[str]:
    gate_targets = HF_TARGETS.intersection(
        _target_set(gate.get("approved_targets"), benchmark_id)
    )
    if not gate_targets:
        return set()
    if (
        gate.get("decision") != "approved"
        or gate.get("id") != expected_gate_id
        or gate.get("benchmark_id") != benchmark_id
        or gate.get("benchmark_version") != benchmark_version
    ):
        raise PublicationError(
            f"{benchmark_id}: HF publication gate identity is invalid"
        )
    checks = gate.get("checks")
    if not isinstance(checks, list):
        raise PublicationError(f"{benchmark_id}: HF publication checks are missing")
    statuses: dict[str, str] = {}
    for check in checks:
        if (
            not isinstance(check, dict)
            or not isinstance(check.get("name"), str)
            or not isinstance(check.get("status"), str)
            or check["name"] in statuses
        ):
            raise PublicationError(f"{benchmark_id}: HF publication checks are invalid")
        statuses[check["name"]] = check["status"]
    if any(statuses.get(name) != "pass" for name in REQUIRED_HF_CHECKS):
        raise PublicationError(
            f"{benchmark_id}: required HF publication checks did not pass"
        )
    return gate_targets


def derive_registry_state(
    registry: dict[str, Any],
    repository_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Derive exactly what HF operations the resolved registry authorizes."""

    benchmarks = registry.get("benchmarks")
    if not isinstance(benchmarks, list):
        raise PublicationError("resolved registry: benchmarks must be an array")

    operations: list[dict[str, Any]] = []
    authorized_targets: defaultdict[tuple[str, str], set[str]] = defaultdict(set)
    lifecycle_counts: Counter[str] = Counter()
    seen_benchmark_identities: set[tuple[str, str]] = set()
    for benchmark in benchmarks:
        if not isinstance(benchmark, dict):
            raise PublicationError("resolved registry: malformed benchmark entry")
        try:
            benchmark_id = benchmark["id"]
            benchmark_version = benchmark["benchmark_version"]
            artifact_ids = benchmark["artifact_ids"]
            lifecycle = benchmark["lifecycle"]
            artifacts = benchmark["artifacts"]
            publication_gate_id = benchmark["publication_gate_id"]
        except KeyError as error:
            raise PublicationError(
                "resolved registry: malformed benchmark entry"
            ) from error
        if (
            not isinstance(benchmark_id, str)
            or not isinstance(benchmark_version, str)
            or not isinstance(artifact_ids, list)
            or any(not isinstance(item, str) for item in artifact_ids)
            or len(set(artifact_ids)) != len(artifact_ids)
            or not isinstance(lifecycle, str)
            or not isinstance(artifacts, list)
            or not isinstance(publication_gate_id, (str, type(None)))
        ):
            raise PublicationError("resolved registry: malformed benchmark entry")
        identity = (benchmark_id, benchmark_version)
        if identity in seen_benchmark_identities:
            raise PublicationError(
                f"duplicate benchmark identity: {benchmark_id}@{benchmark_version}"
            )
        seen_benchmark_identities.add(identity)
        lifecycle_counts[lifecycle] += 1
        gate = benchmark.get("publication_gate")
        if gate is None:
            gate_targets: set[str] = set()
        elif isinstance(gate, dict):
            if not isinstance(publication_gate_id, str):
                raise PublicationError(
                    f"{benchmark_id}: publication gate ID is missing"
                )
            gate_targets = _approved_hf_gate(
                gate,
                benchmark_id,
                benchmark_version,
                publication_gate_id,
            )
        else:
            raise PublicationError("resolved registry: malformed publication gate")

        observed_artifact_ids: list[str] = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise PublicationError("resolved registry: malformed artifact entry")
            artifact_id = artifact.get("id")
            artifact_benchmark_id = artifact.get("benchmark_id")
            artifact_kind = artifact.get("kind")
            sensitivity = artifact.get("sensitivity")
            answer_key_label = artifact.get("answer_key_label")
            if (
                not isinstance(artifact_id, str)
                or artifact_benchmark_id != benchmark_id
                or not isinstance(artifact_kind, str)
                or not isinstance(sensitivity, str)
                or not isinstance(answer_key_label, (str, type(None)))
            ):
                raise PublicationError("resolved registry: malformed artifact entry")
            observed_artifact_ids.append(artifact_id)
            artifact_targets = _target_set(
                artifact.get("approved_targets"), artifact_id
            )
            targets = sorted(gate_targets.intersection(artifact_targets))
            for target in targets:
                source_path = artifact.get("path")
                approved_sha256 = artifact.get("approved_sha256")
                if not isinstance(source_path, str) or not isinstance(
                    approved_sha256, str
                ):
                    raise PublicationError(
                        f"{artifact_id}: HF-authorized artifacts require "
                        "a path and digest"
                    )
                if artifact_kind == "public_input" and (
                    sensitivity != "public_input" or answer_key_label is not None
                ):
                    raise PublicationError(
                        f"{artifact_id}: public input cannot carry answer-key metadata"
                    )
                if target == "hugging_face_viewer":
                    evaluator_marker = re.compile(
                        r"(?:^|[-_./])(evaluator|answer|truth)(?:$|[-_./])"
                    )
                    if (
                        artifact_kind != "public_input"
                        or evaluator_marker.search(source_path.casefold())
                    ):
                        raise PublicationError(
                            f"{artifact_id}: Viewer publication requires "
                            "a public-only artifact"
                        )
                elif artifact_kind != "public_input" and (
                    artifact_kind != "evaluator_truth"
                    or sensitivity != "public_reference_truth"
                    or not answer_key_label
                ):
                    raise PublicationError(
                        f"{artifact_id}: raw reference truth requires "
                        "explicit evaluator labeling"
                    )
                source_file = _source_file(repository_root, source_path)
                if file_sha256(source_file) != approved_sha256:
                    raise PublicationError(
                        f"{artifact_id}: source bytes do not match the approved digest"
                    )
                operations.append(
                    {
                        "answer_key_label": answer_key_label,
                        "artifact_id": artifact_id,
                        "artifact_kind": artifact_kind,
                        "benchmark_id": benchmark_id,
                        "sha256": approved_sha256,
                        "sensitivity": sensitivity,
                        "source_path": source_path,
                        "target": target,
                    }
                )
                authorized_targets[(benchmark_id, benchmark_version)].add(target)
        if artifact_ids != observed_artifact_ids:
            raise PublicationError(
                f"{benchmark_id}: artifact IDs do not match artifact records"
            )

    operations.sort(
        key=lambda item: (
            item["benchmark_id"],
            item["artifact_id"],
            item["target"],
        )
    )
    authorized_benchmarks = [
        {
            "benchmark_id": benchmark_id,
            "benchmark_version": benchmark_version,
            "targets": sorted(targets),
        }
        for (benchmark_id, benchmark_version), targets in sorted(
            authorized_targets.items()
        )
    ]
    summary = {
        "candidate": lifecycle_counts["candidate"],
        "hf_authorized_artifacts": len({item["artifact_id"] for item in operations}),
        "published": lifecycle_counts["published"],
        "total": len(benchmarks),
    }
    return operations, authorized_benchmarks, summary


def build_plan(
    manifest: dict[str, Any], operations: list[dict[str, Any]]
) -> dict[str, Any]:
    """Construct the evidence artifact without adding upload capability."""

    return {
        "dataset_repository": manifest["dataset_repository"],
        "network_access": False,
        "operations": operations,
        "registry_sha256": manifest["registry"]["sha256"],
        "status": (
            "ready_for_protected_dry_run"
            if operations
            else "blocked_no_authorized_targets"
        ),
        "upload_enabled": False,
    }


def validate_publication(
    manifest_path: Path,
    schema_path: Path,
    registry_path: Path,
    registry_schema_path: Path,
    card_path: Path,
    repository_root: Path,
) -> dict[str, Any]:
    """Validate all local controls and return the deterministic dry-run plan."""

    manifest = load_json_object(manifest_path, "publication manifest")
    schema = load_json_object(schema_path, "publication manifest schema")
    registry = load_json_object(registry_path, "resolved registry")
    registry_schema = load_json_object(registry_schema_path, "resolved registry schema")
    validate_schema(manifest, schema, "publication manifest")
    validate_schema(registry, registry_schema, "resolved registry")

    try:
        manifest_bytes = manifest_path.read_bytes()
    except (OSError, ValueError) as error:
        raise PublicationError(
            "publication manifest: cannot read canonical bytes"
        ) from error
    if manifest_bytes != canonical_json(manifest).encode("utf-8"):
        raise PublicationError("publication manifest: JSON is not canonical")
    for label, path, expected in (
        ("resolved registry", registry_path, manifest["registry"]["sha256"]),
        ("dataset card", card_path, manifest["historical_card"]["sha256"]),
    ):
        if file_sha256(path) != expected:
            raise PublicationError(f"{label}: SHA-256 does not match the manifest")

    card_configs = read_card_configs(card_path)
    if card_configs != manifest["historical_card"]["configs"]:
        raise PublicationError(
            "dataset card: config inventory does not match the manifest"
        )

    operations, authorized_benchmarks, summary = derive_registry_state(
        registry, repository_root
    )
    for field, derived in (
        ("operations", operations),
        ("authorized_benchmarks", authorized_benchmarks),
        ("registry_summary", summary),
    ):
        if manifest[field] != derived:
            raise PublicationError(
                f"publication manifest: {field} does not match the registry"
            )

    return build_plan(manifest, operations)


def build_parser() -> argparse.ArgumentParser:
    """Build the local-only command-line interface."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("huggingface/publication-manifest.json"),
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("huggingface/publication-manifest.schema.json"),
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("docs/_data/benchmarks.resolved.json"),
    )
    parser.add_argument(
        "--registry-schema",
        type=Path,
        default=Path("docs/_schemas/benchmarks-resolved.schema.json"),
    )
    parser.add_argument(
        "--card", type=Path, default=Path("huggingface/README.md")
    )
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--emit-plan", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the checker without network access or upload capability."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        plan = validate_publication(
            args.manifest,
            args.schema,
            args.registry,
            args.registry_schema,
            args.card,
            args.repository_root,
        )
    except PublicationError as error:
        parser.error(str(error))
    rendered = canonical_json(plan)
    if args.emit_plan is None:
        print(rendered, end="")
    else:
        args.emit_plan.parent.mkdir(parents=True, exist_ok=True)
        args.emit_plan.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
