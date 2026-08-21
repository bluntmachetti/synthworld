"""Measure generated enterprise-agentic tiers outside deterministic artifacts."""

from __future__ import annotations

import argparse
import hashlib
import platform
import statistics
import time
import tracemalloc
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from synthworld.agentic import AgenticBenchmark, reference_agentic_trace
from synthworld.agentic.enterprise import (
    EnterpriseAgenticScaleTierV2,
    default_enterprise_agentic_generation_config_v2,
    evaluate_generated_enterprise_agentic_trace,
    generate_enterprise_agentic_scale_world,
    generated_enterprise_agentic_scale_evaluator_artifacts,
    generated_enterprise_agentic_scale_public_artifacts,
)
from synthworld.agentic.enterprise.generated_scale_models import (
    EnterpriseAgenticGeneratedBenchmarkV2,
    EnterpriseAgenticPerformanceReceiptV1,
    EnterpriseAgenticTierMeasurementV1,
)
from synthworld.agentic.enterprise.generated_serialization import (
    generated_enterprise_agentic_artifact_set_sha256,
)
from synthworld.agentic.replay import materialize_agentic_world
from synthworld.enterprise.canonical import canonical_json_bytes


def measure_enterprise_agentic_scale(
    *,
    source_revision: str,
    dependency_lock: Path,
    iterations: int,
) -> EnterpriseAgenticPerformanceReceiptV1:
    """Measure host-observed runtime and peak memory for both V2 tiers."""

    if not source_revision.strip():
        raise ValueError("source revision must be nonblank")
    if iterations < 1:
        raise ValueError("measurement iterations must be positive")
    lock_payload = dependency_lock.read_bytes()
    measurements: list[EnterpriseAgenticTierMeasurementV1] = []
    for tier in EnterpriseAgenticScaleTierV2:
        generation_seconds: list[float] = []
        serialization_seconds: list[float] = []
        replay_seconds: list[float] = []
        scoring_seconds: list[float] = []
        peak_memory = 0
        last_generated = None
        tracemalloc.start()
        try:
            for iteration in range(iterations):
                config = default_enterprise_agentic_generation_config_v2(
                    tier,
                    seed=20_260_821 + iteration,
                )
                started = time.perf_counter()
                generated = generate_enterprise_agentic_scale_world(config)
                generation_seconds.append(time.perf_counter() - started)

                started = time.perf_counter()
                generated_enterprise_agentic_scale_public_artifacts(generated)
                generated_enterprise_agentic_scale_evaluator_artifacts(generated)
                serialization_seconds.append(time.perf_counter() - started)

                started = time.perf_counter()
                materialize_agentic_world(
                    generated.public.snapshot,
                    generated.public.events,
                )
                replay_seconds.append(time.perf_counter() - started)

                benchmark = AgenticBenchmark(
                    public=generated.public,
                    evaluator=generated.evaluator,
                )
                started = time.perf_counter()
                evaluate_generated_enterprise_agentic_trace(
                    reference_agentic_trace(benchmark),
                    generated,
                )
                scoring_seconds.append(time.perf_counter() - started)
                last_generated = generated
            _, peak_memory = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        measured = cast(EnterpriseAgenticGeneratedBenchmarkV2, last_generated)
        public_artifacts = generated_enterprise_agentic_scale_public_artifacts(measured)
        measurements.append(
            EnterpriseAgenticTierMeasurementV1(
                tier=tier,
                configuration_sha256=measured.identity.configuration_sha256,
                public_artifact_set_sha256=(
                    generated_enterprise_agentic_artifact_set_sha256(public_artifacts)
                ),
                iterations=iterations,
                generation_seconds_median=statistics.median(generation_seconds),
                serialization_seconds_median=statistics.median(serialization_seconds),
                replay_seconds_median=statistics.median(replay_seconds),
                scoring_seconds_median=statistics.median(scoring_seconds),
                peak_memory_bytes=peak_memory,
            )
        )
    return EnterpriseAgenticPerformanceReceiptV1(
        source_revision=source_revision,
        dependency_lock_sha256=hashlib.sha256(lock_payload).hexdigest(),
        python_version=platform.python_version(),
        platform=platform.platform(),
        measurements=tuple(measurements),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--dependency-lock", type=Path, default=Path("uv.lock"))
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output already exists")
    receipt = measure_enterprise_agentic_scale(
        source_revision=args.source_revision,
        dependency_lock=args.dependency_lock,
        iterations=args.iterations,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
