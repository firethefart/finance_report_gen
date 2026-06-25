# Verifier V2 HTML Test Set Expansion Plan

## Current Inventory

Repository scan results:

- Total `.html` files in repo, excluding `.venv` and `LangAlpha`: 253.
- `dataset_build` HTML files: 198.
- `evals` HTML files: 53, mostly dashboards/results plus 3 synthetic fixtures.
- `generation_test` HTML files: 2 generated reports.
- Report-like HTML files after excluding dashboards, normalized adapter outputs, review pages, and result pages: 72.
- Unique report-like stems: 47.

For V2 development, the cleanest de-duplicated input pool is:

```text
evals/strategy_report/results/v2_html_inventory.json
```

This inventory currently contains 27 rows:

- 22 crawled strategy-report HTML files from `dataset_build/curated_strategy_samples_final`.
- 2 generated local reports from `generation_test`.
- 3 synthetic HTML fixtures from `evals/strategy_report/html_fixtures`.

### Distribution

By group:

| Group | Count | Notes |
| --- | ---: | --- |
| curated_final | 22 | Real crawled institutional strategy-report-like HTML. Many rely on missing/remote resources. |
| generated | 2 | Local generated Chinese HTML reports. Most representative of future agent-generated input. |
| fixtures | 3 | Synthetic edge cases for adapter regression, not full reports. |

By subtype:

| Subtype | Count |
| --- | ---: |
| thematic_strategy | 10 |
| annual_outlook | 5 |
| asset_allocation | 3 |
| fixed_income | 2 |
| equity_strategy | 1 |
| midyear_outlook | 1 |
| generated | 2 |
| fixtures | 3 |

By inferred source:

| Source | Count |
| --- | ---: |
| Goldman Sachs AM | 6 |
| Vanguard | 5 |
| State Street | 3 |
| Morgan Stanley | 3 |
| BlackRock/BII | 2 |
| J.P. Morgan | 2 |
| CMS/Chinese mirror | 1 |
| Generated local | 2 |
| Synthetic fixture | 3 |

## Quality Reading Of Current Pool

### Strong candidates for V2 testing

The two generated local HTML reports are currently the best V2 smoke inputs because they are self-contained and resemble future agent outputs:

- `generation_test/0/index.html`
- `generation_test/1/index.html`

The synthetic fixtures are useful for adapter regression, not scoring calibration:

- `runtime_v2_canvas_dynamic.html`: JavaScript/canvas rendering.
- `runtime_v2_long_visual.html`: oversized visual object, no fixed page split.
- `runtime_v2_static_report.html`: simple static visual blocks.

Some crawled HTML reports have strong text but missing visual resources. They are useful as stress tests for adapter warnings and robustness, but less ideal for score calibration:

- Goldman pages: long text, many missing image resources.
- State Street pages: many SVG/visual objects and publisher shell/cookie elements.
- BlackRock pages: useful text, sometimes no usable visual objects after missing assets.
- J.P. Morgan pages: very large visual/noisy DOM counts, likely publisher-shell heavy.

### Current weakness

The V2 test set is too small and skewed:

- Only 2 full self-contained generated HTML reports.
- Real crawled HTML is mostly English and often resource-incomplete.
- Chinese HTML examples are almost absent except generated reports and one CMS mirror-like page.
- Chart-library cases are underrepresented: ECharts, Plotly, SVG charts, canvas charts, tables, KPI panels, multi-chart pages.
- Need both high-quality and deliberately flawed reports to validate score sensitivity.

## Expansion Targets

Recommended near-term V2 HTML test set size: 30-50 HTML reports.

Target composition:

| Type | Count | Purpose |
| --- | ---: | --- |
| Generated high-quality Chinese reports | 10-12 | Primary V2 target shape; self-contained, realistic. |
| Generated flawed Chinese reports | 6-8 | Calibrate failure modes: weak sourcing, no risk, bad chart labels, overclaiming. |
| Generated English reports | 6-8 | Cross-language behavior and institutional style. |
| Real crawled HTML stress cases | 8-12 | Publisher shell, missing resources, external dependencies, noisy DOM. |
| Synthetic adapter fixtures | 4-6 | Regression only: long visuals, canvas, lazy loading, multi-chart pages. |

