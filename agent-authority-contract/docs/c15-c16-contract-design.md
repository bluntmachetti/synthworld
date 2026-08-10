# C15/C16 agent-authority contract design

Status: design under review, revised 2026-08-10.
Design version: `0.2.0-design`.

This note defines the target shape for `SW-AA-C15` (trusted issuance and
credential-to-grant binding) and `SW-AA-C16` (principal intent and parameter
integrity) as first versions of two control-scoped contract families. It is not an
implemented schema, benchmark, or publication authorization and does not change the
coverage status of either control. Both remain `absent` for Asteria v1.

## Decision summary

- Keep every existing `1.0.0` model, schema, artifact, checksum, loader, and score
  byte-identical. Also keep both frozen C08 `2.0.0` lineages, their manifests,
  loaders, digests, registry records, and benchmark bytes unchanged.
- Introduce independently versioned, control-scoped Asteria and enterprise C15/C16
  contracts. They may share small, proven canonical-value and digest primitives,
  but not one combined cross-domain model.
- Bind each credential to one exact authority source, one subject, one logical
  agent, one runtime, explicit audiences, resources, actions, scopes, purpose, and
  a validity interval.
- Model issuer entitlement and issuance decisions explicitly. Referential integrity
  alone is not issuance authorization.
- Never search for an unrelated grant that can rescue a credential whose bound
  authority is inactive or insufficient.
- Bind an approval to one exact normalized action payload. The payload includes the
  action, target, scope, purpose where applicable, and material parameters.
- Derive a versioned, domain-separated SHA-256 digest in evaluator truth and permit
  it in submissions as an observability field. Do not publish a precomputed digest
  beside each approval and attempt.
- Keep expected decisions, failure reasons, case labels, canonical mismatch paths,
  and evaluator bindings in separately typed evaluator artifacts.
- Score decisions and false-allow/false-deny behavior independently. Reporting a
  public grant reference or digest is observability, not proof of enforcement.
- Gate any future EADS agent/NHI conversion on an accepted and implemented
  enterprise C15/C16 target. Generating credentials against a lineage without C15
  would reproduce the known gap at scale.

## Contract identity and composition

The names below are reserved by this design. They are not aliases for Asteria v1,
enterprise v1, or either frozen C08 v2 lineage.

| Lineage | Python package | Contract family ID | Schema version | Benchmark ID prefix |
|---|---|---|---|---|
| Asteria | `synthworld.agentic.c15_c16_v1` | `asteria-agentic-c15-c16-v1` | `1.0.0` | `asteria-agentic-c15-c16-v1` |
| Enterprise | `synthworld.agentic.enterprise.c15_c16_v1` | `enterprise-agentic-c15-c16-v1` | `1.0.0` | `enterprise-agentic-c15-c16-v1` |

Each lineage reserves three separately typed manifest kinds:

| Surface | Asteria manifest kind | Enterprise manifest kind | Visibility |
|---|---|---|---|
| Public | `asteria-agentic-c15-c16-public-manifest-1.0.0` | `enterprise-agentic-c15-c16-public-manifest-1.0.0` | Public |
| Evaluator | `asteria-agentic-c15-c16-evaluator-manifest-1.0.0` | `enterprise-agentic-c15-c16-evaluator-manifest-1.0.0` | Evaluator only |
| Control | `asteria-agentic-c15-c16-control-manifest-1.0.0` | `enterprise-agentic-c15-c16-control-manifest-1.0.0` | Evaluator-only root binding both trees |

The `v1` suffix means the first version of this separate C15/C16 family. It does
not mean Asteria v1 coverage and it does not reopen the already-owned `2.0.0`
version of either C08 family. Future implementation must use the exact family ID
and schema version together; schema autodetection and a generic
`enterprise-agentic-v2` identity are forbidden.

