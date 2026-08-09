"""Frozen enterprise C08 v2 tree generation and fail-closed loading."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path

from synthworld.agentic.enterprise.c08_v2.models import (
    C08_FROZEN_SEED,
    C08EvaluatorTruthV2,
    C08FrozenArtifactV2,
    C08FrozenManifestV2,
    C08PublicInputV2,
)
from synthworld.agentic.enterprise.c08_v2.projection import (
    c08_public_input_digest,
    validate_c08_truth_against_public,
)
from synthworld.agentic.enterprise.c08_v2.reference import generate_c08_reference
from synthworld.agentic.enterprise.c08_v2.serialization import (
    load_c08_evaluator,
    load_c08_public,
    serialize_c08_evaluator,
    serialize_c08_public,
)
from synthworld.enterprise.canonical import canonical_json_bytes

PACKAGED_BENCHMARK_ROOT = "enterprise-agentic-c08-v2"
MANIFEST_PATH = "manifest.json"
CHECKSUMS_PATH = "SHA256SUMS"
PUBLIC_PATH = "public/public-input.json"
EVALUATOR_PATH = "evaluator/truth.json"
EXPECTED_FILES = frozenset(
    {MANIFEST_PATH, CHECKSUMS_PATH, PUBLIC_PATH, EVALUATOR_PATH}
)
EXPECTED_DIRECTORIES = frozenset({"public", "evaluator"})
_CHECKSUM_ROW = re.compile(r"^([0-9a-f]{64})  ([^\n]+)$")


class FrozenC08BenchmarkError(ValueError):
    """Raised when a frozen enterprise C08 tree violates its contract."""


@dataclass(frozen=True, slots=True)
class FrozenC08BenchmarkV2:
    """Loaded public/evaluator artifacts without source or submission data."""

    manifest: C08FrozenManifestV2
    public: C08PublicInputV2
    evaluator: C08EvaluatorTruthV2


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _artifact(path: str, payload: bytes) -> C08FrozenArtifactV2:
    return C08FrozenArtifactV2(
        path=path,
        byte_size=len(payload),
        sha256=_sha256(payload),
    )


def frozen_files() -> dict[str, bytes]:
    """Return canonical bytes for the fixed-seed authoritative tree."""

    bundle = generate_c08_reference(C08_FROZEN_SEED)
    public_payload = serialize_c08_public(bundle.public)
    evaluator_payload = serialize_c08_evaluator(bundle.evaluator)
    public_digest = c08_public_input_digest(bundle.public)
    if bundle.evaluator.public_input_digest != public_digest:
        raise FrozenC08BenchmarkError("generated evaluator/public digest differs")
    manifest = C08FrozenManifestV2(
        public_input_digest=public_digest,
        public_inventory=(_artifact(PUBLIC_PATH, public_payload),),
        evaluator_inventory=(_artifact(EVALUATOR_PATH, evaluator_payload),),
    )
    payloads = {
        MANIFEST_PATH: canonical_json_bytes(manifest),
        PUBLIC_PATH: public_payload,
        EVALUATOR_PATH: evaluator_payload,
    }
    payloads[CHECKSUMS_PATH] = "".join(
        f"{_sha256(payloads[path])}  {path}\n" for path in sorted(payloads)
    ).encode("ascii")
    return payloads


def write_frozen_benchmark(root: Path, *, replace: bool = False) -> None:
    """Write the authoritative tree, optionally replacing its exact inventory."""

    if root.exists():
        if root.is_symlink() or not root.is_dir():
            raise FrozenC08BenchmarkError("frozen benchmark root is not a directory")
        if any(root.iterdir()):
            if not replace:
                raise FrozenC08BenchmarkError("frozen benchmark root is not empty")
            nodes, payloads = _walk_tree(root)
            if (
                nodes != EXPECTED_FILES | EXPECTED_DIRECTORIES
                or set(payloads) != EXPECTED_FILES
            ):
                raise FrozenC08BenchmarkError(
                    "replacement root does not have the exact frozen inventory"
                )
    root.mkdir(parents=True, exist_ok=True)
    for relative_path, payload in sorted(frozen_files().items()):
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def _walk_tree(root: Path) -> tuple[set[str], dict[str, bytes]]:
    nodes: set[str] = set()
    payloads: dict[str, bytes] = {}

    def visit(directory: Path) -> None:
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            if path.is_symlink():
                raise FrozenC08BenchmarkError(f"symlink is not allowed: {path}")
            relative_path = path.relative_to(root).as_posix()
            nodes.add(relative_path)
            if path.is_dir():
                visit(path)
            elif path.is_file():
                try:
                    payloads[relative_path] = path.read_bytes()
                except OSError as error:
                    raise FrozenC08BenchmarkError(
                        f"frozen artifact is unreadable: {path}"
                    ) from error
            else:
                raise FrozenC08BenchmarkError(
                    f"frozen tree contains a non-regular node: {path}"
                )

    if root.is_symlink() or not root.is_dir():
        raise FrozenC08BenchmarkError("frozen benchmark root is not a directory")
    visit(root)
    return nodes, payloads


def _parse_manifest(payload: bytes) -> C08FrozenManifestV2:
    try:
        manifest = C08FrozenManifestV2.model_validate_json(payload)
    except (TypeError, ValueError) as error:
        raise FrozenC08BenchmarkError("frozen manifest is invalid") from error
    if payload != canonical_json_bytes(manifest):
        raise FrozenC08BenchmarkError("frozen manifest is not canonical JSON")
    return manifest


def _check_checksums(payloads: dict[str, bytes]) -> None:
    checksum_payload = payloads[CHECKSUMS_PATH]
    if not checksum_payload.endswith(b"\n") or b"\r" in checksum_payload:
        raise FrozenC08BenchmarkError("SHA256SUMS is not canonical")
    rows: list[tuple[str, str]] = []
    for raw_row in checksum_payload.splitlines():
        try:
            row = raw_row.decode("ascii")
        except UnicodeDecodeError as error:
            raise FrozenC08BenchmarkError("SHA256SUMS is not ASCII") from error
        match = _CHECKSUM_ROW.fullmatch(row)
        if match is None:
            raise FrozenC08BenchmarkError("SHA256SUMS has an invalid row")
        rows.append((match.group(2), match.group(1)))
    expected_paths = tuple(sorted(EXPECTED_FILES - {CHECKSUMS_PATH}))
    if tuple(path for path, _ in rows) != expected_paths:
        raise FrozenC08BenchmarkError("SHA256SUMS inventory differs")
    for path, digest in rows:
        if _sha256(payloads[path]) != digest:
            raise FrozenC08BenchmarkError(f"SHA256SUMS digest differs for {path}")


def load_frozen_benchmark(root: Path) -> FrozenC08BenchmarkV2:
    """Validate integrity and identity against fixed-seed canonical generation."""

    nodes, payloads = _walk_tree(root)
    expected_nodes = EXPECTED_FILES | EXPECTED_DIRECTORIES
    if nodes != expected_nodes or set(payloads) != EXPECTED_FILES:
        raise FrozenC08BenchmarkError("frozen benchmark inventory differs")
    manifest = _parse_manifest(payloads[MANIFEST_PATH])
    _check_checksums(payloads)
    try:
        public = load_c08_public(root / PUBLIC_PATH)
        evaluator = load_c08_evaluator(root / EVALUATOR_PATH)
    except ValueError as error:
        raise FrozenC08BenchmarkError("frozen C08 payload is invalid") from error
    public_digest = c08_public_input_digest(public)
    if manifest.public_input_digest != public_digest:
        raise FrozenC08BenchmarkError("manifest/public digest differs")
    if evaluator.public_input_digest != public_digest:
        raise FrozenC08BenchmarkError("evaluator/public digest differs")
    try:
        validate_c08_truth_against_public(public, evaluator)
    except ValueError as error:
        raise FrozenC08BenchmarkError("evaluator/public semantics differ") from error
    if manifest.public_inventory != (_artifact(PUBLIC_PATH, payloads[PUBLIC_PATH]),):
        raise FrozenC08BenchmarkError("manifest public inventory differs")
    if manifest.evaluator_inventory != (
        _artifact(EVALUATOR_PATH, payloads[EVALUATOR_PATH]),
    ):
        raise FrozenC08BenchmarkError("manifest evaluator inventory differs")

    canonical_payloads = frozen_files()
    canonical_bundle = generate_c08_reference(C08_FROZEN_SEED)
    if payloads != canonical_payloads:
        raise FrozenC08BenchmarkError("frozen root identity differs from canonical v2")
    if public != canonical_bundle.public or evaluator != canonical_bundle.evaluator:
        raise FrozenC08BenchmarkError("frozen models differ from canonical v2")
    return FrozenC08BenchmarkV2(
        manifest=manifest,
        public=public,
        evaluator=evaluator,
    )


def load_packaged_frozen_benchmark() -> FrozenC08BenchmarkV2:
    """Load the benchmark tree from installed package resources."""

    resource = files("synthworld.benchmarks").joinpath(PACKAGED_BENCHMARK_ROOT)
    with as_file(resource) as root:
        return load_frozen_benchmark(root)


__all__ = [
    "CHECKSUMS_PATH",
    "EVALUATOR_PATH",
    "EXPECTED_DIRECTORIES",
    "EXPECTED_FILES",
    "FrozenC08BenchmarkError",
    "FrozenC08BenchmarkV2",
    "MANIFEST_PATH",
    "PACKAGED_BENCHMARK_ROOT",
    "PUBLIC_PATH",
    "frozen_files",
    "load_frozen_benchmark",
    "load_packaged_frozen_benchmark",
    "write_frozen_benchmark",
]
