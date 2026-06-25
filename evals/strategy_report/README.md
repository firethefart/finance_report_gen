# Strategy Report Automated Evaluation

This harness implements the automated scoring plan in `strategy_report_eval_standard.md`.

Default calibration mode evaluates each golden case by using its original public report as the candidate report. Later, pass a generated report with `--candidate-report` to evaluate the generation pipeline on the same case.

## Flow

1. Build case JSON from extracted golden metadata.
2. Parse candidate PDF/HTML with the existing dataset extractors.
3. Run nine automated modules:
   - render and delivery
   - section coverage
   - source quality
   - claim-citation alignment
   - numeric and entity consistency
   - strategy reasoning rule signals
   - scenario and risk coverage
   - chart QA
   - compliance redline
4. Optionally run one consolidated LLM judge for professional reasoning, evidence, chart usefulness, layout, and compliance nuance.
5. Aggregate to the 100-point weighted rubric and write JSON + Markdown.

## Commands

```powershell
.\.venv\Scripts\python.exe evals\strategy_report\case_builder.py
.\.venv\Scripts\python.exe evals\strategy_report\run_eval.py --max-cases 1 --render-pages 1
.\.venv\Scripts\python.exe evals\strategy_report\run_eval.py --case evals\strategy_report\cases\strategy_sample_001.json --enable-llm-judge --render-pages 1
```

Use LLM judge sparingly during development. Rule-only checks are intended for cheap unit and smoke testing.

## Current Smoke Results

As of the first implementation pass:

- Unit tests: `4 passed`.
- Rule-only smoke on 2 cases: both pass gate.
- Rule-only calibration on all 27 golden cases: all files parse; useful for calibration, with strict gates surfacing lower-scoring cases.
- LLM smoke on `strategy_sample_001`: OpenRouter `deepseek/deepseek-v4-pro` returns structured JSON when `max_tokens=4200`; result is Silver and gate pass.

The first LLM smoke used too small a `max_tokens` budget and the model spent the completion budget on reasoning without content. Keep the larger token cap unless the model/provider behavior changes.

## Cost Control

- Prefer `python -m unittest evals\strategy_report\test_eval_units.py` and rule-only `run_eval.py` during development.
- Use `--enable-llm-judge` only on 1-2 cases while changing prompts or aggregation.
- The LLM judge is one consolidated call per case, rather than separate calls for each rubric dimension.

## Known Calibration Notes

- The current parser enriches PDF text with head pages and tail pages so disclaimers and appendices are visible.
- Rule-only scoring is intentionally strict on source traceability, numeric preservation, and compliance disclaimers.
- Some golden original reports score Bronze/Reject under rule-only mode because the deterministic checks cannot always see chart internals or source context. Use those cases to calibrate thresholds against human review before using the gate as a hard CI blocker.

## Chart QA V2

The chart module now builds a chart-level inventory before scoring. For each detected chart/table candidate it saves:

- page number and bounding box
- screenshot crop when available
- nearby text
- title/caption/source/unit/date/number hints
- expected benchmark chart match when confidence is high
- chart-level subscores and issues

For PDFs, screenshot extraction now uses one stable `page_body_chart` crop per analytical chart page. It clips only thin page margins and footers, preserving the full body visualization, surrounding explanation, axis labels, legends, and source notes. This intentionally avoids narrow crops around sidebar text, footnotes, or individual text blocks.

Run chart QA without VL cost:

```powershell
.\.venv\Scripts\python.exe evals\strategy_report\run_eval.py --case evals\strategy_report\cases\strategy_sample_001.json --chart-max-pages 25 --chart-max-charts 8 --out-dir evals\strategy_report\results\chart_smoke_v3
.\.venv\Scripts\python.exe evals\strategy_report\build_chart_dashboard.py --results-dir evals\strategy_report\results\chart_smoke_v3
```

The review dashboard is written to:

```text
evals/strategy_report/results/chart_smoke_v3/chart_dashboard.html
```

Optional VL judge, use sparingly:

```powershell
.\.venv\Scripts\python.exe evals\strategy_report\run_eval.py --case evals\strategy_report\cases\strategy_sample_001.json --enable-chart-vl-judge --chart-vl-max-charts 3 --out-dir evals\strategy_report\results\chart_vl_smoke
```