A field-by-field compiler may consume an explicitly selected source world. Its
input binds `source_contract_family`, `source_schema_version`, and
`source_root_digest`, and its output is a separately typed C15/C16 public or
evaluator artifact. It must not derive a public projection by dumping an
oracle-bearing source object with exclusions. Composition never changes, relabels,
or republishes the source schema.

## Why existing contracts cannot be extended in place

Asteria v1 `Credential` carries issuer, subject, allowed runtimes, and a validity
window. It has no audience, resource, action, scope, purpose, capability, or
delegation binding. `ActionAttempt` carries resource, action, scope, and purpose,
but no transaction parameters or approved-payload reference. `AuthorityTruth`
therefore cannot represent either missing invariant.

The enterprise v1 lineage has the same semantic split: credential, capability,
delegation, and action records can be named independently. Adding metrics without
new public and evaluator fields would only score a restatement of public IDs.

These are contract gaps, not scorer-only gaps. Closing them requires new public
input, evaluator truth, submission, replay, generation, and metric contracts. A v1
credential-to-grant relationship also cannot be inferred safely from observed use:
one credential may appear with multiple candidate delegations. Migration must fail
on ambiguity rather than choose the grant that makes an observed action valid.

## Shared semantic vocabulary

The two concrete lineages should use equivalent semantics while retaining their own
models, clocks, identifiers, and release versions.

### Authority source

`CredentialAuthorityRefC15C16V1` is a discriminated union:

| Kind | Required fields | Meaning |
|---|---|---|
| `delegation` | `delegation_id`, `capability_id` | Authority derived through one exact delegation chain |
| `direct_capability` | `grant_id`, `capability_id` | Direct authority for a principal model that does not invent a delegation |

The capability reference is explicit so chain splicing can be detected. The
referenced capability must be the capability attached to the referenced grant or
delegation. Asteria C15/C16 v1 must promote its embedded capabilities to first-class,
ID-bearing records. Each `CapabilityC15C16V1` owns one
`CredentialAuthorityEnvelopeC15C16V1`; grants and delegations reference that capability
rather than copying its authority fields.

### Credential authority envelope

`CredentialAuthorityEnvelopeC15C16V1` contains immutable, sorted tuples plus one scalar
purpose:

```text
audience_ids
resource_ids
actions
scopes
purpose (required nonblank scalar for Asteria; absent for enterprise C15/C16 v1)
```

Credentials may attenuate their source authority. They may never amplify it:

```text
credential audiences are within issuer entitlement and source authority
credential resources are a subset of source resources
credential actions are a subset of source actions
credential scopes are a subset of source scopes
credential purpose equals source purpose in a purpose-bearing lineage
credential validity is contained by issuer and source validity
```

Audience and resource are separate concepts. `CredentialAudienceC15C16V1` maps one
audience ID to a tenant and its permitted authorization targets/resources.
`ActionAttemptC15C16V1` must carry the audience used for the attempt. At issuance, every
resource/target in a multi-audience credential envelope must be permitted by at
least one named audience, and every named audience must permit at least one envelope
resource/target. At use, the attempted resource/target must be permitted by the
specific presented audience as well as by the credential envelope. This permits a
credential to cover `(audience A, resource 1)` and `(audience B, resource 2)` while
denying the confused pair `(audience A, resource 2)`.

Purpose support is a lineage-level schema choice, not a nullable per-record choice.
Asteria C15/C16 v1 requires the same nonblank scalar purpose on every source capability,
credential envelope, approval payload, and attempt payload. Enterprise C15/C16 v1 omits
purpose from all four until that lineage defines purpose semantics. A purpose
substitution case and denominator therefore exist only in a purpose-bearing lineage.

### Issuer entitlement

`CredentialIssuerEntitlementC15C16V1` is a first-class, versioned record containing:

```text
id
issuer_principal_id
tenant_id
policy_version
permitted_authority_refs
envelope_ceiling
valid_from / valid_until
```

