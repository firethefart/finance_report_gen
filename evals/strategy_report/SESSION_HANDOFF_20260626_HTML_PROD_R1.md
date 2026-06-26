# HTML Production Refinement Handoff — 2026-06-26

## Context

The production target shifted toward large-volume local HTML verification on Linux.
Inputs are expected to be local/offline HTML reports with no external resource dependency.
Network constraints mostly affect LLM/VLM calls, which should be configured through
internal-compatible base URLs. Chrome/Chromium is expected to be installed on the target
machine.

The priority for this round is honest, comparable scoring and actionable feedback for
skill iteration. Information provenance and deep factual judgment remain useful, but they
are low-priority for this deployment path and should not block content/layout scoring.

Terminology note: older docs and code use "V2" for the candidate-only/no-reference
verifier variant. It is not a semantic version number.

## Implemented in this refinement round

- Added `evals/strategy_report/profiles/html_skill_iteration.json`.
  - Reweighted candidate-only scoring toward content, strategy reasoning, scenario/risk,
    layout, and visual QA.
  - Disabled source/fact traceability as hard gates for local/offline HTML while keeping
    those dimensions visible as low-priority feedback.
- Extended candidate-only gate logic in `scoring_v2.py`.
  - Supports disabled dimensions.
  - Supports disabled gates.
  - Keeps default gate thresholds active unless explicitly set to `null` or disabled.
  - Adds optional source/fact gates for stricter future profiles.
- Added skill-iteration feedback output in `run_eval_v2.py`.
  - When profile `feedback.write_skill_feedback=true`, writes
    `<report_id>.skill_feedback.md`.
  - Feedback prioritizes actionable skill patches and separates low-priority
    source/fact notes.
- Improved HTML text extraction.
  - Attempts article/main/content container extraction with density/link-ratio scoring.
  - Falls back to existing marker/boilerplate trimming when article extraction is not
    reliable.
- Improved HTML visual handling.
  - Infers visual roles such as analytical visual, table, hero, and decorative.
  - Filters likely logos/navigation/social/profile/hero decoration before chart scoring.
- Improved Linux Chrome discovery in `html_adapter.py`.
  - Searches common Linux `PATH` names such as `google-chrome`,
    `google-chrome-stable`, `chromium`, and `chromium-browser`.
- Added `check_html_runtime.py`.
  - Preflights Chrome discovery, headless local-file navigation, screenshot capture,
    and adapter extraction.
- Added `run_html_batch.py`.
  - Runs local HTML manifests, continues after per-sample failures, supports `--resume`,
    and writes `summary.json`/`summary.csv`.
  - Defaults to HTML-only rows when a unified manifest also contains PDFs; use
    `--include-non-html` only for intentional mixed-format runs.

## How to run

HTML runtime preflight:

```bash
./.venv/bin/python evals/strategy_report/check_html_runtime.py --json
```

If Chrome is in a non-standard location:

```bash
./.venv/bin/python evals/strategy_report/check_html_runtime.py --chrome /path/to/chrome --json
```

Single HTML sample:

```bash
./.venv/bin/python evals/strategy_report/run_eval_v2.py \
  --candidate-report dataset_build/v2_localized_html/html_gsam_outlook_backdrop_2026/index.html \
  --report-id html_skill_smoke \
  --out-dir migration_smoke_outputs/html_skill_smoke \
  --verifier-profile html_skill_iteration
```

Batch HTML manifest:

```bash
./.venv/bin/python evals/strategy_report/run_html_batch.py \
  --manifest evals/strategy_report/html_functional_manifest.csv \
  --out-dir migration_smoke_outputs/html_batch_smoke \
  --verifier-profile html_skill_iteration \
  --resume
```

## Validation status

Successful on the Windows development machine:

- `py_compile` passed for:
  - `evals/strategy_report/scoring_v2.py`
  - `evals/strategy_report/run_eval_v2.py`
  - `evals/strategy_report/html_adapter.py`
  - `evals/strategy_report/check_html_runtime.py`
  - `evals/strategy_report/run_html_batch.py`
- HTML runtime preflight:
  - Command: `.\.venv\Scripts\python.exe evals/strategy_report/check_html_runtime.py --json`
  - Chrome found: `C:\Program Files\Google\Chrome\Application\chrome.exe`
  - Headless launch: true
  - CDP available: true
  - Local file navigation: true
  - Screenshot capture: true
  - Adapter OK: true
  - Warning: `html_text_too_short_for_strategy_report` because the synthetic preflight
    page is intentionally short.
