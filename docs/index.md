# Connected synthetic identities. Repeatable tests.

SynthWorld builds connected fictional identity worlds for testing identity,
privacy, and access systems. Generate useful fixtures, or test whether an agent
still has authority after credentials and delegations change.

## Choose your starting point

- **[Generate synthetic identity data](guides/identity-worlds.md)** — linked fictional
  personas and relationships for identity matching, privacy tools, and connected
  data workflows. Start with a repeatable seed; add evidence and ambiguity when
  you need them.
- **[Test agent authorisation](guides/agent-authorisation-quickstart.md)** — seven
  concrete action cases for delegated access and agent lifecycle decisions.
  Compare teaching policies, omit the ReBAC authority view, and inspect the failure.

Both paths work locally. Synthetic identity generation needs no policy engine,
agent runtime, or authorisation setup. Python 3.12 or newer is required.

## Start with connected identity data

```bash
pip install idcognito-synthworld==0.18.0
synthworld generate --seed 20260719 --persona-count 10 --output world.json
```

The same version, seed, and configuration reproduce the same bytes. These are
fictional fixtures, not anonymised records from real people.

Continue to [identity worlds](guides/identity-worlds.md),
[identity resolution](guides/identity-resolution.md), or
[privacy and exposure](guides/privacy-exposure.md).

## See an authorisation failure before integrating anything

A valid credential does not guarantee an active delegation. The
[agent-authorisation quickstart](guides/agent-authorisation-quickstart.md) shows a
post-revocation request that a credential-only check allows, and how adding the
delegation check changes the outcome. You can inspect the result in your browser
before installing the demo.

The comparison uses local teaching policies. It does not contact your production
system or prove that an execution path enforces its decisions.

## Go further

- [Getting started](getting-started.md): installation and both first-use paths.
- [Agent authority](guides/agent-authority.md): generated lifecycle worlds and trace contracts.
- [Enterprise access](guides/enterprise-access.md): authored organisation models.
- [Enterprise authorisation](guides/enterprise-authorization-python.md): compose and score a policy experiment.
- [Experiments](experiments/index.md): retained results and reproduction instructions.
- [Benchmark catalogue](/benchmarks/catalogue): available families and their publication state.
- [Metrics](reference/metrics.md): what a score measures and how to interpret missing evidence.

## Versions and evidence

Both first-use paths above target SynthWorld 0.18.0. Pin the package version for
repeatable integrations. Other reference pages track current main unless they
state a specific released version; check each capability's availability.

Where a benchmark provides public inputs, those inputs are physically separated
from expected answers. Published reference truth is inspectable; this prevents
accidental answer leakage, not deliberate cheating. Frozen conformance fixtures
are not evidence of real-world generalisation.

[Source](https://github.com/bluntmachetti/synthworld) ·
[PyPI](https://pypi.org/project/idcognito-synthworld/) ·
[Releases](https://github.com/bluntmachetti/synthworld/releases) ·
[Hugging Face](https://huggingface.co/datasets/Bluntmachetti7/synthworld-benchmarks) ·
[Support](support/index.md)
