# Contributing

Thank you for helping make privacy-system evaluation more honest and
reproducible. Open an issue before a large change so its intended benchmark or
schema impact can be agreed first. Participation in this project is governed
by the [code of conduct](CODE_OF_CONDUCT.md).

Ask ordinary usage and design questions in
[GitHub Discussions](https://github.com/bluntmachetti/synthworld/discussions).
Use Issues for reproducible defects or agreed work, and keep sensitive reports on
the private route described below.

## Documentation

Start with [the documentation contribution guide](docs/support/contributing-documentation.md).
Authored pages must remain useful as plain Markdown on GitHub. Link to generated
registries, schemas, data dictionaries, and contract READMEs instead of copying
their facts into a second hand-maintained source. Documentation describes current
`main`; unreleased behavior must be labelled `Unreleased` or `Preview on main`.

## Development

Install [uv](https://docs.astral.sh/uv/), then run:

```bash
uv sync --locked --all-groups
make ci
```

Changes to analytical behavior must begin with a ground-truth assertion. The
full suite must retain 100% branch coverage, zero unexplained skips, deterministic
output for a fixed seed, and unchanged benchmark checksums unless a deliberately
reviewed benchmark version is being introduced. User-visible changes should add
an entry to the Unreleased section of [CHANGELOG.md](CHANGELOG.md).

## Reporting a security or safety issue

Do not open a public issue for it. Use the **Report a vulnerability** button under
the repository's [Security tab](https://github.com/bluntmachetti/synthworld/security);
private reporting is enabled, so the report stays between you and the maintainers
until a fix is published. [SECURITY.md](SECURITY.md) sets out the scope.

Three classes belong there rather than in a public issue: **real or realistic
personal data** a generator can emit, **leaked secrets**, and **oracle leakage** -
evaluator truth reachable from a public artifact, directly or by derivation. That
last one is specific to a benchmark and easy to underrate: a system scored against a
leaking artifact produces a number that means nothing, and the result still looks
valid, so the harm is silent.

If you are unsure, report privately. Being wrong about scope costs one reply; being
wrong the other way publishes a defect before it is fixed.

## Synthetic-data boundary

Never submit real personal data or plausible identifiers that could belong to a
real person. New generated identities must retain `synthetic: true`, reserved
domains, fictional phone ranges, obvious example addresses, and deliberately
invalid national identifiers. Public observations and evaluator-only truth must
remain physically separated.

## Consumer-integration boundary

SynthWorld accepts consumer-neutral public inputs, submission contracts,
evaluators, and reference examples. Product-specific adapters, private product
types, proprietary fixtures, execution commands, raw product output, and private
run receipts do not belong in the public repository or distribution.

Use `.local-assurance/` for one-off consumer integrations that must run from this
checkout. Git and the build configuration exclude that directory, and repository
tests reject it if it is force-added. This is accidental-publication protection,
not encrypted storage: do not place reusable credentials there, do not use
`git add -f`, and archive any required audit evidence in approved private storage.
Public CI must not clone a private product, receive its credentials, or publish its
outputs.

If a local integration exposes a reusable SynthWorld improvement, submit the
consumer-neutral contract, validation, or evaluator change separately and prove it
with a public reference baseline. Do not copy the product-specific adapter into the
public implementation or tests.

By submitting a contribution, you agree that it is licensed under Apache-2.0.

## Releasing

Release tags are signed. A consumer pinning a frozen benchmark has no
cryptographic path from a checksum back to a maintainer otherwise: the checksums
that describe an artifact set live inside the tree they describe, so they attest
to internal consistency and nothing else. A signed tag is the external anchor.

Tags v0.6.0 to v0.10.0 predate this and are unsigned. They are left as published
rather than rewritten, because retagging changes what anyone who already fetched
them holds. Only v0.9.0 carries GitHub's Verified badge, which reflects that its
merge commit was created and signed by GitHub's own web-flow key — not that a
maintainer signed anything.

Signing uses SSH rather than GPG: no keyring to maintain, and the key is the one
already registered with the forge.

    git config gpg.format ssh
    git config user.signingkey ~/.ssh/id_ed25519.pub
    git config tag.gpgSign true
    git config gpg.ssh.allowedSignersFile "$(pwd)/.git/allowed_signers"
    printf '%s %s\n' "$(git config user.email)" \
        "$(cut -d' ' -f1-2 ~/.ssh/id_ed25519.pub)" > .git/allowed_signers

The public key must also be registered on GitHub as a **signing** key. That is a
separate entry from the authentication key, even for the same key text; adding it
for authentication alone leaves tags unverified.

Cutting a release:

    make ci                                  # must exit 0
    git tag -a v0.11.0 -m "SynthWorld 0.11.0"
    git verify-tag v0.11.0                   # expect: Good "git" signature
    git push origin v0.11.0

Pushing the tag is the whole release. `release.yml` verifies the tag matches
`pyproject.toml`, runs `make ci`, builds, publishes to PyPI via trusted publishing, and
then creates the GitHub release — notes taken from this version's `CHANGELOG.md`
section, with the distribution attached. If that section is missing or empty the
release step fails rather than publishing an empty note, so write the changelog entry
before tagging.

v0.11.0 had to have its release object created by hand, because the workflow published
to PyPI and stopped there. A consumer checking GitHub releases saw 0.10.0 as current
while PyPI served 0.11.0.

`tag.gpgSign` covers annotated tags only. Create tags with `-a` (or `-s`): a
lightweight tag names a commit directly and carries no signature of its own,
which is why v0.7.0 and v0.8.0 show nothing.

Verifying a release without trusting the forge:

    ssh-keygen -Y verify -f allowed_signers -I <maintainer-email> \
        -n git -s <signature> < <tag-payload>

or, with the repository cloned and `allowed_signers` configured as above,
`git verify-tag v0.11.0`.
