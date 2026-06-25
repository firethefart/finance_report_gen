# Production Migration Handoff — 2026-06-25

## Scope shift

The immediate priority changed from ongoing candidate-only/no-reference optimization to production migration readiness. Reference-based verifier (`run_eval.py`, historically v1) is production-priority. Candidate-only/no-reference verifier remains included and runnable, but it can continue improving after migration.

Terminology note: “V2” in older files means the candidate-only/no-reference verifier variant, not a version number.

## What was completed in this handoff pass

- Added production-safe config layer in `evals/strategy_report/verifier_config.py`.
- Added `.env.example` with separate LLM/VLM, flash/pro, base URL, and API key slots.
- Kept backward compatibility with `--api-key-file`, while preferring environment variables.
- Updated LLM/VLM callers to use channel-specific base URL and API key config.
- Replaced the broken root README with migration-oriented verifier documentation.
- Added `evals/strategy_report/AGENT_RUNBOOK.md`.
- Added `evals/strategy_report/golden_manifest.csv` as unified test entry manifest.
- Updated `.gitignore` to exclude real secrets and generated caches while unignoring selected raw PDFs used by the golden set.
- Verified all manifest paths exist.
- Verified key verifier modules compile using a temporary pycache prefix.
- Ran rules-only smoke tests successfully without API keys.

## Validation notes from this pass

Successful:

- Manifest path check: 0 missing paths.
- `py_compile`: passed after setting `PYTHONPYCACHEPREFIX=.tmp_pycache`.
- Reference-based smoke:
  - Command used output dir `migration_smoke_outputs/local_v1_smoke`.
  - Result: `eastmoney_cn_strategy_001: 80.78 Silver gate=True`.
- Candidate-only/no-reference smoke:
  - Command used output dir `migration_smoke_outputs/local_candidate_only_smoke`.
  - Result: requested 1, completed 1, failure 0.

Failed then worked around:

- Writing smoke outputs directly under `evals/strategy_report/results/local_*` failed on this Windows workspace with `PermissionError: [WinError 5]`.
- Workaround: write local smoke outputs under `migration_smoke_outputs/`, which is ignored by git.
- First `py_compile` attempted to write into an existing `__pycache__` and hit a Windows permission error. Workaround: set `PYTHONPYCACHEPREFIX=.tmp_pycache`.

## Current verifier baselines

Reference-based verifier:

- Main entry: `evals/strategy_report/run_eval.py`
- Cases: `evals/strategy_report/cases_merged33/index.json`
- Preferred production profile: start with `rules_only` for deterministic smoke, then `full_best_effort` once model config is available.

Candidate-only/no-reference verifier:

- Main entries: `evals/strategy_report/run_eval_v2.py`, `evals/strategy_report/run_v2_testset.py`
- Core selection: `evals/strategy_report/v2_testset_selection.json`
- Current baseline run label: `candidate_only_rules_r8`
- Last known full run: 26/26 completed, 0 execution failures, gate 19/26.

## Config contract

Production should set environment variables or `.env`:

```text
STRATEGY_VERIFIER_LLM_BASE_URL
STRATEGY_VERIFIER_LLM_API_KEY
STRATEGY_VERIFIER_LLM_FLASH_MODEL
STRATEGY_VERIFIER_LLM_PRO_MODEL
STRATEGY_VERIFIER_VLM_BASE_URL
STRATEGY_VERIFIER_VLM_API_KEY
STRATEGY_VERIFIER_VLM_MODEL
```

Fallback shared variables:

```text
STRATEGY_VERIFIER_BASE_URL
STRATEGY_VERIFIER_API_KEY
```

Do not commit real keys. `api_key.txt`, `.env`, and `.env.*` are ignored.

## High-priority open items after migration

1. Candidate-only J.P. Morgan Energy sample: audit whether the sample is a strategy-quality report or a thematic/parser robustness case; current parser compaction may omit useful middle pages.
2. Candidate-only Morgan Stanley HTML: continue body-boundary and related-card trimming improvements.
3. State Street HTML: decide whether “no external traceable source links” should remain a hard honesty gate for official outlook pages.
4. Add CI once repo is private/stable: py_compile, rules-only smoke, manifest path existence check.

## Known failure/edge cases

- Legacy Chinese metadata files include mojibake, but source PDFs are preserved.
- Some old indexes have UTF-8 BOM; use `utf-8-sig` when scripting.
- MuPDF may emit a nonfatal structure-tree warning on GSAM Active ETF.
- Rules-only smoke should not require any API key.

## Safe migration order

1. Clone repository.
2. Create `.venv` and install `dataset_tools/strategy_reports/requirements.txt`.
3. Copy `.env.example` to `.env`; fill secrets locally only.
4. Run the two smoke tests in `README.md`.
5. Use `golden_manifest.csv` as the source of truth for golden samples.
