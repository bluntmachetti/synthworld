"""Materialize the deterministic Asteria C08 v2 frozen benchmark tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from synthworld.agentic.c08_v2.frozen import (
    C08_FROZEN_BENCHMARK_PATH,
    freeze_c08_v2_benchmark,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=C08_FROZEN_BENCHMARK_PATH)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    bundle = freeze_c08_v2_benchmark(args.output, replace=args.replace)
    print(
        json.dumps(
            {
                "evaluator_artifact_set_digest": bundle.evaluator_artifact_set_digest,
                "public_artifact_set_digest": bundle.public_artifact_set_digest,
                "public_input_digest": bundle.public_input_digest,
                "root_artifact_set_digest": bundle.root_artifact_set_digest,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
