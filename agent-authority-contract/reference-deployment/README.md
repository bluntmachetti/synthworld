# Disposable live reference deployment

This opt-in Docker Compose lab proves that the agent-authority run protocol can
be executed against real process and network boundaries. It is a reference
harness, not a production authorization system, vendor emulator, topology
model, performance claim, or claim that every control is supported by every
declared deployment pattern.

The runner consumes the public `enterprise-agentic-smoke-1.0.0` world and
adapts it to a plan that is persisted before any service starts. Only then does
it generate a per-run canary and launch the lab. Agent, authority, protected
target, and forbidden-egress networks are distinct Docker `internal` networks;
no host ports are published.

## What it exercises

These are harness-specific experiments. The run plan declares deployment patterns at
run level, so neither this list nor its receipt attributes an individual control result
to one pattern or establishes a control-by-pattern support matrix.

- L01 scans context, log, memory, and trace channels after exercising prompt,
  tool-output, environment, and memory-recall extraction vectors.
- L02 performs different-sender, wrong-audience, and after-expiry replays.
- L03 and L04 probe the direct protected-target and forbidden-egress paths from
  the agent container.
- L05 stops audit, credential, and policy services independently and checks both
  enforcement points while each dependency is unavailable.
- L06 revokes a parent credential and child delegation, polls both enforcement
  points, retains a real pre-revocation in-flight request, and records signed
  observation-v2 offsets from one monotonic epoch.
- L07 runs the exact declared baseline plus two gateway stages with no gaps.
- L08 records one measured gateway target and one unsupported direct target;
  every declared candidate receives a terminal result.

Runtime credentials are generated inside the credential container, stored only
in a named volume, and referenced by opaque handles outside that volume. The
volume is destroyed by `docker compose down --volumes` in the runner's `finally`
path. The canary is mounted only into the agent as a Compose secret. Raw canary
and runtime-token markers are scanned out of the receipt, service logs, and
container inspection output before the run is accepted.

The image is pinned by digest in `compose.yaml`. On SELinux hosts, the runner
temporarily labels the canary file for container access; the temporary directory
is still removed after teardown.

## Run

Docker Engine with Compose v2 must be available, and the pinned image must
already be present locally. The runner deliberately does not pull an unverified
replacement.

```bash
uv run python agent-authority-contract/reference-deployment/run.py \
  --output .local-assurance/reference-live-001 \
  --run-id reference-live-001 \
  --operator-id your-operator-id
```

The output directory must not already exist. When an operator completes the live run,
that local receipt reports ten passing L01-L06 findings, three complete L07 stages,
L08 statuses of `measured` and `unsupported`, evidence claim
`live_lab_conformance`, observation schema `2.0.0`, and scoring formula `2.0.0`.
This describes the expected receipt contract, not evidence that a current run passed.

A failed execution leaves a partial, non-evaluated receipt for diagnosis but
still tears down containers and volumes. Use a new output directory for the next
attempt. Ordinary `make ci` does not run this opt-in Docker workload.
It does run `run.py --check-contract`, which validates the static plan, stimuli,
truth, adapter replay, component references, and L07/L08 denominators without
starting Docker.

## Claim boundary

Measured latency and throughput describe only this local reference run. They do
not transfer to a vendor, production configuration, or hosted service. SGNL and
other vendor pilots use the same external receipt protocol but remain separate
credentialed evaluations. Evaluation-key custody also remains an
operator-approved runbook concern; the disposable runtime canary is not an
evaluation key. Multiple receipts may support a declaration-only pattern report only
when their immutable benchmark, adapter, SUT, and configuration provenance matches;
even then, the report is not per-control exercise or enforcement proof.
