from __future__ import annotations

from importlib.resources import files

from synthworld.extraction import ExtractionCorpus


def extraction_corpus_to_json(corpus: ExtractionCorpus) -> str:
    """Serialize an extraction corpus with stable model and field order."""

    return f"{corpus.model_dump_json(indent=2)}\n"


def load_golden_extraction_corpus() -> ExtractionCorpus:
    """Load the separately versioned frozen exact-span benchmark."""

    serialized = (
        files("synthworld.benchmarks")
        .joinpath("extraction-golden-v1.json")
        .read_text(encoding="utf-8")
    )
    return ExtractionCorpus.model_validate_json(serialized)


__all__ = ["extraction_corpus_to_json", "load_golden_extraction_corpus"]
