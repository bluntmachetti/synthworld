# Generate connected synthetic identity data

Use this path for fictional identity fixtures in tests, demonstrations, graph
imports, and privacy or matching workflows. No agent or policy engine is needed.

## Generate a first world

With Python 3.12 or newer:

```bash
pip install idcognito-synthworld==0.17.0
synthworld generate --seed 20260719 --persona-count 10 --output world.json
```

The command reports the number of personas and relationships it created. Inspect
the JSON with your editor, or print its top-level collections:

```python
import json
from pathlib import Path

world = json.loads(Path("world.json").read_text(encoding="utf-8"))
for field, value in world.items():
    print(field, len(value) if isinstance(value, list) else value)
```

These identities are safely fictional and connected, rather than unrelated fake
rows. The core world is a small, simple fixture: it is useful for repeatable tests,
not for claims about the behaviour of real populations.

## Check that your fixture repeats

Generate another file with the same inputs:

```bash
synthworld generate --seed 20260719 --persona-count 10 --output repeated-world.json
```

```python
from pathlib import Path

assert Path("world.json").read_bytes() == Path("repeated-world.json").read_bytes()
print("The two fixtures are byte-identical.")
```

Keep the package version, seed, and configuration with your test. Increase
`--persona-count` for more personas; use the documented richer generated profiles
when graph structure or conflicting evidence is part of your experiment.

## Choose what to test next

- [Identity resolution](https://bluntmachetti.github.io/synthworld/guides/identity-resolution/): matching and conflicting evidence.
- [Privacy and exposure](https://bluntmachetti.github.io/synthworld/guides/privacy-exposure/): extraction, exposure, and broker behaviour.
- [Evaluating a system](https://bluntmachetti.github.io/synthworld/guides/evaluating-a-system/): pass public observations to your
  system and score predictions against separately loaded answers.
- [Data dictionary](../../DATA_DICTIONARY.md): field contracts.
- [Benchmark inventory](../../BENCHMARKS.md): available profiles and measured limits.

The core world itself is not a product-safe projection for every evaluation task.
Use the public-input exporter documented for the benchmark you select. SynthWorld
does not anonymise real data supplied to it.
