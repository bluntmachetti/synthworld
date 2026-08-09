# EADS adapter: Phase 1 humans-only profile

This example documents the bounded Phase 1 conversion from a declared EADS
organisation export into a SynthWorld enterprise identity/access import. It is
an offline, deterministic adapter example, not an EADS implementation, topology
simulator, directory connector, or production identity migration tool.

Phase 1 imports humans and the identity/access structure needed to compile them.
Agent, workload, service, and other non-human identities are deferred. BIAN
semantics are also deferred; a source label or hierarchy that resembles a BIAN
concept does not acquire BIAN meaning in this profile.

## Isolation and structural mapping

Each EADS organisation is converted independently into exactly one
`TenantTemplateV1` and one `OrganisationTemplateV1`. The tenant is the security
isolation boundary. The one-to-one Phase 1 mapping deliberately does not make
same-tenant, cross-organisation behaviour observable.

Within that boundary, the adapter may map declared domain structure into the
bounded division, department, and team unit vocabulary; map human team classes
through the published population mix policy; and map supported ownerships and
services into enterprise roles, grants, resource sets, and opaque authorization
targets. Enterprise v1 receives no source classification: null and present
classifications become distinct unexpressed gap records. Unsupported ownerships
are recorded and skipped. Supported `owner` and `approver` rows are intentionally
widened through `AllSelector` to the entire mapped employee team population; that
fidelity loss is recorded, as is an owning team that differs from
`owning_team_id`.

EADS regions, regulatory frameworks, and geopolitical groupings are retained as
gap-report metadata. They are not tenants and are not forced into the enterprise
unit hierarchy.

## Explicit source vintages

The caller must select one strict adapter reference profile:

- `sdk-size-v1` models the planning-input shape with a declared `size` field.
- `topology-headcount-v1` models the legacy planning-input shape with a declared
  `headcount` field.

These profiles were inferred from planning inputs and exercised with synthetic
fixtures. They do not demonstrate compatibility with the 31 real exports. A
representative sanitized export or exact serialized schema must be pinned and
tested before making that claim.

Vintage selection is never inferred from field presence. Mixed and undeclared
shapes are rejected. Neither `size` nor `headcount` determines generated
population counts: those source values are recorded as ignored scale metadata.

### Population policy `eads-human-population-policy-v1`

`scale`, `team_type`, and `industry` are source-export fields interpreted by the
adapter profile, not independent SynthWorld inputs. Scale bases are `micro=4`,
`small=8`, `medium=16`, `large=32`, and `enterprise=64`. Team factors are
`product=3/2`, `operations=5/4`, `control=1`, and `platform=3/2`; aliases are
`controls -> control`, `ops -> operations`, `product-team -> product`, and
`platform-team -> platform`. Unknown team types use factor `1` and emit a gap.
Industry factors are `banking=5/4`, `financial-services=5/4`,
`healthcare=5/4`, `logistics=1`, `public-services=1`, `research=1`, and
`technology=3/2`; unknown industries use factor `1` and emit a gap. Source
`size` and `headcount` are ignored.

Raw count is `max(1, nearest(scale_base * team_factor * industry_factor))`.
Exact half increments round up using
`(numerator + denominator // 2) // denominator`. When the organisation total
exceeds `--max-principals-per-organisation`,
`largest-remainder-proportional-v1` floors one person per team, distributes the
remaining cap proportionally to `raw_count - 1`, then assigns residual people
by largest fractional remainder and canonical team key. It fails if the cap is
smaller than the team count. The cap defaults to `10000`, is limited to
`1000000`, and is the trigger for this declared downscaling.

Identical normalized source content, vintage, policy version, seed, private
namespace salt, and adapter configuration must produce byte-identical output.

The reader reads at most 50 MiB plus one detection byte from a no-follow
regular-file descriptor. Its restricted parser permits only JSON-compatible
finite scalars and string mapping keys, enforces depth and node limits, and
rejects YAML duplicate keys, aliases, merges, custom tags, and non-JSON scalars.
Recursion and memory failures produce sanitized errors.

## Command interface

The Phase 1 command interface is:

```bash
uv run python -m examples.eads_adapter \
  --source PATH \
  --vintage sdk-size-v1 \
  --output OUTPUT_DIR \
  --seed 42 \
  --namespace-salt-file PRIVATE_SALT_FILE \
  --max-principals-per-organisation 10000
```

`--source` names one serialized organisation export. `--vintage` is mandatory
and accepts only a supported explicit profile. `--output` may name an absent or
existing empty directory; non-empty roots and non-directories are rejected. The
complete run is staged and atomically promoted. `--seed` and
`--namespace-salt-file` are explicit generation inputs; neither may be replaced
by wall-clock, host, locale, or filesystem state. The salt file contains exactly
one private 256-bit salt encoded as 64 lowercase hexadecimal characters. Never
publish it. Opaque references are keyed HMAC derivations under that salt, not
unkeyed hashes of source identifiers.

Successful output has this boundary:

```text
OUTPUT_DIR/
  private/imports/<opaque-ref>/enterprise-import.json
  private/reports/eads-adapter-gap-report.json
  artifacts/<opaque-ref>/public/
  artifacts/<opaque-ref>/evaluator/
```

The `public/` and `evaluator/` trees are physically separate reference artifacts
written through the enterprise contract serializer with their manifests. The
private import and report must not be published. On partial multi-organisation
failure, the command exits nonzero but retains correctly manifest-bound
artifacts for successful organisations alongside the failure report. An
all-excluded run emits no artifacts and exits nonzero; every other zero-success
run also exits nonzero rather than producing a successful empty conversion.

The report's `canonical_source_payload_digest` hashes normalized
JSON-compatible content. It is not a digest of exact source bytes or a source
path.

Source exports, namespace salts, raw labels, and per-organisation topology are
private inputs. Raw EADS exports are not bundled, tested, or validated by this
example. The adapter must replace
source organisation, vendor, and product labels with safely fictional labels or
opaque stable identifiers before data enters compiled or public output. No real
vendor or product label may appear in compiled artifacts or the published gap
summary.

## Version and publication boundaries

The adapter targets the existing enterprise v1 authoring and compiler contracts
without modifying their schemas or frozen benchmark artifacts. Asteria v1 is
also frozen: Phase 1 does not alter its models, generator, evaluator, checksums,
or benchmark bytes. Generated enterprise-agentic worlds and non-human identity
support require later, independently versioned work.

The per-run machine gap report stays beside private adapter output. The reviewed
public summary is
[`EADS_ADAPTER_GAPS.md`](../../enterprise-identity-access-contract/EADS_ADAPTER_GAPS.md);
it is sanitized requirements evidence, not a frozen benchmark or a claim that a
particular collection of EADS exports ships with this repository.
