# Public input and evaluator truth

Public product input and evaluator truth use separate types and physical artifacts.
Public projection is constructed field by field; it is never an oracle-bearing model
dumped with an exclusion list.

Public artifacts must not contain expected verdicts, hidden canonical bindings, case
labels, ownership truth, or answer-key fields. Evaluator artifacts may be distributed
publicly for reference conformance, so the split is API hygiene and accidental-leak
protection rather than a secrecy claim.

Operational custody remains the consumer's responsibility. A sibling `public/` and
`evaluator/` directory layout does not create an access-control boundary by itself.
