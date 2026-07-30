"""Generate design-intent traces for the three agent-credential pattern classes.

A design-intent trace answers one question: assuming a pattern is implemented
perfectly, what could it make observable? It is **not** a measurement. Nothing here
was produced by running software that implements any pattern, no product was tested,
and none of these files supports a claim that one pattern outperforms another.

What they do support is a coverage argument. Patterns differ in what they can see at
all, and a field a pattern structurally cannot observe is emitted as ``null`` - which
the scorer counts as a miss, honestly. So the shape of the nulls, and the decisions a
pattern's own logic would reach, expose each pattern's ceiling before anyone builds an
integration.

Assumptions per pattern are declared in ``docs/design-intent-assumptions.md``. Change
those assumptions and these files change; that is the point of generating rather than
hand-authoring them.

Usage::

    uv run python agent-authority-contract/tools/generate_design_intent_traces.py

Add ``--check`` to fail without writing when a committed trace is stale.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from synthworld.agentic import generate_asteria_agentic_v1
from synthworld.agentic.evaluation import trace_submission_to_jsonl
from synthworld.agentic.models import (
    ActionAttempt,
    AgenticBenchmark,
    AgenticTraceSubmission,
    CanonicalBinding,
    Decision,
    ObservedActionTrace,
)

# Private, and imported deliberately: restating the closed side-effect vocabulary
# here would let it drift from the oracle silently, whereas a rename breaks this
# generator loudly at the moment someone changes it.
from synthworld.agentic.replay import _side_effect_for

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


@dataclass(frozen=True)
class Visibility:
    """Which observations a perfectly implemented pattern could produce.

    Each flag answers "can this pattern see this at all?", never "did it get it
    right". Where a flag is False the generator emits null, because claiming a value
    the architecture cannot observe would be the dishonest option.
    """

    slug: str
    title: str
    originating_principal: bool
    logical_agent: bool
    runtime_principal: bool
    credential_subject: bool
    attributed_actor: bool
    owner_chain: bool
    delegation_chain: bool
    scope_and_resource: bool
    policy_version: bool
    evidence: bool
    #: True when the pattern evaluates the full delegation state at action time.
    #: False means its decision rests only on the credential being live, which is
    #: the defining limitation of a reusable bearer token.
    authority_aware: bool
    #: True when the pattern can reconstruct the action-time decision later rather
    #: than only re-evaluating current state.
    replays_history: bool


BEARER = Visibility(
    slug="static-bearer",
    title="Static bearer credential (negative control)",
    # A reusable token names its subject and nothing else. The target service sees a
    # valid credential and an API call; it cannot tell which runtime instance
    # presented it, on whose behalf, or under what delegation.
    originating_principal=False,
    logical_agent=False,
    runtime_principal=False,
    credential_subject=True,
    attributed_actor=False,
    owner_chain=False,
    delegation_chain=False,
    scope_and_resource=True,
    policy_version=False,
    evidence=False,
    authority_aware=False,
    replays_history=False,
)

PROXY_INJECTION = Visibility(
    slug="proxy-injection",
    title="Proxy injection: the agent never holds the credential",
    # An enforcement point on the egress path authenticates the workload, holds the
    # credential, and evaluates policy, so it can observe the whole chain and log it.
    # Its structural blind spot is not a null field - it is a missing row, when an
    # agent reaches the target off-path. See the assumptions doc.
    originating_principal=True,
    logical_agent=True,
    runtime_principal=True,
    credential_subject=True,
    attributed_actor=True,
    owner_chain=True,
    delegation_chain=True,
    scope_and_resource=True,
    policy_version=True,
    evidence=True,
    authority_aware=True,
    replays_history=True,
)

SHORT_LIVED_MINTING = Visibility(
    slug="short-lived-minting",
    title="Short-lived scoped credential minted per task",
    # A narrow, sender-constrained, short-lived credential carries subject, audience,
    # scope and lifetime, so credential and temporal questions answer well. What it
    # does not reliably carry is the full delegation chain or an accountable owner
    # distinct from the delegating principal: those are directory facts, not token
    # claims, and a target service validating a token does not learn them.
    originating_principal=True,
    logical_agent=True,
    runtime_principal=True,
    credential_subject=True,
    attributed_actor=False,
    owner_chain=False,
    delegation_chain=False,
    scope_and_resource=True,
    policy_version=True,
    evidence=True,
    authority_aware=True,
    replays_history=True,
)

PATTERNS: tuple[Visibility, ...] = (BEARER, PROXY_INJECTION, SHORT_LIVED_MINTING)


def _bearer_decision(benchmark: AgenticBenchmark, event_id: str) -> Decision:
    """Decide as a reusable-credential deployment would: is the credential live?

    Deliberately ignores delegation state, runtime binding, tenancy and scope
    attenuation, because a bearer token conveys none of them. Computed from public
    artifacts only - no answer-key lookup - so the divergence from truth is derived
    rather than copied.
    """

    attempt = _attempt_for(benchmark, event_id)
    index = _event_index(benchmark, event_id)
    for event in benchmark.public.events:
        if event.event_index >= index:
            break
        payload = event.payload
        if (
            payload.event_type == "credential_issued"
            and payload.credential.id == attempt.presented_credential_id
        ):
            return Decision.ALLOW
    return Decision.DENY


def _attempt_for(benchmark: AgenticBenchmark, event_id: str) -> ActionAttempt:
    for event in benchmark.public.events:
        if event.id == event_id and event.payload.event_type == "action_attempted":
            return event.payload.attempt
    raise KeyError(event_id)


def _event_index(benchmark: AgenticBenchmark, event_id: str) -> int:
    for event in benchmark.public.events:
        if event.id == event_id:
            return event.event_index
    raise KeyError(event_id)


def _visible_evidence(refs: tuple[str, ...], pattern: Visibility) -> tuple[str, ...]:
    """Drop evidence a pattern could not have observed."""

    if pattern.delegation_chain:
        return refs
    return tuple(ref for ref in refs if not ref.startswith("evidence:delegation:"))


def _row(
    benchmark: AgenticBenchmark,
    binding: CanonicalBinding,
    pattern: Visibility,
    decision: Callable[[AgenticBenchmark, str], Decision],
) -> ObservedActionTrace:
    event_id = binding.action_event_id
    truth = next(
        item
        for item in benchmark.evaluator.authority_truth
        if item.action_event_id == event_id
    )
    attempt = _attempt_for(benchmark, event_id)
    verdict = decision(benchmark, event_id)
    allowed = verdict is Decision.ALLOW
    return ObservedActionTrace(
        event_id=event_id,
        originating_principal_id=(
            binding.originating_principal_id if pattern.originating_principal else None
        ),
        logical_agent_id=binding.logical_agent_id if pattern.logical_agent else None,
        runtime_principal_id=(
            binding.runtime_principal_id if pattern.runtime_principal else None
        ),
        credential_subject_id=(
            binding.credential_subject_id if pattern.credential_subject else None
        ),
        attributed_actor_id=(
            binding.attributed_actor_id if pattern.attributed_actor else None
        ),
        accountable_owner_chain=(
            binding.accountable_owner_chain if pattern.owner_chain else None
        ),
        resource_id=attempt.resource_id if pattern.scope_and_resource else None,
        action=attempt.action if pattern.scope_and_resource else None,
        requested_scope=(
            attempt.requested_scope if pattern.scope_and_resource else None
        ),
        decision=verdict,
        # Without action-time replay the only answer available later is "re-evaluate
        # now", which is the current-state substitution the benchmark exists to catch.
        decision_at_audit=(
            truth.decision_at_audit if pattern.replays_history else verdict
        ),
        # Follows the PATTERN's verdict, not the oracle's. A pattern that wrongly
        # allows an action also performs it, so pairing a false allow with the
        # oracle's "none" would both contradict the row and flatter the pattern on
        # expected_side_effect_accuracy.
        side_effect=_side_effect_for(attempt.action) if allowed else "none",
        policy_version=(attempt.policy_version if pattern.policy_version else None),
        delegation_chain_ids=(
            truth.delegation_chain_ids if pattern.delegation_chain else None
        ),
        # A pattern that cannot see the delegation chain cannot cite it as evidence
        # either. Copying the oracle's refs wholesale published the exact chain this
        # pattern is documented as blind to, contradicting its own trace - and it
        # inflated provenance completeness, since the missing refs are precisely what
        # a token-validating service does not learn.
        evidence_refs=_visible_evidence(truth.required_evidence_refs, pattern)
        if pattern.evidence
        else None,
        # None, not False: a pattern that cannot observe retained evidence has not
        # established that reconstruction is impossible, it has established nothing.
        # Asserting False would be a claim, and would accidentally match truth on
        # the one case where evidence really was discarded.
        reconstructable_from_retained_evidence=(
            truth.reconstructable_at_audit if pattern.evidence else None
        ),
    )


def build() -> dict[str, str]:
    """Return one JSONL document per pattern, keyed by file stem."""

    benchmark = generate_asteria_agentic_v1()
    documents: dict[str, str] = {}
    for pattern in PATTERNS:
        decision: Callable[[AgenticBenchmark, str], Decision]
        if pattern.authority_aware:
            # A perfect implementation with full state reaches the same verdict the
            # replay oracle does; the interesting variation is what it can record.
            def decision(bench: AgenticBenchmark, event_id: str) -> Decision:
                return next(
                    item.decision_at_action
                    for item in bench.evaluator.authority_truth
                    if item.action_event_id == event_id
                )
        else:
            decision = _bearer_decision
        rows = tuple(
            _row(benchmark, binding, pattern, decision)
            for binding in benchmark.evaluator.bindings
        )
        documents[f"idealised-{pattern.slug}"] = trace_submission_to_jsonl(
            AgenticTraceSubmission(rows=rows)
        )
    return documents


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if a committed trace differs from what would be generated",
    )
    args = parser.parse_args()

    stale: list[str] = []
    for stem, document in build().items():
        target = EXAMPLES_DIR / f"{stem}.jsonl"
        if args.check:
            current = target.read_text(encoding="utf-8") if target.exists() else ""
            if current != document:
                stale.append(str(target))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(document, encoding="utf-8")
        print(f"wrote {target}")

    if stale:
        for path in stale:
            print(f"STALE: {path}", file=sys.stderr)
        print("re-run without --check to regenerate", file=sys.stderr)
        return 1
    if args.check:
        print("design-intent traces match their generator")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
