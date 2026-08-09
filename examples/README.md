# Examples

Everything here is generated, deterministic, and unmistakably synthetic — the
safeguards described in the top-level README apply to every artifact below.

## Worked evaluation: exact-span extraction

[`evaluate_extraction.py`](evaluate_extraction.py) generates the extraction
benchmark for a seed, feeds a deliberately naive regex email extractor only the
product-safe public pages, then loads the physically separate answer key and
scores the predictions against its exact character spans:

```bash
uv run python examples/evaluate_extraction.py --seed 20260719 --persona-count 10
```

It prints corpus-level precision, recall, and F1. Swap the naive extractor for
a real PII-extraction system to reuse the same scoring loop. `make examples`
runs this script and is part of `make ci`, so the example cannot rot.

## Worked evaluation: public-only baseline walkthrough

[`evaluate_all.py`](evaluate_all.py) creates deliberately simple predictions
from public observations only, then scores five foundational tasks: PII
extraction, entity resolution, relationship inference, risk calibration, and
Asteria agent identity/delegated authority. No prediction rule reads an answer
key. Other contract-specific evaluators are documented separately and are not
claimed by this walkthrough.

```bash
uv run python examples/evaluate_all.py --seed 20260719 --persona-count 10
```

Add `--predictions-dir predictions` to write one valid prediction file per
task. The Asteria output is `predictions/agentic.jsonl`; the other four are
JSON. You can pass those files to `synthworld evaluate`, or replace each naive
rule with an adapter for your own system.

The Asteria example deliberately calls `current_state_agentic_trace` with only
the public bundle. That baseline makes the realistic mistake of applying final
audit state to historical actions, so it is useful for learning the trace
contract but is not an oracle ceiling:

```bash
uv run synthworld validate agentic-trace --predictions predictions/agentic.jsonl
uv run synthworld evaluate agentic \
  --predictions predictions/agentic.jsonl \
  --summary
```

See [`AGENTIC_BENCHMARK.md`](../AGENTIC_BENCHMARK.md) for the public package
layout and the independent identity, authority, temporal, attribution,
ownership, provenance, and side-effect metrics.

## Sample output

Full, frozen sample outputs ship inside the package as the golden benchmarks
under [`src/synthworld/benchmarks/`](../src/synthworld/benchmarks/), each
authenticated by a SHA256 manifest. An abridged persona from `golden-v1.json`
(seed `20260719`):

```json
{
  "id": "persona-0001",
  "synthetic": true,
  "given_name": "Joel",
  "family_name": "Fisher",
  "emails": [
    {
      "synthetic": true,
      "value": "synth_joel_fisher_0001@example.test",
      "kind": "primary"
    }
  ],
  "phones": [
    {
      "synthetic": true,
      "value": "+1-200-555-0100"
    }
  ],
  "national_ids": [
    {
      "synthetic": true,
      "value": "SYN-202607199",
      "checksum_valid": false
    }
  ]
}
```

And one planted relationship with its supporting evidence:

```json
{
  "synthetic": true,
  "id": "relationship-0001",
  "source_person_id": "persona-0001",
  "target_person_id": "persona-0002",
  "kind": "family",
  "evidence": [
    {
      "synthetic": true,
      "signal": "shared_surname",
      "value": "Fisher"
    },
    {
      "synthetic": true,
      "signal": "shared_address",
      "value": "100|1 Example Avenue|Testville|00000"
    }
  ]
}
```

Every record carries `synthetic: true`, emails use the reserved
`example.test` domain, phones sit in the fictional `555-01xx` block, and
national identifiers carry a `SYN-` prefix with deliberately invalid
checksums. See [DATA_DICTIONARY.md](../DATA_DICTIONARY.md) for the full field
reference and the public/oracle boundary.