`permitted_authority_refs` contains exact discriminated authority references. The
requested reference must be an exact member; shared ancestry, string prefixes, and
descent from a listed root do not confer issuance authority. An entitlement that
permits several descendants lists each descendant explicitly. `envelope_ceiling`
independently limits audience, resource, action, scope, purpose, and validity.
Effective issuable authority is the intersection of this entitlement, the live
source chain, and the requested credential envelope.

This is preferable to a generic `may_issue_credentials` flag. Issuance authority is
bounded authority, not a boolean property of a principal.

`CredentialIssuancePolicyC15C16V1` is a public, versioned policy record. Semantic events
activate an exact issuance-policy version before requests are evaluated, and every
`CredentialIssuanceRequestC15C16V1` carries the policy version it requests. Issuance uses
the event-ordered active version; it never derives policy from filesystem order or a
latest-version lookup. Grant/delegation policy remains part of the lineage's normal
authority replay and is not an implicit carrier for issuance-policy version.

### Opaque credential record

`IssuedCredentialC15C16V1` contains metadata only:

```text
handle
issuance_request_id
issued_at
issuer_principal_id
subject_principal_id
logical_agent_id
runtime_id
authority_ref
authority_envelope
not_before / expires_at
```

One credential binds one runtime. Equivalent authority needed by multiple runtimes
requires separate handles. All generated opaque IDs use these dedicated UUID5
namespaces:

```text
Asteria C15/C16:     4b6f478e-0b65-5fb9-9ca4-d5929f770e2a
Enterprise C15/C16: 82ecfb87-68dd-5bd1-a0f6-1b4cb91069ef
```

The UUID5 name octets are `encode_parts` over this exact tuple:

```text
contract_family_id
contract_schema_version
generator_version
seed as unsigned base-10 text
world_slot_id
record_kind
semantic_event_ordinal as unsigned base-10 text
record_ordinal as unsigned base-10 text
```

`encode_parts` concatenates, for each UTF-8 part in order, a four-byte unsigned
big-endian byte length and then the bytes. It rejects an empty required part,
invalid UTF-8, and a part longer than the configured byte ceiling. Implementations
must perform UUID5 over those name octets rather than joining strings with a
delimiter.

World slots and ordinals are allocated from seed, config, and the explicit event
schedule before evaluator case kinds, expected decisions, or failure reasons are
attached. Those answer-key values are forbidden UUID inputs. The UUID output is
opaque: no tenant, subject, grant, or case value is concatenated into the exposed
handle. Uniqueness-critical domain values may influence the preallocated world
slot, but are never exposed as handle components. Handles are identifiers, not
secrets. No token string, private key, signature, bearer secret, or reusable
credential material is generated.

### Normalized transaction parameters

`NormalizedTransactionParametersC15C16V1` contains a `normalization_profile_id` and one
closed, typed object value. The value vocabulary is:

```text
null
boolean
signed 64-bit integer
canonical decimal string
NFC string
ordered array
object whose NFC-normalized members are unique and sorted by normalized UTF-8 member name
```

Binary floating point and non-finite numbers are rejected. Raw decimal input must
match `-?(0|[1-9][0-9]*)(\.[0-9]+)?`; exponent form, a leading plus, leading integer
zeroes, and an empty integer part are rejected. Missing, explicit null, empty object,
and empty array remain distinct. Array order is semantic unless a named rule
explicitly declares set semantics. Object decoders must preserve member pairs long
enough to reject duplicate raw names. They then NFC-normalize every member name,
reject any collision between normalized names, and sort by the raw UTF-8 bytes of
the normalized names. String values are NFC-normalized recursively before canonical
serialization. Uniqueness and ordering are never checked against the pre-normalized
spelling.

`MaterialParameterProfileC15C16V1` is public configuration bound into the benchmark
manifest. It declares the material paths, requiredness, value kinds, and a
normalization from this closed vocabulary:

```text
identity
unicode_nfc
canonical_decimal
utc_datetime
sorted_unique_strings
ordered_values
```

