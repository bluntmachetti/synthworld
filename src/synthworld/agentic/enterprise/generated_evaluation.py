"""Bundle-driven scoring for generated enterprise-agentic worlds."""

from __future__ import annotations

from synthworld.agentic.enterprise.generated_models import (
    EnterpriseAgenticGeneratedBenchmarkV1,
)
from synthworld.agentic.enterprise.generated_scale_models import (
    EnterpriseAgenticGeneratedBenchmarkV2,
)
from synthworld.agentic.enterprise.generated_scale_serialization import (
    generated_enterprise_agentic_scale_artifact_checksums,
)
from synthworld.agentic.enterprise.generated_serialization import (
    generated_enterprise_agentic_artifact_checksums,
)
from synthworld.agentic.evaluation import evaluate_agentic_trace
from synthworld.agentic.models import AgenticBenchmark, AgenticTraceSubmission
from synthworld.evaluation import EvaluationReport


def evaluate_generated_enterprise_agentic_trace(
    submission: AgenticTraceSubmission,
    generated: EnterpriseAgenticGeneratedBenchmarkV1
    | EnterpriseAgenticGeneratedBenchmarkV2,
) -> EvaluationReport:
    """Score an explicit generated bundle without packaged Asteria fallback data."""

    report = evaluate_agentic_trace(
        submission,
        benchmark=AgenticBenchmark(
            public=generated.public,
            evaluator=generated.evaluator,
        ),
    )
    if isinstance(generated, EnterpriseAgenticGeneratedBenchmarkV1):
        checksum_scheme = "sha256-generated-enterprise-agentic-v1"
        checksums = generated_enterprise_agentic_artifact_checksums(generated)
    else:
        checksum_scheme = "sha256-generated-enterprise-agentic-v2"
        checksums = generated_enterprise_agentic_scale_artifact_checksums(generated)
    return EvaluationReport(
        scoring_version=report.scoring_version,
        task=report.task,
        seed=report.seed,
        persona_count=report.persona_count,
        benchmark_version=report.benchmark_version,
        checksum_scheme=checksum_scheme,
        artifact_checksums=checksums,
        metrics=report.metrics,
        slices=report.slices,
    )


__all__ = ["evaluate_generated_enterprise_agentic_trace"]
