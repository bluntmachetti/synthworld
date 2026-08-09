"""Deterministic package-owned recipes for published benchmark artifacts."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from synthworld.agentic.generator import generate_asteria_agentic_v1
from synthworld.agentic.serialization import export_agentic_benchmark
from synthworld.ambiguity_baselines import AMBIGUITY_BASELINE_SEED
from synthworld.ambiguity_generator import generate_ambiguity_benchmark
from synthworld.ambiguity_serialization import ambiguity_artifacts, ambiguity_manifest
from synthworld.authority_governance.reference import (
    reference_authority_governance,
)
from synthworld.authority_governance.serialization import (
    export_authority_governance_benchmark,
)
from synthworld.connection_generator import generate_adversarial_connection_benchmark
from synthworld.connection_serialization import (
    connection_benchmark_to_json,
    public_connection_corpus_to_json,
)
from synthworld.corpus_serialization import corpus_to_json
from synthworld.exposure_generator import generate_exposure_corpus
from synthworld.extraction_generator import (
    generate_extraction_benchmark,
    generate_extraction_corpus,
)
from synthworld.extraction_serialization import (
    extraction_answers_to_json,
    extraction_corpus_to_json,
    public_extraction_corpus_to_json,
)
from synthworld.risk_generator import generate_risk_benchmark
from synthworld.risk_serialization import (
    public_risk_corpus_to_json,
    risk_answer_key_to_json,
)

PublishedBenchmarkId = Literal[
    "ambiguity-v1",
    "asteria-agentic-v1",
    "authority-governance-v1",
    "connection-v1",
    "core-world-v1",
    "extraction-v1",
    "risk-v1",
]

PUBLISHED_BENCHMARK_IDS: tuple[PublishedBenchmarkId, ...] = (
    "ambiguity-v1",
    "asteria-agentic-v1",
    "authority-governance-v1",
    "connection-v1",
    "core-world-v1",
    "extraction-v1",
    "risk-v1",
)

_GOLDEN_SEED = 20_260_719

_ASTERIA_PATHS = (
    "asteria-agentic-v1/evaluator/authority_truth.jsonl",
    "asteria-agentic-v1/evaluator/canonical_bindings.json",
    "asteria-agentic-v1/evaluator/cases.jsonl",
    "asteria-agentic-v1/evaluator/checksums.json",
    "asteria-agentic-v1/evaluator/evidence_epochs.jsonl",
    "asteria-agentic-v1/evaluator/expected_decisions.jsonl",
    "asteria-agentic-v1/evaluator/expected_provenance.jsonl",
    "asteria-agentic-v1/evaluator/expected_side_effects.jsonl",
    "asteria-agentic-v1/public/agents.jsonl",
    "asteria-agentic-v1/public/manifest.json",
    "asteria-agentic-v1/public/organisation.json",
    "asteria-agentic-v1/public/principals.jsonl",
    "asteria-agentic-v1/public/public_credentials.jsonl",
    "asteria-agentic-v1/public/public_delegations.jsonl",
    "asteria-agentic-v1/public/public_events.jsonl",
    "asteria-agentic-v1/public/resources.jsonl",
    "asteria-agentic-v1/public/runtimes.jsonl",
    "asteria-agentic-v1/public/scenarios/procurement-delegation.json",
    "asteria-agentic-v1/public/tool_schemas/procurement-tools.json",
)

_AUTHORITY_PAYLOAD_PATHS = (
    "authority-governance-v1/evaluator/authority-governance-evaluator.json",
    "authority-governance-v1/evaluator/manifest.json",
    "authority-governance-v1/public/authority-governance-input.json",
    "authority-governance-v1/public/manifest.json",
)


def reproduce_benchmark(
    benchmark_id: PublishedBenchmarkId,
    output_directory: Path,
) -> tuple[Path, ...]:
    """Create one complete published benchmark family in a new directory.

    Returned paths are absolute when ``output_directory`` is absolute and retain
    the same paths relative to that directory as package benchmark resources.
    """

    try:
        recipe = _RECIPES[benchmark_id]
    except KeyError as error:
        raise ValueError(f"unknown published benchmark ID: {benchmark_id}") from error

    output_directory = Path(output_directory)
    if output_directory.exists():
        raise FileExistsError(f"benchmark output already exists: {output_directory}")
    output_directory.mkdir(parents=True)
    return recipe(output_directory)


def _reproduce_ambiguity(root: Path) -> tuple[Path, ...]:
    benchmark = generate_ambiguity_benchmark(seed=AMBIGUITY_BASELINE_SEED)
    artifacts = ambiguity_artifacts(benchmark)
    artifacts["AMBIGUITY_SHA256SUMS"] = ambiguity_manifest(artifacts).encode("ascii")
    return _write_artifacts(root, artifacts)


def _reproduce_asteria(root: Path) -> tuple[Path, ...]:
    export_agentic_benchmark(
        root / "asteria-agentic-v1",
        generate_asteria_agentic_v1(),
    )
    return tuple(root / relative_path for relative_path in _ASTERIA_PATHS)


def _reproduce_authority(root: Path) -> tuple[Path, ...]:
    benchmark = reference_authority_governance()
    benchmark_root = root / "authority-governance-v1"
    export_authority_governance_benchmark(
        benchmark_root,
        public=benchmark.public,
        evaluator=benchmark.evaluator,
    )
    manifest = b"".join(
        _checksum_line(
            relative_path.removeprefix("authority-governance-v1/"),
            (root / relative_path).read_bytes(),
        )
        for relative_path in _AUTHORITY_PAYLOAD_PATHS
    )
    checksum_path = benchmark_root / "SHA256SUMS"
    checksum_path.write_bytes(manifest)
    paths = (*_AUTHORITY_PAYLOAD_PATHS, "authority-governance-v1/SHA256SUMS")
    return tuple(root / relative_path for relative_path in sorted(paths))


def _reproduce_connection(root: Path) -> tuple[Path, ...]:
    benchmark = generate_adversarial_connection_benchmark(seed=_GOLDEN_SEED)
    joined = connection_benchmark_to_json(benchmark).encode("utf-8")
    public = public_connection_corpus_to_json(benchmark.public).encode("utf-8")
    return _write_artifacts(
        root,
        {
            "connection-golden-v1.json": joined,
            "CONNECTION_SHA256SUMS": _checksum_line(
                "connection-golden-v1.json", joined
            ),
            "connection-public-golden-v1.json": public,
            "CONNECTION_PUBLIC_SHA256SUMS": _checksum_line(
                "connection-public-golden-v1.json", public
            ),
        },
    )


def _reproduce_core_world(root: Path) -> tuple[Path, ...]:
    payload = corpus_to_json(
        generate_exposure_corpus(seed=_GOLDEN_SEED, persona_count=10)
    ).encode("utf-8")
    return _write_artifacts(
        root,
        {
            "golden-v1.json": payload,
            "SHA256SUMS": _checksum_line("golden-v1.json", payload),
        },
    )


def _reproduce_extraction(root: Path) -> tuple[Path, ...]:
    corpus = generate_extraction_corpus(seed=_GOLDEN_SEED, persona_count=10)
    benchmark = generate_extraction_benchmark(seed=_GOLDEN_SEED, persona_count=10)
    joined = extraction_corpus_to_json(corpus).encode("utf-8")
    public = public_extraction_corpus_to_json(benchmark.public).encode("utf-8")
    answers = extraction_answers_to_json(benchmark.answers).encode("utf-8")
    return _write_artifacts(
        root,
        {
            "extraction-golden-v1.json": joined,
            "EXTRACTION_SHA256SUMS": _checksum_line(
                "extraction-golden-v1.json", joined
            ),
            "extraction-public-golden-v1.json": public,
            "EXTRACTION_PUBLIC_SHA256SUMS": _checksum_line(
                "extraction-public-golden-v1.json", public
            ),
            "extraction-answer-golden-v1.json": answers,
            "EXTRACTION_ANSWER_SHA256SUMS": _checksum_line(
                "extraction-answer-golden-v1.json", answers
            ),
        },
    )


def _reproduce_risk(root: Path) -> tuple[Path, ...]:
    benchmark = generate_risk_benchmark(seed=_GOLDEN_SEED, persona_count=10)
    public = public_risk_corpus_to_json(benchmark.public).encode("utf-8")
    answers = risk_answer_key_to_json(benchmark.answer_key).encode("utf-8")
    return _write_artifacts(
        root,
        {
            "risk-public-golden-v1.json": public,
            "RISK_PUBLIC_SHA256SUMS": _checksum_line(
                "risk-public-golden-v1.json", public
            ),
            "risk-answer-golden-v1.json": answers,
            "RISK_ANSWER_SHA256SUMS": _checksum_line(
                "risk-answer-golden-v1.json", answers
            ),
        },
    )


def _checksum_line(relative_path: str, payload: bytes) -> bytes:
    return f"{hashlib.sha256(payload).hexdigest()}  {relative_path}\n".encode("ascii")


def _write_artifacts(root: Path, artifacts: dict[str, bytes]) -> tuple[Path, ...]:
    paths: list[Path] = []
    for relative_path, payload in sorted(artifacts.items()):
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        paths.append(path)
    return tuple(paths)


_RECIPES: dict[PublishedBenchmarkId, Callable[[Path], tuple[Path, ...]]] = {
    "ambiguity-v1": _reproduce_ambiguity,
    "asteria-agentic-v1": _reproduce_asteria,
    "authority-governance-v1": _reproduce_authority,
    "connection-v1": _reproduce_connection,
    "core-world-v1": _reproduce_core_world,
    "extraction-v1": _reproduce_extraction,
    "risk-v1": _reproduce_risk,
}

__all__ = [
    "PUBLISHED_BENCHMARK_IDS",
    "PublishedBenchmarkId",
    "reproduce_benchmark",
]