Profiles may not contain expressions, scripts, callbacks, or executable
normalizers. Materiality is declared before results exist. A frozen benchmark owns
and digest-binds its profiles; generated worlds receive them as explicit config.

### Exact action payload and approval

Each lineage defines its own `ActionPayloadC15C16V1` projection. The projection contains
one authoritative copy of:

```text
lineage and payload schema version
target or resource
action
requested scopes
purpose, when the lineage uses purpose
normalization profile ID
normalized material parameters
```

Enterprise uses one `access_atom` object as the authoritative representation of
`tenant_id`, `organization_id`, `resource_id`, `action`, and sorted
`scope_ids`. It does not duplicate those values in sibling target, action, or
scope fields, and it does not include request IDs or cell IDs that identify
evaluation plumbing rather than the approved transaction.

`ActionApprovalC15C16V1` contains an ID, approving principal, approved agent, the exact
approved payload, validity, and `max_successful_uses`. The initial C15/C16 v1 release supports exact
payloads only. Ranges, predicates, arbitrary policy expressions, and idempotency
semantics are deferred.

`ActionAttemptC15C16V1` contains `presented_approval_id` and one `attempted_payload` with
no precomputed public digest. It must not retain duplicate top-level action, target,
scope, or purpose fields that can disagree with the payload.

Approval use is consumed only after a final allow. A denied mutation must not let an
attacker exhaust a valid approval. Payload equality and replay limits are separate
gates: an identical payload can still exceed `max_successful_uses`.

## Canonical payload digest

`ActionPayloadDigestC15C16V1` is evaluator-derived and may be reported by a submission. It
has three fields:

```text
algorithm = sha256
digest_profile = synthworld-c15-c16-action-payload-1.0.0
value = 64 lowercase hexadecimal characters
```

The digest profile is independently versioned from either C15/C16 v1 contract and starts at
`1.0.0`. A wrong submitted digest is a reporting failure, not a structurally invalid
public benchmark artifact.

The preimage is a domain-separated prefix plus canonical JSON bytes of an explicit
payload projection:

```text
encode_parts([
  "synthworld",
  "c15-c16-action-payload",
  "synthworld-c15-c16-action-payload-1.0.0",
  contract_family_id,
  contract_schema_version,
  normalization_profile_id,
])
|| canonical_json_bytes_with_lf(payload_digest_projection)
```

This `encode_parts` is the same four-byte big-endian length framing defined for
UUID names. Domain strings are literal ASCII and the remaining parts are NFC UTF-8.
No delimiter-joined or implementation-native tuple encoding is conforming.

The projection excludes the digest, approval ID, event ID, clock value, evidence
references, and wrapper metadata. Asteria includes target/resource, action, scope,
purpose, profile ID, and normalized parameters. Enterprise includes the complete
`access_atom`, profile ID, and normalized parameters. Consequently, equal
parameters cannot authorize a different tenant, organization, target, action, or
scope.

`canonical_json_bytes_with_lf` is a new contract-scoped function, not a behavior
change to any existing serializer. It first constructs the recursively normalized
tree, including normalized-key collision rejection, and only then emits UTF-8,
normalized keys sorted by raw UTF-8 bytes, compact separators, no NaN, and exactly
one trailing LF. Decimal strings have no exponent or leading plus, remove trailing
fractional zeroes and a now-empty decimal point, and normalize every representation
of negative zero to `0`. The accepted input grammar already excludes leading integer
zeroes and an empty integer part.

Existing canonical and digest functions are frozen wherever v1 checksums depend on
them. A C15/C16 canonicalization behavior change requires a new function and profile version; it must not
modify a shared existing helper in place.

The digest profile must publish cross-language vectors covering Unicode values,
precomposed/decomposed member-name collisions, decimals, nesting, empty values,
missing versus null, length framing, the trailing LF, normalized member ordering,
and array ordering. At least one negative vector must prove that two distinct raw
keys that normalize to the same NFC key are rejected before hashing. Do not label
this format RFC 8785 JCS unless it actually implements that standard. Plain SHA-256
does not conceal low-entropy parameters.

