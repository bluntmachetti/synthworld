# Experiments

Experiments must be reproducible from committed code, explicit inputs, versioned
contracts, and retained reports. Record seed/config, benchmark identity, package and
formula versions, checksums, environment, and every metric denominator.

This repository does not host benchmark execution or a public leaderboard. A design
trace, reference baseline, or local lab result must be labelled at its actual evidence
level. Remote API data is not required to render these pages.

## Recorded experiments

- [Enterprise authorization with Topaz](enterprise-authorization.md) records the
  Phase 1 directory prototype, the frozen Phase 2 authorization run, and the
  immutable Phase 3 isolated reference experiment with its limitations and
  reproducible release assets.
- [Enterprise authorization with OPA and an AuthZEN-style adapter](opa-authzen-enterprise-authorization.md)
  records a separate two-topology external-consumer experiment, its enforced
  evaluator boundary, discriminating controls, limitations, and immutable assets.
- [From PII spans to identity resolution](pii-detection-identity-resolution.md)
  records a locally frozen external-consumer error-propagation experiment over
  SynthWorld 0.17.0, including corrected interval metrics, isolation evidence, and
  the limits imposed by two detectors, one seed, and locally retained artifacts.

An entry here is an evidence record, not an endorsement of a system under test.
The entry must distinguish a published, independently reproducible experiment
from a locally frozen baseline or a historical exploratory run.

Community authors can list their own work in the
[Experiment results](https://github.com/bluntmachetti/synthworld/discussions/categories/experiment-results)
Discussion category. Listings are mutable self-reports, not evidence hosted or
validated by SynthWorld.
