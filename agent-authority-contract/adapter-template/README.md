# Adapter template

A working starting point for scoring your own system against Asteria Agentic v1.
Copy `adapter.py`, replace one function, and you have an integration.

## Run it as shipped

```bash
synthworld generate-agentic --output asteria-agentic-v1
python adapter.py --public-dir asteria-agentic-v1/public --output trace.jsonl
synthworld validate agentic-trace --predictions trace.jsonl
synthworld evaluate agentic --predictions trace.jsonl --summary
```

That works before you write anything. The trace is structurally valid, `validate`
exits `0` with eleven `no_scored_fields` warnings, and the scorer reports zeros. The
loop closing on an empty integration is the point: you can see the shape of the
workflow before wiring in a system, and the warnings name exactly what is missing.

## What to change

One function: `observe_action(event)`. It receives one `action_attempted` event from
the public stream and returns an `Observation` describing **what your system
determined** about that action. Look the action up in your gateway, policy engine, or
audit log by its identifiers, and report what you find.

Everything else is plumbing you should not need to touch — reading the events, and
writing rows in the order the scorer expects.

## Two rules that decide whether your result means anything

**Null means "not captured", and that is a legitimate answer.** Unset fields are
scored as misses and never back-filled. Guessing a plausible value scores the same as
being wrong while also claiming a capability your system does not have, so leave it
null. A trace full of honest nulls tells you where to invest; a trace full of guesses
tells you nothing.

**Do not echo the claims.** Every action event carries what the *agent asserted* —
`originating_principal_claim`, `runtime_principal_claim`, `attributed_actor_claim`.
Copying those into your trace scores well on this fixture, because most of its claims
are truthful, and measures nothing about your system. The benchmark asks what your
system *independently established*. One labelled case exists specifically to catch
claim-echoing, and a generated world will contain more.

## Things that will trip you up

- `synthetic` must be `true` or omitted. `false` is rejected — the marker is what
  makes the artifact unmistakably fictional.
- `evidence_refs: []` is not `null`. The empty list claims you captured evidence and
  there was none; `null` claims you captured nothing. They score differently.
- Timestamps must be timezone-aware UTC. A naive timestamp is rejected, and so is a
  non-UTC offset.
- Submit exactly one row per action event — no omissions, duplicates, or extras.
  `validate` will tell you which before the scorer refuses the file.

## Validating from another language

`adapter.py` is Python because the rest of this repository is, but nothing about the
contract requires it. The wire format is JSON Lines and
`../schemas/observed-action-trace.schema.json` is a plain JSON Schema you can feed to
`ajv`, `go-jsonschema`, or any other validator.

One caveat if you do: `format` is an annotation rather than an assertion in JSON
Schema 2020-12, so several validators ignore `format: date-time` unless explicitly
configured. The timestamp property therefore also carries a `pattern`, which every
conformant validator does enforce. See `../README.md` for why that matters.
