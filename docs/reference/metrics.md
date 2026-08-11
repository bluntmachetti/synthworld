# Metrics

Metric field definitions and report schemas remain canonical in
[DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) and the relevant contract README.

Every metric must expose its numerator, denominator, support, and meaning. Independent
metrics remain independent; an aggregate must not conceal failures. A metric that
only compares a reported public reference measures reporting accuracy, not underlying
enforcement or evidence retention.
