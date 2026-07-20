from __future__ import annotations

import hashlib
from importlib.resources import files

from synthworld.risk import PublicRiskCorpus, RiskAnswerKey, RiskBenchmark

_PUBLIC_FILENAME = "risk-public-golden-v1.json"
_PUBLIC_MANIFEST = "RISK_PUBLIC_SHA256SUMS"
_ANSWER_FILENAME = "risk-answer-golden-v1.json"
_ANSWER_MANIFEST = "RISK_ANSWER_SHA256SUMS"


class RiskBenchmarkIntegrityError(ValueError):
    """Raised when a frozen risk artifact fails its independent integrity gate."""


def public_risk_corpus_to_json(corpus: PublicRiskCorpus) -> str:
    """Serialize only canonical product-safe risk input."""

    canonical = PublicRiskCorpus.model_validate(corpus.model_dump(mode="python"))
    return f"{canonical.model_dump_json(indent=2)}\n"


def risk_answer_key_to_json(answer_key: RiskAnswerKey) -> str:
    """Serialize only canonical evaluator truth."""

    canonical = RiskAnswerKey.model_validate(answer_key.model_dump(mode="python"))
    return f"{canonical.model_dump_json(indent=2)}\n"


def load_golden_public_risk_corpus() -> PublicRiskCorpus:
    """Load and verify the physically separate frozen public risk corpus."""

    return PublicRiskCorpus.model_validate_json(
        _verified_artifact(_PUBLIC_FILENAME, _PUBLIC_MANIFEST)
    )


def load_golden_risk_answer_key() -> RiskAnswerKey:
    """Load and verify the physically separate frozen risk answer key."""

    return RiskAnswerKey.model_validate_json(
        _verified_artifact(_ANSWER_FILENAME, _ANSWER_MANIFEST)
    )


def load_golden_risk_benchmark() -> RiskBenchmark:
    """Load both verified artifacts and reject any cross-file truth drift."""

    public = load_golden_public_risk_corpus()
    answer_key = load_golden_risk_answer_key()
    if public.seed != answer_key.seed:
        raise RiskBenchmarkIntegrityError("frozen risk artifact seeds differ")
    try:
        return RiskBenchmark(
            seed=public.seed,
            public=public,
            answer_key=answer_key,
        )
    except ValueError as error:
        raise RiskBenchmarkIntegrityError(
            "frozen risk artifacts contain cross-file drift"
        ) from error


def _verified_artifact(filename: str, manifest_name: str) -> bytes:
    benchmark_directory = files("synthworld.benchmarks")
    artifact = benchmark_directory.joinpath(filename).read_bytes()
    manifest = benchmark_directory.joinpath(manifest_name).read_text(encoding="utf-8")
    fields = manifest.strip().split()
    if len(fields) != 2 or fields[1] != filename:
        raise RiskBenchmarkIntegrityError("frozen risk manifest is invalid")
    if hashlib.sha256(artifact).hexdigest() != fields[0]:
        raise RiskBenchmarkIntegrityError("frozen risk artifact checksum differs")
    return artifact


__all__ = [
    "RiskBenchmarkIntegrityError",
    "load_golden_public_risk_corpus",
    "load_golden_risk_answer_key",
    "load_golden_risk_benchmark",
    "public_risk_corpus_to_json",
    "risk_answer_key_to_json",
]
