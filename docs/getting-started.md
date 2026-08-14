# Getting Started

> These instructions track current `main`. Use a matching release tag for released
> behavior.

SynthWorld requires Python 3.12 or newer. The distribution is
`idcognito-synthworld`; the import package and command are `synthworld`.

## Install

```bash
pip install idcognito-synthworld
synthworld --help
```

For repository development, use the locked environment:

```bash
uv sync --locked --all-groups
```

## Create a deterministic world

```bash
synthworld generate \
  --seed 20260719 \
  --persona-count 10 \
  --output world.json
```

Repeat the command with the same explicit inputs to reproduce the artifact. Do not
replace the seed with wall-clock time when reproducibility matters.

## Run the foundational walkthrough

From a repository checkout:

```bash
uv run python examples/evaluate_all.py --predictions-dir predictions
```

This demonstrates five foundational public-input adapters. It is not an exhaustive
list of every contract-specific evaluator.

## Choose the next guide

- [Identity worlds](guides/identity-worlds.md)
- [Identity resolution](guides/identity-resolution.md)
- [Privacy exposure](guides/privacy-exposure.md)
- [Agent authority](guides/agent-authority.md)
- [Enterprise access](guides/enterprise-access.md)
- [Enterprise Identity Planning](guides/enterprise-identity-planning.md)
- [Evaluating a system](guides/evaluating-a-system.md)

The legacy [user guide](../USER_GUIDE.md) remains available as a compatibility
surface while detailed guidance moves to these canonical pages.
