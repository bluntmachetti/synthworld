# Contributing

Thank you for helping make privacy-system evaluation more honest and
reproducible. Open an issue before a large change so its intended benchmark or
schema impact can be agreed first. Participation in this project is governed
by the [code of conduct](CODE_OF_CONDUCT.md).

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

## Synthetic-data boundary

Never submit real personal data or plausible identifiers that could belong to a
real person. New generated identities must retain `synthetic: true`, reserved
domains, fictional phone ranges, obvious example addresses, and deliberately
invalid national identifiers. Public observations and evaluator-only truth must
remain physically separated.

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

`tag.gpgSign` covers annotated tags only. Create tags with `-a` (or `-s`): a
lightweight tag names a commit directly and carries no signature of its own,
which is why v0.7.0 and v0.8.0 show nothing.

Verifying a release without trusting the forge:

    ssh-keygen -Y verify -f allowed_signers -I <maintainer-email> \
        -n git -s <signature> < <tag-payload>

or, with the repository cloned and `allowed_signers` configured as above,
`git verify-tag v0.11.0`.
