.PHONY: baselines benchmark-registry benchmark-registry-check ci examples install lint metrics package reference-lab schemas test typecheck

UV := uv
SEED := 20260719
PERSONAS := 10
GENERATED_PERSONAS := 100
REFERENCE_LAB_OUTPUT ?= .local-assurance/reference-live
REFERENCE_LAB_RUN_ID ?= reference-live
REFERENCE_LAB_OPERATOR ?= local-operator
PROJECT_VERSION := $(shell $(UV) version --short)
WHEEL := dist/idcognito_synthworld-$(PROJECT_VERSION)-py3-none-any.whl

install:
	$(UV) sync --locked --all-groups

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy

package:
	$(UV) build --clear
	$(UV) run python -c "from pathlib import Path; from tarfile import open as open_tar; archives=list(Path('dist').glob('*.tar.gz')); assert len(archives) == 1; archive=open_tar(archives[0], 'r:gz'); names={item.name for item in archive.getmembers()}; archive.close(); assert not any('/.local-assurance/' in name or name.endswith('/.local-assurance') for name in names)"
	$(UV) run python -c "from zipfile import ZipFile; names=set(ZipFile('$(WHEEL)').namelist()); assert any(name.endswith('dist-info/licenses/LICENSE') for name in names); assert 'synthworld/py.typed' in names"
	$(UV) run python tools/generate_benchmark_registry.py --check-wheel $(WHEEL)
	$(UV) run python tools/generate_benchmark_registry.py --check-reproduction $(WHEEL)
	$(UV) run --isolated --no-project --with ./$(WHEEL) synthworld connection-metrics
	$(UV) run --isolated --no-project --with ./$(WHEEL) synthworld risk-metrics
	$(UV) run --isolated --no-project --no-cache --with ./$(WHEEL) python -c "import tempfile; from pathlib import Path; from synthworld.agentic import generate_asteria_agentic_v1, reference_agentic_trace, trace_submission_to_jsonl; from synthworld.cli import main; benchmark=generate_asteria_agentic_v1(); path=Path(tempfile.mkdtemp())/'trace.jsonl'; path.write_text(trace_submission_to_jsonl(reference_agentic_trace(benchmark)), encoding='utf-8'); assert main(['validate','agentic-trace','--predictions',str(path)]) == 0; assert main(['validate','agentic-trace','--predictions','/dev/null']) == 1"
	$(UV) run --isolated --no-project --no-cache --with ./$(WHEEL) python -c "from synthworld.agentic import evaluate_agentic_trace, generate_asteria_agentic_v1, load_golden_agentic_benchmark, reference_agentic_trace; from synthworld.agentic.serialization import agentic_artifact_checksums; generated=generate_asteria_agentic_v1(); assert generated == load_golden_agentic_benchmark(); assert dict(agentic_artifact_checksums(generated)) == {'public':'9ef217b5d604f42a68b7c97596c550698293f1a44f402dbc3d39a2cef19c4594','evaluator':'3d856f39a5c34ca891ec61298a40ee5bfcb134feae5db7b8a20f6ce9078b2b3f'}; report=evaluate_agentic_trace(reference_agentic_trace(generated), benchmark=generated); assert report.scoring_version == '0.3.0'; assert {'provenance_exact_match','provenance_precision'} <= {item.name for item in report.metrics}"
	$(UV) run --isolated --no-project --no-cache --with ./$(WHEEL) python -c "from synthworld.authority_governance import load_golden_authority_governance_benchmark, reference_authority_governance; assert load_golden_authority_governance_benchmark() == reference_authority_governance()"
	$(UV) run --isolated --no-project --no-cache --with ./$(WHEEL) python -c "import yaml; from synthworld.enterprise import compile_enterprise_identity_access_universe; from synthworld.enterprise.reference import reference_enterprise_identity_access_import; result=compile_enterprise_identity_access_universe(import_model=reference_enterprise_identity_access_import(),seed=20260804); assert len(result.public_universe.principals) == 6"
	$(UV) run --isolated --no-project --no-cache --with ./$(WHEEL) python -c "from synthworld.continuous_assurance import evaluate_continuous_assurance_prediction, perfect_continuous_assurance_prediction, reference_continuous_assurance; b=reference_continuous_assurance(); r=evaluate_continuous_assurance_prediction(public=b.public,evaluator=b.evaluator,prediction=perfect_continuous_assurance_prediction(b.evaluator)); assert len(b.public.cases)==8 and len(r.metrics)==16"

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
	$(UV) run python examples/evaluate_all.py --seed $(SEED) --persona-count $(PERSONAS)
	$(UV) run python examples/evaluate_broker_adapter.py --seed $(SEED)

