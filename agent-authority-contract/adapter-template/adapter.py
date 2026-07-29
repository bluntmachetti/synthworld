"""Starting point for an adapter that scores your system against Asteria Agentic v1.

Copy this file, replace one function, and you have a working integration.

It reads only the public package - the action events your system is asked to account
for - and writes observed-action JSONL. It never touches the evaluator tree, so you
cannot accidentally score against truth you were not meant to see. Run it as shipped
and it produces a valid trace that scores poorly; that is deliberate, so the loop
closes before you have written anything.

    python adapter.py --public-dir asteria-agentic-v1/public --output trace.jsonl
    synthworld validate agentic-trace --predictions trace.jsonl
    synthworld evaluate agentic --predictions trace.jsonl --summary

The only function you need to change is ``observe_action``. Everything else is
plumbing: reading the events, and writing rows in the order the scorer expects.

Two rules worth internalising before you start.

**Null means "my system did not capture this".** It is scored as a miss and never
back-filled, so it is the honest answer for anything you genuinely cannot observe.
Guessing a plausible value scores the same as being wrong, and it makes your report
claim a capability you do not have. Leave it null.

**Do not echo the claims.** Every action event carries what the *agent asserted* -
``originating_principal_claim``, ``runtime_principal_claim`` and so on. Copying those
into your trace will score well on the frozen fixture, because most of its claims are
truthful, and will tell you nothing about your system. The question the benchmark asks
is what *your* system independently determined. One labelled case in the fixture
exists precisely to catch claim-echoing.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Observation:
    """What your system determined about one attempted action.

    Every field defaults to None, which asserts "not captured". Fill in only what
    your system actually established.
    """

    #: The principal on whose behalf the action was initiated.
    originating_principal_id: str | None = None
    #: The stable agent identity holding the authority.
    logical_agent_id: str | None = None
    #: The concrete runtime instance that executed it.
    runtime_principal_id: str | None = None
    #: Subject of the credential presented.
    credential_subject_id: str | None = None
    #: The actor the action is attributed to.
    attributed_actor_id: str | None = None
    #: Owner chain reaching an accountable human or organisational principal.
    accountable_owner_chain: tuple[str, ...] | None = None
    #: "allow" or "deny", as decided at the time of the action.
    decision: str | None = None
    #: "allow" or "deny" when the action is re-examined at audit time. If your system
    #: can only re-evaluate current state, say so by reporting that answer here - the
    #: benchmark is specifically looking for whether the two can differ.
    decision_at_audit: str | None = None
    #: Delegation identifiers, root first.
    delegation_chain_ids: tuple[str, ...] | None = None
    #: Evidence references retained for later reconstruction.
    evidence_refs: tuple[str, ...] | None = None
    #: Whether the decision could still be reconstructed from retained evidence.
    reconstructable_from_retained_evidence: bool | None = None
    #: Policy version in force for the decision.
    policy_version: str | None = None
    #: Effect recorded for the action; "none" when denied.
    side_effect: str | None = None
    #: Resource, action and scope as your system saw them.
    resource_id: str | None = None
    action: str | None = None
    requested_scope: tuple[str, ...] | None = None
    #: When your system decided, timezone-aware UTC, ISO 8601.
    timestamp: str | None = None
    extra: dict[str, Any] = field(default_factory=dict, repr=False)


def observe_action(event: dict[str, Any]) -> Observation:
    """Replace this with a call into your own gateway, policy engine, or audit log.

    ``event`` is one ``action_attempted`` entry from ``public_events.jsonl``. Use its
    identifiers to look the action up in your system, then report what your system
    determined - not what the event claims.

    The shipped implementation reports only the request shape, which your system
    necessarily knows because it handled the request, and leaves every authority
    question null. It therefore produces a valid trace that scores near zero: a
    correct starting point rather than a pretend integration.
    """

    attempt = event["payload"]["attempt"]
    return Observation(
        resource_id=attempt.get("resource_id"),
        action=attempt.get("action"),
        requested_scope=tuple(attempt.get("requested_scope") or ()) or None,
        # Everything below is intentionally left unset. Fill these in from your system:
        #   decision / decision_at_audit  - what did you authorise, and would you
        #                                   still reach that verdict at audit time?
        #   *_id fields                   - who did you independently determine acted?
        #   delegation_chain_ids          - which grants did you rely on?
        #   evidence_refs                 - what did you retain to prove it later?
    )


def action_events(public_dir: Path) -> list[dict[str, Any]]:
    """Return the action events, in the order the scorer expects them."""

    events_path = public_dir / "public_events.jsonl"
    events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [
        event
        for event in events
        if event.get("payload", {}).get("event_type") == "action_attempted"
    ]


def to_row(event_id: str, observation: Observation) -> dict[str, Any]:
    """Project an Observation onto one observed-action trace row.

    Unset fields are emitted as explicit nulls rather than omitted, so the trace
    states what was not captured instead of leaving it to inference.
    """

    row: dict[str, Any] = {"schema_version": "1.0.0", "event_id": event_id}
    for name in (
        "timestamp",
        "originating_principal_id",
        "logical_agent_id",
        "runtime_principal_id",
        "credential_subject_id",
        "attributed_actor_id",
        "resource_id",
        "action",
        "requested_scope",
        "decision",
        "decision_at_audit",
        "side_effect",
        "policy_version",
        "delegation_chain_ids",
        "accountable_owner_chain",
        "evidence_refs",
        "reconstructable_from_retained_evidence",
    ):
        value = getattr(observation, name)
        row[name] = list(value) if isinstance(value, tuple) else value
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--public-dir",
        type=Path,
        required=True,
        help="the public/ directory of an exported Asteria world",
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="where to write the JSONL trace"
    )
    args = parser.parse_args()

    events = action_events(args.public_dir)
    lines = [
        json.dumps(to_row(event["id"], observe_action(event)), separators=(",", ":"))
        for event in events
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(lines)} rows to {args.output}")
    print("next: synthworld validate agentic-trace --predictions", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
