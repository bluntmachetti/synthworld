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
uv run synthworld evaluate agentic \
  --predictions predictions/agentic.jsonl \
  --summary
```

See [`AGENTIC_BENCHMARK.md`](../AGENTIC_BENCHMARK.md) for the public package
layout and the independent identity, authority, temporal, attribution,
ownership, provenance, and side-effect metrics.

## Real-system integration: Claude LLM adapter

[`claude_adapter.py`](claude_adapter.py) is a complete public-only adapter for
a real LLM system. It sends only product-safe observations to Claude through
the Anthropic API and writes prediction files that `synthworld evaluate`
scores unchanged:

```bash
synthworld generate-agentic --output asteria-agentic-v1
uv run --with anthropic python examples/claude_adapter.py agentic \
  --public-dir asteria-agentic-v1/public \
  --output predictions/claude-agentic.jsonl
uv run synthworld evaluate agentic \
  --predictions predictions/claude-agentic.jsonl --summary

synthworld generate-public-extraction --seed 20260719 --persona-count 10 \
  --output extraction-public.json
uv run --with anthropic python examples/claude_adapter.py extraction \
  --corpus extraction-public.json \
  --output predictions/claude-extraction.json
uv run synthworld evaluate extraction \
  --predictions predictions/claude-extraction.json \
  --seed 20260719 --persona-count 10 --summary
```

Uncached calls need Anthropic API credentials in the environment;
`uv run --with anthropic` supplies the SDK without adding it to the project
environment.

The `agentic` subcommand puts the entire Asteria public package in a cached
context block, states the documented trace conventions in its instructions,
and asks the model to judge one action event per request; the `extraction`
subcommand asks for verbatim PII values per page and derives exact character
spans locally, so the model never has to count characters.

The public boundary is enforced before any model call: the agentic public
directory must carry its `manifest.json` with `oracle_free: true`; every
listed artifact name must be a normalized relative path that stays beneath
the public directory without crossing symlinks; every listed artifact must
match its recorded SHA-256 and the artifact-set digest; unlisted files are
rejected; and the model context and scenario list are built from the
verified artifact bytes only — passing the benchmark root instead of
`public/` fails loudly instead of leaking evaluator truth. These checks
prove the package is internally consistent, not that it is the canonical
Asteria release; to verify authenticity, compare the
`benchmark_artifact_set_digest` recorded in the run manifest against the
published Asteria public digest.

Runs are reproducible and attributable. Each model response is cached under
`<output>.responses/` in a validated envelope stored under a
SHA-256-derived filename, so benchmark-controlled unit IDs never become
filesystem paths. The envelope records its unit ID, a fingerprint of the
adapter version, requested model, generation configuration (fallback mode,
output budget, beta headers), instructions, response schema, and exact
input bytes, together with the served model, stop reason, fallback
occurrence, response ID, and SDK version. Cached and freshly returned
outputs are validated against the task's response contract, and a cached
envelope whose unit ID, fingerprint, provenance, or output shape does not
match the current run is rejected instead of silently reused. Each run
writes a `run-manifest.json` that binds the evidence it describes: prompt, schema, and input digests,
per-unit fingerprints, an artifact-set digest over the response envelopes,
and the output file's SHA-256. Server-side refusal fallbacks are disabled
by default so a run's results stay attributable to one requested model;
pass `--fallbacks` to opt in, with the served model per response recorded
in the envelopes.

The offline logic — the public manifest boundary, cache invalidation and
envelope validation, replay, offset conversion, manifest evidence binding,
and both completer request paths — is covered by
`tests/test_claude_adapter.py` with fakes. Live model calls need network
access and API credentials, so `make ci` does not make them.

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
