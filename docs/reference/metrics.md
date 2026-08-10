# Metrics

Metric field definitions and report schemas remain canonical in
[DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) and the relevant contract README.

Metric envelopes are independently versioned and are not field-identical:

- Legacy `TaskMetric` records expose `value`, `support`, `family`, and
  `support_meaning`, but no explicit numerator or denominator. Support is the
  denominator for its direct ratios; agentic authorization F1 instead uses support as
  classification support and is derived from the separately reported precision and
  recall.
- Enterprise authorization metrics expose numerator, denominator, support, family,
  denominator meaning, value, and empty behavior; support equals denominator.
- C08 v2 metrics expose numerator, denominator, denominator meaning, value, and an
  undefined reason, but no separate support field.

Interpret each metric through its own report contract and documented polarity. Keep
independent metrics independent; an aggregate must not conceal failures. A metric that
only compares a reported public reference measures reporting accuracy, not underlying
enforcement or evidence retention.
