from __future__ import annotations

import hashlib
from importlib.resources import files
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld import (
    DataClass,
    ExtractionBenchmarkIntegrityError,
    extraction_serialization,
    generate_extraction_benchmark,
    load_golden_extraction_answers,
    load_golden_extraction_benchmark,
    load_golden_public_extraction_corpus,
)
from synthworld.extraction import (
    ExtractionAnswerKey,
    ExtractionAnswerKeyCorpus,
    ExtractionBenchmark,
    ExtractionPage,
    ExtractionPageAnswer,
    ExtractionPagePurpose,
    ExtractionSourceType,
    ExtractionSpan,
    PublicExtractionCorpus,
)
from synthworld.extraction_generator import generate_extraction_corpus
from synthworld.extraction_serialization import (
    extraction_answers_to_json,
    public_extraction_corpus_to_json,
)

_SEED = 20_260_719


def _negative_page(content: str = "safe control content\n") -> ExtractionPage:
    return ExtractionPage(
        source_type=ExtractionSourceType.SEARCH,
        source_record_id="negative-control-0001",
        purpose=ExtractionPagePurpose.NEGATIVE_CONTROL,
        title="Synthetic no-result page",
        content=content,
    )


def _answer(
    *,
    source_record_id: str = "negative-control-0001",
    spans: tuple[ExtractionSpan, ...] = (),
) -> ExtractionPageAnswer:
    return ExtractionPageAnswer(
        source_type=ExtractionSourceType.SEARCH,
        source_record_id=source_record_id,
        answer_key=ExtractionAnswerKey(content_persona_id="persona-0001", spans=spans),
    )


def _public(page: ExtractionPage) -> PublicExtractionCorpus:
    return PublicExtractionCorpus(seed=_SEED, pages=(page,))


def _answers(
    answer: ExtractionPageAnswer, *, seed: int = _SEED
) -> ExtractionAnswerKeyCorpus:
    return ExtractionAnswerKeyCorpus(seed=seed, answers=(answer,))


def test_benchmark_generation_separates_public_pages_from_answers() -> None:
    benchmark = generate_extraction_benchmark(seed=_SEED, persona_count=10)
    annotated = generate_extraction_corpus(seed=_SEED, persona_count=10)

    assert benchmark.seed == _SEED
    assert len(benchmark.public.pages) == 62
    assert len(benchmark.answers.answers) == 62
    assert benchmark.public.pages == tuple(item.page for item in annotated.pages)
    public_json = public_extraction_corpus_to_json(benchmark.public)
    assert "answer_key" not in public_json
    assert "content_persona_id" not in public_json
    assert '"spans"' not in public_json


def test_public_corpus_rejects_duplicate_keys_and_missing_control() -> None:
    page = _negative_page()
    with pytest.raises(ValidationError, match="page keys must be unique"):
        PublicExtractionCorpus(seed=_SEED, pages=(page, page))
    exposure_page = ExtractionPage(
        source_type=ExtractionSourceType.SEARCH,
        source_record_id="search-0001-01",
        purpose=ExtractionPagePurpose.EXPOSURE,
        title="Example",
        content="safe content\n",
    )
    with pytest.raises(ValidationError, match="exactly one negative control"):
        PublicExtractionCorpus(seed=_SEED, pages=(exposure_page,))


def test_page_answer_rejects_unsafe_ids_and_unordered_spans() -> None:
    with pytest.raises(ValidationError, match="page fields must be nonblank"):
        _answer(source_record_id=" ")
    with pytest.raises(ValidationError, match="corpus routing key"):
        _answer(source_record_id="persona-0001")
    early = ExtractionSpan(data_class=DataClass.EMAIL, start=0, end=3, text="one")
    late = ExtractionSpan(data_class=DataClass.PHONE, start=8, end=13, text="three")
    with pytest.raises(ValidationError, match="must be sorted"):
        _answer(spans=(late, early))


def test_answer_corpus_rejects_duplicate_keys() -> None:
    answer = _answer()
    with pytest.raises(ValidationError, match="page keys must be unique"):
        ExtractionAnswerKeyCorpus(seed=_SEED, answers=(answer, answer))


