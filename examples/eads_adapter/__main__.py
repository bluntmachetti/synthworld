"""Command-line entry point for the Phase 1 EADS adapter."""

from __future__ import annotations

import argparse
import json
import math
import os
import stat
import sys
from collections.abc import Hashable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import yaml
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, Node, ScalarNode

from examples.eads_adapter.adapter import AdapterConfig, run_adapter
from examples.eads_adapter.models import SourceVintage

MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_SOURCE_DEPTH = 64
MAX_SOURCE_NODES = 100_000

_JSON_SCALAR_TAGS = {
    "tag:yaml.org,2002:null",
    "tag:yaml.org,2002:bool",
    "tag:yaml.org,2002:int",
    "tag:yaml.org,2002:float",
    "tag:yaml.org,2002:str",
}
_JSON_NODE_TAGS = _JSON_SCALAR_TAGS | {
    "tag:yaml.org,2002:map",
    "tag:yaml.org,2002:seq",
}


class _RestrictedSourceYamlLoader(yaml.SafeLoader):
    def compose_node(self, parent: Node | None, index: int) -> Node:
        if self.check_event(AliasEvent):  # type: ignore[no-untyped-call]
            raise yaml.constructor.ConstructorError(
                None,
                None,
                "yaml_alias_forbidden",
                self.peek_event().start_mark,  # type: ignore[no-untyped-call]
            )
        node = cast(Node, super().compose_node(parent, index))
        if node.tag not in _JSON_NODE_TAGS:
            raise yaml.constructor.ConstructorError(
                None,
                None,
                "yaml_non_json_tag_forbidden",
                node.start_mark,
            )
        if isinstance(node, ScalarNode):
            _validate_json_compatible_yaml_scalar(node)
        return node

    def construct_mapping(
        self,
        node: MappingNode,
        deep: bool = False,
    ) -> dict[Hashable, Any]:
        if not isinstance(node, MappingNode):
            raise yaml.constructor.ConstructorError(
                None,
                None,
                "yaml_mapping_required",
                node.start_mark,
            )
        mapping: dict[Hashable, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise yaml.constructor.ConstructorError(
                    None,
                    None,
                    "yaml_string_key_required",
                    key_node.start_mark,
                )
            if key in mapping:
                raise yaml.constructor.ConstructorError(
                    None,
                    None,
                    "duplicate_mapping_key",
                    key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _validate_json_compatible_yaml_scalar(node: ScalarNode) -> None:
    value = node.value
    valid = True
    if node.tag == "tag:yaml.org,2002:null":
        valid = value == "null"
    elif node.tag == "tag:yaml.org,2002:bool":
        valid = value in {"true", "false"}
    elif node.tag == "tag:yaml.org,2002:int":
        valid = _is_json_integer(value)
    elif node.tag == "tag:yaml.org,2002:float":
        valid = _is_json_number(value)
    if not valid:
        raise yaml.constructor.ConstructorError(
            None,
            None,
            "yaml_non_json_scalar_forbidden",
            node.start_mark,
        )


def _is_json_integer(value: str) -> bool:
    if value == "0":
        return True
    unsigned = value[1:] if value.startswith("-") else value
    return bool(unsigned) and unsigned.isdigit() and not unsigned.startswith("0")


def _is_json_number(value: str) -> bool:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return False
    return (
        isinstance(parsed, int | float)
        and not isinstance(parsed, bool)
        and math.isfinite(parsed)
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument(
        "--vintage",
        choices=tuple(item.value for item in SourceVintage),
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--namespace-salt-file", type=Path, required=True)
    parser.add_argument(
        "--max-principals-per-organisation",
        type=int,
        default=10_000,
    )
    arguments = parser.parse_args(argv)

    try:
        payload = _load_source(arguments.source)
        config = AdapterConfig(
            seed=arguments.seed,
            namespace_salt=_load_namespace_salt(arguments.namespace_salt_file),
            max_principals_per_organisation=(arguments.max_principals_per_organisation),
        )
        report = run_adapter(
            payload=payload,
            vintage=cast(str, arguments.vintage),
            output_dir=cast(Path, arguments.output),
            config=config,
        )
    except (
        OSError,
        ValueError,
        TypeError,
        RecursionError,
        MemoryError,
        json.JSONDecodeError,
        yaml.YAMLError,
    ):
        print("eads-adapter: source_or_configuration_error", file=sys.stderr)
        return 2
    return 1 if report.status == "failed" else 0


def _load_source(path: Path) -> Mapping[str, object]:
    suffix = path.suffix.casefold()
    source_bytes = _read_bounded_regular_file(path)
    text = source_bytes.decode("utf-8")
    if suffix == ".json":
        loaded = cast(
            object,
            json.loads(
                text,
                object_pairs_hook=_unique_json_mapping,
                parse_constant=_reject_nonfinite_json,
            ),
        )
    elif suffix in {".yaml", ".yml"}:
        loaded = cast(
            object,
            yaml.load(text, Loader=_RestrictedSourceYamlLoader),  # noqa: S506
        )
    else:
        raise ValueError("unsupported_source_suffix")
    if not isinstance(loaded, Mapping):
        raise ValueError("source_mapping_required")
    _validate_json_tree(loaded)
    return cast(Mapping[str, object], loaded)


def _read_bounded_regular_file(
    path: Path,
    *,
    max_bytes: int = MAX_SOURCE_BYTES,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError("source_regular_file_required")
        payload = source.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError("source_byte_limit_exceeded")
    return payload


def _load_namespace_salt(path: Path) -> str:
    payload = _read_bounded_regular_file(path, max_bytes=65)
    if payload.endswith(b"\n"):
        payload = payload[:-1]
    if len(payload) != 64:
        raise ValueError("namespace_salt_file_invalid")
    salt = payload.decode("ascii")
    if any(character not in "0123456789abcdef" for character in salt):
        raise ValueError("namespace_salt_file_invalid")
    return salt


def _unique_json_mapping(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_mapping_key")
        result[key] = value
    return result


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"nonfinite_json_number:{value}")


def _validate_json_tree(value: object) -> None:
    nodes = 0

    def visit(item: object, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_SOURCE_NODES:
            raise ValueError("source_node_limit_exceeded")
        if depth > MAX_SOURCE_DEPTH:
            raise ValueError("source_depth_limit_exceeded")
        if item is None or isinstance(item, str | bool | int):
            return
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("source_nonfinite_number")
            return
        if isinstance(item, list | tuple):
            for nested in item:
                visit(nested, depth + 1)
            return
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise ValueError("source_string_keys_required")
                visit(nested, depth + 1)
            return
        raise ValueError("source_non_json_value")

    visit(value, 0)


if __name__ == "__main__":
    raise SystemExit(main())
