from __future__ import annotations

import hashlib
from importlib.resources import files

from synthworld import (
    corpus_to_json,
    generate_exposure_corpus,
    load_golden_corpus,
)


def test_frozen_golden_corpus_matches_fresh_generation_byte_for_byte() -> None:
    generated = corpus_to_json(
        generate_exposure_corpus(seed=20_260_719, persona_count=10)
    )
    benchmark = files("synthworld.benchmarks").joinpath("golden-v1.json")

    assert benchmark.read_text(encoding="utf-8") == generated
    assert corpus_to_json(load_golden_corpus()) == generated


def test_golden_manifest_matches_corpus_sha256() -> None:
    benchmark_directory = files("synthworld.benchmarks")
    corpus_bytes = benchmark_directory.joinpath("golden-v1.json").read_bytes()
    manifest = benchmark_directory.joinpath("SHA256SUMS").read_text(encoding="utf-8")
    expected_hash, filename = manifest.strip().split(maxsplit=1)

    assert filename == "golden-v1.json"
    assert hashlib.sha256(corpus_bytes).hexdigest() == expected_hash
