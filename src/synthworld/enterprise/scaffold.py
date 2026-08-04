"""Operator-facing deterministic enterprise access authoring templates."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Literal

from synthworld.enterprise.reference import (
    reference_enterprise_csv_bundle,
    reference_enterprise_identity_access_import,
)


class EnterpriseScaffoldError(ValueError):
    """Raised when a scaffold destination or format is unsafe."""


def scaffold_enterprise_access(
    *,
    output_format: Literal["yaml", "json", "csv"],
    output: Path,
    id_namespace_salt: str | None = None,
) -> str:
    """Write one private authoring template and return the salt used."""

    if output.exists():
        raise EnterpriseScaffoldError("scaffold output must not already exist")
    salt = id_namespace_salt or secrets.token_hex(32)
    model = reference_enterprise_identity_access_import(id_namespace_salt=salt)
    if output_format == "yaml":
        import yaml

        payload = yaml.safe_dump(
            model.model_dump(mode="json"), allow_unicode=True, sort_keys=False
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8", newline="\n")
    elif output_format == "json":
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            model.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    else:
        output.mkdir(parents=True)
        for name, payload in reference_enterprise_csv_bundle(
            id_namespace_salt=salt
        ).items():
            (output / name).write_text(payload, encoding="utf-8", newline="\n")
    return salt


__all__ = ["EnterpriseScaffoldError", "scaffold_enterprise_access"]