Chart QA V2 scores six subscores: inventory, spec completeness, data faithfulness, chart-text alignment, visual clarity, and financial appropriateness. Data faithfulness and chart-text alignment are hard-threshold dimensions: below 0.5 they produce high-severity issues.

The next VLM iteration is specified in `chart_vl_checklist_design.md`. It moves the VL judge from coarse subscore grading to an auditable checklist flow:

- universal checklist items for almost all financial visualizations
- contextual checklist items generated per chart/table
- evidence-backed checklist scoring
- explicit separation between structured numeric checks and VLM visual/text-alignment checks
- export-ready fields for a 30-50 chart human-alignment set

## Chart Object Alignment Smoke

The chart evaluator now carries both object-level context and full-page context:

- `nearby_text` is kept as the local text around the detected visual object.
- `page_text` stores the full page text used by chart-text alignment checks.
- `page_text_blocks` stores ordered page spans with bounding boxes when available.
- `object_index`, `object_count_on_page`, and `object_role` reserve fields for future multi-chart page splitting.

This lets rule and VL judges evaluate a "current visualization + full page text" pair. On pages with multiple visuals, the judge should search the full page text for the matching explanation instead of assuming the nearest text belongs to the current visual.

Five-case chart smoke without VL cost:

```powershell
$out='evals\strategy_report\results\chart_object_smoke5'
foreach ($id in '001','002','003','004','032') {
  .\.venv\Scripts\python.exe evals\strategy_report\run_eval.py --case "evals\strategy_report\cases\strategy_sample_$id.json" --render-pages 0 --chart-max-pages 25 --chart-max-charts 8 --out-dir $out --no-cache
}
.\.venv\Scripts\python.exe evals\strategy_report\build_chart_dashboard.py --results-dir $out
```

The dashboard is written to:

```text
evals/strategy_report/results/chart_object_smoke5/chart_dashboard.html
```

Full five-case VLM chart QA with target-crop screenshots, full-page screenshots, and raw VL judge responses:

```powershell
$out='evals\strategy_report\results\chart_vl_full_smoke5'
foreach ($id in '001','002','003','004','032') {
  .\.venv\Scripts\python.exe evals\strategy_report\run_eval.py --case "evals\strategy_report\cases\strategy_sample_$id.json" --render-pages 0 --chart-max-pages 25 --chart-max-charts 8 --enable-chart-vl-judge --chart-vl-max-charts 8 --out-dir $out --no-cache
}
.\.venv\Scripts\python.exe evals\strategy_report\build_chart_dashboard.py --results-dir $out --out "$out\index.html"
```

The VLM dashboard is written to:

```text
evals/strategy_report/results/chart_vl_full_smoke5/index.html
```

The checklist VLM judge now starts with a lightweight visual gate. If the target
crop is a table of contents, cover/section divider, pure text page, logo/sidebar,
footer, or another non-analytical artifact, the judge returns
`visual_gate.decision = "skip_checklist"` and does not run U1-U12 or contextual
checklist items. These candidates are kept in the dashboard as extractor false
positives, but excluded from report-level chart-score averages via
`excluded_from_chart_score = true`.

Crop-accuracy iteration dashboard without VLM cost:

```powershell
$out='evals\strategy_report\results\chart_crop90_smoke5'
foreach ($id in '001','002','003','004','032') {
  .\.venv\Scripts\python.exe evals\strategy_report\run_eval.py --case "evals\strategy_report\cases\strategy_sample_$id.json" --render-pages 0 --chart-max-pages 25 --chart-max-charts 8 --out-dir $out --no-cache
}
.\.venv\Scripts\python.exe evals\strategy_report\build_chart_dashboard.py --results-dir $out --out "$out\index.html"
```

Full 27-case crop-only validation:

```powershell
$out='evals\strategy_report\results\chart_crop90_all27'
Get-ChildItem evals\strategy_report\cases -Filter "strategy_sample_*.json" | Sort-Object Name | ForEach-Object {
  .\.venv\Scripts\python.exe evals\strategy_report\run_eval.py --case $_.FullName --render-pages 0 --chart-max-pages 25 --chart-max-charts 8 --out-dir $out --no-cache
}
.\.venv\Scripts\python.exe evals\strategy_report\build_chart_dashboard.py --results-dir $out --out "$out\index.html"
```
