# Agent-authority schemas

`agent-authority-run-plan.schema.json`,
`agent-authority-observations.schema.json`, the lab truth/report schemas, and the
generic receipt/execution v2 schemas are generated from the authoritative frozen
Pydantic models. Run:

```bash
uv run python agent-authority-contract/tools/generate_protocol_schemas.py
```

`run-manifest.schema.json` is the superseded hand-authored `0.1.0-draft`. It is
retained under its original filename solely so draft adopters can identify and
migrate old documents. It is not the current receipt schema, and the filename is
never repurposed. Its fields now map to the generic receipt v2, pre-execution run
plan, and post-execution observations contracts described in the parent README.

`partition_legacy_draft_manifest` implements that field-ownership map without
discarding values. It is intentionally not an automatic converter: the draft did
not record component IDs, dependency-lock and adapter-source digests, typed control
coverage, stimuli, or normalized observations required by the executable contracts.
A caller must supply those facts rather than have SynthWorld invent them. Unknown
extension fields fail with their names, and the migration fixture proves that all
supported source values can be reconstructed exactly after partitioning.
