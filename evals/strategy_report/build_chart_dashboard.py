from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any

from eval_utils import ROOT, write_text


def load_chart_records(results_dir: Path, embed_images: bool = False) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*.eval.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        chart_qa = (result.get("module_results") or {}).get("chart_qa") or {}
        for chart in chart_qa.get("charts") or []:
            if embed_images:
                add_data_url(chart, "image_path", "image_href")
                add_data_url(chart, "page_image_path", "page_image_href")
            else:
                add_href(chart, "image_path", "image_href", results_dir)
                add_href(chart, "page_image_path", "page_image_href", results_dir)
            records.append(
                {
                    "case_id": result.get("case_id"),
                    "candidate_report": result.get("candidate_report"),
                    "overall_score": result.get("overall_score"),
                    "grade": result.get("grade"),
                    "chart_module_score": chart_qa.get("score"),
                    "chart_module_subscores": chart_qa.get("subscores"),
                    "chart": chart,
                }
            )
    return records


def add_href(chart: dict[str, Any], source_key: str, href_key: str, base: Path) -> None:
    value = chart.get(source_key)
    if not value:
        return
    try:
        chart[href_key] = rel_href(Path(value), base)
    except Exception:
        chart[href_key] = value


def add_data_url(chart: dict[str, Any], source_key: str, href_key: str) -> None:
    value = chart.get(source_key)
    if not value:
        return
    path = Path(value)
    if not path.exists():
        return
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    chart[href_key] = f"data:{mime};base64,{encoded}"


def rel_href(path: Path, base: Path) -> str:
    try:
        return os.path.relpath(path.resolve(), base.resolve()).replace("\\", "/")
    except ValueError:
        return str(path)