reference-lab:
	$(UV) run python agent-authority-contract/reference-deployment/run.py --output $(REFERENCE_LAB_OUTPUT) --run-id $(REFERENCE_LAB_RUN_ID) --operator-id $(REFERENCE_LAB_OPERATOR)

baselines:
	$(UV) run python examples/generate_benchmarks_doc.py --check
	$(UV) run python -c "from synthworld.ambiguity_baselines import AMBIGUITY_BASELINES, run_ambiguity_baseline; rows=[(name, run_ambiguity_baseline(fn)) for name, fn in AMBIGUITY_BASELINES]; assert len(rows) == 3; assert all(m.false_merges + m.false_splits + m.unwarranted_decisions > 0 for _, m in rows), 'a baseline resolved the ambiguity pack'; assert any(m.coverage < 1.0 for _, m in rows), 'no baseline abstains, so abstention is unscored'; print('\n'.join(f'{name}: coverage={m.coverage:.2f} decided_precision={m.decided_precision} false_merges={m.false_merges} false_splits={m.false_splits} unwarranted={m.unwarranted_decisions}' for name, m in rows))"
	$(UV) run python -c "from synthworld.ambiguity_baselines import AMBIGUITY_V2_BASELINES, run_ambiguity_v2_baseline; rows=[(name, run_ambiguity_v2_baseline(fn, seed=7, key=b'make-baselines')) for name, fn in AMBIGUITY_V2_BASELINES]; assert len(rows) == 3; assert all(m.false_merges + m.false_splits + m.unwarranted_decisions > 0 for _, m in rows), 'a baseline resolved the v2 ambiguity pack'; assert all(m.correct_decided_count / m.pair_count <= 1.0 - m.pack_floor for _, m in rows), 'a baseline crossed the published ceiling'; print('\n'.join(f'{name}: coverage={m.coverage:.2f} decided_precision={m.decided_precision} floor={m.pack_floor} false_merges={m.false_merges} false_splits={m.false_splits} unwarranted={m.unwarranted_decisions}' for name, m in rows))"
	$(UV) run python -c "from synthworld.search_baselines import SEARCH_BASELINES, run_search_baseline; from synthworld.search_generator import generate_search_projection; p=generate_search_projection(seed=1); rows=[(n, run_search_baseline(f, projection=p).metrics) for n, f in SEARCH_BASELINES]; assert all(m.false_accepts + m.false_rejects + m.unwarranted_decisions > 0 for _, m in rows), 'a baseline scored the search projection cleanly'; assert any(m.coverage < 1.0 for _, m in rows), 'no baseline abstains, so abstention is unscored'; assert any(m.distinct_findings < m.accepted_results for _, m in rows), 'syndication is not being collapsed, so the metric proves nothing'; print(chr(10).join(f'{n}: coverage={m.coverage:.2f} false_accepts={m.false_accepts} false_rejects={m.false_rejects} unwarranted={m.unwarranted_decisions} findings={m.distinct_findings}/{m.accepted_results}' for n, m in rows))"

	$(UV) run python -c "from synthworld.broker_metrics import BROKER_BASELINES, run_broker_baseline; from synthworld.temporal import materialise; from synthworld.temporal_generator import generate_temporal_world; w=generate_temporal_world(seed=3); t=materialise(w, as_of=w.horizon); rows=[(n, run_broker_baseline(f, timeline=t, truth=w.truth)) for n, f in BROKER_BASELINES]; assert all(m.false_completions > 0 for _, m in rows), 'a baseline resolved the broker pack'; assert all(m.missed_surviving_copies > 0 for _, m in rows), 'no baseline overstates propagation, so reseller copies are unscored'; assert all(m.false_recurrence_alerts == 0 for _, m in rows), 'a baseline is spamming reappearance alerts'; assert any(m.attribution_accuracy.value == 1.0 for _, m in rows) and any(m.unwarranted_attributions > 0 for _, m in rows), 'attribution does not separate reading the evidence from guessing'; assert any(m.recurrence_detected == 0 for _, m in rows) and any(m.recurrence_detected == m.recurrence_count for _, m in rows), 'recurrence does not separate the baselines'; print(chr(10).join(f'{n}: completion={m.completion_accuracy.value:.2f} false_completions={m.false_completions} recurrence={m.recurrence_detected}/{m.recurrence_count} missed_surviving_copies={m.missed_surviving_copies}' for n, m in rows))"
	$(UV) run python -c "from synthworld.continuous_assurance import CONTINUOUS_ASSURANCE_BASELINES, evaluate_continuous_assurance_prediction, reference_continuous_assurance; b=reference_continuous_assurance(); rows=[(n,evaluate_continuous_assurance_prediction(public=b.public,evaluator=b.evaluator,prediction=f(b.public))) for n,f in CONTINUOUS_ASSURANCE_BASELINES]; values=lambda r:{m.name:m.value for m in r.metrics}; assert values(rows[0][1])['finding_detection_recall'] < 1.0; assert values(rows[1][1])['pre_observation_opening_rate'] > 0.0; assert values(rows[2][1])['stale_finding_duration_mean_ticks'] > 0.0; print(chr(10).join(f'{n}: recall={values(r)[\"finding_detection_recall\"]} pre_observation={values(r)[\"pre_observation_opening_rate\"]} stale_ticks={values(r)[\"stale_finding_duration_mean_ticks\"]}' for n,r in rows))"

