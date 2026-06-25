# HTML Runtime Adapter V2

This adapter is the first input layer for the candidate-only strategy report verifier V2. It targets local or crawled HTML reports and converts them into verifier-friendly artifacts without relying on a reference PDF or golden metadata.

## Why V2 Exists

The older HTML path could render an HTML file to a PDF-like page sequence, but fixed-height page slicing can split one visual across two pages. That is risky for chart QA because a cropped or half-visible chart can make the VLM judge score the wrong object.

Runtime Adapter V2 uses a browser runtime instead:

1. Normalize the source HTML and remove obvious overlays such as cookie banners and share widgets.
2. Render the page in headless Chrome through the Chrome DevTools Protocol.
3. Execute page JavaScript and scroll the document so lazy/dynamic content has a chance to render.
4. Collect visual objects by DOM selector and bounding box.
5. Capture one full-page screenshot plus per-object target and context screenshots.
6. Emit text, headings, links, resource audit, visual inventory, and warnings.

## Windows Browser Work Path

Chrome does not navigate directly to the formal `normalized.html` output path.
The adapter writes the same normalized document to a short temporary `n.html`
path, navigates Chrome to that work copy, and deletes it after capture. The
normalized HTML keeps its source-directory base URL, so localized report assets
continue to resolve from the audited source bundle.

`adapter_manifest.json` records the formal path length, actual browser URL,
browser path length, navigation frame id, and temporary-copy cleanup status
under `browser_navigation`. A CDP navigation error or a final
`chrome-error://` URL now fails the adapter instead of producing a misleading
low-scoring report.

## Pagination Strategy

HTML is not treated as fixed pages. The adapter records:

- `full_page.png`: a long page overview, capped for practical dashboard display.
- `*_target.png`: exact DOM bounding-box crop for each visual object.
- `*_context.png`: a surrounding vertical window centered on the visual.

This avoids splitting one chart because of arbitrary page height. Very large visuals are marked with `oversized_visual=true` and the manifest adds `html_has_oversized_visuals`.

## Main Outputs

For each adapted report:

- `normalized.html`: cleaned HTML used for rendering.
- `adapter_manifest.json`: high-level status, counts, warnings, and resource summary.
- `report_text.json`: rendered document text, headings, links, numbers, dates, and document size.
- `visual_objects.json`: visual inventory with target/context screenshot paths.
- `layout_snapshot.json`: viewport, document geometry, headings, and full-page screenshot path.
- `screenshots/*.png`: full-page screenshots.
- `visuals/*_target.png` and `visuals/*_context.png`: chart/table/KPI candidate images.

## Warnings

- `html_static_resource_missing`: local referenced resources were not found.
- `html_has_external_resources`: the file depends on remote assets.
- `html_text_too_short_for_strategy_report`: rendered text is probably too short for a full strategy report.
- `html_no_visual_objects`: no usable visual object was captured.
- `html_has_oversized_visuals`: at least one visual is larger than the viewport.
- `html_broken_visual_resources`: image-like visual candidates were skipped because the browser reported broken/unloaded image resources.

## Regression Set

The regression manifest is:

```text
evals/strategy_report/html_runtime_test_set.json
```

Run it with:

```powershell
.\.venv\Scripts\python.exe evals\strategy_report\run_html_runtime_test_set.py --out-dir evals\strategy_report\results\html_runtime_v2_regression --max-visuals 40
```

Current baseline:

- 7 / 7 samples completed.
- Generated local HTML report: text and visual objects captured.
- Synthetic long visual: captured as one target object and marked oversized.
- Synthetic canvas chart: JavaScript-rendered canvas captured successfully.
- Crawled Goldman HTML: text retained; broken image resources skipped and recorded.
- Crawled State Street HTML: cookie/share/modal shell cleaned while article text remains.
- Crawled BlackRock HTML: article text retained; missing visual assets surfaced as warnings.

## Known Limits

- DOM selectors intentionally favor recall. Downstream VLM gate should still decide whether a visual object is a true financial chart/table/KPI.
- Remote resources are audited but not downloaded. For offline evaluation, missing resources become explicit warnings rather than hard failures.
- Full-page screenshot height is capped for size, but individual visual target/context screenshots remain the primary QA input.
- Very complex single-page apps may require a longer render wait or site-specific readiness checks later.
