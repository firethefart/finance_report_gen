from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path
from typing import Any

from eval_utils import ROOT, read_json, write_text


def image_data_uri(path: str | Path | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return ""
    suffix = p.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def collect_results(results_dirs: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for directory in results_dirs:
        base = directory if directory.is_absolute() else ROOT / directory
        for path in sorted(base.glob("*.v2.eval.json")):
            result = read_json(path)
            charts = ((result.get("module_results") or {}).get("visual_qa") or {}).get("charts") or []
            chart_rows = []
            for chart in charts[:12]:
                chart_rows.append(
                    {
                        "chart_id": chart.get("chart_id"),
                        "score": chart.get("score"),
                        "title": chart.get("title"),
                        "image_data": image_data_uri(chart.get("image_path")),
                        "page_image_data": image_data_uri(chart.get("page_image_path")),
                        "subscores": chart.get("subscores") or {},
                        "vl_judged": chart.get("vl_judged"),
                        "vl_judge": compact_chart_judge(chart.get("vl_judge") or {}),
                        "skip_reason": chart.get("skip_reason"),
                    }
                )
            rows.append(
                {
                    "result_path": str(path),
                    "report_id": result.get("report_id"),
                    "candidate_report": result.get("candidate_report"),
                    "overall_score": result.get("overall_score"),
                    "grade": result.get("grade"),
                    "gate": result.get("gate") or {},
                    "dimension_score_normalized": result.get("dimension_score_normalized") or {},
                    "issues": result.get("issues") or [],
                    "adapter_manifest": result.get("adapter_manifest") or {},
                    "module_results": summarize_modules(result.get("module_results") or {}),
                    "llm_details": collect_llm_details(result.get("module_results") or {}),
                    "charts": chart_rows,
                }
            )
    return rows


def summarize_modules(modules: dict[str, Any]) -> dict[str, Any]:
    summary = {}
    for key, value in modules.items():
        item = {
            "score": value.get("score"),
            "metrics": value.get("metrics") or {},
            "subscores": value.get("subscores") or {},
            "issue_count": len(value.get("issues") or []),
        }
        if key == "source_traceability":
            item["source_evidence"] = (value.get("source_evidence") or [])[:20]
        summary[key] = item
    return summary


def collect_llm_details(modules: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    claim = modules.get("claim_numeric_llm")
    if claim:
        details["claim_numeric_llm"] = {
            "score": claim.get("score"),
            "subscores": claim.get("subscores") or {},
            "module_complete": claim.get("module_complete"),
            "candidate_claims": ((claim.get("candidate_claims") or {}).get("claims") or [])[:10],
            "numeric_profile": claim.get("numeric_profile") or {},
            "judgement": compact_judgement(claim.get("llm_judgement") or {}),
            "issues": claim.get("issues") or [],
        }
    strategy = modules.get("strategy_reasoning_llm")
    if strategy:
        details["strategy_reasoning_llm"] = {
            "score": strategy.get("score"),
            "subscores": strategy.get("subscores") or {},
            "report_archetype": strategy.get("report_archetype"),
            "archetype_rubric": strategy.get("archetype_rubric") or {},
            "module_complete": strategy.get("module_complete"),
            "chains": ((strategy.get("extraction") or {}).get("chains") or [])[:8],
            "judgement": compact_judgement(strategy.get("llm_judgement") or {}),
            "issues": strategy.get("issues") or [],
        }
    for key in ["claim_numeric_discipline", "strategy_reasoning"]:
        module = modules.get(key) or {}
        if module.get("llm_blend"):
            details[f"{key}_blend"] = module.get("llm_blend")
    return details


def compact_judgement(judgement: dict[str, Any]) -> dict[str, Any]:
    if not judgement:
        return {}
    omitted = {"raw", "raw_response_content", "content"}
    out = {key: value for key, value in judgement.items() if key not in omitted}
    if isinstance(out.get("claim_results"), list):
        out["claim_results"] = out["claim_results"][:8]
    if isinstance(out.get("chain_results"), list):
        out["chain_results"] = out["chain_results"][:8]
    if isinstance(out.get("issues"), list):
        out["issues"] = out["issues"][:8]
    return out


def compact_chart_judge(judge: dict[str, Any]) -> dict[str, Any]:
    if not judge:
        return {}
    omitted = {"raw", "raw_response_content", "content"}
    out = {key: value for key, value in judge.items() if key not in omitted}
    for key in ["universal_checklist", "contextual_checklist", "matched_text_spans", "hard_flags", "issues"]:
        if isinstance(out.get(key), list):
            out[key] = out[key][:12]
    return out


def build_html(rows: list[dict[str, Any]], title: str) -> str:
    payload = json.dumps(rows, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; background: #f5f7fa; color: #172033; }}
    header {{ padding: 16px 22px; background: #fff; border-bottom: 1px solid #dce2ea; display:flex; gap:12px; align-items:center; }}
    select, button {{ padding: 7px 10px; border: 1px solid #b8c2d1; border-radius: 5px; background:#fff; }}
    main {{ display:grid; grid-template-columns: 360px 1fr; min-height: calc(100vh - 66px); }}
    aside {{ border-right:1px solid #dce2ea; background:#fff; padding:14px; overflow:auto; }}
    section {{ padding:18px; overflow:auto; }}
    .card {{ border:1px solid #dce2ea; background:#fff; border-radius:8px; padding:14px; margin-bottom:14px; }}
    .score {{ font-size: 34px; font-weight: 800; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:7px; margin:8px 0; }}
    .chip {{ background:#eef2f7; border-radius:999px; padding:4px 8px; font-size:12px; }}
    .bad {{ background:#fdecec; color:#9c2f2f; }}
    .ok {{ background:#e8f6ef; color:#166b48; }}
    .dim {{ display:grid; grid-template-columns: 190px 1fr 48px; gap:8px; align-items:center; margin:8px 0; }}
    .bar {{ height:9px; background:#e7ebf1; border-radius:99px; overflow:hidden; }}
    .fill {{ height:100%; background:#2f6fed; }}
    pre {{ white-space:pre-wrap; word-break:break-word; background:#f8fafc; border:1px solid #dce2ea; border-radius:6px; padding:10px; max-height:260px; overflow:auto; }}
    .charts {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap:12px; }}
    .chart {{ border:1px solid #dce2ea; border-radius:6px; overflow:hidden; background:#fbfcfe; }}
    .chart img {{ width:100%; max-height:230px; object-fit:contain; display:block; background:#fff; }}
    .chart div {{ padding:8px; font-size:12px; color:#52606f; }}
    .issue {{ border-left:4px solid #d8a03a; padding:8px 10px; background:#fff9ed; margin:8px 0; }}
  </style>
</head>
<body>
  <header>
    <strong>{html.escape(title)}</strong>
    <button id="prev">上一个</button>
    <button id="next">下一个</button>
    <select id="sample"></select>
    <span id="count"></span>
  </header>
  <main>
    <aside id="list"></aside>
    <section id="detail"></section>
  </main>
  <script>
    const rows = {payload};
    let idx = 0;
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    const fmt = n => Number.isFinite(Number(n)) ? Number(n).toFixed(3) : '-';
    function renderSelect() {{
      sample.innerHTML = rows.map((r,i)=>`<option value="${{i}}">${{esc(r.report_id)}} · ${{esc(r.overall_score)}} · ${{esc(r.grade)}}</option>`).join('');
      sample.value = String(idx);
      count.textContent = `${{idx+1}} / ${{rows.length}}`;
    }}
    function dimRow(k,v) {{
      const n = Math.max(0, Math.min(1, Number(v)||0));
      return `<div class="dim"><span>${{esc(k)}}</span><div class="bar"><div class="fill" style="width:${{n*100}}%"></div></div><b>${{fmt(n)}}</b></div>`;
    }}
    function renderList() {{
      list.innerHTML = rows.map((r,i)=>`<div class="card" style="cursor:pointer;${{i===idx?'outline:2px solid #2f6fed;':''}}" onclick="idx=${{i}};render()">
        <b>${{esc(r.report_id)}}</b><div>${{esc(r.overall_score)}} / ${{esc(r.grade)}}</div>
        <div class="chips"><span class="chip ${{r.gate.passed?'ok':'bad'}}">${{r.gate.passed?'PASS':'FAIL'}}</span></div>
      </div>`).join('');
    }}
    function renderCharts(charts) {{
      if (!charts.length) return '<div class="card">无视觉对象</div>';
      return `<div class="charts">${{charts.map(c=>`<div class="chart">
        ${{c.image_data ? `<img src="${{c.image_data}}" alt="chart" />` : ''}}
        <div><b>${{esc(c.chart_id)}}</b><br>score=${{fmt(c.score)}} / VLM=${{c.vl_judged ? 'yes' : 'no'}}<br>${{esc(c.title || '')}}<pre>${{esc(JSON.stringify({{subscores:c.subscores, vl_judge:c.vl_judge}},null,2))}}</pre></div>
      </div>`).join('')}}</div>`;
    }}
    function render() {{
      renderSelect(); renderList();
      const r = rows[idx];
      detail.innerHTML = `<div class="card">
        <h2>${{esc(r.report_id)}}</h2>
        <div class="score">${{esc(r.overall_score)}} <small>${{esc(r.grade)}}</small></div>
        <div class="chips"><span class="chip ${{r.gate.passed?'ok':'bad'}}">${{r.gate.passed?'Gate PASS':'Gate FAIL'}}</span>${{(r.gate.failures||[]).map(f=>`<span class="chip bad">${{esc(f)}}</span>`).join('')}}</div>
        <pre>${{esc(r.candidate_report)}}</pre>
      </div>
      <div class="card"><h3>维度分</h3>${{Object.entries(r.dimension_score_normalized).map(([k,v])=>dimRow(k,v)).join('')}}</div>
      <div class="card"><h3>Adapter Manifest</h3><pre>${{esc(JSON.stringify(r.adapter_manifest,null,2))}}</pre></div>
      <div class="card"><h3>模块摘要</h3><pre>${{esc(JSON.stringify(r.module_results,null,2))}}</pre></div>
      <div class="card"><h3>LLM 细节</h3><pre>${{esc(JSON.stringify(r.llm_details || {{}},null,2))}}</pre></div>
      <div class="card"><h3>Top Issues</h3>${{r.issues.length ? r.issues.slice(0,20).map(i=>`<div class="issue"><b>[${{esc(i.severity)}}] ${{esc(i.module)}} / ${{esc(i.issue_type)}}</b><br>${{esc(i.description)}}<br><small>${{esc(i.location || '')}}</small></div>`).join('') : '无'}}</div>
      <div class="card"><h3>视觉对象</h3>${{renderCharts(r.charts)}}</div>`;
    }}
    prev.onclick = () => {{ idx = (idx - 1 + rows.length) % rows.length; render(); }};
    next.onclick = () => {{ idx = (idx + 1) % rows.length; render(); }};
    sample.onchange = e => {{ idx = Number(e.target.value); render(); }};
    render();
  </script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Verifier V2 review dashboard.")
    parser.add_argument("--results-dir", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--title", default="Strategy Report Verifier V2 Review")
    args = parser.parse_args()
    rows = collect_results(args.results_dir)
    out = args.out or (args.results_dir[0] / "v2_review_dashboard.html")
    out = out if out.is_absolute() else ROOT / out
    write_text(out, build_html(rows, args.title))
    print(f"wrote {out} with {len(rows)} rows")


if __name__ == "__main__":
    main()
