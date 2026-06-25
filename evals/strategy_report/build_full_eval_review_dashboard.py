from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from eval_utils import ROOT, read_json, write_text


def href_for(path: str | None, base_dir: Path) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    try:
        rel = Path(os.path.relpath(p, base_dir))
        return quote(rel.as_posix(), safe="/:#?&=%")
    except ValueError:
        return quote(p.as_posix(), safe="/:#?&=%")


def file_href_for(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return "file:///" + quote(p.resolve().as_posix(), safe="/:#?&=%")


def http_href_for(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    try:
        rel = p.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return ""
    return "/" + quote(rel.as_posix(), safe="/:#?&=%")


def short_text(value: Any, limit: int = 2200) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n...[truncated {len(text) - limit} chars]"


def module_score(module: dict[str, Any] | None) -> float | None:
    if not isinstance(module, dict):
        return None
    score = module.get("score")
    return score if isinstance(score, (int, float)) else None


def slim_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue_type": issue.get("issue_type"),
        "severity": issue.get("severity"),
        "location": issue.get("location"),
        "description": short_text(issue.get("description"), 800),
        "evidence": short_text(issue.get("evidence"), 800),
        "suggested_skill_patch": short_text(issue.get("suggested_skill_patch"), 800),
    }


def collect_chart_rows(chart_module: dict[str, Any], out_file: Path) -> list[dict[str, Any]]:
    rows = []
    for chart in chart_module.get("charts") or []:
        vl = chart.get("vl_judge") or {}
        rows.append(
            {
                "chart_id": chart.get("chart_id"),
                "page": chart.get("page"),
                "title": chart.get("title"),
                "chart_kind_hint": chart.get("chart_kind_hint"),
                "detection_method": chart.get("detection_method"),
                "object_index": chart.get("object_index"),
                "object_count_on_page": chart.get("object_count_on_page"),
                "score": chart.get("score"),
                "subscores": chart.get("subscores") or {},
                "vl_judged": chart.get("vl_judged"),
                "excluded_from_chart_score": chart.get("excluded_from_chart_score"),
                "skip_reason": chart.get("skip_reason"),
                "image_href": href_for(chart.get("image_path"), out_file.parent),
                "image_file_href": file_href_for(chart.get("image_path")),
                "image_http_href": http_href_for(chart.get("image_path")),
                "page_image_href": href_for(chart.get("page_image_path"), out_file.parent),
                "page_image_file_href": file_href_for(chart.get("page_image_path")),
                "page_image_http_href": http_href_for(chart.get("page_image_path")),
                "nearby_text": short_text(chart.get("nearby_text"), 1600),
                "page_text": short_text(chart.get("page_text"), 2200),
                "numbers": chart.get("numbers") or [],
                "dates": chart.get("dates") or [],
                "warnings": chart.get("warnings") or [],
                "issues": [slim_issue(item) for item in chart.get("issues") or []],
                "vl_judge": vl,
            }
        )
    return rows


def collect_case(eval_path: Path, out_file: Path) -> dict[str, Any]:
    data = read_json(eval_path)
    modules = data.get("module_results") or {}
    chart_module = modules.get("chart_qa") or {}
    claim_module = modules.get("claim_numeric_llm") or {}
    strategy_module = modules.get("strategy_reasoning_llm") or {}
    dimensions = data.get("dimension_score_normalized") or {}
    diagnostics = data.get("score_diagnostics") or {}
    gate = data.get("gate") or {}
    return {
        "case_id": data.get("case_id"),
        "candidate_report": data.get("candidate_report"),
        "candidate_href": href_for(data.get("candidate_report"), out_file.parent),
        "candidate_file_href": file_href_for(data.get("candidate_report")),
        "candidate_http_href": http_href_for(data.get("candidate_report")),
        "overall_score": data.get("overall_score"),
        "grade": data.get("grade"),
        "gate_passed": gate.get("passed"),
        "gate_failures": gate.get("failures") or [],
        "weights": data.get("weights") or {},
        "dimensions": dimensions,
        "dimension_scores": data.get("dimension_scores") or {},
        "score_diagnostics": diagnostics,
        "redline_issues": [slim_issue(item) for item in data.get("redline_issues") or []],
        "issues": [slim_issue(item) for item in data.get("issues") or []],
        "modules_summary": {
            key: {
                "score": module_score(value),
                "issue_count": len(value.get("issues") or []) if isinstance(value, dict) else 0,
                "metrics": value.get("metrics") if isinstance(value, dict) else None,
            }
            for key, value in modules.items()
            if isinstance(value, dict)
        },
        "claim_numeric": {
            "ok": claim_module.get("ok"),
            "score": claim_module.get("score"),
            "subscores": claim_module.get("subscores") or {},
            "issues": [slim_issue(item) for item in claim_module.get("issues") or []],
            "models": claim_module.get("models") or {},
            "candidate_claims": (claim_module.get("candidate_claims") or {}).get("claims") or [],
            "evidence_packs": claim_module.get("evidence_packs") or [],
            "numeric_audit": claim_module.get("numeric_audit") or {},
            "llm_judgement": claim_module.get("llm_judgement") or {},
        },
        "strategy_reasoning": {
            "ok": strategy_module.get("ok"),
            "module_complete": strategy_module.get("module_complete"),
            "fallback_used": strategy_module.get("fallback_used"),
            "score": strategy_module.get("score"),
            "subscores": strategy_module.get("subscores") or {},
            "issues": [slim_issue(item) for item in strategy_module.get("issues") or []],
            "models": strategy_module.get("models") or {},
            "chains": (strategy_module.get("extraction") or {}).get("chains") or [],
            "expectation": strategy_module.get("expectation") or {},
            "programmatic_audit": strategy_module.get("programmatic_audit") or {},
            "llm_judgement": strategy_module.get("llm_judgement") or {},
        },
        "chart_qa": {
            "score": chart_module.get("score"),
            "subscores": chart_module.get("subscores") or {},
            "metrics": chart_module.get("metrics") or {},
            "issues": [slim_issue(item) for item in chart_module.get("issues") or []],
            "charts": collect_chart_rows(chart_module, out_file),
        },
    }


def collect_rows(results_dir: Path, out_file: Path) -> list[dict[str, Any]]:
    return [collect_case(path, out_file) for path in sorted(results_dir.glob("*.eval.json"))]


def build_html(rows: list[dict[str, Any]], title: str) -> str:
    payload = json.dumps(rows, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg:#f4f6f8; --panel:#fff; --line:#d8dee8; --ink:#172033; --muted:#667085;
      --accent:#155eef; --good:#087443; --bad:#b42318; --warn:#b54708;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font-family:Arial, "Microsoft YaHei", "PingFang SC", sans-serif; }}
    header {{ height:58px; padding:0 14px; background:var(--panel); border-bottom:1px solid var(--line); display:flex; align-items:center; gap:10px; }}
    h1 {{ font-size:16px; margin:0 10px 0 0; white-space:nowrap; }}
    button, select {{ height:34px; border:1px solid var(--line); border-radius:6px; background:#fff; padding:0 10px; color:var(--ink); }}
    button:hover {{ border-color:var(--accent); }}
    main {{ height:calc(100vh - 58px); display:grid; grid-template-columns:minmax(680px, 61vw) 1fr; }}
    .left {{ overflow:auto; padding:14px; }}
    .right {{ border-left:1px solid var(--line); background:#242933; display:flex; flex-direction:column; min-width:360px; }}
    iframe {{ width:100%; flex:1; border:0; background:#30343c; }}
    .pdfbar {{ color:#e5e7eb; font-size:12px; padding:8px 10px; border-bottom:1px solid #3d4350; display:flex; justify-content:space-between; gap:12px; }}
    .pdfbar a {{ color:#bdd7ff; }}
    .topgrid {{ display:grid; grid-template-columns:1.25fr .9fr; gap:12px; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; margin-bottom:12px; overflow:hidden; }}
    .panel h2 {{ font-size:15px; margin:0; padding:10px 12px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:10px; }}
    .content {{ padding:12px; }}
    .score-grid {{ display:grid; grid-template-columns:repeat(4,minmax(110px,1fr)); gap:8px; }}
    .score {{ border:1px solid var(--line); border-radius:6px; padding:8px; background:#fbfcfe; min-height:68px; }}
    .score span {{ color:var(--muted); font-size:12px; display:block; }}
    .score strong {{ display:block; font-size:20px; margin-top:6px; }}
    .muted {{ color:var(--muted); font-size:12px; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
    .chip {{ border:1px solid var(--line); background:#f8fafc; border-radius:999px; padding:3px 8px; font-size:12px; }}
    .ok {{ border-color:#7cd6a0; color:var(--good); background:#f0fdf4; }}
    .bad {{ border-color:#fecdca; color:var(--bad); background:#fff3f2; }}
    .warn {{ border-color:#fedf89; color:var(--warn); background:#fffbeb; }}
    nav.tabs {{ display:flex; flex-wrap:wrap; gap:6px; margin-bottom:12px; }}
    nav.tabs button {{ height:32px; }}
    nav.tabs button.active {{ background:#eaf1ff; border-color:#8bb7ff; color:#0b4db3; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-top:1px solid var(--line); padding:8px; vertical-align:top; text-align:left; }}
    th {{ background:#f8fafc; color:var(--muted); font-weight:600; }}
    details {{ border:1px solid var(--line); border-radius:6px; margin:8px 0; background:#fbfcfe; }}
    summary {{ cursor:pointer; padding:8px 10px; color:#344054; }}
    pre {{ margin:0; padding:10px; max-height:320px; overflow:auto; white-space:pre-wrap; word-break:break-word; font-size:12px; line-height:1.45; }}
    .card {{ border:1px solid var(--line); border-radius:8px; background:#fff; margin-bottom:10px; overflow:hidden; }}
    .card-head {{ padding:10px 12px; border-bottom:1px solid var(--line); display:flex; align-items:center; justify-content:space-between; gap:10px; }}
    .card-body {{ padding:10px 12px; }}
    .quote {{ border-left:3px solid var(--accent); padding-left:8px; color:#344054; }}
    .chart-layout {{ display:grid; grid-template-columns:240px 1fr; gap:12px; }}
    .chart-imgs {{ display:grid; grid-template-columns:1fr; gap:8px; }}
    .chart-imgs img {{ width:100%; border:1px solid var(--line); background:#f2f4f7; border-radius:6px; }}
    .two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
    @media (max-width: 1100px) {{
      main {{ grid-template-columns:1fr; }}
      .right {{ display:none; }}
      .topgrid, .two-col, .chart-layout {{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(title)}</h1>
    <button id="prev">上一个</button>
    <button id="next">下一个</button>
    <select id="caseSelect"></select>
    <select id="filterSelect">
      <option value="all">全部样本</option>
      <option value="gate_failed">只看 Gate 未通过</option>
      <option value="chart15">只看图表已扩展到 15 张</option>
      <option value="chart_lt15">只看图表少于 15 张</option>
    </select>
    <span class="muted" id="count"></span>
  </header>
  <main>
    <section class="left">
      <div id="summary"></div>
      <nav class="tabs" id="tabs"></nav>
      <div id="content"></div>
    </section>
    <section class="right">
      <div class="pdfbar"><span id="pdfTitle"></span><a id="pdfLink" target="_blank">打开原报告</a></div>
      <iframe id="pdf"></iframe>
    </section>
  </main>
  <script>
    const allRows = {payload};
    let rows = allRows.slice();
    let index = 0;
    let tab = 'overview';
    const tabs = [
      ['overview', '总览'],
      ['modules', '模块分'],
      ['claim', 'Claim/Numeric'],
      ['strategy', 'Strategy'],
      ['charts', 'Chart QA'],
      ['raw', '原始 JSON']
    ];
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    const num = (v, digits=3) => typeof v === 'number' ? v.toFixed(digits) : (v ?? '-');
    const pct = (v) => typeof v === 'number' ? (v * 100).toFixed(1) + '%' : '-';
    const chip = (text, cls='') => `<span class="chip ${{cls}}">${{esc(text)}}</span>`;
    const scoreBox = (label, value, digits=2) => `<div class="score"><span>${{esc(label)}}</span><strong>${{num(value, digits)}}</strong></div>`;
    function assetUrl(relativeHref, fileHref, httpHref) {{
      if (location.protocol === 'file:') return fileHref || relativeHref || httpHref || '';
      if (location.protocol === 'http:' || location.protocol === 'https:') return httpHref || relativeHref || fileHref || '';
      return relativeHref || httpHref || fileHref || '';
    }}
    function issueChips(items) {{
      if (!items || !items.length) return chip('无 issue', 'ok');
      return items.map(i => chip(`${{i.severity || '-'}}: ${{i.issue_type || '-'}}`, ['high','blocker','critical'].includes(i.severity) ? 'bad' : 'warn')).join('');
    }}
    function setRows() {{
      const filter = document.getElementById('filterSelect').value;
      rows = allRows.filter(r => {{
        const judged = r.chart_qa?.metrics?.vl_judged_chart_count || 0;
        if (filter === 'gate_failed') return !r.gate_passed;
        if (filter === 'chart15') return judged >= 15;
        if (filter === 'chart_lt15') return judged < 15;
        return true;
      }});
      index = Math.min(index, Math.max(rows.length - 1, 0));
      renderSelect();
      render();
    }}
    function renderSelect() {{
      const sel = document.getElementById('caseSelect');
      sel.innerHTML = rows.map((r, i) => {{
        const judged = r.chart_qa?.metrics?.vl_judged_chart_count || 0;
        return `<option value="${{i}}">${{esc(r.case_id)}} | ${{num(r.overall_score, 2)}} | chart VL ${{judged}}</option>`;
      }}).join('');
    }}
    function renderTabs() {{
      document.getElementById('tabs').innerHTML = tabs.map(([id, label]) => `<button class="${{tab === id ? 'active' : ''}}" data-tab="${{id}}">${{label}}</button>`).join('');
      document.querySelectorAll('#tabs button').forEach(btn => btn.onclick = () => {{ tab = btn.dataset.tab; render(); }});
    }}
    function renderSummary(r) {{
      const dims = r.dimensions || {{}};
      const chartMetrics = r.chart_qa?.metrics || {{}};
      const gateCls = r.gate_passed ? 'ok' : 'bad';
      document.getElementById('summary').innerHTML = `
        <section class="panel"><h2>当前样本概览 <span class="muted">${{esc(r.case_id)}}</span></h2><div class="content">
          <div class="topgrid">
            <div>
              <div class="score-grid">
                ${{scoreBox('Overall', r.overall_score, 2)}}
                ${{scoreBox('Grade', r.grade, 0)}}
                ${{scoreBox('Gate', r.gate_passed ? 'PASS' : 'FAIL', 0)}}
                ${{scoreBox('Chart VL', `${{chartMetrics.vl_judged_chart_count || 0}} / ${{chartMetrics.chart_count || 0}}`, 0)}}
              </div>
              <div class="chips" style="margin-top:10px;">${{chip(r.gate_passed ? 'gate passed' : 'gate failed', gateCls)}}${{(r.gate_failures || []).map(x => chip(x, 'bad')).join('')}}</div>
            </div>
            <div>
              <table><tbody>
                <tr><th>Facts</th><td>${{pct(dims.facts)}} / Claim LLM ${{num(r.claim_numeric?.score)}}</td></tr>
                <tr><th>Strategy</th><td>${{pct(dims.strategy_reasoning)}} / Strategy LLM ${{num(r.strategy_reasoning?.score)}}</td></tr>
                <tr><th>Charts</th><td>${{pct(dims.charts)}} / Chart score ${{num(r.chart_qa?.score)}}</td></tr>
                <tr><th>Source</th><td>${{pct(dims.sources)}}</td></tr>
              </tbody></table>
            </div>
          </div>
        </div></section>`;
    }}
    function overview(r) {{
      const dims = r.dimensions || {{}};
      return `<section class="panel"><h2>维度分</h2><div class="content"><div class="score-grid">
        ${{Object.entries(dims).map(([k,v]) => scoreBox(k, v, 3)).join('')}}
      </div></div></section>
      <section class="panel"><h2>Gate / Issues</h2><div class="content">
        <p><strong>Gate failures:</strong></p><div class="chips">${{(r.gate_failures || []).map(x => chip(x, 'bad')).join('') || chip('无', 'ok')}}</div>
        <p><strong>All issues:</strong></p><div class="chips">${{issueChips(r.issues)}}</div>
        <details><summary>Score diagnostics</summary><pre>${{esc(JSON.stringify(r.score_diagnostics, null, 2))}}</pre></details>
      </div></section>`;
    }}
    function modules(r) {{
      const rowsHtml = Object.entries(r.modules_summary || {{}}).map(([name, m]) => `<tr>
        <td>${{esc(name)}}</td><td>${{num(m.score)}}</td><td>${{m.issue_count ?? 0}}</td><td><pre>${{esc(JSON.stringify(m.metrics || {{}}, null, 2))}}</pre></td>
      </tr>`).join('');
      return `<section class="panel"><h2>所有子模块摘要</h2><div class="content"><table><thead><tr><th>模块</th><th>分数</th><th>Issue 数</th><th>Metrics</th></tr></thead><tbody>${{rowsHtml}}</tbody></table></div></section>`;
    }}
    function claim(r) {{
      const c = r.claim_numeric || {{}};
      const facts = (c.evidence_packs || []).map(pack => {{
        const judge = (c.llm_judgement?.golden_fact_results || []).find(x => x.fact_id === pack.fact_id) || {{}};
        const snippets = (pack.candidate_snippets || []).slice(0, 4).map(s => `<details><summary>证据片段 ${{s.rank}} | score ${{num(s.score)}} | numbers ${{esc((s.numbers || []).join(', '))}}</summary><pre>${{esc(s.text)}}</pre></details>`).join('');
        return `<div class="card"><div class="card-head"><strong>${{esc(pack.fact_id)}}</strong><div class="chips">${{chip(judge.decision || 'no decision')}}${{chip('numeric: ' + (judge.numeric_status || '-'))}}${{chip('score: ' + (judge.score ?? '-'))}}</div></div>
        <div class="card-body"><div class="quote">${{esc(pack.golden_claim || '')}}</div><p><strong>LLM reason:</strong> ${{esc(judge.reason || '')}}</p><p><strong>Evidence quote:</strong> ${{esc(judge.evidence_quote || '')}}</p>${{snippets}}</div></div>`;
      }}).join('');
      const claims = (c.candidate_claims || []).slice(0, 40).map(x => `<tr><td>${{esc(x.claim_id)}}</td><td>${{esc(x.claim_type)}}</td><td>${{esc(x.claim)}}</td><td>${{esc((x.numbers || []).join(', '))}}</td></tr>`).join('');
      return `<section class="panel"><h2>Claim/Numeric 总分与子分</h2><div class="content"><div class="score-grid">
        ${{scoreBox('overall', c.score)}}${{Object.entries(c.subscores || {{}}).map(([k,v]) => scoreBox(k, v)).join('')}}
      </div><div class="chips" style="margin-top:10px;">${{issueChips(c.issues)}}</div></div></section>
      <section class="panel"><h2>Golden facts 对齐</h2><div class="content">${{facts || '<p class="muted">无 evidence pack</p>'}}</div></section>
      <section class="panel"><h2>抽取出的候选 claims</h2><div class="content"><table><thead><tr><th>ID</th><th>类型</th><th>Claim</th><th>数字</th></tr></thead><tbody>${{claims}}</tbody></table></div></section>
      <section class="panel"><h2>Numeric audit / LLM raw</h2><div class="content"><details open><summary>numeric audit</summary><pre>${{esc(JSON.stringify(c.numeric_audit, null, 2))}}</pre></details><details><summary>llm judgement</summary><pre>${{esc(JSON.stringify(c.llm_judgement, null, 2))}}</pre></details></div></section>`;
    }}
    function strategy(r) {{
      const s = r.strategy_reasoning || {{}};
      const chainMap = {{}};
      for (const item of (s.llm_judgement?.chain_results || [])) chainMap[item.chain_id] = item;
      const chains = (s.chains || []).map(ch => {{
        const j = chainMap[ch.chain_id] || {{}};
        return `<div class="card"><div class="card-head"><strong>${{esc(ch.chain_id)}} | ${{esc(ch.thesis_type)}} | ${{esc(ch.importance)}}</strong><div class="chips">${{chip(j.decision || 'no decision')}}${{chip('score: ' + (j.score ?? '-'))}}</div></div>
        <div class="card-body">
          <p><strong>Thesis:</strong> ${{esc(ch.thesis)}}</p>
          <div class="two-col"><div><strong>Mechanism</strong><pre>${{esc(ch.mechanism)}}</pre></div><div><strong>Implication / Risk</strong><pre>${{esc((ch.investment_implication || '') + '\\n' + (ch.risk_boundary || ''))}}</pre></div></div>
          <p><strong>LLM strengths:</strong> ${{esc((j.strengths || []).join('; '))}}</p>
          <p><strong>LLM gaps:</strong> ${{esc((j.gaps || []).join('; '))}}</p>
          <p><strong>Evidence quote:</strong> ${{esc(j.evidence_quote || '')}}</p>
          <details><summary>source context</summary><pre>${{esc(ch.source_context || '')}}</pre></details>
        </div></div>`;
      }}).join('');
      return `<section class="panel"><h2>Strategy Reasoning 总分与子分</h2><div class="content"><div class="score-grid">
        ${{scoreBox('overall', s.score)}}${{Object.entries(s.subscores || {{}}).map(([k,v]) => scoreBox(k, v)).join('')}}
      </div><div class="chips" style="margin-top:10px;">${{chip('complete: ' + s.module_complete, s.module_complete ? 'ok' : 'bad')}}${{chip('fallback: ' + s.fallback_used)}}${{issueChips(s.issues)}}</div></div></section>
      <section class="panel"><h2>Reasoning chains</h2><div class="content">${{chains || '<p class="muted">无 reasoning chain</p>'}}</div></section>
      <section class="panel"><h2>Expectation / audit / raw</h2><div class="content"><details><summary>expectation</summary><pre>${{esc(JSON.stringify(s.expectation, null, 2))}}</pre></details><details><summary>programmatic audit</summary><pre>${{esc(JSON.stringify(s.programmatic_audit, null, 2))}}</pre></details><details><summary>llm judgement</summary><pre>${{esc(JSON.stringify(s.llm_judgement, null, 2))}}</pre></details></div></section>`;
    }}
    function chartCard(chart) {{
      const gate = chart.vl_judge?.visual_gate || {{}};
      const checklist = [...(chart.vl_judge?.universal_checklist || []), ...(chart.vl_judge?.contextual_checklist || [])];
      const checks = checklist.map(x => `<tr><td>${{esc(x.id || x.type || x.check_type || '')}}</td><td>${{esc(x.label || x.item || x.check || x.what_to_check || '')}}</td><td>${{esc(x.score ?? '')}}</td><td>${{esc(x.evidence || x.reason || x.status || '')}}</td></tr>`).join('');
      const imageUrl = assetUrl(chart.image_href, chart.image_file_href, chart.image_http_href);
      const pageImageUrl = assetUrl(chart.page_image_href, chart.page_image_file_href, chart.page_image_http_href);
      return `<div class="card"><div class="card-head"><strong>${{esc(chart.chart_id)}} | page ${{chart.page ?? '-'}}</strong><div class="chips">${{chip('score: ' + (chart.score ?? '-'))}}${{chip(chart.vl_judged ? 'VLM judged' : 'rule only', chart.vl_judged ? 'ok' : 'warn')}}${{chart.excluded_from_chart_score ? chip('excluded', 'warn') : ''}}</div></div>
      <div class="card-body chart-layout">
        <div class="chart-imgs">
          ${{imageUrl ? `<a href="${{imageUrl}}" target="_blank"><img src="${{imageUrl}}" loading="lazy" /></a>` : '<span class="muted">无目标截图</span>'}}
          ${{pageImageUrl ? `<details><summary>查看整页截图</summary><a href="${{pageImageUrl}}" target="_blank"><img src="${{pageImageUrl}}" loading="lazy" /></a></details>` : ''}}
        </div>
        <div>
          <div class="chips">${{chip(chart.chart_kind_hint || '-')}}${{chip(chart.detection_method || '-')}}${{chip('object ' + (chart.object_index ?? '-') + '/' + (chart.object_count_on_page ?? '-'))}}${{chip('gate: ' + (gate.decision || '-'))}}</div>
          <table style="margin-top:8px;"><tbody>${{Object.entries(chart.subscores || {{}}).map(([k,v]) => `<tr><th>${{esc(k)}}</th><td>${{num(v)}}</td></tr>`).join('')}}</tbody></table>
          <p><strong>Title:</strong> ${{esc(chart.title || '')}}</p>
          <p><strong>Gate reason:</strong> ${{esc(gate.reason || chart.skip_reason || '')}}</p>
          <details><summary>VLM checklist</summary><table><thead><tr><th>类型</th><th>检查项</th><th>分</th><th>证据</th></tr></thead><tbody>${{checks}}</tbody></table></details>
          <details><summary>周围文本</summary><pre>${{esc(chart.nearby_text || '')}}</pre></details>
          <details><summary>全页文本</summary><pre>${{esc(chart.page_text || '')}}</pre></details>
          <details><summary>VLM raw</summary><pre>${{esc(JSON.stringify(chart.vl_judge, null, 2))}}</pre></details>
        </div>
      </div></div>`;
    }}
    function charts(r) {{
      const q = r.chart_qa || {{}};
      const m = q.metrics || {{}};
      const cards = (q.charts || []).map(chartCard).join('');
      return `<section class="panel"><h2>Chart QA 总分与覆盖状态</h2><div class="content"><div class="score-grid">
        ${{scoreBox('chart score', q.score)}}${{scoreBox('candidates', m.chart_count, 0)}}${{scoreBox('VLM judged', m.vl_judged_chart_count, 0)}}${{scoreBox('non-visual skipped', m.non_visual_skipped_count, 0)}}
        ${{Object.entries(q.subscores || {{}}).map(([k,v]) => scoreBox(k, v)).join('')}}
      </div><div class="chips" style="margin-top:10px;">${{issueChips(q.issues)}}</div></div></section>
      <section class="panel"><h2>逐图结果</h2><div class="content">${{cards || '<p class="muted">当前样本没有图表候选</p>'}}</div></section>`;
    }}
    function raw(r) {{
      return `<section class="panel"><h2>当前样本 JSON</h2><div class="content"><pre>${{esc(JSON.stringify(r, null, 2))}}</pre></div></section>`;
    }}
    function render() {{
      if (!rows.length) {{
        document.getElementById('summary').innerHTML = '<section class="panel"><div class="content">没有符合筛选条件的样本。</div></section>';
        document.getElementById('content').innerHTML = '';
        return;
      }}
      const r = rows[index];
      document.getElementById('caseSelect').value = String(index);
      document.getElementById('count').textContent = `${{index + 1}} / ${{rows.length}}（总样本 ${{allRows.length}}）`;
      const pdfUrl = assetUrl(r.candidate_href, r.candidate_file_href, r.candidate_http_href);
      document.getElementById('pdf').src = pdfUrl || '';
      document.getElementById('pdfLink').href = pdfUrl || '#';
      document.getElementById('pdfTitle').textContent = r.candidate_report || '';
      renderTabs();
      renderSummary(r);
      const renderer = {{overview, modules, claim, strategy, charts, raw}}[tab] || overview;
      document.getElementById('content').innerHTML = renderer(r);
    }}
    document.getElementById('prev').onclick = () => {{ index = (index - 1 + rows.length) % rows.length; render(); }};
    document.getElementById('next').onclick = () => {{ index = (index + 1) % rows.length; render(); }};
    document.getElementById('caseSelect').onchange = (e) => {{ index = Number(e.target.value); render(); }};
    document.getElementById('filterSelect').onchange = setRows;
    renderSelect();
    render();
  </script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a paginated dashboard for full strategy verifier results.")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title", default="Strategy Verifier Full Eval Review")
    args = parser.parse_args()
    results_dir = args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = collect_rows(results_dir, out)
    write_text(out, build_html(rows, args.title))
    print(f"wrote {out} ({len(rows)} cases)")


if __name__ == "__main__":
    main()
