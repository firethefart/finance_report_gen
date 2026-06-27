# Agent Runbook: Strategy Report Verifier

This runbook is for agents operating the verifier after cloning the repository on Windows or Linux.

## 1. Environment

Use the repository-root `.venv`; do not use the nested historical `LangAlpha/` environment.

Windows:

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

For HTML runtime visual extraction, Chrome/Chromium must be available. The adapter searches common Windows/Linux Chrome locations and `PATH` names such as `google-chrome`, `google-chrome-stable`, `chromium`, and `chromium-browser`. It runs through the Chrome DevTools Protocol without Playwright.

HTML runtime preflight:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/check_html_runtime.py --json
```

Linux equivalent:

```bash
./.venv/bin/python evals/strategy_report/check_html_runtime.py --json
```

If Chrome is installed in a non-standard location, add `--chrome /path/to/chrome`.

## 2. Secrets and model config

Never read, print, or commit real secrets. Preferred production config is `.env` or process environment:

```text
STRATEGY_VERIFIER_LLM_BASE_URL=
STRATEGY_VERIFIER_LLM_API_KEY=
STRATEGY_VERIFIER_LLM_FLASH_MODEL=
STRATEGY_VERIFIER_LLM_PRO_MODEL=
STRATEGY_VERIFIER_VLM_BASE_URL=
STRATEGY_VERIFIER_VLM_API_KEY=
STRATEGY_VERIFIER_VLM_MODEL=
```

The VLM channel is used by chart/visual QA. Keep it separate from the LLM channel because provider, model, cost, and reliability often differ.

The old `--api-key-file api_key.txt` option remains compatible, but `.env` should be used for migration.

## 3. Manifests

Start from the manifest that matches the verifier mode:

- Reference-based golden set: `evals/strategy_report/golden_manifest.csv`.
  This is v1/reference-based only. It contains 21 rows with standalone metadata:
  query, strategy subtype, expected report contract, institution, report title/date,
  quality tier, source-document metadata, source path, and recommended runner.
- Agent-pipeline copy of the same reference-based golden set:
  `evals/strategy_report/agent_pipeline_golden_manifest.csv`.
- Candidate-only/no-reference test cases:
  `evals/strategy_report/candidate_only_test_manifest.csv` and
  `evals/strategy_report/v2_testset_selection.json`. These are test cases, not
  golden samples, because they do not carry a reference query/source contract.
- Local HTML parser/layout functional fixtures:
  `evals/strategy_report/html_functional_manifest.csv`. These are also not
  golden samples.

All paths in these manifests are relative to repository root.

## 4. Reference-based verifier commands

Rules-only smoke:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_eval.py --cases-dir evals/strategy_report/cases_merged33 --max-cases 1 --out-dir migration_smoke_outputs/local_v1_smoke --no-extract-charts
```

Single case:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_eval.py --case evals/strategy_report/cases_merged33/strategy_sample_001.json --out-dir migration_smoke_outputs/local_v1_case --verifier-profile rules_only
```

Best-effort with LLM/VLM modules:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_eval.py --cases-dir evals/strategy_report/cases_merged33 --max-cases 3 --out-dir evals/strategy_report/results/local_v1_best_effort --verifier-profile full_best_effort
```

## 5. Candidate-only/no-reference verifier commands

One candidate:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_eval_v2.py --candidate-report dataset_build/v2_localized_html/html_gsam_outlook_backdrop_2026/index.html --report-id local_candidate_only_smoke --out-dir migration_smoke_outputs/local_candidate_only_smoke --verifier-profile v2_html_smoke
```

Core test set:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_v2_testset.py --selection evals/strategy_report/v2_testset_selection.json --out-dir evals/strategy_report/results/local_candidate_only_core --verifier-profile v2_html_smoke
```