## C15 issuance contract

### Public request

`CredentialIssuanceRequestC15C16V1` contains:

```text
request_id and candidate opaque handle
issuer principal and issuer entitlement IDs
requested issuance policy version
subject principal, logical agent, and runtime IDs
exact authority reference
requested authority envelope
requested not-before and expiry
```

A structurally valid request is permitted if and only if all of these predicates
hold:

1. The issuer entitlement exists, is active at issuance, names the issuer, and
   contains the exact requested authority reference.
2. The request and entitlement policy versions both equal the event-ordered active
   `CredentialIssuancePolicyC15C16V1` version.
3. Issuer, subject, runtime, authority source, capability, and audience belong to
   the same tenant.
4. The source grant/delegation and every ancestor are active at issuance.
5. The referenced capability is exactly attached to the referenced authority
   source.
6. Subject and logical agent match the source grantee, and the runtime belongs to
   that subject/agent.
7. Requested audience, resource, action, scope, purpose when applicable, and
   validity are within both issuer entitlement and every capability in the source
   chain. In a purpose-bearing lineage, every source capability and the request have
   the same scalar purpose. Every requested resource/target is permitted by at least
   one requested audience, and every requested audience permits at least one
   requested resource/target.
8. The candidate handle has not already been materialized by an earlier permitted
   request or pre-issued credential record.

Scored issuance requests and action-use credentials are separate fixture sets. A
request whose decision is scored must not be followed by a public issued-record
event that reveals the oracle decision before submission. Evaluator replay still
materializes handles from earlier oracle-permitted requests when deciding a later
candidate-handle replay. Credential-use cases use separately declared, pre-issued
metadata records with valid provenance.

### Use-time replay

Replay resolves only the authority named by the presented credential:

```text
credential = issued_credentials[presented_handle]
source = resolve_exactly(credential.authority_ref)
capability = resolve_exactly(credential.authority_ref.capability_id)
effective authority = source chain intersect credential
```

The oracle must not search all live grants for one that covers the attempted action.
If bound grant A is inactive or insufficient while unrelated grant B would permit the
action, the result remains deny. This is the decisive anti-laundering invariant.

All authority intervals use half-open semantics: `from <= event_time < until`, with
equivalent `not_before` and `expires_at` names where used. Issuer entitlement is
evaluated at issuance only. Its later expiry or revocation
does not retroactively invalidate an already issued credential; explicit credential
revocation or source-chain revocation does. Use additionally requires issuance
before action, credential validity at `not_before <= action_time < expires_at`, no
direct credential revocation, an active source chain, exact subject/agent/runtime
binding, a permitted audience, an attempted target/resource permitted by that
specific audience, and action payload authority within the credential envelope. In
a purpose-bearing lineage, scalar purpose intersects by transitive equality:
disagreement at any source-chain link, credential, approval, or attempt is a denial.
In a purpose-absent lineage no purpose field or purpose metric is synthesized.
Revoking a source or ancestor
invalidates all descendant credentials from the next semantic event onward without
requiring a separate credential-revocation event.

## C16 approval and parameter contract

Before each attempt, replay materializes approvals in semantic event order and then:

1. Resolves the presented approval without fallback.
2. Checks approving principal, approved agent, validity, revocation, and use limit.
3. Computes the approved and attempted payload digests from the public payloads.
4. Compares the complete payload projections, not parameters alone.
5. Denies target, action, scope, purpose, field, value, or approval substitution.
6. Computes canonical mismatch paths for evaluator diagnostics.
7. Evaluates C15 and all other authority gates independently.
8. Consumes one use only if the final decision is allow.

The first C15/C16 v1 release uses exact equality after declared normalization. Constraint/range
approvals need a separate bounded constraint language and are not approximated here.
Normalization equivalence and ignored nonmaterial raw fields belong in conformance
vectors until a product interface accepts raw, pre-normalized input; scoring them
when every product receives the normalized value would not discriminate.