## Expansion Methods

### 1. Generate self-contained HTML reports

This should be the first expansion path because V2 will mainly evaluate agent-generated HTML.

Generate reports with:

- Inline CSS and no external network dependencies.
- Embedded SVG/canvas or inline chart data.
- Clear strategy-report sections:
  - executive summary
  - thesis
  - evidence/source table
  - strategy reasoning
  - scenario/risk
  - chart/table section
  - conclusion
  - disclaimer
- Chinese and English variants.
- Multiple chart styles:
  - table
  - KPI cards
  - bar chart
  - line chart
  - scenario probability chart
  - multi-chart page
  - long table
  - source footnotes

Use LLM generation for content plus deterministic template rendering. Prefer saving the generation spec/metadata next to each HTML:

```text
dataset_build/v2_html_generated/
  high_quality_zh/
  flawed_zh/
  high_quality_en/
  flawed_en/
```

Each sample should include:

```json
{
  "sample_id": "...",
  "language": "zh|en",
  "quality_intent": "high|flawed",
  "topic": "...",
  "expected_strengths": [],
  "intentional_flaws": [],
  "chart_types": [],
  "source_style": "inline links|source table|weak/no source",
  "notes": ""
}
```

### 2. Convert existing PDF strategy reports to controlled HTML

Use already curated Chinese/English PDFs as content sources, then ask an LLM or deterministic converter to produce self-contained HTML summaries/reports. This gives more realistic strategy content while preserving local resource stability.

Good for:

- Chinese expert-readable cases.
- Reports with real strategy structure.
- Comparing V1 PDF-oriented expectations with V2 HTML-oriented scoring.

Risk:

- Conversion may introduce hallucinated sections unless prompts force traceability.

### 3. Keep a small real-crawled HTML stress suite

Use `curated_strategy_samples_final` as a robustness suite, not the main calibration set.

Suggested initial real HTML stress set:

- Goldman annual outlook / asset allocation: missing image resources.
- State Street annual outlook: cookie/share/modal cleanup and many SVG candidates.
- BlackRock/BII thematic or asset allocation: text retained but visuals may be absent.
- Morgan Stanley midyear/equity: publisher DOM with many visual resources.
- J.P. Morgan pages: noisy DOM stress case.

Purpose:

- Adapter warning correctness.
- Resource audit correctness.
- Avoiding broken-image screenshots.
- V2 gate behavior when visual resources are missing.

### 4. Add more synthetic adapter fixtures

Add 2-3 fixtures for edge cases we do not yet cover:

- Lazy-loaded chart appears after scroll.
- Two charts side by side with shared page text.
- External CDN chart library fallback: local inline script version preferred.
- Very long table with sticky header.
- Decorative hero image plus real chart later, to test visual gate.

## Suggested Next Execution Order

1. Create `dataset_build/v2_html_generated/manifest.json`.
2. Generate 12 self-contained Chinese HTML reports:
   - 8 high quality
   - 4 flawed
3. Generate 6 English HTML reports:
   - 4 high quality
   - 2 flawed
4. Add 3 synthetic fixtures for adapter edges.
5. Select 8 real crawled HTML stress cases from `curated_strategy_samples_final`.
6. Run `run_eval_v2.py` rules-only over all candidates.
7. Run LLM-enabled V2 on a stratified subset of 6-8 cases.
8. Build a V2 dashboard sorted by:
   - source
   - intended quality
   - language
   - gate result
   - score delta between rules-only and LLM-enabled.

## Acceptance Criteria For The Expanded Test Set

The expanded V2 HTML test set should include:

- At least 20 full reports with `text_length > 2500`.
- At least 15 self-contained reports with no missing static resources.
- At least 15 reports with 2+ visual objects.
- At least 8 Chinese reports suitable for expert review.
- At least 6 intentionally flawed reports with documented flaws.
- At least 5 real crawled HTML stress cases with explicit resource warnings.

## Immediate Recommendation

Do not spend the next round crawling first. The highest-value next step is to generate a controlled V2 HTML suite because it matches the future deployment scenario and gives known expected quality/flaws. Crawled HTML should remain a robustness/stress supplement.
