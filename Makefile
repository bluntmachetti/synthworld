.PHONY: baselines ci examples install lint metrics package test typecheck

UV := uv
SEED := 20260719
PERSONAS := 10
GENERATED_PERSONAS := 100
WHEEL := dist/idcognito_synthworld-0.7.0-py3-none-any.whl

install:
	$(UV) sync --locked --all-groups

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy

package:
	$(UV) build --clear
	$(UV) run python -c "from zipfile import ZipFile; names=set(ZipFile('$(WHEEL)').namelist()); assert any(name.endswith('dist-info/licenses/LICENSE') for name in names); required={'synthworld/py.typed','synthworld/benchmarks/golden-v1.json','synthworld/benchmarks/SHA256SUMS','synthworld/benchmarks/extraction-golden-v1.json','synthworld/benchmarks/EXTRACTION_SHA256SUMS','synthworld/benchmarks/extraction-public-golden-v1.json','synthworld/benchmarks/EXTRACTION_PUBLIC_SHA256SUMS','synthworld/benchmarks/extraction-answer-golden-v1.json','synthworld/benchmarks/EXTRACTION_ANSWER_SHA256SUMS','synthworld/benchmarks/connection-golden-v1.json','synthworld/benchmarks/CONNECTION_SHA256SUMS','synthworld/benchmarks/connection-public-golden-v1.json','synthworld/benchmarks/CONNECTION_PUBLIC_SHA256SUMS','synthworld/benchmarks/risk-public-golden-v1.json','synthworld/benchmarks/RISK_PUBLIC_SHA256SUMS','synthworld/benchmarks/risk-answer-golden-v1.json','synthworld/benchmarks/RISK_ANSWER_SHA256SUMS'}; assert required <= names"
	$(UV) run --isolated --no-project --with ./$(WHEEL) synthworld connection-metrics
	$(UV) run --isolated --no-project --with ./$(WHEEL) synthworld risk-metrics

test:
	$(UV) run pytest

metrics:
	$(UV) run synthworld metrics --seed $(SEED) --persona-count $(PERSONAS)
	$(UV) run synthworld corpus-metrics --seed $(SEED) --persona-count $(PERSONAS)
	$(UV) run synthworld corpus-metrics --seed $(SEED) --persona-count $(GENERATED_PERSONAS)
	$(UV) run synthworld connection-metrics --seed $(SEED) --persona-count $(PERSONAS)
	$(UV) run synthworld connection-metrics --seed $(SEED) --persona-count $(GENERATED_PERSONAS)
	$(UV) run synthworld risk-metrics --seed $(SEED) --persona-count $(PERSONAS)
	$(UV) run synthworld risk-metrics --seed $(SEED) --persona-count $(GENERATED_PERSONAS)

examples:
	$(UV) run python examples/evaluate_extraction.py --seed $(SEED) --persona-count $(PERSONAS)

baselines:
	$(UV) run python examples/generate_benchmarks_doc.py --check

ci: lint typecheck package test metrics examples baselines