## Structural validity versus scoreable truth

Structural validation and benchmark truth stay separate.

| Condition | Treatment |
|---|---|
| Dangling authority, capability, profile, or audience reference in a world record | Structurally invalid world |
| Duplicate materialized credential handle, approval definition ID, or contradictory lifecycle history | Structurally invalid world |
| Unknown `presented_handle` or `presented_approval_id` in an attempt | Scoreable action denial |
| Candidate handle materialized by an earlier permitted request or pre-issued record | Scoreable issuance denial |
| Evaluator-derived digest does not match its enclosed evaluator payload | Integrity failure |
| Submitted digest does not match the evaluator-derived digest | Scoreable reporting failure |
| Issued-record fixture violates its own issuance provenance | Integrity failure |
| Known issuer lacks entitlement | Scoreable issuance denial |
| Known source is inactive or requested envelope amplifies it | Scoreable issuance denial |
| Attempt uses a valid digest different from its approval | Scoreable action denial |
| Material field is omitted, added, changed, or replaced by null | Scoreable action denial |
| Attempt precedes approval or follows revocation/expiry | Scoreable action denial |
| Exact payload exceeds successful-use limit | Scoreable replay denial |

The implementation must publish closed, ordered failure-reason vocabularies and an
exhaustive precedence rule before freezing a C15/C16 v1 benchmark. Failure reasons do not replace the
independent gate and final-decision metrics.

## Public, evaluator, and submission boundaries

| Surface | Contents |
|---|---|
| Public input | Entitlements, issuance-policy records and activations, audiences, authority records, scored issuance requests, separately pre-issued credential records, revocations, normalization profiles, approvals and attempts without precomputed payload digests, event order, schema/generator/policy versions |
| Evaluator truth | Expected issuance and action decisions, ordered reasons, canonical authority binding, effective-authority digest, approved and attempted payload digests, approval resolution, mismatch paths, use count before attempt, case labels |
| Submission | Issuance decision observations, resolved credential/approval observations, per-gate decisions, final decision, ordered reasons, optional computed digests and diagnostic bindings |

Public projection is constructed field by field and serialized separately from
evaluator truth. This is API hygiene and leakage protection, not a secrecy claim:
reference evaluator artifacts may still be distributed publicly.

A public manifest may bind only public bytes, public-safe generator configuration,
the selected source family/version, and public root digests. Evaluator-truth,
canonical-binding, case-label, mismatch-path, and private compiler-fidelity digests
belong in a separately typed evaluator manifest. A control-plane root that binds
both trees is evaluator-only and must never be reused as the public manifest.

Grant IDs, approval IDs, and digests reported by a submission are observability
fields. Metrics over them must say `reporting accuracy`; they do not prove issuance,
possession, target-side validation, or enforcement. More generally, the core C16
gate metrics establish correct decisions over public approved and attempted payloads.
They cannot prove that a deployed target enforced those decisions. That stronger
claim remains a lab obligation.

## Discriminating generation cases

Every scored negative slice needs multiple independently generated examples and a
positive counterpart. At minimum, generators plant these cases explicitly.

### C15 cases

| Case | Expected result |
|---|---|
| Valid issuance and attenuated use | Issue, then allow within envelope |
| Unauthorized, inactive, or wrong-policy issuer | Refuse issuance |
| Cross-tenant issuer, subject, runtime, source, or audience | Refuse issuance |
| Exact source inactive at issuance | Refuse issuance |
| Resource, action, scope, purpose, audience, or validity amplification | Refuse issuance |
| Issuer-ceiling-only amplification while source authority permits | Refuse issuance |
| Delegation/capability chain splicing | Refuse issuance |
| Subject or runtime mismatch | Refuse issuance |
| Candidate handle already materialized | Refuse issuance |
| Credential laundering through unrelated live grant | Deny use |
| Bound grant revoked while unrelated grant remains live | Deny use |
| Ancestor revocation cascade | Deny use |
| Direct credential revocation | Deny use |
| Wrong audience or narrowed-scope excess | Deny use |
| Audience/resource confusion within the same tenant | Deny use |

