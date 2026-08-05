# Agent-authority observation v2 migration

## Why v2 exists

Observation v1 contains `revocation_epoch_ns`, but its L06 validator and scorer
compare non-negative `sent_elapsed_ns` values directly with the declared propagation
bound. They do not subtract or otherwise use the epoch. A row whose epoch is
100 ms and whose send value is 11 ms is consequently treated as 11 ms after
revocation even though a run-relative reading would place it 89 ms before revocation.

That ambiguity prevents a live harness from representing a request that began before
revocation with a signed value. V1 is a published contract, so its fields, generated
schema, accepted values, and replay result remain frozen.

## Narrow v2 surface

Only the observation document changes. Existing v1 run plans, stimuli, truth,
reports, and generic receipt v2 artifacts are reused.

| Observation v1 | Observation v2 | V2 meaning |
|---|---|---|
| `revocation_epoch_ns` | `revocation_epoch_monotonic_ns` | Harness monotonic timestamp captured when the revocation request is issued |
| `ack_elapsed_ns` | `ack_offset_ns` | First observed rejection timestamp minus the revocation epoch; `>= 0` or `null` |
| `sent_elapsed_ns` | `sent_offset_ns` | Attempt send timestamp minus the revocation epoch; signed |
| `completed_elapsed_ns` | `completed_offset_ns` | Attempt completion timestamp minus the revocation epoch; signed and no earlier than send |

An attempt is post-bound exactly when `sent_offset_ns > bound_ns`. A negative send
offset is retained as pre-revocation in-flight evidence and is not placed in the
post-bound false-allow denominator. Every declared enforcement point and every
issued-credential or child-delegation handle still requires at least one post-bound
attempt.

Observation-v1 receipts bind scoring formula `1.0.0`; observation-v2 receipts bind
formula `2.0.0`. Receipt validation dispatches from the canonical observation
payload, verifies that its artifact descriptor names the same schema, and then
replays the corresponding formula.

## Migration rule

Do not change only `schema_version` or rename fields in a stored v1 document. Such a
rewrite would guess which clock the old values used.

An operator may construct a v2 observation only from original instrumentation that
retained the monotonic revocation, acknowledgement, send, and completion timestamps
in one clock domain. Compute each offset as `event_timestamp_ns -
revocation_timestamp_ns`, preserve the original evidence handles, validate the v2
document, and issue a new receipt. If those source timestamps are unavailable, retain
the v1 receipt and its v1 interpretation.

The deterministic fake reference fixture intentionally remains v1 and continues to
make no live-control claim. Live reference-deployment and vendor evidence must use
observation v2.