def test_benchmark_rejects_seed_page_and_span_drift() -> None:
    page = _negative_page()
    answer = _answer()

    with pytest.raises(ValidationError, match="seeds must match"):
        ExtractionBenchmark(
            seed=_SEED,
            public=PublicExtractionCorpus(seed=_SEED + 1, pages=(page,)),
            answers=_answers(answer),
        )
    with pytest.raises(ValidationError, match="seeds must match"):
        ExtractionBenchmark(
            seed=_SEED,
            public=_public(page),
            answers=_answers(answer, seed=_SEED + 1),
        )
    with pytest.raises(ValidationError, match="public and answer pages must match"):
        ExtractionBenchmark(
            seed=_SEED,
            public=_public(page),
            answers=_answers(_answer(source_record_id="other-record")),
        )
    mismatched_span = ExtractionSpan(
        data_class=DataClass.EMAIL, start=0, end=3, text="zzz"
    )
    with pytest.raises(ValidationError, match="does not match page content"):
        ExtractionBenchmark(
            seed=_SEED,
            public=_public(page),
            answers=_answers(_answer(spans=(mismatched_span,))),
        )


def test_frozen_public_and_answer_artifacts_match_generation() -> None:
    benchmark = generate_extraction_benchmark(seed=_SEED, persona_count=10)

    assert public_extraction_corpus_to_json(
        load_golden_public_extraction_corpus()
    ) == public_extraction_corpus_to_json(benchmark.public)
    assert extraction_answers_to_json(
        load_golden_extraction_answers()
    ) == extraction_answers_to_json(benchmark.answers)
    assert load_golden_extraction_benchmark() == benchmark


@pytest.mark.parametrize("manifest", ["empty", "wrong_name", "wrong_hash"])
def test_frozen_loader_rejects_manifest_and_checksum_tampering(
    manifest: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = public_extraction_corpus_to_json(
        generate_extraction_benchmark(seed=_SEED, persona_count=10).public
    ).encode()
    (tmp_path / "extraction-public-golden-v1.json").write_bytes(artifact)
    expected_hash = hashlib.sha256(artifact).hexdigest()
    manifest_content = {
        "empty": "",
        "wrong_name": f"{expected_hash}  wrong.json\n",
        "wrong_hash": f"{'0' * 64}  extraction-public-golden-v1.json\n",
    }[manifest]
    (tmp_path / "EXTRACTION_PUBLIC_SHA256SUMS").write_text(
        manifest_content,
        encoding="utf-8",
    )
    monkeypatch.setattr(extraction_serialization, "files", lambda package: tmp_path)

    with pytest.raises(ExtractionBenchmarkIntegrityError):
        load_golden_public_extraction_corpus()


def test_frozen_loader_rejects_schema_drift_after_a_valid_checksum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = b"{}\n"
    (tmp_path / "extraction-answer-golden-v1.json").write_bytes(artifact)
    (tmp_path / "EXTRACTION_ANSWER_SHA256SUMS").write_text(
        f"{hashlib.sha256(artifact).hexdigest()}  extraction-answer-golden-v1.json\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(extraction_serialization, "files", lambda package: tmp_path)

    with pytest.raises(ValidationError):
        load_golden_extraction_answers()


def test_combined_loader_rejects_seed_and_cross_file_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark = generate_extraction_benchmark(seed=_SEED, persona_count=10)
    changed_seed = benchmark.answers.model_copy(update={"seed": _SEED + 1})
    monkeypatch.setattr(
        extraction_serialization,
        "load_golden_public_extraction_corpus",
        lambda: benchmark.public,
    )
    monkeypatch.setattr(
        extraction_serialization,
        "load_golden_extraction_answers",
        lambda: changed_seed,
    )
    with pytest.raises(ExtractionBenchmarkIntegrityError, match="seeds differ"):
        load_golden_extraction_benchmark()

    dropped_answer = benchmark.answers.model_copy(
        update={"answers": benchmark.answers.answers[:-1]}
    )
    monkeypatch.setattr(
        extraction_serialization,
        "load_golden_extraction_answers",
        lambda: dropped_answer,
    )
    with pytest.raises(ExtractionBenchmarkIntegrityError, match="cross-file drift"):
        load_golden_extraction_benchmark()


def test_frozen_extraction_manifests_match_sha256() -> None:
    benchmark_directory = files("synthworld.benchmarks")
    for filename, manifest_name in (
        ("extraction-public-golden-v1.json", "EXTRACTION_PUBLIC_SHA256SUMS"),
        ("extraction-answer-golden-v1.json", "EXTRACTION_ANSWER_SHA256SUMS"),
    ):
        artifact = benchmark_directory.joinpath(filename).read_bytes()
        manifest = benchmark_directory.joinpath(manifest_name).read_text(
            encoding="utf-8"
        )
        expected_hash, name = manifest.strip().split(maxsplit=1)
        assert name == filename
        assert hashlib.sha256(artifact).hexdigest() == expected_hash