### C16 cases

| Case | Expected result |
|---|---|
| Exact active unused approval | Allow, subject to other gates |
| Amount or beneficiary substitution | Deny payload mismatch |
| Nested partial mutation, omission, addition, or null replacement | Deny payload mismatch |
| Action, target, scope, or purpose substitution in a purpose-bearing lineage | Deny payload mismatch |
| Approval substitution | Deny |
| Exact replay after successful use | Deny replay limit |
| Failed mutation followed by exact use | Deny, then allow |

Case labels and expected outcomes stay evaluator-only. Public IDs, event ordinals,
request ordinals, handles, approval IDs, and serialized order must not use case-kind
enumeration order, expected decisions, or failure reasons as inputs. Conformance
tests must rename and reorder evaluator-only case labels while holding seed, config,
public slot schedule, and semantic payloads fixed, and assert byte-identical public
artifacts.

## Independent metrics

No aggregate C15, C16, or security score is introduced.

### C15 metrics

| Metric | Numerator / denominator |
|---|---|
| `credential_issuance_decision_accuracy` | Correct issuance decisions / all issuance requests |
| `credential_issuance_valid_recall` | Permitted requests issued / all permitted requests |
| `credential_source_amplification_rate` | Requests exceeding source authority that were issued / all source-amplification requests |
| `credential_issuer_ceiling_amplification_rate` | Requests within source authority but exceeding issuer ceiling that were issued / all issuer-ceiling-only requests |
| `credential_issuer_entitlement_enforcement_accuracy` | Correct decisions / unauthorized, inactive, wrong-policy, and cross-tenant issuance cases |
| `credential_source_binding_enforcement_accuracy` | Correct decisions / chain-splicing and inactive-source issuance cases |
| `credential_subject_runtime_enforcement_accuracy` | Correct decisions / subject and runtime mismatch issuance cases |
| `credential_bound_use_accuracy` | Correct bound-credential decisions / all credential-use cases |
| `credential_valid_use_recall` | Valid uses allowed / all valid-use cases |
| `credential_laundering_false_allow_rate` | Laundering actions allowed / all laundering actions |
| `credential_audience_enforcement_accuracy` | Correct decisions / wrong-audience and audience/resource-confusion cases |
| `credential_revocation_enforcement_accuracy` | Correct direct/source/ancestor revocation decisions / all revocation-use cases |

False-issue and false-allow rates must be reported beside valid recall so a
deny-everything system cannot appear strong.

### C16 metrics

| Metric | Numerator / denominator |
|---|---|
| `parameter_integrity_gate_accuracy` | Correct parameter-gate decisions / all C16 cases |
| `parameter_mismatch_false_allow_rate` | Mismatch cases finally allowed / all payload-mismatch cases |
| `approval_substitution_false_allow_rate` | Substitution cases allowed / all substitution cases |
| `approval_replay_false_allow_rate` | Exhausted approvals allowed / all replay-limit cases |
| `valid_parameter_false_deny_rate` | Matching active unused approvals denied by the parameter gate / all matching cases |
| `parameter_failure_reason_exact_match` | Exact ordered reason reports / all C16 denial cases |

Optional digest, reference, and mismatch-path metrics are observability metrics. They
must not be presented as enforcement evidence because their expected values are
derivable from public input. The C16 decision metrics likewise demonstrate oracle
agreement over public payloads, not target-side enforcement; their discriminating
value comes from products that otherwise authorize only at action/resource/scope
granularity.

## Determinism, safety, and budgets

- Generation is a pure function of seed, config, schema version, and event schedule.
- Security semantics use explicit event ordinal, never filesystem order or lexical
  ID order. Enterprise C15/C16 v1 needs an ordinal when ticks collide.
