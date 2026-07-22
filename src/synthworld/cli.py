from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from synthworld.connection_generator import (
    generate_adversarial_connection_benchmark,
    generate_relationship_connection_benchmark,
)
from synthworld.connection_metrics import evaluate_connection_benchmarks
from synthworld.connection_serialization import (
    connection_benchmark_to_json,
    public_connection_corpus_to_json,
)
from synthworld.corpus_metrics import evaluate_corpus
from synthworld.corpus_serialization import corpus_to_json
from synthworld.evaluation import (
    EntityResolutionPrediction,
    EvaluationInputError,
    EvaluationReport,
    ExtractionPredictionSet,
    RelationshipPrediction,
    RiskPrediction,
    evaluate_entity_resolution,
    evaluate_extraction,
    evaluate_relationship_inference,
    evaluate_risk_calibration,
)
from synthworld.exposure_generator import generate_exposure_corpus
from synthworld.extraction_generator import (
    generate_extraction_benchmark,
    generate_extraction_corpus,
)
from synthworld.extraction_serialization import (
    extraction_answers_to_json,
    extraction_corpus_to_json,
    public_extraction_corpus_to_json,
)
from synthworld.generator import generate_world
from synthworld.metrics import evaluate_world
from synthworld.risk_generator import generate_risk_benchmark
from synthworld.risk_metrics import evaluate_risk_benchmark
from synthworld.risk_serialization import (
    public_risk_corpus_to_json,
    risk_answer_key_to_json,
)
from synthworld.serialization import world_to_json


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    if args.command == "evaluate":
        text = args.predictions.read_text(encoding="utf-8")
        try:
            if args.task == "extraction":
                report = evaluate_extraction(
                    ExtractionPredictionSet.model_validate_json(text),
                    seed=args.seed,
                    persona_count=args.persona_count,
                )
            elif args.task == "entity-resolution":
                report = evaluate_entity_resolution(
                    EntityResolutionPrediction.model_validate_json(text),
                    seed=args.seed,
                )
            elif args.task == "relationship":
                report = evaluate_relationship_inference(
                    RelationshipPrediction.model_validate_json(text),
                    seed=args.seed,
                    persona_count=args.persona_count,
                )
            else:
                report = evaluate_risk_calibration(
                    RiskPrediction.model_validate_json(text),
                    seed=args.seed,
                    persona_count=args.persona_count,
                )
        except EvaluationInputError as error:
            print(str(error), file=sys.stderr)
            return 1

        if args.summary:
            print(_metric_table(report))
        else:
            print(report.model_dump_json(indent=2))
        return 0

    if args.command == "generate-connection-benchmark":
        benchmark = generate_adversarial_connection_benchmark(seed=args.seed)
        output = args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(connection_benchmark_to_json(benchmark), encoding="utf-8")
        print(
            "Connection benchmark ready: "
            f"{len(benchmark.public.identity_records)} raw records -> {output}"
        )
        return 0

    if args.command == "generate-public-connections":
        relationship_benchmark = generate_relationship_connection_benchmark(
            seed=args.seed,
            persona_count=args.persona_count,
        )
        output = args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            public_connection_corpus_to_json(relationship_benchmark.public),
            encoding="utf-8",
        )
        print(
            "Public connections ready: "
            f"{len(relationship_benchmark.public.identity_records)} identity records, "
            f"{len(relationship_benchmark.public.association_records)} associations "
            f"-> {output}"
        )
        return 0

    if args.command == "connection-metrics":
        adversarial = generate_adversarial_connection_benchmark(seed=args.seed)
        relationships = generate_relationship_connection_benchmark(
            seed=args.seed,
            persona_count=args.persona_count,
        )
        print(
            evaluate_connection_benchmarks(
                adversarial,
                relationships,
            ).model_dump_json(indent=2)
        )
        return 0

    if args.command in {"generate-risk-public", "generate-risk-answer"}:
        risk_benchmark = generate_risk_benchmark(
            seed=args.seed,
            persona_count=args.persona_count,
        )
        output = args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        if args.command == "generate-risk-public":
            output.write_text(
                public_risk_corpus_to_json(risk_benchmark.public),
                encoding="utf-8",
            )
            print(
                f"Public risk corpus ready: {len(risk_benchmark.public.cases)} cases "
                f"-> {output}"
            )
        else:
            output.write_text(
                risk_answer_key_to_json(risk_benchmark.answer_key),
                encoding="utf-8",
            )
            print(
                f"Risk answer key ready: {len(risk_benchmark.answer_key.cases)} cases "
                f"-> {output}"
            )
        return 0

    if args.command == "risk-metrics":
        risk_benchmark = generate_risk_benchmark(
            seed=args.seed,
            persona_count=args.persona_count,
        )
        print(evaluate_risk_benchmark(risk_benchmark).model_dump_json(indent=2))
        return 0

    if args.command in {"generate-public-extraction", "generate-extraction-answers"}:
        extraction_benchmark = generate_extraction_benchmark(
            seed=args.seed,
            persona_count=args.persona_count,
        )
        output = args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        if args.command == "generate-public-extraction":
            output.write_text(
                public_extraction_corpus_to_json(extraction_benchmark.public),
                encoding="utf-8",
            )
            print(
                "Public extraction corpus ready: "
                f"{len(extraction_benchmark.public.pages)} pages -> {output}"
            )
        else:
            output.write_text(
                extraction_answers_to_json(extraction_benchmark.answers),
                encoding="utf-8",
            )
            print(
                "Extraction answer key ready: "
                f"{len(extraction_benchmark.answers.answers)} answers -> {output}"
            )
        return 0

    if args.command in {"generate", "metrics"}:
        world = generate_world(seed=args.seed, persona_count=args.persona_count)
    elif args.command in {"generate-corpus", "corpus-metrics"}:
        corpus = generate_exposure_corpus(
            seed=args.seed,
            persona_count=args.persona_count,
        )
    else:
        extraction_corpus = generate_extraction_corpus(
            seed=args.seed,
            persona_count=args.persona_count,
        )

    if args.command == "generate":
        output = args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(world_to_json(world), encoding="utf-8")
        print(
            f"SynthWorld ready: {len(world.personas)} personas, "
            f"{len(world.relationships)} relationships -> {output}"
        )
        return 0

    if args.command == "metrics":
        print(evaluate_world(world).model_dump_json(indent=2))
        return 0

    if args.command == "generate-corpus":
        output = args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(corpus_to_json(corpus), encoding="utf-8")
        print(
            f"Exposure corpus ready: {len(corpus.exposure_scripts)} scripts -> {output}"
        )
        return 0

    if args.command == "generate-extraction":
        output = args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            extraction_corpus_to_json(extraction_corpus),
            encoding="utf-8",
        )
        print(
            f"Extraction corpus ready: {len(extraction_corpus.pages)} pages -> {output}"
        )
        return 0

    print(evaluate_corpus(corpus).model_dump_json(indent=2))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="synthworld")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="write a world as JSON")
    _add_world_arguments(generate)
    generate.add_argument("--output", type=Path, required=True)

    metrics = subparsers.add_parser("metrics", help="print ground-truth metrics")
    _add_world_arguments(metrics)

    generate_corpus = subparsers.add_parser(
        "generate-corpus",
        help="write a world plus exposure scripts as JSON",
    )
    _add_world_arguments(generate_corpus)
    generate_corpus.add_argument("--output", type=Path, required=True)

    corpus_metrics = subparsers.add_parser(
        "corpus-metrics",
        help="print exposure-corpus ground-truth metrics",
    )
    _add_world_arguments(corpus_metrics)

    generate_extraction = subparsers.add_parser(
        "generate-extraction",
        help="write safe source pages plus evaluator-only span answer keys",
    )
    _add_world_arguments(generate_extraction)
    generate_extraction.add_argument("--output", type=Path, required=True)

    generate_public_extraction = subparsers.add_parser(
        "generate-public-extraction",
        help="write only product-safe extraction pages",
    )
    _add_world_arguments(generate_public_extraction)
    generate_public_extraction.add_argument("--output", type=Path, required=True)

    generate_extraction_answers = subparsers.add_parser(
        "generate-extraction-answers",
        help="write the physically separate exact-span answer key",
    )
    _add_world_arguments(generate_extraction_answers)
    generate_extraction_answers.add_argument("--output", type=Path, required=True)

    generate_connection_benchmark = subparsers.add_parser(
        "generate-connection-benchmark",
        help="write the adversarial raw-record corpus plus its separate truth",
    )
    _add_seed_argument(generate_connection_benchmark)
    generate_connection_benchmark.add_argument("--output", type=Path, required=True)

    generate_public_connections = subparsers.add_parser(
        "generate-public-connections",
        help="write only product-safe public relationship records",
    )
    _add_world_arguments(generate_public_connections)
    generate_public_connections.add_argument("--output", type=Path, required=True)

    connection_metrics = subparsers.add_parser(
        "connection-metrics",
        help="print raw-record and relationship-input benchmark metrics",
    )
    _add_world_arguments(connection_metrics)

    generate_risk_public = subparsers.add_parser(
        "generate-risk-public",
        help="write only opaque public breach-risk observations",
    )
    _add_world_arguments(generate_risk_public)
    generate_risk_public.add_argument("--output", type=Path, required=True)

    generate_risk_answer = subparsers.add_parser(
        "generate-risk-answer",
        help="write the physically separate breach-risk calibration truth",
    )
    _add_world_arguments(generate_risk_answer)
    generate_risk_answer.add_argument("--output", type=Path, required=True)

    risk_metrics = subparsers.add_parser(
        "risk-metrics",
        help="print public/truth risk benchmark integrity metrics",
    )
    _add_world_arguments(risk_metrics)

    evaluate = subparsers.add_parser(
        "evaluate",
        help="evaluate system predictions against separate truth",
    )
    evaluate.add_argument(
        "task",
        choices=["extraction", "entity-resolution", "relationship", "risk"],
        help="evaluation task to run",
    )
    evaluate.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="path to predictions JSON file",
    )
    evaluate.add_argument(
        "--seed",
        type=int,
        default=20_260_719,
        help="benchmark seed",
    )
    evaluate.add_argument(
        "--persona-count",
        type=int,
        default=10,
        help="benchmark persona count",
    )
    evaluate.add_argument(
        "--summary",
        action="store_true",
        help="print compact human table of metrics instead of JSON",
    )
    return parser


def _add_world_arguments(parser: argparse.ArgumentParser) -> None:
    _add_seed_argument(parser)
    parser.add_argument("--persona-count", type=int, default=10)


def _add_seed_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--seed", type=int, default=20_260_719)


def _metric_table(report: EvaluationReport) -> str:
    header = ("Metric", "Value", "Support")
    rows = [
        (
            metric.name,
            "None" if metric.value is None else f"{metric.value:.4f}",
            str(metric.support),
        )
        for metric in report.metrics
    ]
    widths = [
        max(len(cell) for cell in column) for column in zip(header, *rows, strict=True)
    ]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True))
        for row in (header, *rows)
    )
