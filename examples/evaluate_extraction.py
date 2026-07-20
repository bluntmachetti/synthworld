"""Evaluate a naive email extractor against SynthWorld's exact-span answer keys.

SynthWorld's extraction corpus pairs product-safe source pages with
evaluator-only answer keys listing the exact character spans of each planted
identifier. This example runs a deliberately simple regex extractor over the
public page content and scores it against the ground truth, demonstrating the
scoring loop a real PII-extraction system would plug into.

Run with:

    uv run python examples/evaluate_extraction.py
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence

from synthworld.exposures import DataClass
from synthworld.extraction_generator import generate_extraction_corpus

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluate_extraction")
    parser.add_argument("--seed", type=int, default=20_260_719)
    parser.add_argument("--persona-count", type=int, default=10)
    args = parser.parse_args(argv)

    corpus = generate_extraction_corpus(
        seed=args.seed,
        persona_count=args.persona_count,
    )

    gold: set[tuple[str, int, int]] = set()
    predicted: set[tuple[str, int, int]] = set()
    for annotated in corpus.pages:
        page_key = f"{annotated.page.source_type}:{annotated.page.source_record_id}"
        for span in annotated.answer_key.spans:
            if span.data_class is DataClass.EMAIL:
                gold.add((page_key, span.start, span.end))
        for match in _EMAIL_PATTERN.finditer(annotated.page.content):
            predicted.add((page_key, match.start(), match.end()))

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
                "pages": len(corpus.pages),
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
