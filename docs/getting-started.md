# Getting started

Choose the result you need. Generating synthetic identities does not require
learning the agent-authorisation workflow.

## Generate connected synthetic identities

Use Python 3.12 or newer, preferably in a virtual environment:

```bash
python -m venv .venv
# Activate the environment using the command for your operating system.
pip install idcognito-synthworld==0.18.0
synthworld generate --seed 20260719 --persona-count 10 --output world.json
```

On macOS/Linux, activate with `source .venv/bin/activate`. On Windows PowerShell,
use `.venv\Scripts\Activate.ps1` before running `pip`.

You now have ten fictional personas and their connected relationships in
`world.json`. Continue with [identity worlds](guides/identity-worlds.md) to inspect
the data and check reproducibility. For matching or privacy evaluation, use
[identity resolution](guides/identity-resolution.md) or
[privacy and exposure](guides/privacy-exposure.md).

## Test agent authorisation

Start with the [complete demo](guides/agent-authorisation-quickstart.md). It provides
a browser preview and runs generation, teaching policies, and scoring without an
unwritten adapter or a pre-existing trace file. The packaged `synthworld-demo`
command is included in 0.18.0; the guide covers installation and source-checkout
usage.

After the demo, follow [agent authority](guides/agent-authority.md) to understand the
trace contract, then [development pipelines](guides/development-pipelines.md) for
integration. Connecting your real system is separate from running the demo.

## Develop or run repository examples

From a repository checkout:

```bash
uv sync --locked --all-groups
uv run python examples/evaluate_all.py --predictions-dir predictions
```

That walkthrough demonstrates five foundational public-input adapters, including
extraction and identity resolution. It is not an exhaustive evaluator inventory.

Reference pages describe current main unless they state a released version. Pin the
package version used by your integration. The legacy [user guide](../USER_GUIDE.md)
remains a compatibility index for historical links.
