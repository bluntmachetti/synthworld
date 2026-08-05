# Evaluation key custody: operator approval checklist

Status: **template only — no operator approval is implied by this repository.**

This checklist governs competitive or comparative held-out runs. It supplements
the threat model in `DATA_DICTIONARY.md`; deterministic public fixtures and CI
examples intentionally use non-secret inputs and make no secrecy claim.

`ContinuousAssuranceConfigV1` has no secret-key field. Its `held_out` tier only
changes the deterministic generation profile, so it must never be described as
keyed concealment. If an external evaluation harness adds keyed case selection,
that key remains outside SynthWorld and is governed by this checklist.

## Before generation

- [ ] Name the evaluation campaign, accountable owner, custodians, and approved
  operators.
- [ ] Record which inputs are confidential: held-out seed/configuration,
  purpose-separated generator key, namespace salt, encryption key, and receipt
  signing key. Never reuse one value for two purposes.
- [ ] Generate every operational key with at least 256 bits from an approved
  cryptographic random source. Do not derive it from a seed, campaign name, or
  human phrase.
- [ ] Store secrets outside the repository in the approved secret manager with
  least-privilege access, access logging, backup/recovery policy, and an expiry.
- [ ] Approve the generator version, schema versions, source artifact digests,
  tier/configuration, scorer version, and retention period before the run.

## CI and execution

- [ ] Inject secrets as masked, ephemeral material through the approved runner;
  do not place them in command-line arguments, source, workflow YAML, cache,
  container layers, or durable workspace files.
- [ ] Prevent shell tracing, exception dumps, telemetry, and debug logs from
  recording secret values.
- [ ] Keep product-visible input physically separate from evaluator truth and
  limit evaluator access to the scoring stage.
- [ ] Bind receipts to the approved public/evaluator artifacts, tool versions,
  and execution evidence. Use an independently generated opaque evidence handle;
  never use a key, key digest, fingerprint, or recoverable key correlator as an
  artifact identifier.
- [ ] Verify protected side effects independently when making runtime-enforcement
  claims. A vendor decision or API response alone is not enforcement evidence.

## Closeout and incidents

- [ ] Revoke runner access and remove ephemeral material immediately after the
  campaign; verify cleanup rather than assuming job teardown did it.
- [ ] Retain only approved artifacts and receipt evidence. Confirm that no secret
  bytes or derived recoverable correlators appear in artifacts, logs, reports,
  caches, tickets, or chat transcripts.
- [ ] Rotate keys between campaigns. Treat rotation as a new comparison boundary
  and record that boundary in result reporting.
- [ ] If exposure is suspected, stop scoring, preserve incident evidence, revoke
  affected credentials, invalidate the campaign, and follow the operator's
  incident process. Key exposure voids the evaluation.

## Approval record

| Role | Name | Decision | Date | Evidence reference |
|---|---|---|---|---|
| Evaluation owner |  |  |  |  |
| Security/custody approver |  |  |  |  |
| Benchmark reviewer |  |  |  |  |
| Runtime evidence reviewer (if applicable) |  |  |  |  |

An unchecked or unsigned copy means the custody gate is open. SynthWorld cannot
close this operational gate through deterministic code or committed examples.
