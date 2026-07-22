"""Evaluate a naive email extractor against SynthWorld's exact-span answer key.

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
import json
import re
from collections.abc import Sequence

from synthworld.exposures import DataClass
from synthworld.extraction_generator import generate_extraction_benchmark

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_PageKey = tuple[str, str]
_Span = tuple[_PageKey, int, int]


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
    predicted: set[_Span] = set()
    for page in benchmark.public.pages:
        key = (page.source_type, page.source_record_id)
        for match in _EMAIL_PATTERN.finditer(page.content):
            predicted.add((key, match.start(), match.end()))

    # Evaluator side: reveal the separately serialized answer key to score.
    gold: set[_Span] = set()
    for answer in benchmark.answers.answers:
        key = (answer.source_type, answer.source_record_id)
        for span in answer.answer_key.spans:
            if span.data_class is DataClass.EMAIL:
                gold.add((key, span.start, span.end))

    true_positives = len(gold & predicted)
    precision = true_positives / len(predicted) if predicted else 0.0
    recall = true_positives / len(gold) if gold else 0.0
    denominator = precision + recall
    f1 = 2 * precision * recall / denominator if denominator else 0.0
    print(
        json.dumps(
            {
                "synthetic": True,
                "seed": args.seed,
                "pages": len(benchmark.public.pages),
                "gold_email_spans": len(gold),
                "predicted_email_spans": len(predicted),
                "true_positives": true_positives,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
