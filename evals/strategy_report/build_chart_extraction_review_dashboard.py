from __future__ import annotations

import argparse
import base64
import html
import json
import os
from pathlib import Path
from urllib.parse import quote

from eval_utils import ROOT, read_json, write_text


def href_for(path: str | Path | None, base_dir: Path) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if is_under_root(p):
        rel = Path(os.path.relpath(p, base_dir))
        return quote(rel.as_posix(), safe="/:#?&=%")
    return quote(p.as_posix(), safe="/:#?&=%")


def is_under_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def image_data_uri(path: str | Path | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return ""
    suffix = p.suffix.lower().lstrip(".") or "jpeg"
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{data}"


def collect_rows(results_dir: Path, out_file: Path) -> list[dict]:
    rows: list[dict] = []
    inventory_dir = results_dir / "chart_inventory"
    for inventory_path in sorted(inventory_dir.glob("*.charts.json")):
        inventory = read_json(inventory_path)
        source_path = inventory.get("source_path") or ""
        audit = inventory.get("audit") or {}
        charts = inventory.get("charts") or []
        for chart in charts:
            rows.append(
                {
                    "report_id": inventory.get("report_id"),
                    "source_path": source_path,
                    "pdf_href": href_for(source_path, out_file.parent),
                    "chart_id": chart.get("chart_id"),
                    "page": chart.get("page"),
                    "title": chart.get("title") or chart.get("caption") or "",
                    "bbox": chart.get("bbox"),
                    "method": chart.get("detection_method"),
                    "tier": chart.get("candidate_tier"),
                    "score": chart.get("candidate_score"),
                    "signals": chart.get("candidate_signals") or [],
                    "warnings": chart.get("warnings") or [],
                    "page_type": chart.get("page_type"),
                    "page_signals": chart.get("page_signals") or [],
                    "crop_quality": chart.get("crop_quality") or {},
                    "nearby_text": chart.get("nearby_text") or "",
                    "image_data": image_data_uri(chart.get("image_path")),
                    "page_image_data": image_data_uri(chart.get("page_image_path")),
                }
            )
        if not charts:
            rows.append(
                {
                    "report_id": inventory.get("report_id"),
                    "source_path": source_path,
                    "pdf_href": href_for(source_path, out_file.parent),
                    "chart_id": f"{inventory.get('report_id')}_no_charts",
                    "page": None,
                    "title": "No chart candidates extracted",
                    "bbox": None,
                    "method": "",
                    "tier": "",
                    "score": None,
                    "signals": [],
                    "warnings": ["no_chart_candidates"],
                    "page_type": "",
                    "page_signals": [],
                    "crop_quality": {},
                    "nearby_text": json.dumps(audit, ensure_ascii=False, indent=2),
                    "image_data": "",
                    "page_image_data": "",
                }
            )
    return rows


def build_html(rows: list[dict], title: str) -> str:
    payload = json.dumps(rows, ensure_ascii=False)
    escaped_title = html.escape(title)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escaped_title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d9dee7;
      --ink: #172033;
      --muted: #667085;
      --accent: #155eef;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--ink); }}
    header {{ height: 56px; display: flex; align-items: center; gap: 12px; padding: 0 16px; border-bottom: 1px solid var(--line); background: var(--panel); }}
    h1 {{ font-size: 16px; margin: 0 12px 0 0; white-space: nowrap; }}
    select, button {{ height: 34px; border: 1px solid var(--line); background: white; border-radius: 6px; padding: 0 10px; color: var(--ink); }}
    button {{ cursor: pointer; }}
    button:hover {{ border-color: var(--accent); }}
    .count {{ margin-left: auto; color: var(--muted); font-size: 13px; }}
    main {{ display: grid; grid-template-columns: minmax(380px, 42vw) 1fr; height: calc(100vh - 56px); }}
    .left {{ overflow-y: auto; border-right: 1px solid var(--line); background: var(--panel); }}
    .right {{ min-width: 0; background: #20242c; }}
    iframe {{ width: 100%; height: 100%; border: 0; background: #30343c; }}
    .card {{ padding: 14px 16px 18px; border-bottom: 1px solid var(--line); }}
    .meta {{ display: grid; grid-template-columns: 92px 1fr; gap: 6px 10px; font-size: 13px; margin: 10px 0; }}
    .label {{ color: var(--muted); }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
    .chip {{ border: 1px solid var(--line); background: #f8fafc; border-radius: 999px; padding: 3px 8px; font-size: 12px; }}
    .tier1 {{ border-color: #159947; color: #087443; }}
    .tier2 {{ border-color: #d98b00; color: #985900; }}
    .tier3 {{ border-color: #d92d20; color: #b42318; }}
    .image-wrap {{ margin-top: 10px; border: 1px solid var(--line); background: #f8fafc; min-height: 160px; display: flex; align-items: center; justify-content: center; }}
    .image-wrap img {{ max-width: 100%; max-height: 56vh; object-fit: contain; display: block; }}
    .empty {{ color: var(--muted); padding: 32px; text-align: center; }}
    details {{ margin-top: 10px; border: 1px solid var(--line); border-radius: 6px; background: #fbfcfe; }}
    summary {{ cursor: pointer; padding: 8px 10px; color: var(--muted); }}
    pre {{ margin: 0; padding: 10px; max-height: 260px; overflow: auto; white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.45; }}
    @media (max-width: 900px) {{
      main {{ grid-template-columns: 1fr; grid-template-rows: 50vh 50vh; }}
      .left {{ border-right: 0; border-bottom: 1px solid var(--line); }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{escaped_title}</h1>
    <button id="prev">上一张</button>
    <button id="next">下一张</button>
    <select id="report"></select>
    <select id="sort">
      <option value="default">默认排序</option>
      <option value="page">按 page 排序</option>
      <option value="score">按 score 排序</option>
    </select>
    <select id="chart"></select>
    <span class="count" id="count"></span>
  </header>
  <main>
    <section class="left" id="left"></section>
    <section class="right"><iframe id="pdf"></iframe></section>
  </main>
  <script>
    const rows = {payload}.map((row, originalIndex) => ({{...row, originalIndex}}));
    let index = 0;
    const reportSelect = document.getElementById('report');
    const chartSelect = document.getElementById('chart');
    const sortSelect = document.getElementById('sort');
    const left = document.getElementById('left');
    const pdf = document.getElementById('pdf');
    const count = document.getElementById('count');
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    const reports = [...new Set(rows.map(r => r.report_id))];
    reportSelect.innerHTML = reports.map(r => `<option value="${{esc(r)}}">${{esc(r)}}</option>`).join('');
    function sortedRows() {{
      const mode = sortSelect.value;
      const report = reportSelect.value;
      const filtered = rows.filter(r => r.report_id === report);
      if (mode === 'page') {{
        return filtered.slice().sort((a, b) =>
          (a.page ?? 99999) - (b.page ?? 99999) ||
          (a.bbox?.[1] ?? 99999) - (b.bbox?.[1] ?? 99999) ||
          (a.bbox?.[0] ?? 99999) - (b.bbox?.[0] ?? 99999) ||
          a.originalIndex - b.originalIndex
        );
      }}
      if (mode === 'score') {{
        return filtered.slice().sort((a, b) =>
          (b.score ?? -1) - (a.score ?? -1) ||
          (a.page ?? 99999) - (b.page ?? 99999) ||
          a.originalIndex - b.originalIndex
        );
      }}
      return filtered.slice().sort((a, b) => a.originalIndex - b.originalIndex);
    }}
    function tierClass(tier) {{
      if ((tier || '').includes('tier_1')) return 'tier1';
      if ((tier || '').includes('tier_2')) return 'tier2';
      return 'tier3';
    }}
    function refreshChartSelect() {{
      const filtered = sortedRows();
      chartSelect.innerHTML = filtered.map((r, k) => `<option value="${{r.originalIndex}}">#${{k + 1}} p${{r.page ?? '-'}} ${{esc(r.method || '')}} ${{r.score ?? ''}}</option>`).join('');
      if (!filtered.some(r => r.originalIndex === index)) index = filtered[0]?.originalIndex ?? 0;
      chartSelect.value = String(index);
    }}
    function render() {{
      if (!rows.length) {{
        left.innerHTML = '<div class="empty">没有找到 chart inventory</div>';
        return;
      }}
      const r = rows[index];
      reportSelect.value = r.report_id;
      refreshChartSelect();
      chartSelect.value = String(index);
      const pdfHref = r.pdf_href ? `${{r.pdf_href}}${{r.page ? '#page=' + r.page : ''}}` : '';
      pdf.src = pdfHref;
      count.textContent = `${{index + 1}} / ${{rows.length}}`;
      const crop = r.crop_quality || {{}};
      const signalChips = [...(r.signals || []), ...(r.warnings || []).map(w => 'warn:' + w)];
      left.innerHTML = `
        <article class="card">
          <h2 style="font-size:15px;margin:0 0 6px;">${{esc(r.title || r.chart_id)}}</h2>
          <div class="chips">
            <span class="chip ${{tierClass(r.tier)}}">${{esc(r.tier || 'no_tier')}}</span>
            <span class="chip">score: ${{r.score ?? '-'}}</span>
            <span class="chip">page: ${{r.page ?? '-'}}</span>
            <span class="chip">${{esc(r.method || '-')}}</span>
          </div>
          <div class="image-wrap">${{r.image_data ? `<img src="${{r.image_data}}" alt="chart crop" />` : '<div class="empty">无 crop 图片</div>'}}</div>
          <div class="meta">
            <div class="label">report</div><div>${{esc(r.report_id)}}</div>
            <div class="label">chart_id</div><div>${{esc(r.chart_id)}}</div>
            <div class="label">bbox</div><div>${{esc(JSON.stringify(r.bbox))}}</div>
            <div class="label">page_type</div><div>${{esc(r.page_type || '-')}}</div>
            <div class="label">crop</div><div>${{esc(JSON.stringify(crop))}}</div>
          </div>
          <div class="chips">${{signalChips.map(s => `<span class="chip">${{esc(s)}}</span>`).join('')}}</div>
          <details open><summary>附近文本</summary><pre>${{esc(r.nearby_text || '')}}</pre></details>
          <details><summary>完整页截图</summary><div class="image-wrap">${{r.page_image_data ? `<img src="${{r.page_image_data}}" alt="full page" />` : '<div class="empty">无完整页截图</div>'}}</div></details>
        </article>
      `;
    }}
    function move(delta) {{
      const filtered = sortedRows();
      const pos = filtered.findIndex(r => r.originalIndex === index);
      const nextPos = pos >= 0 ? (pos + delta + filtered.length) % filtered.length : 0;
      index = filtered[nextPos]?.originalIndex ?? 0;
      render();
    }}
    document.getElementById('prev').onclick = () => move(-1);
    document.getElementById('next').onclick = () => move(1);
    reportSelect.onchange = () => {{ const first = rows.findIndex(r => r.report_id === reportSelect.value); index = Math.max(0, first); render(); }};
    sortSelect.onchange = () => {{ const first = sortedRows()[0]; index = first?.originalIndex ?? 0; render(); }};
    chartSelect.onchange = () => {{ index = Number(chartSelect.value); render(); }};
    render();
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a chart extraction recall/precision review dashboard.")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title", default="Chart Extraction Review")
    args = parser.parse_args()
    results_dir = args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = collect_rows(results_dir, out)
    write_text(out, build_html(rows, args.title))
    print(f"wrote {out} ({len(rows)} chart rows)")


if __name__ == "__main__":
    main()
