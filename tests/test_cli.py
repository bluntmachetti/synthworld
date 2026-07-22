from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from uuid import UUID

import pytest

from synthworld.cli import main
from synthworld.connection import ConnectionBenchmark, PublicConnectionCorpus
from synthworld.connection_generator import (
    generate_adversarial_connection_benchmark,
    generate_relationship_connection_benchmark,
)
from synthworld.connection_metrics import ConnectionBenchmarkMetrics
from synthworld.evaluation import (
    EntityResolutionPrediction,
    ExtractionPagePrediction,
    ExtractionPredictionSet,
    PredictedRelationship,
    PredictedSpan,
    RelationshipPrediction,
    RiskCasePrediction,
    RiskPrediction,
)
from synthworld.exposures import CorpusMetrics, ExposureCorpus
from synthworld.extraction import (
    ExtractionAnswerKeyCorpus,
    ExtractionCorpus,
    PublicExtractionCorpus,
)
from synthworld.extraction_generator import generate_extraction_benchmark
from synthworld.models import SyntheticModel, SynthWorld, WorldMetrics
from synthworld.risk import PublicRiskCorpus, RiskAnswerKey, RiskBand
from synthworld.risk_generator import generate_risk_benchmark
from synthworld.risk_metrics import RiskBenchmarkMetrics


