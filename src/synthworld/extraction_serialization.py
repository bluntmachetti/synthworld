from __future__ import annotations

import hashlib
from importlib.resources import files

from synthworld.extraction import (
    ExtractionAnswerKeyCorpus,
    ExtractionBenchmark,
    ExtractionCorpus,
    PublicExtractionCorpus,
)

_PUBLIC_FILENAME = "extraction-public-golden-v1.json"
_PUBLIC_MANIFEST = "EXTRACTION_PUBLIC_SHA256SUMS"
_ANSWER_FILENAME = "extraction-answer-golden-v1.json"
_ANSWER_MANIFEST = "EXTRACTION_ANSWER_SHA256SUMS"


class ExtractionBenchmarkIntegrityError(ValueError):
    """Raised when a frozen extraction artifact fails its integrity gate."""


def extraction_corpus_to_json(corpus: ExtractionCorpus) -> str:
    """Serialize the annotated evaluator bundle with stable ordering."""

    return f"{corpus.model_dump_json(indent=2)}\n"


def public_extraction_corpus_to_json(corpus: PublicExtractionCorpus) -> str:
    """Serialize only the product-safe public extraction pages."""

    canonical = PublicExtractionCorpus.model_validate(corpus.model_dump(mode="python"))
    return f"{canonical.model_dump_json(indent=2)}\n"


def extraction_answers_to_json(answers: ExtractionAnswerKeyCorpus) -> str:
    """Serialize only the evaluator-only extraction answer key."""

    canonical = ExtractionAnswerKeyCorpus.model_validate(
        answers.model_dump(mode="python")
    )
    return f"{canonical.model_dump_json(indent=2)}\n"


def load_golden_extraction_corpus() -> ExtractionCorpus:
    """Load the separately versioned frozen annotated evaluator bundle."""

    serialized = (
        files("synthworld.benchmarks")
        .joinpath("extraction-golden-v1.json")
        .read_text(encoding="utf-8")
    )
    return ExtractionCorpus.model_validate_json(serialized)


def load_golden_public_extraction_corpus() -> PublicExtractionCorpus:
    """Load and verify the physically separate frozen public extraction corpus."""

    return PublicExtractionCorpus.model_validate_json(
        _verified_artifact(_PUBLIC_FILENAME, _PUBLIC_MANIFEST)
    )


def load_golden_extraction_answers() -> ExtractionAnswerKeyCorpus:
    """Load and verify the physically separate frozen extraction answer key."""

    return ExtractionAnswerKeyCorpus.model_validate_json(
        _verified_artifact(_ANSWER_FILENAME, _ANSWER_MANIFEST)
    )


def load_golden_extraction_benchmark() -> ExtractionBenchmark:
    """Load both verified artifacts and reject any cross-file truth drift."""

    public = load_golden_public_extraction_corpus()
    answers = load_golden_extraction_answers()
    if public.seed != answers.seed:
        raise ExtractionBenchmarkIntegrityError(
            "frozen extraction artifact seeds differ"
        )
    try:
        return ExtractionBenchmark(
            seed=public.seed,
            public=public,
            answers=answers,
        )
    except ValueError as error:
        raise ExtractionBenchmarkIntegrityError(
            "frozen extraction artifacts contain cross-file drift"
        ) from error


def _verified_artifact(filename: str, manifest_name: str) -> bytes:
    benchmark_directory = files("synthworld.benchmarks")
    artifact = benchmark_directory.joinpath(filename).read_bytes()
    manifest = benchmark_directory.joinpath(manifest_name).read_text(encoding="utf-8")
    fields = manifest.strip().split()
    if len(fields) != 2 or fields[1] != filename:
        raise ExtractionBenchmarkIntegrityError("frozen extraction manifest is invalid")
    if hashlib.sha256(artifact).hexdigest() != fields[0]:
        raise ExtractionBenchmarkIntegrityError(
            "frozen extraction artifact checksum differs"
        )
    return artifact


__all__ = [
    "ExtractionBenchmarkIntegrityError",
    "extraction_answers_to_json",
    "extraction_corpus_to_json",
    "load_golden_extraction_answers",
    "load_golden_extraction_benchmark",
    "load_golden_extraction_corpus",
    "load_golden_public_extraction_corpus",
    "public_extraction_corpus_to_json",
]
