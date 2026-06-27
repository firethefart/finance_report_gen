# Finance Report Verifier

This repository packages the strategy-report verifier for production migration. The current focus is the verifier under `evals/strategy_report/`, plus reference-based golden samples, candidate-only test cases, and local HTML functional fixtures under `dataset_build/`, `generation_test/`, and `evals/strategy_report/`.

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

On Linux production hosts, the HTML runtime only needs a Chrome/Chromium-compatible
browser executable. The verifier launches it headlessly through the Chrome DevTools
Protocol; it does not require Playwright, Puppeteer, Selenium, or a browser driver.
For restricted networks, prepare an offline OS package for the target architecture
such as `google-chrome-stable` or the distribution `chromium` package plus its RPM
dependencies, install it on the server, then run the preflight command above. If the
binary is outside `PATH`, pass `--chrome /absolute/path/to/google-chrome`.

Single local HTML skill-iteration run:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_eval_v2.py --candidate-report dataset_build/v2_localized_html/html_gsam_outlook_backdrop_2026/index.html --report-id html_skill_smoke --out-dir migration_smoke_outputs/html_skill_smoke --verifier-profile html_skill_iteration
```

Batch local HTML run from a manifest:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_html_batch.py --manifest evals/strategy_report/html_functional_manifest.csv --out-dir migration_smoke_outputs/html_batch_smoke --verifier-profile html_skill_iteration --resume
```

When `html_skill_iteration` is used, each completed sample also writes
`<report_id>.feedback.md` and `<report_id>.feedback.json` for downstream skill
refinement. The Markdown file is intended for human/agent review; the JSON file is
the structured automation artifact. Some legacy profiles may still emit
`<report_id>.skill_feedback.md` as an alias, but new workflows should prefer the
shared feedback files.

To expand the local HTML development set before larger production runs, follow
[HTML sample expansion runbook](evals/strategy_report/HTML_SAMPLE_EXPANSION_RUNBOOK.md).

Small user-reviewed HTML functional set:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_html_batch.py --manifest evals/strategy_report/html_functional_manifest.csv --out-dir migration_smoke_outputs/html_functional_baseline --verifier-profile html_skill_iteration --resume
```

## Golden set entry point

Use [evals/strategy_report/golden_manifest.csv](evals/strategy_report/golden_manifest.csv) for the reference-based golden set only. It is v1/reference-based by definition and contains 21 samples with enough metadata to be consumed as a standalone CSV:

- sample ID
- case JSON path
- reference query and query metadata
- strategy subtype, expected report type/depth/output/time horizon/reader
- institution, report title/date/period, quality tier
- original source document path and source-document metadata
- recommended runner

For agent-pipeline tests that need a self-contained copy, use
[evals/strategy_report/agent_pipeline_golden_manifest.csv](evals/strategy_report/agent_pipeline_golden_manifest.csv).
[evals/strategy_report/v1_golden_manifest.csv](evals/strategy_report/v1_golden_manifest.csv) is an explicit alias with the same rows.

Candidate-only/no-reference verifier samples are not golden samples. They live in
[evals/strategy_report/candidate_only_test_manifest.csv](evals/strategy_report/candidate_only_test_manifest.csv)
and in the curated selection JSON used by `run_v2_testset.py`.

The small user-reviewed local HTML parser/layout regression set lives in
[evals/strategy_report/html_functional_manifest.csv](evals/strategy_report/html_functional_manifest.csv).
It is also a functional test fixture, not a golden set.

## Production configuration

The verifier reads `.env` or process environment variables:

- shared fallback: `STRATEGY_VERIFIER_BASE_URL`, `STRATEGY_VERIFIER_API_KEY`
- LLM: `STRATEGY_VERIFIER_LLM_BASE_URL`, `STRATEGY_VERIFIER_LLM_API_KEY`
- VLM: `STRATEGY_VERIFIER_VLM_BASE_URL`, `STRATEGY_VERIFIER_VLM_API_KEY`
- model names: `STRATEGY_VERIFIER_LLM_FLASH_MODEL`, `STRATEGY_VERIFIER_LLM_PRO_MODEL`, `STRATEGY_VERIFIER_VLM_MODEL`

The legacy `--api-key-file api_key.txt` path is still supported for local runs, but environment variables are preferred for production and migration.

## Important docs

- [Agent runbook](evals/strategy_report/AGENT_RUNBOOK.md)
- [Feedback design and schema notes](evals/strategy_report/feedback/FEEDBACK_DESIGN.md)
- [Production handoff](evals/strategy_report/PRODUCTION_MIGRATION_HANDOFF_20260625.md)
- [HTML production refinement handoff](evals/strategy_report/SESSION_HANDOFF_20260626_HTML_PROD_R1.md)
- [HTML sample expansion handoff](evals/strategy_report/SESSION_HANDOFF_20260626_HTML_SAMPLE_EXPANSION_R1.md)
- [HTML sample expansion runbook](evals/strategy_report/HTML_SAMPLE_EXPANSION_RUNBOOK.md)
- [Development goals](DEVELOPMENT_GOALS.md)
- [Candidate-only core test set README](evals/strategy_report/V2_CORE_TESTSET_README.md)
- [Candidate-only development notes](evals/strategy_report/V2_DEVELOPMENT_GOALS.md)

## Repository hygiene

Large generated caches, full eval result folders, temporary logs, local virtual environments, and real secrets are ignored. The short-lived public repository must not contain real API keys.
