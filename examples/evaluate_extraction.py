"""Evaluate a naive PII extractor against SynthWorld's exact-span answer key.

SynthWorld's extraction benchmark keeps the two sides of an evaluation
physically separate: a product-safe ``PublicExtractionCorpus`` of pages, and an
``ExtractionAnswerKeyCorpus`` of exact character spans. This example feeds a
deliberately simple regex extractor only the public page fields, then loads the
answer key afterwards to score it — the honest flow a real PII-extraction
system would plug into.

Run with:

    uv run python examples/evaluate_extraction.py
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence

from synthworld.evaluation import (
    ExtractionPagePrediction,
    ExtractionPredictionSet,
    PredictedSpan,
    evaluate_extraction,
)
from synthworld.exposures import DataClass
from synthworld.extraction_generator import generate_extraction_benchmark

_EMAIL = re.compile(r"[a-z0-9][a-z0-9._%+-]*@example\.test")
_PHONE = re.compile(r"\+1-[0-9]{3}-555-01[0-9]{2}")
_NATIONAL_ID = re.compile(r"SYN-[0-9]+")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluate_extraction")
    parser.add_argument("--seed", type=int, default=20_260_719)
    parser.add_argument("--persona-count", type=int, default=10)
    args = parser.parse_args(argv)

    benchmark = generate_extraction_benchmark(
        seed=args.seed,
        persona_count=args.persona_count,
    )

    # Product side: only the public pages are visible to the system under test.
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

    # Score predictions
    report = evaluate_extraction(
        preds,
        seed=args.seed,
        persona_count=args.persona_count,
    )

    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
