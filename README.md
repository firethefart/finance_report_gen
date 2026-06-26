# Finance Report Verifier

This repository packages the strategy-report verifier for production migration. The current focus is the verifier under `evals/strategy_report/`, plus its golden set samples and metadata under `dataset_build/`, `generation_test/`, and `evals/strategy_report/`.

Two verifier modes are maintained:

- `run_eval.py`: reference-based verifier, historically called v1. This is the production-priority path.
- `run_eval_v2.py` / `run_v2_testset.py`: candidate-only/no-reference verifier. “V2” here means a verifier variant, not a semantic version number.

For local HTML production use, prefer the candidate-only/no-reference verifier with the
`html_skill_iteration` profile. This profile is tuned for skill iteration feedback on
locally available HTML reports: content quality, strategy reasoning, risk/scenario
coverage, and layout/visual QA carry most of the score; source/fact traceability is kept
as low-priority feedback instead of a hard gate.

## Quick start

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r dataset_tools/strategy_reports/requirements.txt
Copy-Item .env.example .env
```

Linux/macOS:

```bash
python -m venv .venv
./.venv/bin/python -m pip install -r dataset_tools/strategy_reports/requirements.txt
cp .env.example .env
```

Edit `.env` with real provider values. Do not commit `.env`, `api_key.txt`, or any real secret.

## Smoke tests

Rules-only reference-based smoke:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_eval.py --cases-dir evals/strategy_report/cases_merged33 --max-cases 1 --out-dir migration_smoke_outputs/local_v1_smoke --no-extract-charts
```

Rules-only candidate-only smoke:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_v2_testset.py --selection evals/strategy_report/v2_testset_selection.json --max-samples 1 --out-dir migration_smoke_outputs/local_candidate_only_smoke --verifier-profile v2_html_smoke --no-extract-charts
```

Full/best-effort runs can enable LLM/VLM modules through verifier profiles and `.env` configuration. See [agent runbook](evals/strategy_report/AGENT_RUNBOOK.md).

HTML runtime preflight:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/check_html_runtime.py --json
```

If Chrome/Chromium is installed in a non-standard location, pass `--chrome`.

Single local HTML skill-iteration run:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_eval_v2.py --candidate-report dataset_build/v2_localized_html/html_gsam_outlook_backdrop_2026/index.html --report-id html_skill_smoke --out-dir migration_smoke_outputs/html_skill_smoke --verifier-profile html_skill_iteration
```

Batch local HTML run from a manifest:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_html_batch.py --manifest evals/strategy_report/golden_manifest.csv --out-dir migration_smoke_outputs/html_batch_smoke --verifier-profile html_skill_iteration --sample-id v2_html_gsam_backdrop_2026
```

When `html_skill_iteration` is used, each completed sample also writes
`<report_id>.skill_feedback.md` for downstream skill refinement.

## Golden set entry point

Use [evals/strategy_report/golden_manifest.csv](evals/strategy_report/golden_manifest.csv) as the unified manifest. It lists:

- suite: `v1_reference_based` or `candidate_only_no_reference`
- sample ID
- case/metadata path
- original candidate report path
- optional HTML resource manifest
- language, format, institution, subtype, quality tier
- recommended runner

The committed golden set includes original PDFs/HTML, case metadata, localized HTML resources, generated-control HTML samples, and candidate-only selection metadata.

## Production configuration

The verifier reads `.env` or process environment variables:

- shared fallback: `STRATEGY_VERIFIER_BASE_URL`, `STRATEGY_VERIFIER_API_KEY`
- LLM: `STRATEGY_VERIFIER_LLM_BASE_URL`, `STRATEGY_VERIFIER_LLM_API_KEY`
- VLM: `STRATEGY_VERIFIER_VLM_BASE_URL`, `STRATEGY_VERIFIER_VLM_API_KEY`
- model names: `STRATEGY_VERIFIER_LLM_FLASH_MODEL`, `STRATEGY_VERIFIER_LLM_PRO_MODEL`, `STRATEGY_VERIFIER_VLM_MODEL`

The legacy `--api-key-file api_key.txt` path is still supported for local runs, but environment variables are preferred for production and migration.

## Important docs

- [Agent runbook](evals/strategy_report/AGENT_RUNBOOK.md)
- [Production handoff](evals/strategy_report/PRODUCTION_MIGRATION_HANDOFF_20260625.md)
- [HTML production refinement handoff](evals/strategy_report/SESSION_HANDOFF_20260626_HTML_PROD_R1.md)
- [Development goals](DEVELOPMENT_GOALS.md)
- [Candidate-only core test set README](evals/strategy_report/V2_CORE_TESTSET_README.md)
- [Candidate-only development notes](evals/strategy_report/V2_DEVELOPMENT_GOALS.md)

## Repository hygiene

Large generated caches, full eval result folders, temporary logs, local virtual environments, and real secrets are ignored. The short-lived public repository must not contain real API keys.
