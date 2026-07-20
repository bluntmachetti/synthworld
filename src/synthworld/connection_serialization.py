from __future__ import annotations

from importlib.resources import files

from synthworld.connection import ConnectionBenchmark, PublicConnectionCorpus


def connection_benchmark_to_json(benchmark: ConnectionBenchmark) -> str:
    """Serialize a connection benchmark using canonical model ordering."""

    return f"{benchmark.model_dump_json(indent=2)}\n"


def public_connection_corpus_to_json(corpus: PublicConnectionCorpus) -> str:
    """Serialize only the public, product-safe connection input corpus."""

    public = PublicConnectionCorpus.model_validate(corpus)
    return f"{public.model_dump_json(indent=2)}\n"


def load_golden_connection_benchmark() -> ConnectionBenchmark:
    """Load the separately versioned frozen connection benchmark."""

    serialized = (
        files("synthworld.benchmarks")
        .joinpath("connection-golden-v1.json")
        .read_text(encoding="utf-8")
    )
    return ConnectionBenchmark.model_validate_json(serialized)


def load_golden_public_connection_corpus() -> PublicConnectionCorpus:
    """Load the physically separate frozen product-safe public corpus."""

    serialized = (
        files("synthworld.benchmarks")
        .joinpath("connection-public-golden-v1.json")
        .read_text(encoding="utf-8")
    )
    return PublicConnectionCorpus.model_validate_json(serialized)


__all__ = [
    "connection_benchmark_to_json",
    "load_golden_connection_benchmark",
    "load_golden_public_connection_corpus",
    "public_connection_corpus_to_json",
]
