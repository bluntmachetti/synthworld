"""Evaluate all four SynthWorld task prediction types against separate truth.

This example runs a full evaluation sweep across:
- Exact-span PII extraction (using naive regex rules over public pages);
- Entity resolution (using correct ground-truth clusters);
- Relationship inference (using perfect undirected relationship edges);
- Risk calibration (using correct breach-risk assessments).

Run with:

    uv run python examples/evaluate_all.py
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from uuid import UUID

from synthworld.connection_generator import (
    generate_adversarial_connection_benchmark,
    generate_relationship_connection_benchmark,
)
from synthworld.evaluation import (
    EntityResolutionPrediction,
    ExtractionPagePrediction,
    ExtractionPredictionSet,
    PredictedRelationship,
    PredictedSpan,
    RelationshipPrediction,
    RiskCasePrediction,
    RiskPrediction,
    evaluate_entity_resolution,
    evaluate_extraction,
    evaluate_relationship_inference,
    evaluate_risk_calibration,
)
from synthworld.exposures import DataClass
from synthworld.extraction_generator import generate_extraction_benchmark
from synthworld.risk import RiskBand
from synthworld.risk_generator import generate_risk_benchmark

_EMAIL = re.compile(r"[a-z0-9][a-z0-9._%+-]*@example\.test")
_PHONE = re.compile(r"\+1-[0-9]{3}-555-01[0-9]{2}")
_NATIONAL_ID = re.compile(r"SYN-[0-9]+")


def run_extraction_eval(seed: int, persona_count: int) -> None:
    print("\n=== Evaluating Extraction ===")
    benchmark = generate_extraction_benchmark(seed=seed, persona_count=persona_count)

    pages: list[ExtractionPagePrediction] = []
    for page in benchmark.public.pages:
        spans: list[PredictedSpan] = []
        for pattern, data_class in (
            (_EMAIL, DataClass.EMAIL),
            (_PHONE, DataClass.PHONE),
            (_NATIONAL_ID, DataClass.NATIONAL_ID),
        ):
            for match in pattern.finditer(page.content):
                spans.append(
                    PredictedSpan(
                        data_class=data_class,
                        start=match.start(),
                        end=match.end(),
                    )
                )
        pages.append(
            ExtractionPagePrediction(
                source_type=page.source_type,
                source_record_id=page.source_record_id,
                spans=tuple(spans),
            )
        )

    preds = ExtractionPredictionSet(predictions=tuple(pages))
    report = evaluate_extraction(preds, seed=seed, persona_count=persona_count)
    print(report.model_dump_json(indent=2))


def run_entity_resolution_eval(seed: int) -> None:
    print("\n=== Evaluating Entity Resolution ===")
    benchmark = generate_adversarial_connection_benchmark(seed=seed)

    by_entity: dict[str, list[UUID]] = {}
    for item in benchmark.answer_key.record_memberships:
        by_entity.setdefault(item.entity_id, []).append(item.record_id)

    preds = EntityResolutionPrediction(
        clusters=tuple(tuple(records) for records in by_entity.values())
    )
    report = evaluate_entity_resolution(preds, seed=seed)
    print(report.model_dump_json(indent=2))


def run_relationship_eval(seed: int, persona_count: int) -> None:
    print("\n=== Evaluating Relationship Inference ===")
    benchmark = generate_relationship_connection_benchmark(
        seed=seed, persona_count=persona_count
    )

    preds = RelationshipPrediction(
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
    report = evaluate_relationship_inference(
        preds, seed=seed, persona_count=persona_count
    )
    print(report.model_dump_json(indent=2))


def run_risk_eval(seed: int, persona_count: int) -> None:
    print("\n=== Evaluating Risk Calibration ===")
    benchmark = generate_risk_benchmark(seed=seed, persona_count=persona_count)

    preds = RiskPrediction(
        cases=tuple(
            RiskCasePrediction(
                case_id=case.case_id,
                band=case.band,
                score=case.score,
                band_probabilities=tuple(
                    (item, 1.0 if item is case.band else 0.0) for item in RiskBand
                ),
            )
            for case in benchmark.answer_key.cases
        )
    )
    report = evaluate_risk_calibration(preds, seed=seed, persona_count=persona_count)
    print(report.model_dump_json(indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluate_all")
    parser.add_argument("--seed", type=int, default=20_260_719)
    parser.add_argument("--persona-count", type=int, default=10)
    args = parser.parse_args(argv)

    run_extraction_eval(args.seed, args.persona_count)
    run_entity_resolution_eval(args.seed)
    run_relationship_eval(args.seed, args.persona_count)
    run_risk_eval(args.seed, args.persona_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
