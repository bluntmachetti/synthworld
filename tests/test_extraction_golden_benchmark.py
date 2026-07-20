from __future__ import annotations

import hashlib
from importlib.resources import files

from synthworld import generate_extraction_corpus
from synthworld.extraction_serialization import (
    extraction_corpus_to_json,
    load_golden_extraction_corpus,
)


def test_frozen_extraction_corpus_matches_generation_byte_for_byte() -> None:
    generated = extraction_corpus_to_json(
        generate_extraction_corpus(seed=20_260_719, persona_count=10)
    )
    benchmark = files("synthworld.benchmarks").joinpath("extraction-golden-v1.json")

    assert benchmark.read_text(encoding="utf-8") == generated
    assert extraction_corpus_to_json(load_golden_extraction_corpus()) == generated


def test_extraction_manifest_matches_benchmark_sha256() -> None:
    benchmark_directory = files("synthworld.benchmarks")
    corpus_bytes = benchmark_directory.joinpath(
        "extraction-golden-v1.json"
    ).read_bytes()
    manifest = benchmark_directory.joinpath("EXTRACTION_SHA256SUMS").read_text(
        encoding="utf-8"
    )
    expected_hash, filename = manifest.strip().split(maxsplit=1)

    assert filename == "extraction-golden-v1.json"
    assert hashlib.sha256(corpus_bytes).hexdigest() == expected_hash
