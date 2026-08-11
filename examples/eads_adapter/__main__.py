"""Run the repository-only fictional EADS-shaped structure adapter."""

from __future__ import annotations

import argparse
import errno
import json
import math
import os
import stat
import sys
from collections.abc import Hashable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, NoReturn, cast

import yaml
from pydantic import ValidationError
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, Node, ScalarNode

from examples.eads_adapter.adapter import (
    AdapterConfig,
    AdapterPathError,
    run_adapter,
)
from examples.eads_adapter.models import (
    MAX_SOURCE_BYTES,
    MAX_SOURCE_DEPTH,
    MAX_SOURCE_NODES,
    SourceVintage,
)

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


class _CliErrorCategory(StrEnum):
    CONFIGURATION = "config"
    OUTPUT = "output"
    PATH_SAFETY = "path-safety"
    RESOURCE_LIMIT = "resource"
    SOURCE = "source"


_CLI_EXIT_CODES = {
    _CliErrorCategory.SOURCE: 2,
    _CliErrorCategory.CONFIGURATION: 3,
    _CliErrorCategory.PATH_SAFETY: 4,
    _CliErrorCategory.OUTPUT: 5,
    _CliErrorCategory.RESOURCE_LIMIT: 6,
}


class _CliError(Exception):
    def __init__(self, category: _CliErrorCategory) -> None:
        super().__init__(category.value)
        self.category = category


class _ClosedArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise _CliError(_CliErrorCategory.CONFIGURATION)


class _RestrictedSourceYamlLoader(yaml.SafeLoader):
    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self._source_node_count = 0
        self._source_node_depth = 0

    def compose_node(self, parent: Node | None, index: int) -> Node:
        if self.check_event(AliasEvent):  # type: ignore[no-untyped-call]
            raise yaml.constructor.ConstructorError(
                None,
                None,
                "yaml_alias_forbidden",
                self.peek_event().start_mark,  # type: ignore[no-untyped-call]
            )
        self._source_node_count += 1
        if self._source_node_count > MAX_SOURCE_NODES:
            raise yaml.constructor.ConstructorError(
                None,
                None,
                "source_node_limit_exceeded",
                self.peek_event().start_mark,  # type: ignore[no-untyped-call]
            )
        self._source_node_depth += 1
        if self._source_node_depth > MAX_SOURCE_DEPTH:
            self._source_node_depth -= 1
            raise yaml.constructor.ConstructorError(
                None,
                None,
                "source_depth_limit_exceeded",
                self.peek_event().start_mark,  # type: ignore[no-untyped-call]
            )
        try:
            node = cast(Node, super().compose_node(parent, index))
        finally:
            self._source_node_depth -= 1
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
    parser = _ClosedArgumentParser(description=__doc__)
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
    try:
        arguments = parser.parse_args(argv)
    except _CliError as error:
        return _emit_cli_failure(error.category)

    try:
        payload = _load_source(arguments.source)
    except _CliError as error:
        return _emit_cli_failure(error.category)
    try:
        namespace_salt = _load_namespace_salt(arguments.namespace_salt_file)
        config = AdapterConfig(
            seed=arguments.seed,
            namespace_salt=namespace_salt,
            max_principals_per_organisation=(arguments.max_principals_per_organisation),
        )
    except _CliError as error:
        return _emit_cli_failure(error.category)
    except (TypeError, ValueError, ValidationError):
        return _emit_cli_failure(_CliErrorCategory.CONFIGURATION)

    try:
        report = run_adapter(
            payload=payload,
            vintage=cast(str, arguments.vintage),
            output_dir=cast(Path, arguments.output),
            config=config,
        )
    except AdapterPathError:
        return _emit_cli_failure(_CliErrorCategory.PATH_SAFETY)
    except FileExistsError:
        return _emit_cli_failure(_CliErrorCategory.OUTPUT)
    except OSError:
        return _emit_cli_failure(_CliErrorCategory.OUTPUT)
    except (MemoryError, RecursionError):
        return _emit_cli_failure(_CliErrorCategory.RESOURCE_LIMIT)
    return 1 if report.status.value == "failed" else 0


def _emit_cli_failure(category: _CliErrorCategory) -> int:
    print(f"eads-shaped-adapter: {category.value}", file=sys.stderr)
    return _CLI_EXIT_CODES[category]


def _load_source(path: Path) -> Mapping[str, object]:
    source_bytes = _read_bounded_regular_file(
        path,
        max_bytes=MAX_SOURCE_BYTES,
        failure_category=_CliErrorCategory.SOURCE,
    )
    try:
        text = source_bytes.decode("utf-8")
        suffix = path.suffix.casefold()
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
    except (UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as error:
        raise _CliError(_CliErrorCategory.SOURCE) from error
    except (MemoryError, RecursionError) as error:
        raise _CliError(_CliErrorCategory.RESOURCE_LIMIT) from error
    if not isinstance(loaded, Mapping):
        raise _CliError(_CliErrorCategory.SOURCE)
    return cast(Mapping[str, object], loaded)


def _read_bounded_regular_file(
    path: Path,
    *,
    max_bytes: int,
    failure_category: _CliErrorCategory,
) -> bytes:
    if (
        not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_NONBLOCK")
        or not hasattr(os, "O_DIRECTORY")
        or os.open not in os.supports_dir_fd
    ):
        raise _CliError(_CliErrorCategory.PATH_SAFETY)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise _CliError(_CliErrorCategory.PATH_SAFETY)
        flags = (
            os.O_RDONLY
            | os.O_NOFOLLOW
            | os.O_NONBLOCK
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        descriptor = _open_without_symlink_components(
            path,
            flags=flags,
            failure_category=failure_category,
        )
        with os.fdopen(descriptor, "rb") as source:
            opened = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != before.st_dev
                or opened.st_ino != before.st_ino
            ):
                raise _CliError(_CliErrorCategory.PATH_SAFETY)
            payload = source.read(max_bytes + 1)
    except _CliError:
        raise
    except OSError as error:
        raise _CliError(failure_category) from error
    if len(payload) > max_bytes:
        raise _CliError(_CliErrorCategory.RESOURCE_LIMIT)
    return payload


def _open_without_symlink_components(
    path: Path,
    *,
    flags: int,
    failure_category: _CliErrorCategory,
) -> int:
    directory_flags = (
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    )
    anchored_path = Path.cwd() / path
    components = anchored_path.parts[1:]
    descriptor = os.open(anchored_path.anchor, directory_flags)
    try:
        for index, component in enumerate(components):
            component_flags = flags if index == len(components) - 1 else directory_flags
            next_descriptor = os.open(
                component,
                component_flags,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
    except OSError as error:
        os.close(descriptor)
        category = (
            _CliErrorCategory.PATH_SAFETY
            if error.errno in {errno.ELOOP, errno.ENOTDIR}
            else failure_category
        )
        raise _CliError(category) from error
    return descriptor


def _load_namespace_salt(path: Path) -> str:
    payload = _read_bounded_regular_file(
        path,
        max_bytes=66,
        failure_category=_CliErrorCategory.CONFIGURATION,
    )
    if payload.endswith(b"\n"):
        payload = payload[:-1]
    if len(payload) != 64:
        raise _CliError(_CliErrorCategory.CONFIGURATION)
    try:
        salt = payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise _CliError(_CliErrorCategory.CONFIGURATION) from error
    if any(character not in "0123456789abcdef" for character in salt):
        raise _CliError(_CliErrorCategory.CONFIGURATION)
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


if __name__ == "__main__":
    raise SystemExit(main())
