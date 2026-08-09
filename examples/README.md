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
from public observations only, then scores all five supported tasks: PII
extraction, entity resolution, relationship inference, risk calibration, and
Asteria agent identity/delegated authority. No prediction rule reads an answer
key.

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

## EADS adapter: humans-only Phase 1

[`eads_adapter/README.md`](eads_adapter/README.md) defines the documentation
contract for a deterministic Phase 1 EADS-to-enterprise adapter. It maps each
source organisation independently to one tenant and one organisation, treats
the tenant as the isolation boundary, and retains region and regulatory concepts
as gap metadata rather than inventing enterprise unit semantics.

The caller explicitly selects the strict `sdk-size-v1` or
`topology-headcount-v1` reference profile. These profiles were inferred from
planning inputs and synthetic fixtures; compatibility with the 31 real exports
requires a representative sanitized export or pinned schema. Source `size` and
`headcount` are validated but never drive generated population. Source-export
`scale`, `team_type`, and `industry` fields are interpreted by the exact
published [`eads-human-population-policy-v1`](eads_adapter/README.md#population-policy-eads-human-population-policy-v1),
not supplied as independent SynthWorld inputs. It specifies the scale bases,
rational factors, aliases, unknown-value gaps, half-up rounding, and
`largest-remainder-proportional-v1` downscaling. Phase 1 is humans-only, defers
BIAN and other non-human identities, preserves frozen Asteria v1, and forbids
real vendor or product labels in compiled and public output.

The documented command interface is:

```bash
uv run python -m examples.eads_adapter \
  --source PATH \
  --vintage sdk-size-v1 \
  --output OUTPUT_DIR \
  --seed 42 \
  --namespace-salt-file PRIVATE_SALT_FILE \
  --max-principals-per-organisation 10000
```

The salt file contains a private 256-bit salt as 64 lowercase hexadecimal
characters and must never be published; opaque references use keyed HMAC under
it. The principal cap defaults to `10000`, is limited to `1000000`, and triggers
the published downscaling policy. The output root may be absent or existing and
empty; non-empty roots and non-directories are rejected, and staging is
atomically promoted. A partial failure exits nonzero but retains manifest-bound
artifacts for successful organisations beside the failure report; all-excluded
emits no artifacts and exits nonzero. Private imports and reports remain
separate from public and evaluator trees. The reader reads at most 50 MiB plus
one detection byte from a no-follow regular-file descriptor, applies a depth-
and node-bounded JSON-compatible restricted parser, and sanitizes recursion or
memory errors. The example does not bundle, test, or claim validation of raw
EADS exports. See the
[sanitized aggregate gap requirements](../enterprise-identity-access-contract/EADS_ADAPTER_GAPS.md)
for the publication boundary and later issue #27 needs.

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