- Set-like tuples and mismatch paths use canonical ordering; event streams retain
  semantic order.
- Public world slots and record ordinals are allocated before answer-key assignment.
  No evaluator label, expected verdict, failure reason, or metric slice may influence
  a public ID or serialized position.
- Models remain immutable `SyntheticModel` records with `extra="forbid"` and
  recursive `synthetic: true`.
- Depth, count, member, string-byte, and canonical-payload-byte budgets are checked
  before traversal or hashing.
- Replay indexes immutable IDs once and remains linear in events plus the referenced
  authority members.
- Parameters remain safely fictional and contain no real payment identifiers,
  credential material, or secrets.

Exact defaults and hard ceilings are fixed with implementation benchmarks, not by
this design note. The C15/C16 v1 config must at least bound issuer entitlements, audiences,
issuance requests, materialized credentials, approvals, attempts, delegation depth,
members per authority envelope, payload depth, array length, object members, string
bytes, and canonical payload bytes.

## Version transition and migration cost

`asteria-agentic-c15-c16-v1` and `enterprise-agentic-c15-c16-v1` are
separate control-scoped version transitions. They may share reviewed canonical
primitives, but neither waits for the other to publish and neither changes the
other's schema version. Neither family extends or mutates Asteria v1, enterprise
v1, Asteria C08 v2, or enterprise C08 v2.

D8 is complete as a C08-only transition and is not reopened here. C13 remains a
separate deferred transition; it does not share a schema, benchmark identity,
manifest, freeze, or release authorization with C15/C16.

Each implemented lineage requires:

- New authoritative C15/C16 v1 models, explicit loaders, replay, projection, evaluation,
  generation, and serialization.
- New public, evaluator, submission, and metric schemas generated from those models.
- New CLI routing with explicit version selection and no schema autodetection.
- New benchmark manifests, package-data inventory, checksums, integrity tests,
  discriminating metric tests, documentation, and a `GOLDEN_REVIEW.md` record.
- Digest conformance vectors and public/evaluator leakage tests.
- A reviewed migration manifest for any imported v1 world. Ambiguous credentials
  split explicitly or fail; they never bind from observed action success.

Scores from existing contracts and C15/C16 v1 are not directly comparable because
cases and denominators change. Relabeling any existing artifact into a C15/C16
family or filling missing bindings with empty values is invalid.

## Provisional choices and remaining acceptance gates

Proposed by this design:

- Support both delegated and direct-capability authority through a discriminated
  reference; do not invent fake delegations.
- Use first-class audience and issuer-entitlement records.
- Bind one runtime per credential and allow authority attenuation.
- Use exact-payload approvals, explicit bounded successful uses, and event-ordered
  approval/revocation history.
- Consume approval uses only on final allow.
- Implement dependency-free canonical JSON behavior in a new contract-scoped function under
  an independently versioned digest profile; freeze existing v1 helpers and do not
  claim JCS compatibility.
- Keep mismatch paths evaluator-only and optional in submissions.
- Keep frozen materiality profiles benchmark-owned and generated-world profiles
  explicit and manifest-bound.
- Do not attempt implicit migration from an existing family into a C15/C16 v1 family.

Remaining gates:

- Numeric budget defaults and hard ceilings, established by implementation evidence.
- Cross-language digest, UUID-framing, normalized-key-collision, and
  answer-independent-ordering vectors.
- Conformance vectors binding the complete enterprise access atom into payload
  equality and digest computation.
- Independent acceptance review of the exact package, schema, benchmark, and
  manifest identities above.
- The catalogue's unverified `KLRC` section 10.7 mapping is not normative input and
  must not support a C16 claim. Pin and verify it separately or remove it from the
  catalogue before any publication cites it.

This revision does not resolve Stage 3 acceptance. It records a reviewable contract
and the remaining gates. It does not claim implementation, benchmark coverage,
publication authorization, or permission to run any EADS agent/NHI conversion.