def test_generate_command_writes_a_populated_world(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "world.json"

    exit_code = main(
        [
            "generate",
            "--seed",
            "20260719",
            "--persona-count",
            "10",
            "--output",
            str(output),
        ]
    )

    world = SynthWorld.model_validate_json(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert len(world.personas) == 10
    assert len(world.relationships) == 9
    assert "SynthWorld ready" in capsys.readouterr().out


def test_metrics_command_prints_machine_readable_ground_truth(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["metrics", "--seed", "20260719", "--persona-count", "10"])

    metrics = WorldMetrics.model_validate(json.loads(capsys.readouterr().out))
    assert exit_code == 0
    assert metrics.safely_fake_record_rate == 1.0
    assert metrics.relationship_evidence_integrity == 1.0
    assert metrics.graph_connected is True


def test_generate_corpus_command_writes_exposure_ground_truth(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "corpus.json"

    exit_code = main(
        [
            "generate-corpus",
            "--seed",
            "20260719",
            "--persona-count",
            "10",
            "--output",
            str(output),
        ]
    )

    corpus = ExposureCorpus.model_validate_json(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert len(corpus.exposure_scripts) == 10
    assert "Exposure corpus ready" in capsys.readouterr().out


def test_corpus_metrics_command_prints_machine_readable_ground_truth(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["corpus-metrics", "--seed", "20260719", "--persona-count", "10"])

    metrics = CorpusMetrics.model_validate(json.loads(capsys.readouterr().out))
    assert exit_code == 0
    assert metrics.script_coverage == 1.0
    assert metrics.exposure_reference_integrity == 1.0
    assert metrics.safely_fake_record_rate == 1.0


def test_generate_extraction_command_writes_span_ground_truth(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "extraction.json"

    exit_code = main(
        [
            "generate-extraction",
            "--seed",
            "20260719",
            "--persona-count",
            "10",
            "--output",
            str(output),
        ]
    )

    corpus = ExtractionCorpus.model_validate_json(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert len(corpus.pages) == 62
    assert sum(len(item.answer_key.spans) for item in corpus.pages) == 150
    assert "Extraction corpus ready" in capsys.readouterr().out


def test_generate_public_extraction_command_writes_no_answer_key(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "public-extraction.json"

    exit_code = main(
        [
            "generate-public-extraction",
            "--seed",
            "20260719",
            "--persona-count",
            "10",
            "--output",
            str(output),
        ]
    )

    public = PublicExtractionCorpus.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    written = output.read_text(encoding="utf-8")
    assert exit_code == 0
    assert len(public.pages) == 62
    assert "Public extraction corpus ready" in capsys.readouterr().out
    assert "answer_key" not in written
    assert '"spans"' not in written
    assert "content_persona_id" not in written


def test_generate_extraction_answers_command_writes_separate_spans(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "extraction-answers.json"

    exit_code = main(
        [
            "generate-extraction-answers",
            "--seed",
            "20260719",
            "--persona-count",
            "10",
            "--output",
            str(output),
        ]
    )

    answers = ExtractionAnswerKeyCorpus.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert len(answers.answers) == 62
    assert sum(len(item.answer_key.spans) for item in answers.answers) == 150
    assert "Extraction answer key ready" in capsys.readouterr().out


def test_generate_connection_benchmark_command_writes_separate_truth(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "connection-benchmark.json"

    exit_code = main(
        [
            "generate-connection-benchmark",
            "--seed",
            "20260719",
            "--output",
            str(output),
        ]
    )

    benchmark = ConnectionBenchmark.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert len(benchmark.public.identity_records) == 18
    assert len(benchmark.answer_key.record_memberships) == 18
    assert "Connection benchmark ready" in capsys.readouterr().out


def test_generate_public_connections_command_writes_no_answer_key(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "public-connections.json"

    exit_code = main(
        [
            "generate-public-connections",
            "--seed",
            "20260719",
            "--persona-count",
            "10",
            "--output",
            str(output),
        ]
    )

    public = PublicConnectionCorpus.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert len(public.identity_records) == 10
    assert len(public.association_records) == 8
    assert "Public connections ready" in capsys.readouterr().out
    assert "answer_key" not in output.read_text(encoding="utf-8")


def test_connection_metrics_command_prints_benchmark_claims(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "connection-metrics",
            "--seed",
            "20260719",
            "--persona-count",
            "10",
        ]
    )

    metrics = ConnectionBenchmarkMetrics.model_validate_json(capsys.readouterr().out)
    assert exit_code == 0
    assert metrics.adversarial_record_count == 18
    assert metrics.public_identity_record_count == 10
    assert metrics.answer_key_separation_integrity == 1.0


def test_generate_risk_commands_write_physically_separate_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    public_output = tmp_path / "risk-public.json"
    answer_output = tmp_path / "risk-answer.json"

    public_exit = main(
        [
            "generate-risk-public",
            "--seed",
            "20260719",
            "--persona-count",
            "10",
            "--output",
            str(public_output),
        ]
    )
    public_message = capsys.readouterr().out
    answer_exit = main(
        [
            "generate-risk-answer",
            "--seed",
            "20260719",
            "--persona-count",
            "10",
            "--output",
            str(answer_output),
        ]
    )
    answer_message = capsys.readouterr().out

    public = PublicRiskCorpus.model_validate_json(
        public_output.read_text(encoding="utf-8")
    )
    answer = RiskAnswerKey.model_validate_json(
        answer_output.read_text(encoding="utf-8")
    )
    assert public_exit == answer_exit == 0
    assert len(public.cases) == len(answer.cases) == 10
    assert "Public risk corpus ready" in public_message
    assert "Risk answer key ready" in answer_message
    assert "answer_key" not in public_output.read_text(encoding="utf-8")
    assert "breaches" not in answer_output.read_text(encoding="utf-8")


def test_risk_metrics_command_prints_strict_benchmark_integrity(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["risk-metrics", "--seed", "20260719", "--persona-count", "10"])

    metrics = RiskBenchmarkMetrics.model_validate_json(capsys.readouterr().out)
    assert exit_code == 0
    assert metrics.case_count == 10
    assert metrics.factor_count == 18
    assert metrics.frozen_artifact_checked is True
    assert metrics.frozen_artifact_integrity == 1.0


def test_module_entrypoint_runs_the_metrics_command(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["synthworld", "metrics"])

    with pytest.raises(SystemExit, match="0"):
        runpy.run_module("synthworld", run_name="__main__")

    metrics = WorldMetrics.model_validate_json(capsys.readouterr().out)
    assert metrics.persona_count == 10


def _extraction_predictions() -> ExtractionPredictionSet:
    benchmark = generate_extraction_benchmark(seed=20260719, persona_count=10)
    return ExtractionPredictionSet(
        predictions=tuple(
            ExtractionPagePrediction(
                source_type=answer.source_type,
                source_record_id=answer.source_record_id,
                spans=tuple(
                    PredictedSpan(
                        data_class=span.data_class,
                        start=span.start,
                        end=span.end,
                    )
                    for span in answer.answer_key.spans
                ),
            )
            for answer in benchmark.answers.answers
        )
    )


def _write_prediction(tmp_path: Path, prediction: SyntheticModel) -> str:
    path = tmp_path / "predictions.json"
    path.write_text(prediction.model_dump_json(), encoding="utf-8")
    return str(path)


def test_evaluate_extraction_command_scores_predictions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    predictions = _write_prediction(tmp_path, _extraction_predictions())

    exit_code = main(
        ["evaluate", "extraction", "--predictions", predictions, "--seed", "20260719"]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["task"] == "extraction"
    assert report["seed"] == 20260719


def test_evaluate_command_summary_prints_a_metric_table(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    predictions = _write_prediction(tmp_path, _extraction_predictions())

    exit_code = main(
        ["evaluate", "extraction", "--predictions", predictions, "--summary"]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Metric" in out
    assert "exact_precision" in out


def test_evaluate_entity_resolution_command_scores_predictions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    benchmark = generate_adversarial_connection_benchmark(seed=20260719)
    by_entity: dict[str, list[UUID]] = {}
    for item in benchmark.answer_key.record_memberships:
        by_entity.setdefault(item.entity_id, []).append(item.record_id)
    prediction = EntityResolutionPrediction(
        clusters=tuple(tuple(records) for records in by_entity.values())
    )

    exit_code = main(
        [
            "evaluate",
            "entity-resolution",
            "--predictions",
            _write_prediction(tmp_path, prediction),
            "--seed",
            "20260719",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["task"] == "entity_resolution"


def test_evaluate_summary_prints_null_for_undefined_metrics(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    benchmark = generate_adversarial_connection_benchmark(seed=20260719)
    singletons = EntityResolutionPrediction(
        clusters=tuple(
            (item.record_id,) for item in benchmark.answer_key.record_memberships
        )
    )

    exit_code = main(
        [
            "evaluate",
            "entity-resolution",
            "--predictions",
            _write_prediction(tmp_path, singletons),
            "--summary",
        ]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "pairwise_precision" in out
    assert "None" in out


def test_evaluate_relationship_command_scores_predictions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    benchmark = generate_relationship_connection_benchmark(
        seed=20260719, persona_count=10
    )
    prediction = RelationshipPrediction(
        edges=tuple(
            PredictedRelationship(
                source_record_id=item.source_record_id,
                target_record_id=item.target_record_id,
                kind=item.kind,
                evidence_association_ids=item.reciprocal_association_ids,
            )
            for item in benchmark.answer_key.relationships
        )
    )

    exit_code = main(
        [
            "evaluate",
            "relationship",
            "--predictions",
            _write_prediction(tmp_path, prediction),
            "--seed",
            "20260719",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["task"] == "relationship_inference"


def test_evaluate_risk_command_scores_predictions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    benchmark = generate_risk_benchmark(seed=20260719, persona_count=10)
    prediction = RiskPrediction(
        cases=tuple(
            RiskCasePrediction(
                case_id=case.case_id,
                band=case.band,
                score=case.score,
                band_probabilities=tuple(
                    (band, 1.0 if band is case.band else 0.0) for band in RiskBand
                ),
            )
            for case in benchmark.answer_key.cases
        )
    )

    exit_code = main(
        [
            "evaluate",
            "risk",
            "--predictions",
            _write_prediction(tmp_path, prediction),
            "--seed",
            "20260719",
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report["task"] == "risk_calibration"


def test_evaluate_reports_input_error_as_exit_code_one(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    incomplete = RiskPrediction(cases=())

    exit_code = main(
        [
            "evaluate",
            "risk",
            "--predictions",
            _write_prediction(tmp_path, incomplete),
            "--seed",
            "20260719",
        ]
    )

    assert exit_code == 1
    assert "must cover exactly the public cases" in capsys.readouterr().err


def test_evaluate_reports_a_missing_file_as_exit_code_one(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "evaluate",
            "extraction",
            "--predictions",
            str(tmp_path / "does-not-exist.json"),
        ]
    )

    assert exit_code == 1
    assert capsys.readouterr().err.strip()


def test_evaluate_reports_malformed_predictions_as_exit_code_one(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    predictions = tmp_path / "malformed.json"
    predictions.write_text("{not valid json", encoding="utf-8")

    exit_code = main(["evaluate", "extraction", "--predictions", str(predictions)])

    assert exit_code == 1
    assert capsys.readouterr().err.strip()
