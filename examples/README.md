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