- Single local HTML run:
  - Command used `run_eval_v2.py` with `html_skill_iteration`.
  - Sample: `dataset_build/v2_localized_html/html_gsam_outlook_backdrop_2026/index.html`
  - Result: `html_skill_smoke: 93.3 Gold gate=True`
- Batch local HTML run:
  - Command used `run_html_batch.py` with `html_skill_iteration`.
  - Manifest: `evals/strategy_report/golden_manifest.csv`
  - Sample: `v2_html_gsam_backdrop_2026`
  - Result: requested 1, completed 1, failure 0.
  - Confirmed `v2_html_gsam_backdrop_2026.skill_feedback.md` was generated.
- Batch local HTML default filtering:
  - Command used `run_html_batch.py --max-samples 1` against the unified
    `golden_manifest.csv`.
  - Result: selected the first HTML sample, completed 1, failure 0.
  - Confirms PDF rows in the unified manifest are skipped by default.

No execution failures were observed in this round.

## 2026-06-26 stability refinement update

This follow-up pass intentionally avoided framework rewrites and focused on making each
HTML verifier stage more robust while preserving honest scoring.

Implemented:

- Added encoding-aware HTML reads in `html_adapter.py`.
  - Tries `utf-8-sig`, `utf-8`, `gb18030`, then `latin-1`.
  - Records read diagnostics instead of silently dropping undecodable text.
- Hardened `html_runtime_adapter_v2.py`.
  - Chrome/CDP/screenshot failures now become structured `browser_status` values.
  - If Chrome is unavailable, the adapter falls back to static DOM text extraction.
  - The verifier still records visual unavailability through warnings and confidence;
    it does not pretend visual QA succeeded.
- Added HTML parse diagnostics in `run_eval_v2.py`.
  - `html_parse_status`
  - `parse_quality`
  - `report_likeness`
  - `report_likeness_reasons`
- Added report-likeness pressure to `v2_checks.py`.
  - Navigation/landing/empty pages get explicit `low_report_likeness` and
    `html_parse_low_confidence` issues.
  - Structure score is capped when the extracted body does not look like a strategy
    report.
- Added `quality_score` and `evaluation_confidence` in `scoring_v2.py`.
  - `quality_score` remains the actual report score.
  - `evaluation_confidence` separately records parse/runtime uncertainty.
- Added `report_likeness_min` to the `html_skill_iteration` gate.
- Expanded `run_html_batch.py` summaries.
  - `summary.csv` now includes parse status, parse quality, report-likeness,
    confidence, browser status, adapter warnings, and top issue.

Validation metrics from this pass:

- Functional HTML baseline before this pass:
  - Manifest: `evals/strategy_report/html_functional_manifest.csv`
  - Requested/completed/failed: 4 / 4 / 0
  - Average score: 77.70
  - Gate pass count: 3 / 4
- Functional HTML after this pass:
  - Requested/completed/failed: 4 / 4 / 0
  - Average score: 76.57
  - Gate pass count: 3 / 4
  - Parse status: `ok=4`
  - Browser status: `ok=4`
  - Average evaluation confidence: 0.950
  - Minimum evaluation confidence: 0.800
  - Average report-likeness: 0.800
  - Minimum report-likeness: 0.420
- Temporary parser-robustness edge fixtures:
  - Fixtures: empty HTML, navigation-like HTML, GBK Chinese HTML, malformed HTML.
  - Requested/completed/failed: 4 / 4 / 0
  - All 4 failed the quality gate honestly.
  - Score range: 25.17 to 28.61.
  - Report-likeness range: 0.00 to 0.22.
  - Evaluation-confidence range: 0.00 to 0.29.
- Forced Chrome-missing probe:
  - Adapter completed with `browser_status.status=chrome_not_found`.
  - Static fallback extracted 50,592 text characters from a functional HTML sample.
  - Warnings included `html_no_visual_objects` and `html_browser_chrome_not_found`.
- Reference-based regression smoke:
  - Command used `run_eval.py --cases-dir evals/strategy_report/cases_merged33 --max-cases 1 --no-extract-charts`.
  - Result: `eastmoney_cn_strategy_001: 80.78 Silver gate=True`.

## Known risks / next candidates

- The local golden HTML set remains relatively small. After this round, add or collect
  more difficult local HTML samples: SPA-like pages, very long pages, table-heavy pages,
  generated reports with many SVG/canvas figures, and reports with decorative hero art.
- Current visual role inference is heuristic. It should be calibrated against a larger
  HTML corpus before high-confidence scoring claims are made.
- The `html_skill_iteration` profile intentionally relaxes source/fact gates. Use a
  stricter profile when source traceability or numeric claim verification becomes a
  production requirement.
