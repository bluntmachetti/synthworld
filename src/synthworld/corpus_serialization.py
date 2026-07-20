from __future__ import annotations

from importlib.resources import files

from synthworld.exposures import ExposureCorpus


def corpus_to_json(corpus: ExposureCorpus) -> str:
    """Serialize an exposure corpus using stable model and field order."""

    return f"{corpus.model_dump_json(indent=2)}\n"


def load_golden_corpus() -> ExposureCorpus:
    """Load the committed golden-v1 benchmark from package data."""

    serialized = (
        files("synthworld.benchmarks")
        .joinpath("golden-v1.json")
        .read_text(encoding="utf-8")
    )
    return ExposureCorpus.model_validate_json(serialized)
