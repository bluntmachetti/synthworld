from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from synthworld.agentic.evaluation import (
    evaluate_agentic_trace,
    trace_submission_from_jsonl,
)
from synthworld.agentic.generator import generate_asteria_agentic_v1
from synthworld.agentic.serialization import (
    AgenticArtifactError,
    export_agentic_benchmark,
    load_public_agentic_bundle,
)
from synthworld.agentic.trace_validation import (
    TraceValidationReport,
    validate_trace_jsonl,
)
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

    if args.command == "validate":
        # Its own try block: the evaluate handler below guards a different set of
        # calls, and this path raises different things. Narrow on purpose - catching
        # every ValueError would report an internal defect as though the user's file
        # were at fault. UnicodeDecodeError is itself a ValueError but is listed
        # explicitly so a non-UTF-8 predictions file stays covered if the tuple
        # changes.
        try:
            expected = load_public_agentic_bundle().scenario.action_event_ids
            validation = validate_trace_jsonl(
                # utf-8-sig, not utf-8: editors on Windows commonly prepend a BOM, and
                # decoding it as content yields "Invalid JSON at line 1 column 1" with
                # no hint that three invisible bytes are the cause. Applied to the
                # evaluate path too - fixing only one would let this command bless a
                # file the scorer then refuses.
                args.predictions.read_text(encoding="utf-8-sig"),
                expected_event_ids=expected,
            )
        except (
            OSError,
            UnicodeDecodeError,
            AgenticArtifactError,
            ValidationError,
        ) as error:
            print(str(error), file=sys.stderr)
            return 1

        if args.json:
            print(validation.model_dump_json(indent=2))
        else:
            print(_validation_summary(validation))
        return 0 if validation.valid else 1

    if args.command == "evaluate":
        try:
            text = args.predictions.read_text(encoding="utf-8-sig")
            if args.task == "agentic":
                report = evaluate_agentic_trace(trace_submission_from_jsonl(text))
            elif args.task == "extraction":
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
        except (OSError, ValidationError, EvaluationInputError) as error:
            print(str(error), file=sys.stderr)
            return 1

        if args.summary:
            print(_metric_table(report))
        else:
            print(report.model_dump_json(indent=2))
        return 0

    if args.command == "generate-agentic":
        agentic_benchmark = generate_asteria_agentic_v1()
        export_agentic_benchmark(args.output, agentic_benchmark)
        print(
            "Asteria Agentic v1 ready: "
            f"{len(agentic_benchmark.public.events)} events, "
            f"{len(agentic_benchmark.evaluator.authority_truth)} actions "
            f"-> {args.output}"
        )
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

    generate_agentic = subparsers.add_parser(
        "generate-agentic",
        help="write frozen Asteria public and evaluator artifact trees",
    )
    generate_agentic.add_argument("--output", type=Path, required=True)

    validate = subparsers.add_parser(
        "validate",
        help="check a submission's shape before scoring, without answer-key truth",
    )
    validate.add_argument(
        "task",
        choices=["agentic-trace"],
        help="artifact to validate",
    )
    validate.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="path to the observed-action JSONL file to check",
    )
    validate.add_argument(
        "--json",
        action="store_true",
        help="print the machine-readable report instead of a human summary",
    )

    evaluate = subparsers.add_parser(
        "evaluate",
        help="evaluate system predictions against separate truth",
    )
    evaluate.add_argument(
        "task",
        choices=[
            "agentic",
            "extraction",
            "entity-resolution",
            "relationship",
            "risk",
        ],
        help="evaluation task to run",
    )
    evaluate.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="path to predictions JSON file, or JSONL for agentic traces",
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


def _validation_summary(report: TraceValidationReport) -> str:
    """Render a validation report as a terminal diagnostic.

    Human-readable is the default here, inverting ``evaluate``, which prints JSON
    unless asked for a table. The reasoning is that an evaluation report is a record
    to keep, whereas this output is read once to find a broken line - and automation
    should branch on the exit code rather than parse either form.
    """

    verdict = "valid" if report.valid else "invalid"
    lines = [
        f"agentic-trace: {verdict}",
        (
            f"rows {report.row_count}, "
            f"expected actions {report.expected_action_count}, "
            f"{report.error_count} errors, {report.warning_count} warnings"
        ),
    ]
    if not report.issues:
        return "\n".join(lines)
    severities = [item.severity for item in report.issues]
    locations = [
        "-" if item.line is None else f"line {item.line}" for item in report.issues
    ]
    codes = [item.code for item in report.issues]
    widths = (
        max(len(cell) for cell in severities),
        max(len(cell) for cell in locations),
        max(len(cell) for cell in codes),
    )
    for item, severity, location, code in zip(
        report.issues, severities, locations, codes, strict=True
    ):
        subject = f"{item.event_id}: " if item.event_id is not None else ""
        lines.append(
            f"{severity.ljust(widths[0])}  {location.ljust(widths[1])}  "
            f"{code.ljust(widths[2])}  {subject}{item.message}"
        )
    return "\n".join(lines)


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
