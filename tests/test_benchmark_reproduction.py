from __future__ import annotations

import ast
from importlib.resources import files
from pathlib import Path
from typing import cast

import pytest

from synthworld.benchmark_reproduction import (
    PUBLISHED_BENCHMARK_IDS,
    PublishedBenchmarkId,
    reproduce_benchmark,
)

_EXPECTED_PATHS: dict[PublishedBenchmarkId, tuple[str, ...]] = {
    "ambiguity-v1": (
        "AMBIGUITY_SHA256SUMS",
        "ambiguity-dispositions-v1.json",
        "ambiguity-memberships-v1.json",
        "ambiguity-public-v1.json",
    ),
    "asteria-agentic-v1": (
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
    ),
    "authority-governance-v1": (
        "authority-governance-v1/SHA256SUMS",
        "authority-governance-v1/evaluator/authority-governance-evaluator.json",
        "authority-governance-v1/evaluator/manifest.json",
        "authority-governance-v1/public/authority-governance-input.json",
        "authority-governance-v1/public/manifest.json",
    ),
    "connection-v1": (
        "CONNECTION_PUBLIC_SHA256SUMS",
        "CONNECTION_SHA256SUMS",
        "connection-golden-v1.json",
        "connection-public-golden-v1.json",
    ),
    "core-world-v1": (
        "SHA256SUMS",
        "golden-v1.json",
    ),
    "extraction-v1": (
        "EXTRACTION_ANSWER_SHA256SUMS",
        "EXTRACTION_PUBLIC_SHA256SUMS",
        "EXTRACTION_SHA256SUMS",
        "extraction-answer-golden-v1.json",
        "extraction-golden-v1.json",
        "extraction-public-golden-v1.json",
    ),
    "risk-v1": (
        "RISK_ANSWER_SHA256SUMS",
        "RISK_PUBLIC_SHA256SUMS",
        "risk-answer-golden-v1.json",
        "risk-public-golden-v1.json",
    ),
}


def test_reproduction_recipes_cannot_read_packaged_benchmark_resources() -> None:
    recipe_module = (
        Path(__file__).parents[1] / "src/synthworld/benchmark_reproduction.py"
    )
    module = ast.parse(recipe_module.read_text(encoding="utf-8"))
    imported_modules = {
        alias.name
        for node in ast.walk(module)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        node.module
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    assert not {
        module_name
        for module_name in imported_modules
        if module_name in {"importlib.resources", "importlib_resources"}
        or module_name.startswith("synthworld.benchmarks")
    }

    forbidden_calls = {
        "open",
        "read",
        "read_text",
    }
    call_names = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(module)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert not forbidden_calls & call_names


def test_reproduction_recipes_do_not_read_frozen_artifacts_at_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    frozen_root = (Path(__file__).parents[1] / "src/synthworld/benchmarks").resolve()

    def guard_frozen_read(path: Path) -> None:
        try:
            path.resolve().relative_to(frozen_root)
        except ValueError:
            return
        raise AssertionError(f"recipe attempted to read frozen artifact: {path}")

    def guarded_read_bytes(path: Path) -> bytes:
        guard_frozen_read(path)
        return original_read_bytes(path)

    def guarded_read_text(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        guard_frozen_read(path)
        return original_read_text(path, encoding=encoding, errors=errors)

    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text
    outputs: dict[PublishedBenchmarkId, tuple[Path, ...]] = {}

    with monkeypatch.context() as guarded_paths:
        guarded_paths.setattr(Path, "read_bytes", guarded_read_bytes)
        guarded_paths.setattr(Path, "read_text", guarded_read_text)
        for benchmark_id in PUBLISHED_BENCHMARK_IDS:
            outputs[benchmark_id] = reproduce_benchmark(
                benchmark_id,
                tmp_path / "guarded" / benchmark_id,
            )

    frozen = files("synthworld.benchmarks")
    for benchmark_id, output_paths in outputs.items():
        for output_path in output_paths:
            relative_path = output_path.relative_to(
                tmp_path / "guarded" / benchmark_id
            ).as_posix()
            frozen_bytes = frozen.joinpath(*relative_path.split("/")).read_bytes()
            assert output_path.read_bytes() == frozen_bytes


@pytest.mark.parametrize("benchmark_id", PUBLISHED_BENCHMARK_IDS)
def test_reproduction_matches_every_frozen_byte_and_replays_deterministically(
    benchmark_id: PublishedBenchmarkId,
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first" / benchmark_id
    second_root = tmp_path / "second" / benchmark_id

    first = reproduce_benchmark(benchmark_id, first_root)
    second = reproduce_benchmark(benchmark_id, second_root)
    expected_paths = _EXPECTED_PATHS[benchmark_id]

    assert tuple(path.relative_to(first_root).as_posix() for path in first) == (
        expected_paths
    )
    assert tuple(path.relative_to(second_root).as_posix() for path in second) == (
        expected_paths
    )
    assert (
        tuple(
            path.relative_to(first_root).as_posix()
            for path in sorted(first_root.rglob("*"))
            if path.is_file()
        )
        == expected_paths
    )

    frozen = files("synthworld.benchmarks")
    for relative_path in expected_paths:
        first_bytes = (first_root / relative_path).read_bytes()
        second_bytes = (second_root / relative_path).read_bytes()
        frozen_bytes = frozen.joinpath(*relative_path.split("/")).read_bytes()

        assert first_bytes == frozen_bytes
        assert second_bytes == first_bytes
        assert first_bytes.decode("utf-8").endswith("\n")
        assert b"\r" not in first_bytes


def test_published_benchmark_ids_are_exactly_the_supported_closed_set() -> None:
    assert tuple(_EXPECTED_PATHS) == PUBLISHED_BENCHMARK_IDS
    assert sum(map(len, _EXPECTED_PATHS.values())) == 44


def test_unknown_benchmark_id_is_rejected_without_creating_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "unknown"

    with pytest.raises(ValueError, match="unknown published benchmark ID: unknown-v1"):
        reproduce_benchmark(cast(PublishedBenchmarkId, "unknown-v1"), output)

    assert not output.exists()


@pytest.mark.parametrize("existing_kind", ("directory", "file"))
def test_pre_existing_output_is_rejected_without_modification(
    existing_kind: str,
    tmp_path: Path,
) -> None:
    output = tmp_path / "existing"
    if existing_kind == "directory":
        output.mkdir()
        sentinel = output / "sentinel"
        sentinel.write_bytes(b"unchanged")
    else:
        output.write_bytes(b"unchanged")
        sentinel = output

    with pytest.raises(FileExistsError, match="benchmark output already exists"):
        reproduce_benchmark("core-world-v1", output)

    assert sentinel.read_bytes() == b"unchanged"
