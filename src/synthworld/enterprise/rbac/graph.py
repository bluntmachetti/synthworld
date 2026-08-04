"""Bounded DAG path counting and enumeration for access derivations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from synthworld.enterprise.compiler import EnterpriseCompileError


def canonical_adjacency(
    nodes: Iterable[str], edges: Iterable[tuple[str, str]]
) -> dict[str, tuple[str, ...]]:
    """Build canonical adjacency and reject cycles without enumerating paths."""

    adjacency: dict[str, list[str]] = {node: [] for node in nodes}
    indegree = {node: 0 for node in adjacency}
    for source, target in edges:
        adjacency[source].append(target)
        indegree[target] += 1
    queue = sorted(node for node, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        source = queue.pop(0)
        visited += 1
        for target in sorted(adjacency[source]):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
                queue.sort()
    if visited != len(adjacency):
        raise EnterpriseCompileError(
            "directory_rbac_graph_cycle", "directory/RBAC derivation graph has a cycle"
        )
    return {key: tuple(sorted(value)) for key, value in adjacency.items()}


def bounded_paths(
    *,
    adjacency: Mapping[str, tuple[str, ...]],
    starts: Iterable[str],
    max_paths_per_start: int,
    max_total_paths: int,
    budget_code: str,
) -> dict[str, tuple[tuple[str, ...], ...]]:
    """Pre-count with saturation, then enumerate every distinct DAG path."""

    memo: dict[str, int] = {}
    saturation = max(max_paths_per_start, max_total_paths) + 1

    def count(node: str) -> int:
        prior = memo.get(node)
        if prior is not None:
            return prior
        measured = 1
        for child in adjacency[node]:
            measured = min(saturation, measured + count(child))
        memo[node] = measured
        return measured

    ordered_starts = tuple(sorted(starts))
    total = 0
    for start in ordered_starts:
        measured = count(start)
        if measured > max_paths_per_start:
            raise EnterpriseCompileError(
                budget_code,
                "one directory/RBAC source exceeds its derivation-path budget",
                measured=measured,
                allowed=max_paths_per_start,
            )
        total = min(saturation, total + measured)
    if total > max_total_paths:
        raise EnterpriseCompileError(
            budget_code,
            "directory/RBAC sources exceed the total derivation-path budget",
            measured=total,
            allowed=max_total_paths,
        )

    path_memo: dict[str, tuple[tuple[str, ...], ...]] = {}

    def enumerate_from(node: str) -> tuple[tuple[str, ...], ...]:
        prior = path_memo.get(node)
        if prior is not None:
            return prior
        paths: list[tuple[str, ...]] = [(node,)]
        for child in adjacency[node]:
            paths.extend((node, *suffix) for suffix in enumerate_from(child))
        result = tuple(sorted(paths))
        path_memo[node] = result
        return result

    return {start: enumerate_from(start) for start in ordered_starts}


__all__ = ["bounded_paths", "canonical_adjacency"]
