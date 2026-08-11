# Fictional EADS-shaped fixture adapter gaps

This record covers the repository-only fictional EADS-shaped fixture adapter
under `examples/eads_adapter/`. The adapter is not real-EADS compatible and
does not claim compatibility with any external product, API, schema, tenant,
deployment, or organisation.

## Current implemented boundary

The adapter is limited to a bounded shared input contract and human identity
fixtures. Its output root is absent-only. Input and output traversal requires
no-follow regular-file support, and canonical bytes and declared inventories
are part of the accepted contract. Determinism is bound through explicit seed,
configuration, provenance, and typed digest inventories.

Generated files remain staged repository artifacts. Any change in artifact
visibility or custody is a separate output-promotion decision outside the
adapter.

## Deferred work

Agent and non-human identity support is deferred behind implemented C15 and C16
contracts. The active dependency is the
[C15/C16 v2 design under review](../agent-authority-contract/docs/c15-c16-v2-design.md),
not the earlier issue #27 assumptions. Until those contracts are implemented,
the adapter remains humans-only and must not introduce provisional agent or NHI
records, identifiers, authority fields, lifecycle states, or target bindings.

If C15/C16 are implemented, a follow-up adapter change must define an explicit
typed projection, update the bounded shared input contract, add deterministic
fixtures and inventories, and separately review artifact visibility, custody,
and output-promotion consequences.

## Out of scope

The adapter intentionally provides no:

- identity, adapter, organisation, or target registry;
- human, agent, account, credential, or entitlement lifecycle management;
- target-system authorisation, provisioning, policy evaluation, or
  enforcement;
- network integration or external side effects;
- real-EADS compatibility claim; or
- automatic output promotion or custody transfer.
