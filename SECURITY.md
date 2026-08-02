# Security policy

## Reporting

**Report privately.** Use the **Report a vulnerability** button under this
repository's [Security tab](https://github.com/bluntmachetti/synthworld/security).
Private vulnerability reporting is enabled, so the report and the discussion stay
between you and the maintainers until a fix is published.

Do not open a public issue for anything in the scope below, and do not include real
personal data in a report — a description of the pattern is enough, and a synthetic
reproduction is better.

For ordinary non-sensitive defects, a public issue with the smallest synthetic
reproduction possible is the right route.

## Scope

SynthWorld is a synthetic-data library, so its security surface is not the usual
one. There is no server, no authentication and no user data. Three classes matter
instead.

**Real or realistic personal data.** The library accepts only unmistakably
synthetic identities. A generator that can emit a real person's identifier, a
routable email address, a dialable phone number, a valid national identifier, or
anything else mistakable for a real person is a safety defect regardless of how
unlikely the path is.

**Leaked secrets.** Credentials, keys or tokens committed to the repository or
embedded in a generated artifact.

**Oracle leakage.** Evaluator truth reachable from a public artifact — directly, or
by deriving it from published values. This is the class most specific to a
benchmark: a system scored against a leaking artifact reports a number that means
nothing, and every downstream conclusion drawn from it is void. It is a security
issue in the sense that matters here, because the harm is silent and the result
still looks valid. Examples that have occurred: an identifier encoding the persona
ordinal; a task whose inputs could not be obtained without reading the answer key;
match truth carried on the same object as the observable result.

If you are unsure whether something qualifies, report it privately. Being wrong
about scope costs a maintainer one reply; being wrong in the other direction
publishes a defect before it is fixed.

## Out of scope

- Non-deterministic output caused by an unpinned dependency in *your* environment.
  Determinism is guaranteed against the declared reproducibility tuple and the
  published locked environment.
- Findings in a benchmark's *contents* that are deliberate and documented, such as
  the core identity world's ordinal-bearing identifiers, which are recorded as a
  known limitation rather than a defect.
- Resource exhaustion from a configuration you chose, such as generating a world at
  the upper bound of `person_count`.

## Supported versions

Fixes land on `main` and ship in the next release. Earlier releases are not
patched; the project is pre-1.0 and the expectation is that consumers track the
current release.

## Response

This is a small project. You should expect an acknowledgement within a few days
rather than within hours. If a report is confirmed, the fix, the release and the
advisory are published together, and you will be credited unless you ask not to be.
