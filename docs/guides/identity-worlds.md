# Identity worlds

Use the core generator for stable fictional fixtures in tests, demos, and graph
imports:

```bash
synthworld generate --seed 20260719 --persona-count 100 --output world.json
```

Treat the core world as a deterministic smoke surface, not as a population model or
an anonymized real dataset. Seeds change generated values; configuration and schema
version also belong in any reproducibility record.

The detailed household, workplace, ambiguity, and generation-cost walkthroughs
remain in [USER_GUIDE.md](../../USER_GUIDE.md). Field definitions remain canonical
in [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md).
