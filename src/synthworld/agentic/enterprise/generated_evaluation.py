"""Bundle-driven scoring for generated enterprise-agentic worlds."""

from __future__ import annotations

from synthworld.agentic.enterprise.generated_models import (
    EnterpriseAgenticGeneratedBenchmarkV1,
)
from synthworld.agentic.enterprise.generated_serialization import (
    generated_enterprise_agentic_artifact_checksums,
)
from synthworld.agentic.evaluation import evaluate_agentic_trace
from synthworld.agentic.models import AgenticBenchmark, AgenticTraceSubmission
from synthworld.evaluation import EvaluationReport


def evaluate_generated_enterprise_agentic_trace(
    submission: AgenticTraceSubmission,
    generated: EnterpriseAgenticGeneratedBenchmarkV1,
) -> EvaluationReport:
    """Score an explicit generated bundle without packaged Asteria fallback data."""

    report = evaluate_agentic_trace(
        submission,
        benchmark=AgenticBenchmark(
            public=generated.public,
            evaluator=generated.evaluator,
        ),
    )
    return EvaluationReport(
        scoring_version=report.scoring_version,
        task=report.task,
        seed=report.seed,
        persona_count=report.persona_count,
        benchmark_version=report.benchmark_version,
        checksum_scheme="sha256-generated-enterprise-agentic-v1",
        artifact_checksums=generated_enterprise_agentic_artifact_checksums(generated),
        metrics=report.metrics,
        slices=report.slices,
    )


__all__ = ["evaluate_generated_enterprise_agentic_trace"]
