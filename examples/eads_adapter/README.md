# Fictional EADS-shaped fixture adapter

This directory contains a repository-only adapter for fictional, EADS-shaped
fixtures. It demonstrates a bounded transformation between SynthWorld fixture
artifacts and a deliberately small fictional enterprise identity shape. It is
not compatible with, endorsed by, or tested against any real EADS product,
service, API, schema, deployment, or organisation.

The adapter is an example boundary, not a product integration. It provides no
registry, identity lifecycle, target-system authorisation, entitlement
enforcement, provisioning, credential handling, network transport, or external
side effects.

## Supported scope

The supported input contract is intentionally bounded:

- one canonical SynthWorld organisation profile;
- human principals only;
- the profile's declared regions, domains, teams, services, and ownerships;
- explicit seed and configuration values supplied to the adapter; and
- repository fixture files that are canonical UTF-8 JSON or restricted YAML
  regular files.

Agent and non-human identity projections remain deferred until the C15/C16
contracts are implemented. The design currently under review is documented in
[C15/C16 contract-family design under review](../../agent-authority-contract/docs/c15-c16-contract-design.md).
This adapter must not anticipate that design by inventing agent or NHI fields.

Input trees and files are opened without following symbolic links. Supported
platforms must provide no-follow regular-file checks; a platform that cannot
enforce those checks is outside the supported adapter boundary. Directories,
symbolic links, non-regular files, noncanonical bytes, undeclared extras, and
files outside the bounded input contract are rejected rather than repaired or
silently ignored.

## Output root and promotion

The requested output root must be absent. The adapter does not merge into,
replace, or clean an existing path. This absent-only rule prevents a caller
from presenting a self-consistent replacement tree or retaining stale files
under an otherwise valid output root.

A successful local build produces a staged repository artifact. Moving that
artifact into a wider visibility or custody class is a separate output-
promotion decision. The adapter itself does not promote outputs, assign
custodians, upload artifacts, or change access controls.

## Determinism and inventories

The output is bound to explicit seed and configuration inputs. Provenance
records the adapter contract version, source vintage, digest of the canonical
parsed source payload, seed, configuration digest, and ordered output
inventories needed to reproduce the transformation.

Digest inventories are typed rather than represented as unlabelled hashes:
each artifact row identifies its role, visibility, canonical relative path,
byte length, and SHA-256 digest. The report separately binds the canonical
source snapshot and adapter configuration through SHA-256 digests. Artifact
rows bind every generated output except the private report itself, whose
exclusion is explicit in the report. Private provenance remains a custody-
controlled record and is not copied into a wider-visibility artifact by
implication.

## Fictionalisation boundary

[`fixtures/fictionalisation-boundary.json`](fixtures/fictionalisation-boundary.json)
contains obvious canary names. They are intentionally fictional and exist to
detect accidental substitution of real vendor, customer, tenant, service, or
organisation names. They must not be interpreted as interoperability claims.

## Explicit non-goals

This example does not define:

- a registry of identities, organisations, adapters, or target systems;
- joiner, mover, leaver, credential, or account lifecycle behaviour;
- target authorisation, policy evaluation, or enforcement;
- real-EADS compatibility or conformance;
- agent or non-human identity support; or
- automatic output promotion between visibility or custody classes.