schemas:
	$(UV) run python agent-authority-contract/reference-deployment/run.py --check-contract
	$(UV) run python agent-authority-contract/tools/generate_trace_schema.py --check
	$(UV) run python agent-authority-contract/tools/generate_protocol_schemas.py --check
	$(UV) run python enterprise-identity-access-contract/tools/generate_contract.py --check
	$(UV) run python contextual-access-contract/tools/generate_contract.py --check
	$(UV) run python authority-governance-contract/tools/generate_contract.py --check
	$(UV) run python continuous-assurance-contract/tools/generate_contract.py --check
	$(UV) run python agent-authority-contract/tools/generate_design_intent_traces.py --check
	$(UV) run python agent-authority-contract/tools/render_coverage_table.py --check
	$(UV) run python -c "import subprocess,sys,tempfile; from pathlib import Path; d=Path(tempfile.mkdtemp()); subprocess.run([sys.executable,'-m','synthworld.cli' if False else 'synthworld'],capture_output=True); from synthworld.cli import main; assert main(['generate-agentic','--output',str(d/'a')])==0; subprocess.run([sys.executable,'agent-authority-contract/adapter-template/adapter.py','--public-dir',str(d/'a/public'),'--output',str(d/'t.jsonl')],check=True,capture_output=True); assert main(['validate','agentic-trace','--predictions',str(d/'t.jsonl')])==0, 'the shipped adapter template must produce a valid trace'"

benchmark-registry:
	$(UV) run python tools/generate_benchmark_registry.py

benchmark-registry-check:
	$(UV) run python tools/generate_benchmark_registry.py --check

ci: lint typecheck benchmark-registry-check package test metrics examples baselines schemas
