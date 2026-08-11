#!/usr/bin/env python3
"""Write or load the packaged enterprise C08 v2 frozen benchmark tree."""

from __future__ import annotations

import argparse
from pathlib import Path

from synthworld.agentic.enterprise.c08_v2.frozen import (
    FrozenC08BenchmarkError,
    frozen_files,
    load_frozen_benchmark,
    write_frozen_benchmark,
)

DEFAULT_ROOT = (
    Path(__file__).resolve().parents[2]
    / "src/synthworld/benchmarks/enterprise-agentic-c08-v2"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--load",
        action="store_true",
        help="load an existing tree instead of writing",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace an existing exact frozen inventory in write mode",
    )
    args = parser.parse_args(argv)
    if args.load:
        if args.replace:
            parser.error("--replace cannot be combined with --load")
        load_frozen_benchmark(args.root)
        print(f"Loaded frozen enterprise C08 v2 tree: {args.root}")
    else:
        write_frozen_benchmark(args.root, replace=args.replace)
        print(f"Wrote frozen enterprise C08 v2 tree: {args.root}")
    return 0


__all__ = [
    "DEFAULT_ROOT",
    "FrozenC08BenchmarkError",
    "frozen_files",
    "load_frozen_benchmark",
    "main",
    "write_frozen_benchmark",
]


if __name__ == "__main__":
    raise SystemExit(main())