Local HTML skill-iteration profile:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_eval_v2.py --candidate-report dataset_build/v2_localized_html/html_gsam_outlook_backdrop_2026/index.html --report-id html_skill_smoke --out-dir migration_smoke_outputs/html_skill_smoke --verifier-profile html_skill_iteration
```

Batch local HTML from a manifest:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_html_batch.py --manifest evals/strategy_report/html_functional_manifest.csv --out-dir migration_smoke_outputs/html_batch_smoke --verifier-profile html_skill_iteration --resume
```

For production HTML batches, provide a manifest with `sample_id`/`id` and one of
`path`, `candidate_path`, `html_path`, or `file_path`. By default, the runner only
executes rows that look like `.html`/`.htm` or have HTML format metadata; add
`--include-non-html` only for an intentional mixed-format run. Use `--resume` to avoid
rerunning samples whose `<sample_id>.v2.eval.json` already exists. The runner writes
`summary.json` and `summary.csv` and continues after per-sample failures. For HTML
stability triage, inspect `html_parse_status`, `parse_quality`, `report_likeness`,
`evaluation_confidence`, `browser_status`, `adapter_warnings`, and `top_issue` in the
summary CSV.

For visual QA triage, inspect `visual_coverage_status`, `visual_object_count`,
`chart_count`, `scorable_chart_count`, `visual_filter_drop_count`, and the VLM timing
columns. When VLM is enabled and the HTML adapter finds visual objects but chart QA has
`chart_count=0`, `html_skill_iteration` runs a small gate-only fallback over up to two
filtered visual objects. If VLM accepts one, the sample reports
`scorable_visuals_found_by_vlm_fallback`; if VLM rejects all, it reports
`no_scorable_visuals_after_vlm_gate`.

When the `html_skill_iteration` profile is active, each sample writes
`<report_id>.skill_feedback.md`. This file is intended as the first artifact to feed
back into skill refinement; it suppresses source/fact traceability as a hard gate but
still records low-priority notes.

Small user-reviewed HTML functional set:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_html_batch.py --manifest evals/strategy_report/html_functional_manifest.csv --out-dir migration_smoke_outputs/html_functional_baseline --verifier-profile html_skill_iteration --resume
```

This functional set is not a public-HTML golden set. It contains four retained
report-like web pages for parser/layout/visual regression while verifier optimization
shifts toward model-generated HTML reports.

To expand the local HTML development set, use
`evals/strategy_report/HTML_SAMPLE_EXPANSION_RUNBOOK.md`. The expansion pipeline discovers
report-like HTML pages from source configs, builds a balanced localization manifest,
localizes pages for offline use, audits resource cleanliness, and emits an HTML verifier
manifest. Aim for a near 1:1 Chinese/English admitted set, but do not admit weak pages
just to satisfy the ratio.

Summarize a candidate-only run:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/summarize_v2_testset.py --summary evals/strategy_report/results/local_candidate_only_core/summary.json --out-json evals/strategy_report/results/local_candidate_only_core/layered_summary.json --out-md evals/strategy_report/results/local_candidate_only_core/layered_summary.md
```

## 6. Expected known issues

- Some old Chinese case JSON text is mojibake in metadata; the source PDFs are the authoritative samples.
- Some JSON files may contain a UTF-8 BOM. Python readers should use `utf-8-sig` when consuming legacy indexes.
- GSAM Active ETF may emit a nonfatal MuPDF warning: `No common ancestor in structure tree`.
- Candidate-only/no-reference verifier currently has honest rejects for State Street HTML pages without traceable source links and some Morgan Stanley/J.P. Morgan cases; see the production handoff.

## 7. Migration checklist for another agent

1. Create `.venv`.
2. Install requirements.
3. Copy `.env.example` to `.env`, fill model config and keys.
4. Run one rules-only v1 smoke.
5. Run one rules-only candidate-only smoke.
6. If secrets are configured, run a small best-effort LLM/VLM sample.
7. Use `golden_manifest.csv` or `agent_pipeline_golden_manifest.csv` only for reference-based golden samples.
8. Use `candidate_only_test_manifest.csv`/`v2_testset_selection.json` for candidate-only tests, and `html_functional_manifest.csv` for local HTML functional regression.
