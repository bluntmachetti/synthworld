"""Exercise the generated-agentic consumer path through an installed wheel only."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("synthworld")
    if executable is None:
        raise RuntimeError("installed wheel did not provide the synthworld command")
    return subprocess.run(  # noqa: S603 - fixed local console script, no shell
        (executable, *arguments),
        check=True,
        capture_output=True,
        text=True,
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary = Path(temporary_directory)
        complete_root = temporary / "complete"
        _run(
            "generate-enterprise-agentic",
            "--profile",
            "generated",
            "--tier",
            "smoke",
            "--seed",
            "17",
            "--output",
            str(complete_root),
        )

        public_only_root = temporary / "public-only"
        shutil.copytree(complete_root / "public", public_only_root / "public")
        if (public_only_root / "evaluator").exists():
            raise RuntimeError(
                "public-only adapter root unexpectedly has evaluator data"
            )
        public_document = json.loads(
            (public_only_root / "public" / "public-input.json").read_text(
                encoding="utf-8"
            )
        )
        action_event_ids = public_document["benchmark"]["scenario"]["action_event_ids"]
        trace = temporary / "all-deny.jsonl"
        trace.write_text(
            "".join(
                json.dumps(
                    {"event_id": event_id, "decision": "deny"},
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
                for event_id in action_event_ids
            ),
            encoding="utf-8",
        )

        _run(
            "validate",
            "generated-enterprise-agentic-trace",
            "--benchmark-root",
            str(public_only_root),
            "--predictions",
            str(trace),
        )
        evaluation = _run(
            "evaluate",
            "generated-enterprise-agentic",
            "--benchmark-root",
            str(complete_root),
            "--predictions",
            str(trace),
        )
        report = json.loads(evaluation.stdout)
        if report["checksum_scheme"] != "sha256-generated-enterprise-agentic-v1":
            raise RuntimeError("generated evaluator reported the wrong checksum scheme")
        if not any(
            metric["name"] == "authorization_decision_accuracy"
            for metric in report["metrics"]
        ):
            raise RuntimeError("generated evaluator omitted authorization accuracy")


if __name__ == "__main__":
    main()