def build_html(records: list[dict[str, Any]], title: str) -> str:
    data = json.dumps(records, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(title)}</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --panel: #fff;
      --line: #d8dee9;
      --text: #172033;
      --muted: #657085;
      --accent: #0f766e;
      --bad: #b42318;
      --warn: #b54708;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; background: var(--bg); color: var(--text); }}
    header {{ position: sticky; top: 0; z-index: 5; background: rgba(255,255,255,.96); border-bottom: 1px solid var(--line); }}
    .topbar {{ display: grid; grid-template-columns: auto auto minmax(280px,1fr) auto auto; gap: 10px; align-items: center; padding: 10px 14px; }}
    button, select, input {{ height: 34px; border: 1px solid var(--line); background: #fff; border-radius: 6px; padding: 0 10px; font: inherit; }}
    button {{ cursor: pointer; font-weight: 700; }}
    button:hover {{ border-color: var(--accent); color: var(--accent); }}
    select {{ min-width: 320px; }}
    .layout {{ display: grid; grid-template-columns: minmax(440px, 45vw) minmax(500px, 1fr); gap: 12px; padding: 12px; height: calc(100vh - 55px); }}
    .pane {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; min-height: 0; overflow: hidden; }}
    .image-pane {{ display: grid; grid-template-rows: auto minmax(0, 1fr) minmax(0, 1fr); }}
    .pane-head {{ border-bottom: 1px solid var(--line); padding: 10px 12px; display:flex; align-items:center; justify-content:space-between; gap: 10px; }}
    .image-block {{ min-height: 0; display:grid; grid-template-rows:auto minmax(0, 1fr); border-top:1px solid var(--line); }}
    .image-label {{ padding: 8px 12px; font-weight:700; color:var(--muted); background:#f8fafc; border-bottom:1px solid var(--line); }}
    .image-wrap {{ overflow: auto; background: #eef2f7; display:flex; align-items:flex-start; justify-content:center; padding: 12px; }}
    img {{ max-width: 100%; height: auto; background:#fff; border:1px solid var(--line); }}
    .empty {{ padding: 24px; color: var(--muted); }}
    .detail {{ overflow: auto; padding: 14px; height: 100%; }}
    .grid {{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
    .field {{ border:1px solid var(--line); border-radius:6px; padding:8px; background:#fff; }}
    .label {{ display:block; color:var(--muted); font-size:12px; margin-bottom:4px; }}
    .value {{ white-space:pre-wrap; word-break:break-word; }}
    .score-row {{ display:grid; grid-template-columns: 220px 1fr auto; gap: 8px; align-items:center; margin: 6px 0; }}
    .bar {{ height: 10px; background:#e5e7eb; border-radius: 999px; overflow:hidden; }}
    .fill {{ height:100%; background: var(--accent); }}
    .issue {{ border-left: 4px solid var(--warn); padding: 8px 10px; background:#fff8eb; margin: 8px 0; }}
    .issue.high, .issue.blocker {{ border-left-color: var(--bad); background:#fff1f0; }}
    .checklist-item {{ border:1px solid var(--line); border-radius:6px; padding:9px; margin:8px 0; background:#fff; }}
    .check-head {{ display:grid; grid-template-columns: auto 1fr auto auto; gap:8px; align-items:center; }}
    .badge {{ border:1px solid var(--line); border-radius:999px; padding:3px 8px; font-size:12px; background:#f8fafc; color:var(--muted); }}
    .badge.universal {{ color:#155e75; border-color:#a5f3fc; background:#ecfeff; }}
    .badge.contextual {{ color:#6d28d9; border-color:#ddd6fe; background:#f5f3ff; }}
    .status-pass {{ color:#047857; }}
    .status-partial {{ color:#b54708; }}
    .status-fail {{ color:#b42318; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background:#f8fafc; border:1px solid var(--line); padding:10px; border-radius:6px; }}
    .text-box {{ max-height: 260px; overflow: auto; }}
    .text-box.tall {{ max-height: 360px; }}
    h3 {{ margin: 18px 0 8px; }}
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <button id="prevBtn">上一张</button>
      <button id="nextBtn">下一张</button>
      <select id="chartSelect"></select>
      <input id="searchInput" placeholder="搜索 case / 标题 / 文本 / issue / crop flag" />
      <span id="counter"></span>
    </div>
  </header>
  <main class="layout">
    <section class="pane image-pane">
      <div class="pane-head">
        <strong id="imageTitle">Chart</strong>
        <a id="imageLink" target="_blank" rel="noreferrer">打开截图</a>
      </div>
      <div class="image-block">
        <div class="image-label">目标可视化截图</div>
        <div id="imageWrap" class="image-wrap"></div>
      </div>
      <div class="image-block">
        <div class="image-label">完整页截图</div>
        <div id="pageImageWrap" class="image-wrap"></div>
      </div>
    </section>
    <section class="pane">
      <div id="detail" class="detail"></div>
    </section>
  </main>
  <script id="recordsData" type="application/json">{data}</script>
  <script>
    const records = JSON.parse(document.getElementById('recordsData').textContent);
    const $ = (id) => document.getElementById(id);
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    let filtered = records.map((_, index) => index);
    let current = 0;

    function scoreBar(label, value) {{
      const n = Number(value ?? 0);
      return `<div class="score-row"><span>${{esc(label)}}</span><div class="bar"><div class="fill" style="width:${{Math.max(0, Math.min(100, n * 100))}}%"></div></div><strong>${{n.toFixed(3)}}</strong></div>`;
    }}

    function renderSelect() {{
      $('chartSelect').innerHTML = filtered.map((idx, pos) => {{
        const r = records[idx], c = r.chart;
        return `<option value="${{pos}}">${{esc(r.case_id)}} | p${{esc(c.page)}} | ${{esc(c.title || c.chart_id)}}</option>`;
      }}).join('');
      $('chartSelect').value = String(current);
      render();
    }}

    function render() {{
      if (!filtered.length) {{
        $('imageWrap').innerHTML = '<div class="empty">没有匹配的图表。</div>';
        $('pageImageWrap').innerHTML = '<div class="empty">没有匹配的图表。</div>';
        $('detail').innerHTML = '';
        $('counter').textContent = '0 / 0';
        return;
      }}
      const r = records[filtered[current]];
      const c = r.chart;
      $('counter').textContent = `${{current + 1}} / ${{filtered.length}} | total ${{records.length}}`;
      $('imageTitle').textContent = `${{r.case_id}} | ${{c.chart_id || ''}}`;
      if (c.image_href) {{
        $('imageLink').href = c.image_href;
        $('imageWrap').innerHTML = `<img src="${{esc(c.image_href)}}" alt="chart screenshot" />`;
      }} else {{
        $('imageLink').href = '#';
        $('imageWrap').innerHTML = '<div class="empty">这个图表没有截图，可能来自 HTML table/snippet。</div>';
      }}
      if (c.page_image_href) {{
        $('pageImageWrap').innerHTML = `<img src="${{esc(c.page_image_href)}}" alt="full page screenshot" />`;
      }} else {{
        $('pageImageWrap').innerHTML = '<div class="empty">没有完整页截图。</div>';
      }}
      const subs = c.subscores || {{}};
      const issues = (c.issues || []).map(i => `<div class="issue ${{esc(i.severity)}}"><strong>[${{esc(i.severity)}}] ${{esc(i.issue_type)}}</strong><br>${{esc(i.description)}}<br><span>${{esc(i.location || '')}}</span></div>`).join('') || '<div class="empty">No chart-level issues.</div>';
      const vl = c.vl_judge || {{}};
      const checklist = renderChecklist(vl);
      $('detail').innerHTML = `
        <div class="grid">
          <div class="field"><span class="label">Case</span><div class="value">${{esc(r.case_id)}} / ${{esc(r.grade)}} / overall ${{esc(r.overall_score)}}</div></div>
          <div class="field"><span class="label">Chart Module</span><div class="value">${{esc(r.chart_module_score)}} | ${{esc(JSON.stringify(r.chart_module_subscores || {{}}))}}</div></div>
          <div class="field"><span class="label">Source / Method</span><div class="value">${{esc(c.source_format || 'unknown')}} | p${{esc(c.page)}} | ${{esc(c.detection_method)}} | ${{esc(c.chart_kind_hint)}}</div></div>
          <div class="field"><span class="label">Object</span><div class="value">${{esc(c.object_index || 1)}} / ${{esc(c.object_count_on_page || 1)}} | ${{esc(c.object_role || '')}}</div></div>
          <div class="field"><span class="label">Visual Gate</span><div class="value">${{esc(JSON.stringify({{excluded_from_chart_score: c.excluded_from_chart_score || false, skip_reason: c.skip_reason || null, gate: vl.visual_gate || null}}, null, 2))}}</div></div>
          <div class="field"><span class="label">Crop Quality</span><div class="value">${{esc(JSON.stringify(c.crop_quality || {{}}, null, 2))}}</div></div>
          <div class="field"><span class="label">Warnings</span><div class="value">${{esc(JSON.stringify(c.warnings || [], null, 2))}}</div></div>
          <div class="field"><span class="label">Expected Match</span><div class="value">${{esc(c.expected_match || 'None')}}</div></div>
          <div class="field"><span class="label">Unit</span><div class="value">${{esc(c.unit_hint || 'None')}}</div></div>
          <div class="field"><span class="label">Source Note</span><div class="value">${{esc(c.source_note || 'None')}}</div></div>
        </div>
        <h3>Scores</h3>
        ${{scoreBar('chart overall', c.score)}}${{scoreBar('spec completeness', subs.spec_completeness)}}${{scoreBar('data faithfulness', subs.data_faithfulness)}}${{scoreBar('chart-text alignment', subs.chart_text_alignment)}}${{scoreBar('visual clarity', subs.visual_clarity)}}${{scoreBar('financial appropriateness', subs.financial_appropriateness)}}
        <h3>Title</h3><pre class="text-box">${{esc(c.title || '')}}</pre>
        <h3>Object / Nearby Text</h3><pre class="text-box tall">${{esc(c.nearby_text || '')}}</pre>
        <h3>Full Page Text For Alignment Judge</h3><pre class="text-box tall">${{esc(c.page_text || c.nearby_text || '')}}</pre>
        <h3>Page Text Blocks</h3><pre class="text-box">${{esc(JSON.stringify(c.page_text_blocks || [], null, 2))}}</pre>
        <h3>Numbers / Dates</h3><pre class="text-box">${{esc(JSON.stringify({{numbers: c.numbers || [], dates: c.dates || []}}, null, 2))}}</pre>
        <h3>Issues</h3>${{issues}}
        <h3>VLM Checklist</h3>${{checklist}}
        <h3>VLM Subscores / Flags</h3><pre class="text-box tall">${{esc(JSON.stringify({{subscores: vl.subscores || {{}}, hard_flags: vl.hard_flags || [], overall_vlm_visual_score: vl.overall_vlm_visual_score, confidence: vl.confidence, review_notes: vl.review_notes}}, null, 2))}}</pre>
        <h3>VL Judge</h3><pre class="text-box tall">${{esc(JSON.stringify(c.vl_judge || {{skipped: true}}, null, 2))}}</pre>
      `;
    }}

    function renderChecklist(vl) {{
      if (!vl || !vl.ok) return '<div class="empty">No VLM checklist for this chart.</div>';
      if ((vl.visual_gate && vl.visual_gate.decision === 'skip_checklist') || vl.is_analytical_visual === false) {{
        return `<div class="issue high"><strong>Skipped by Visual Gate</strong><br>${{esc((vl.visual_gate && vl.visual_gate.reason) || vl.review_notes || 'This candidate is not an analytical visualization.')}}</div>`;
      }}
      const renderItems = (items, typeLabel, cls) => (items || []).map(item => {{
        const score = Number(item.score ?? 0);
        const status = String(item.status || '').replace('_', '-');
        return `<div class="checklist-item">
          <div class="check-head">
            <span class="badge ${{cls}}">${{esc(typeLabel)}} · ${{esc(item.id || '')}}</span>
            <strong>${{esc(item.label || '')}}</strong>
            <span class="status-${{esc(status)}}">${{esc(item.status || '')}}</span>
            <strong>${{Number.isFinite(score) ? score.toFixed(2) : esc(item.score)}}</strong>
          </div>
          <div class="value">${{esc(item.evidence || '')}}</div>
          <span class="label">severity_if_failed: ${{esc(item.severity_if_failed || '')}}</span>
        </div>`;
      }}).join('');
      const universal = renderItems(vl.universal_checklist, 'universal', 'universal') || '<div class="empty">No universal checklist returned.</div>';
      const contextual = renderItems(vl.contextual_checklist, 'case-specific', 'contextual') || '<div class="empty">No contextual checklist returned.</div>';
      return `<h4>Universal Checklist</h4>${{universal}}<h4>Case-Specific Checklist</h4>${{contextual}}`;
    }}

    $('prevBtn').onclick = () => {{ current = (current - 1 + filtered.length) % filtered.length; $('chartSelect').value = String(current); render(); }};
    $('nextBtn').onclick = () => {{ current = (current + 1) % filtered.length; $('chartSelect').value = String(current); render(); }};
    $('chartSelect').onchange = (event) => {{ current = Number(event.target.value || 0); render(); }};
    $('searchInput').oninput = (event) => {{
      const q = event.target.value.trim().toLowerCase();
      filtered = records.map((_, index) => index).filter(index => {{
        const r = records[index], c = r.chart;
        const blob = [r.case_id, c.title, c.nearby_text, c.page_text, c.expected_match, JSON.stringify(c.issues || []), JSON.stringify(c.crop_quality || {{}})].join(' ').toLowerCase();
        return !q || blob.includes(q);
      }});
      current = 0;
      renderSelect();
    }};
    renderSelect();
  </script>
</body>
</html>
"""


def esc(value: Any) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build chart-level QA dashboard from strategy report eval results.")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "evals" / "strategy_report" / "results" / "chart_smoke")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--title", default="Strategy Report Chart QA Review")
    parser.add_argument("--embed-images", action="store_true", help="Inline screenshots as data URLs for file:// review.")
    args = parser.parse_args()
    out = args.out or args.results_dir / "chart_dashboard.html"
    records = load_chart_records(args.results_dir, embed_images=args.embed_images)
    write_text(out, build_html(records, args.title))
    print(f"Wrote {out} with {len(records)} chart records")


if __name__ == "__main__":
    main()
