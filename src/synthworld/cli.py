from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from synthworld.agent_authority.models import AgentAuthorityRunPlanV1
from synthworld.agentic.enterprise import (
    EnterpriseAgenticArtifactError,
    EnterpriseAgenticEvaluationError,
    EnterpriseAgenticGenerationConfigV1,
    enterprise_agentic_trace_from_jsonl,
    evaluate_enterprise_agentic_prediction,
    export_enterprise_agentic_benchmark,
    export_generated_enterprise_agentic_benchmark,
    generate_enterprise_agentic_world,
    load_evaluator_enterprise_agentic_benchmark,
    load_public_enterprise_agentic_benchmark,
    reference_enterprise_agentic,
    validate_enterprise_agentic_trace_jsonl,
)
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
from synthworld.assurance.agent_authority import validate_agent_authority_run_receipt
from synthworld.assurance.contextual_access import (
    validate_contextual_access_run_receipt,
)
from synthworld.assurance.receipt import ReceiptIntegrityError
from synthworld.broker_metrics import BrokerAssessment
from synthworld.connection_generator import (
    generate_adversarial_connection_benchmark,
    generate_relationship_connection_benchmark,
)
from synthworld.connection_metrics import evaluate_connection_benchmarks
from synthworld.connection_serialization import (
    connection_benchmark_to_json,
    public_connection_corpus_to_json,
)
from synthworld.contextual_access import (
    ContextualAccessArtifactError,
    ContextualAccessEvaluationError,
    ContextualAccessRunPlanV1,
    contextual_access_trace_from_jsonl,
    evaluate_contextual_access_prediction,
    export_contextual_access_benchmark,
    load_evaluator_contextual_access_benchmark,
    load_public_contextual_access_benchmark,
    reference_contextual_access,
    validate_contextual_access_trace_jsonl,
)
from synthworld.continuous_assurance import (
    ContinuousAssuranceArtifactError,
    ContinuousAssuranceEvaluationError,
    ContinuousAssurancePredictionV1,
    evaluate_continuous_assurance_prediction,
    export_continuous_assurance_benchmark,
    load_evaluator_continuous_assurance_benchmark,
    load_public_continuous_assurance_benchmark,
    reference_continuous_assurance,
)
from synthworld.corpus_metrics import evaluate_corpus
from synthworld.corpus_serialization import corpus_to_json
from synthworld.enterprise.compiler import (
    EnterpriseCompileError,
    compile_enterprise_identity_access_universe,
)
from synthworld.enterprise.models import EnterpriseIdentityAccessValidationReportV1
from synthworld.enterprise.parsers import load_enterprise_identity_access_import
from synthworld.enterprise.scaffold import (
    EnterpriseScaffoldError,
    scaffold_enterprise_access,
)
from synthworld.enterprise.serialization import (
    EnterpriseArtifactError,
    export_enterprise_identity_access_compile_result,
)
from synthworld.enterprise.validation import EnterpriseImportError
from synthworld.evaluation import (
    EntityResolutionPrediction,
    EvaluationInputError,
    EvaluationReport,
    ExtractionPredictionSet,
    RelationshipPrediction,
    RiskPrediction,
    evaluate_broker_removal,
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
from synthworld.profiles.households import (
    HouseholdsConfig,
    generate_households_benchmark,
)
from synthworld.profiles.realism import RealismError
from synthworld.risk_generator import generate_risk_benchmark
from synthworld.risk_metrics import evaluate_risk_benchmark
from synthworld.risk_serialization import (
    public_risk_corpus_to_json,
    risk_answer_key_to_json,
)
from synthworld.serialization import world_to_json

REPRODUCIBLE_BENCHMARK_IDS = (
    "ambiguity-v1",
    "asteria-agentic-v1",
    "authority-governance-v1",
    "connection-v1",
    "core-world-v1",
    "extraction-v1",
    "risk-v1",
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)

    if args.command == "reproduce-benchmark":
        reproduction = importlib.import_module("synthworld.benchmark_reproduction")
        try:
            reproduction.reproduce_benchmark(
                benchmark_id=args.benchmark,
                output_directory=args.output,
            )
        except (OSError, ValueError) as error:
            print(f"reproduce-benchmark: {error}", file=sys.stderr)
            return 1
        print(f"Benchmark reproduced: {args.benchmark} -> {args.output}")
        return 0

    if args.command == "scaffold-enterprise-access":
        try:
            scaffold_enterprise_access(
                output_format=args.format,
                output=args.output,
                id_namespace_salt=args.id_namespace_salt,
            )
        except (OSError, ValidationError, EnterpriseScaffoldError) as error:
            print(str(error), file=sys.stderr)
            return 1
        print(
            "Private enterprise identity/access template ready "
            f"({args.format}) -> {args.output}"
        )
        print(
            "Importing structure is not anonymisation; protect the source and "
            "namespace salt."
        )
        return 0

    if args.command == "validate-enterprise-access":
        try:
            load_enterprise_identity_access_import(args.input)
            validation_report = EnterpriseIdentityAccessValidationReportV1(
                valid=True, diagnostics=()
            )
        except EnterpriseImportError as error:
            validation_report = EnterpriseIdentityAccessValidationReportV1(
                valid=False, diagnostics=error.diagnostics
            )
        if args.json:
            print(validation_report.model_dump_json(indent=2))
        elif validation_report.valid:
            print("enterprise identity/access import: valid")
        else:
            for diagnostic in validation_report.diagnostics:
                location = ":".join(
                    str(item)
                    for item in (diagnostic.file, diagnostic.row, diagnostic.column)
                    if item is not None
                )
                print(
                    f"{diagnostic.code} {location}: {diagnostic.message}".strip(),
                    file=sys.stderr,
                )
        return 0 if validation_report.valid else 1

    if args.command == "compile-enterprise-access":
        try:
            import_model = load_enterprise_identity_access_import(args.input)
            result = compile_enterprise_identity_access_universe(
                import_model=import_model,
                seed=args.seed,
            )
            export_enterprise_identity_access_compile_result(args.output, result)
        except (
            EnterpriseArtifactError,
            EnterpriseCompileError,
            EnterpriseImportError,
            OSError,
            ValidationError,
        ) as error:
            print(str(error), file=sys.stderr)
            return 1
        print(
            "Enterprise identity/access universe ready: "
            f"{len(result.public_universe.principals)} principals, "
            f"{len(result.public_universe.accounts)} account slots, "
            f"{len(result.public_universe.access_atoms)} access atoms -> "
            f"{args.output}"
        )
        return 0

    if args.command == "validate":
        if args.task == "contextual-access-run-plan":
            try:
                ContextualAccessRunPlanV1.model_validate_json(
                    args.input.read_text(encoding="utf-8-sig")
                )
            except (OSError, UnicodeDecodeError, ValidationError) as error:
                print(str(error), file=sys.stderr)
                return 1
            print("contextual-access-run-plan: structurally valid")
            return 0

        if args.task == "agent-authority-run-plan":
            try:
                AgentAuthorityRunPlanV1.model_validate_json(
                    args.input.read_text(encoding="utf-8-sig")
                )
            except (OSError, UnicodeDecodeError, ValidationError) as error:
                print(str(error), file=sys.stderr)
                return 1
            print("agent-authority-run-plan: valid")
            return 0

        if args.task == "agent-authority-receipt":
            try:
                manifest = validate_agent_authority_run_receipt(args.input)
            except (OSError, UnicodeDecodeError, ReceiptIntegrityError) as error:
                print(str(error), file=sys.stderr)
                return 1
            print(
                "agent-authority-receipt: valid "
                f"({len(manifest.artifacts)} bound artifacts)"
            )
            return 0

        if args.task == "contextual-access-receipt":
            try:
                manifest = validate_contextual_access_run_receipt(args.input)
            except (OSError, UnicodeDecodeError, ReceiptIntegrityError) as error:
                print(str(error), file=sys.stderr)
                return 1
            print(
                "contextual-access-receipt: valid "
                f"({len(manifest.artifacts)} bound artifacts)"
            )
            return 0

        if args.task == "enterprise-agentic-trace":
            try:
                enterprise_public = load_public_enterprise_agentic_benchmark(
                    args.benchmark_root
                )
                enterprise_validation = validate_enterprise_agentic_trace_jsonl(
                    args.predictions.read_text(encoding="utf-8-sig"),
                    public=enterprise_public,
                )
            except (
                OSError,
                UnicodeDecodeError,
                EnterpriseAgenticArtifactError,
                ValidationError,
            ) as error:
                print(str(error), file=sys.stderr)
                return 1
            if args.json:
                print(enterprise_validation.model_dump_json(indent=2))
            else:
                verdict = "valid" if enterprise_validation.valid else "invalid"
                print(
                    f"enterprise-agentic-trace: {verdict}; "
                    f"rows={enterprise_validation.row_count}, "
                    f"expected={enterprise_validation.expected_case_count}, "
                    f"issues={len(enterprise_validation.issues)}"
                )
            return 0 if enterprise_validation.valid else 1

        if args.task == "contextual-access-trace":
            try:
                contextual_public = load_public_contextual_access_benchmark(
                    args.benchmark_root
                )
                contextual_validation = validate_contextual_access_trace_jsonl(
                    args.predictions.read_text(encoding="utf-8-sig"),
                    public=contextual_public,
                )
            except (
                OSError,
                UnicodeDecodeError,
                ContextualAccessArtifactError,
                ValidationError,
            ) as error:
                print(str(error), file=sys.stderr)
                return 1
            if args.json:
                print(contextual_validation.model_dump_json(indent=2))
            else:
                verdict = "valid" if contextual_validation.valid else "invalid"
                print(
                    f"contextual-access-trace: {verdict}; "
                    f"rows={contextual_validation.row_count}, "
                    f"expected={contextual_validation.expected_request_count}, "
                    f"issues={len(contextual_validation.issues)}"
                )
            return 0 if contextual_validation.valid else 1

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
            elif args.task == "enterprise-agentic":
                if args.benchmark_root is None:
                    raise EnterpriseAgenticEvaluationError(
                        "--benchmark-root is required for enterprise-agentic evaluation"
                    )
                enterprise_public = load_public_enterprise_agentic_benchmark(
                    args.benchmark_root
                )
                enterprise_evaluator = load_evaluator_enterprise_agentic_benchmark(
                    args.benchmark_root
                )
                enterprise_report = evaluate_enterprise_agentic_prediction(
                    public=enterprise_public,
                    evaluator=enterprise_evaluator,
                    prediction=enterprise_agentic_trace_from_jsonl(text),
                )
                if args.summary:
                    for metric in enterprise_report.metrics:
                        value = (
                            "null" if metric.value is None else f"{metric.value:.4f}"
                        )
                        print(
                            f"{metric.family:>26}  {metric.name:<48} "
                            f"{value:>6} n={metric.denominator}"
                        )
                else:
                    print(enterprise_report.model_dump_json(indent=2))
                return 0
            elif args.task == "contextual-access":
                if args.benchmark_root is None:
                    raise ContextualAccessEvaluationError(
                        "--benchmark-root is required for contextual-access evaluation"
                    )
                contextual_public = load_public_contextual_access_benchmark(
                    args.benchmark_root
                )
                contextual_evaluator = load_evaluator_contextual_access_benchmark(
                    args.benchmark_root
                )
                contextual_report = evaluate_contextual_access_prediction(
                    public=contextual_public,
                    evaluator=contextual_evaluator,
                    prediction=contextual_access_trace_from_jsonl(text),
                )
                if args.summary:
                    for metric in contextual_report.metrics:
                        value = (
                            "null" if metric.value is None else f"{metric.value:.4f}"
                        )
                        print(
                            f"{metric.family:>26}  {metric.name:<48} "
                            f"{value:>6} n={metric.denominator}"
                        )
                else:
                    print(contextual_report.model_dump_json(indent=2))
                return 0
            elif args.task == "continuous-assurance":
                if args.benchmark_root is None:
                    raise ContinuousAssuranceEvaluationError(
                        "--benchmark-root is required for continuous-assurance "
                        "evaluation"
                    )
                assurance_public = load_public_continuous_assurance_benchmark(
                    args.benchmark_root
                )
                assurance_evaluator = load_evaluator_continuous_assurance_benchmark(
                    args.benchmark_root
                )
                assurance_report = evaluate_continuous_assurance_prediction(
                    public=assurance_public,
                    evaluator=assurance_evaluator,
                    prediction=ContinuousAssurancePredictionV1.model_validate_json(
                        text
                    ),
                )
                if args.summary:
                    for assurance_metric in assurance_report.metrics:
                        value = (
                            "null"
                            if assurance_metric.value is None
                            else f"{assurance_metric.value:.4f}"
                        )
                        print(
                            f"{assurance_metric.family:>26}  "
                            f"{assurance_metric.name:<48} "
                            f"{value:>6} n={assurance_metric.denominator}"
                        )
                else:
                    print(assurance_report.model_dump_json(indent=2))
                return 0
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
            elif args.task == "broker":
                report = evaluate_broker_removal(
                    BrokerAssessment.model_validate_json(text),
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
        except (
            OSError,
            ValidationError,
            EvaluationInputError,
            EnterpriseAgenticArtifactError,
            EnterpriseAgenticEvaluationError,
            ContextualAccessArtifactError,
            ContextualAccessEvaluationError,
            ContinuousAssuranceArtifactError,
            ContinuousAssuranceEvaluationError,
        ) as error:
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

    if args.command == "generate-enterprise-agentic":
        if args.profile == "generated":
            try:
                generated = generate_enterprise_agentic_world(
                    EnterpriseAgenticGenerationConfigV1(
                        seed=args.seed,
                        tier=args.tier,
                    )
                )
                export_generated_enterprise_agentic_benchmark(args.output, generated)
            except (OSError, ValidationError) as error:
                print(str(error), file=sys.stderr)
                return 1
            print(
                "Generated enterprise-agentic smoke world ready: "
                f"{len(generated.public.snapshot.principals)} principals, "
                f"{len(generated.evaluator.authority_truth)} actions -> {args.output}"
            )
            return 0
        enterprise_agentic = reference_enterprise_agentic(seed=args.seed)
        try:
            export_enterprise_agentic_benchmark(
                args.output,
                public=enterprise_agentic.public,
                evaluator=enterprise_agentic.evaluator,
            )
        except (OSError, EnterpriseAgenticArtifactError) as error:
            print(str(error), file=sys.stderr)
            return 1
        print(
            "Enterprise-agentic smoke pack ready: "
            f"{len(enterprise_agentic.evaluator.truth.cases)} cases -> {args.output}"
        )
        return 0

    if args.command == "generate-contextual-access":
        contextual = reference_contextual_access(seed=args.seed)
        try:
            export_contextual_access_benchmark(
                args.output,
                public=contextual.public,
                evaluator=contextual.evaluator,
            )
        except (OSError, ContextualAccessArtifactError) as error:
            print(str(error), file=sys.stderr)
            return 1
        print(
            "Contextual-access smoke pack ready: "
            f"{len(contextual.evaluator.truth.cases)} cases -> {args.output}"
        )
        return 0

    if args.command == "generate-continuous-assurance":
        try:
            assurance = reference_continuous_assurance(
                tier=args.tier,
                seed=args.seed,
                risk_threshold=args.risk_threshold,
                justification_kind=args.justification_kind,
            )
            export_continuous_assurance_benchmark(
                args.output,
                public=assurance.public,
                evaluator=assurance.evaluator,
            )
        except (OSError, ValidationError, ContinuousAssuranceArtifactError) as error:
            print(str(error), file=sys.stderr)
            return 1
        print(
            "Continuous-assurance pack ready: "
            f"tier={assurance.config.tier.value}, "
            f"{len(assurance.evaluator.truth)} cases -> {args.output}"
        )
        if assurance.config.tier.value == "held_out":
            print(
                "Held-out is a generation profile, not a secrecy claim; withhold "
                "the configuration and apply operator-approved key custody for a "
                "competitive evaluation."
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

    if args.command == "generate-households":
        try:
            households = generate_households_benchmark(
                seed=args.seed,
                config=HouseholdsConfig(
                    person_count=args.person_count,
                    community_count=args.community_count,
                ),
            )
        except (RealismError, ValidationError) as error:
            # A world below its declared shape is a failure, not a warning: every
            # number reported downstream would describe something nobody asked for.
            print(str(error), file=sys.stderr)
            return 1
        root = args.output
        root.mkdir(parents=True, exist_ok=True)
        # The exact bytes the manifest digest was taken over. Re-serializing here
        # would let the digest describe something the file does not contain.
        root.joinpath("world.json").write_text(
            households.world_json(), encoding="utf-8"
        )
        root.joinpath("manifest.json").write_text(
            households.manifest.model_dump_json(indent=2), encoding="utf-8"
        )
        realism = households.manifest.realism
        print(
            f"households_and_workplaces ready: {realism.person_count} people, "
            f"{realism.edge_count} relationships, {realism.component_count} "
            f"components -> {root}"
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

    scaffold_enterprise = subparsers.add_parser(
        "scaffold-enterprise-access",
        help="write a private enterprise identity/access authoring template",
    )
    scaffold_enterprise.add_argument(
        "--format", choices=["yaml", "json", "csv"], default="yaml"
    )
    scaffold_enterprise.add_argument("--output", type=Path, required=True)
    scaffold_enterprise.add_argument("--id-namespace-salt")

    validate_enterprise = subparsers.add_parser(
        "validate-enterprise-access",
        help="validate a YAML, JSON, CSV-directory, or ZIP identity/access import",
    )
    validate_enterprise.add_argument("--input", type=Path, required=True)
    validate_enterprise.add_argument("--json", action="store_true")

    compile_enterprise = subparsers.add_parser(
        "compile-enterprise-access",
        help="compile a fixed fictional enterprise identity/access universe",
    )
    compile_enterprise.add_argument("--input", type=Path, required=True)
    compile_enterprise.add_argument("--seed", type=int, required=True)
    compile_enterprise.add_argument("--output", type=Path, required=True)

    households = subparsers.add_parser(
        "generate-households",
        help="write a households_and_workplaces world and its manifest",
    )
    households.add_argument("--seed", type=int, required=True)
    households.add_argument("--person-count", type=int, default=100)
    households.add_argument("--community-count", type=int, default=4)
    households.add_argument("--output", type=Path, required=True)

    reproduce_benchmark = subparsers.add_parser(
        "reproduce-benchmark",
        help="recreate one published benchmark's complete artifact inventory",
    )
    reproduce_benchmark.add_argument(
        "--benchmark",
        choices=REPRODUCIBLE_BENCHMARK_IDS,
        required=True,
    )
    reproduce_benchmark.add_argument("--output", type=Path, required=True)

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

    generate_enterprise_agentic = subparsers.add_parser(
        "generate-enterprise-agentic",
        help="write fixed-reference or generated enterprise-agentic artifacts",
    )
    _add_seed_argument(generate_enterprise_agentic)
    generate_enterprise_agentic.add_argument(
        "--profile", choices=("fixed", "generated"), default="fixed"
    )
    generate_enterprise_agentic.add_argument(
        "--tier", choices=("smoke",), default="smoke"
    )
    generate_enterprise_agentic.add_argument("--output", type=Path, required=True)

    generate_contextual_access = subparsers.add_parser(
        "generate-contextual-access",
        help="write the fixed-universe contextual-access smoke artifact trees",
    )
    _add_seed_argument(generate_contextual_access)
    generate_contextual_access.add_argument(
        "--tier", choices=("smoke",), default="smoke"
    )
    generate_contextual_access.add_argument("--output", type=Path, required=True)

    generate_continuous_assurance = subparsers.add_parser(
        "generate-continuous-assurance",
        help="write a digest-bound longitudinal identity-assurance pack",
    )
    _add_seed_argument(generate_continuous_assurance)
    generate_continuous_assurance.add_argument(
        "--tier",
        choices=("smoke", "standard", "longitudinal", "held_out"),
        default="smoke",
    )
    generate_continuous_assurance.add_argument("--risk-threshold", type=int, default=70)
    generate_continuous_assurance.add_argument(
        "--justification-kind",
        choices=("business_need", "case_assignment", "emergency_access"),
        default="business_need",
    )
    generate_continuous_assurance.add_argument("--output", type=Path, required=True)

    validate = subparsers.add_parser(
        "validate",
        help="check a submission's shape before scoring, without answer-key truth",
    )
    validation_tasks = validate.add_subparsers(dest="task", required=True)
    agentic_trace = validation_tasks.add_parser(
        "agentic-trace",
        help="validate an observed-action JSONL submission",
    )
    agentic_trace.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="path to the observed-action JSONL file to check",
    )
    agentic_trace.add_argument(
        "--json",
        action="store_true",
        help="print the machine-readable report instead of a human summary",
    )
    run_plan = validation_tasks.add_parser(
        "agent-authority-run-plan",
        help="validate a pre-execution agent-authority run plan",
    )
    run_plan.add_argument("--input", type=Path, required=True)
    receipt = validation_tasks.add_parser(
        "agent-authority-receipt",
        help="validate an agent-authority receipt directory",
    )
    receipt.add_argument("--input", type=Path, required=True)
    enterprise_agentic_trace = validation_tasks.add_parser(
        "enterprise-agentic-trace",
        help="validate an enterprise-agentic JSONL trace against public input",
    )
    enterprise_agentic_trace.add_argument("--predictions", type=Path, required=True)
    enterprise_agentic_trace.add_argument("--benchmark-root", type=Path, required=True)
    enterprise_agentic_trace.add_argument("--json", action="store_true")
    contextual_run_plan = validation_tasks.add_parser(
        "contextual-access-run-plan",
        help="structurally validate a pre-execution contextual-access run plan",
    )
    contextual_run_plan.add_argument("--input", type=Path, required=True)
    contextual_receipt = validation_tasks.add_parser(
        "contextual-access-receipt",
        help="validate a contextual-access receipt directory",
    )
    contextual_receipt.add_argument("--input", type=Path, required=True)
    contextual_trace = validation_tasks.add_parser(
        "contextual-access-trace",
        help="validate a contextual-access JSONL trace against public input",
    )
    contextual_trace.add_argument("--predictions", type=Path, required=True)
    contextual_trace.add_argument("--benchmark-root", type=Path, required=True)
    contextual_trace.add_argument("--json", action="store_true")

    evaluate = subparsers.add_parser(
        "evaluate",
        help="evaluate system predictions against separate truth",
    )
    evaluate.add_argument(
        "task",
        choices=[
            "agentic",
            "enterprise-agentic",
            "contextual-access",
            "continuous-assurance",
            "extraction",
            "broker",
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
    evaluate.add_argument(
        "--benchmark-root",
        type=Path,
        help=(
            "enterprise-agentic, contextual-access, or continuous-assurance "
            "artifact root"
        ),
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
