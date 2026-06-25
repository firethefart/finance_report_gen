# HTML Report Adapter

Updated: 2026-06-16

`html_adapter.py` is a first-pass compatibility layer for using the strategy-report verifier on local or generated HTML reports.

The design goal is to avoid changing the main verifier pipeline. HTML is first frozen into verifier-friendly artifacts, then the existing parser, chart extractor, Chart QA, Claim/Numeric, Strategy Reasoning, and scoring modules can continue to operate.

## Current Entry Point

```powershell
.\.venv\Scripts\python.exe evals\strategy_report\html_adapter.py `
  --html generation_test\1\index.html `
  --out-dir evals\strategy_report\results\html_adapter_smoke_generation_test_1 `
  --report-id generation_test_1 `
  --max-charts 30
```

## Outputs

The adapter writes a small package:

```text
adapter_out/
  normalized.html          # cleaned HTML with local base URL
  rendered.pdf             # Chrome-rendered PDF for the existing PDF verifier path
  report_text.json         # extracted title/headings/text/numbers/dates
  chart_candidates.json    # static HTML chart/table/img candidates
  render_manifest.json     # health, resource, screenshot, cleanup audit
  screenshots/
    *_page_001.png         # browser screenshot
  chart_inventory/
    <report_id>/
      *.jpg                # rendered table/img previews
```

## Current Capabilities

- Parses local HTML with BeautifulSoup.
- Audits static resources:
  - local exists / local missing
  - remote resource
  - inline data URI
  - unsupported scheme
- Removes common overlay-like nodes conservatively:
  - cookie/consent
  - newsletter/subscribe
  - modal/popup/overlay
  - share/social/ad-like blocks
- Captures a headless Chrome screenshot.
- Renders the HTML to `rendered.pdf` with headless Chrome.
- Extracts static chart candidates through the existing HTML chart extractor:
  - `figure`
  - `table`
  - `img`
  - `svg`
  - `canvas`
- Uses CJK-capable fonts for static table/text previews where available.

## Recommended Integration Path

Minimal change path:

```text
HTML report
  -> html_adapter.py
  -> rendered.pdf
  -> existing parse_candidate_report(fmt="pdf")
  -> existing extract_chart_candidates(fmt="pdf")
  -> existing verifier modules
```

This is the safest path for generated HTML reports because it converts HTML into a stable paginated artifact before the normal verifier runs.

Alternative path:

```text
HTML report
  -> html_adapter.py
  -> chart_candidates.json
  -> directly attach as parsed["chart_inventory"]
```

This preserves HTML DOM chart candidates, but currently lacks precise browser element bboxes unless Playwright or Chrome DevTools support is added later.

## Smoke Test Result

Tested on:

```text
generation_test/1/index.html
```

Result:

- `screenshot.ok = true`
- `rendered_pdf.ok = true`
- `text_length = 3689`
- `heading_count = 21`
- `chart_candidate_count = 1`
- `warnings = []`

The generated `rendered.pdf` was also parsed successfully by the existing PDF parser, and the existing PDF chart extractor found visual candidates from it.

## Known Limitations

- The first-page screenshot uses a configured viewport height; it is not yet a full scrolling screenshot.
- Static HTML candidate previews are lossy for long tables; full text remains available in `nearby_text/page_text`.
- JavaScript-rendered charts are best handled through `rendered.pdf` today.
- Precise DOM element screenshots for ECharts/Highcharts/Plotly would require a Playwright or Chrome DevTools layer.
- Remote resource downloading is audited but not yet fully rewritten into a self-contained HTML bundle.

## Next Upgrade

Recommended next step is an optional browser-backed mode:

```text
--browser-dom-crops
```

It should:

- Execute JavaScript.
- Wait for network idle and chart containers to render.
- Scroll through the report to trigger lazy loading.
- Capture DOM element screenshots with exact bounding boxes.
- Split long HTML into virtual pages with viewport screenshots and page text.
