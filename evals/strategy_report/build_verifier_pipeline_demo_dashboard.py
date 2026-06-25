from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path
from typing import Any

from eval_utils import ROOT, read_json, write_text


FLOWCHART_MERMAID = """flowchart TD
  A["Golden metadata JSONL<br/>final_cases.jsonl"] --> B["case_builder.py<br/>Build eval case JSON"]
  B --> C["run_eval.py<br/>Select golden case + candidate report"]
  C --> D["report_parser.py<br/>Parse PDF/HTML text, sections, numbers, dates, links"]
  D --> E["checks.py<br/>Baseline rule modules"]
  E --> E1["Render / section / source / risk / compliance rules"]
  E --> E2["Legacy claim-citation + numeric/entity rules"]
  E --> E3["Legacy strategy reasoning signal rules"]
  D --> F{"Extract charts?"}
  F -- Yes --> G["chart_extractor.py<br/>Recall-first page scan + visual candidates + dedup"]
  G --> H{"Enable chart VLM judge?"}
  H -- No --> I["chart_qa.py<br/>Chart inventory rule scoring"]
  H -- Yes --> J["chart_judges.py<br/>VLM visual gate + universal/contextual checklist"]
  J --> I
  D --> K{"Enable Claim/Numeric LLM?"}
  K -- Yes --> L["claim_numeric_verifier.py<br/>Claim extraction + evidence packs + numeric audit + LLM judge"]
  D --> M{"Enable Strategy Reasoning LLM?"}
  M -- Yes --> N["strategy_reasoning_verifier.py<br/>Thesis extraction + reasoning-chain audit + LLM judge"]
  D --> O{"Enable consolidated LLM judge?"}
  O -- Yes --> P["llm_judges.py<br/>Broad professional quality judge"]
  E1 --> Q["scoring.py<br/>Weighted aggregation"]
  E2 --> Q
  E3 --> Q
  I --> Q
  L --> Q
  N --> Q
  P --> Q
  Q --> R["*.eval.json / *.eval.md<br/>summary.json"]
  R --> S["Review dashboards<br/>chart / claim-numeric / strategy-reasoning / pipeline demo"]"""


DEMO_CASES = [
    {"case_id": "eastmoney_cn_strategy_005", "label": "中文例子：东方财富中文策略报告"},
    {"case_id": "strategy_sample_003", "label": "English example: institutional strategy report"},
]


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
    return f"data:image/{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def load_result_json(results_dir: Path, case_id: str, suffix: str) -> dict[str, Any]:
    path = results_dir / f"{case_id}{suffix}"
    return read_json(path) if path.exists() else {}


def repair_mojibake_text(text: str) -> str:
    markers = ["鎶", "鏁", "绛", "鍥", "涓", "浜", "锛", "銆", "€", "瀵", "勬", "熷"]
    if not any(marker in text for marker in markers):
        return text
    try:
        repaired = text.encode("gbk", errors="strict").decode("utf-8", errors="strict")
    except UnicodeError:
        return text
    repaired_markers = sum(1 for marker in markers if marker in repaired)
    original_markers = sum(1 for marker in markers if marker in text)
    return repaired if repaired_markers < original_markers else text


def repair_mojibake(value: Any) -> Any:
    if isinstance(value, str):
        return repair_mojibake_text(value)
    if isinstance(value, list):
        return [repair_mojibake(item) for item in value]
    if isinstance(value, dict):
        return {key: repair_mojibake(item) for key, item in value.items()}
    return value


def collect_case(case_id: str) -> dict[str, Any]:
    case_path = ROOT / "evals" / "strategy_report" / "cases_merged33" / f"{case_id}.json"
    chart_dir = ROOT / "evals" / "strategy_report" / "results" / "chart_extractor_dedup_smoke2"
    claim_dir = ROOT / "evals" / "strategy_report" / "results" / "claim_numeric_smoke3"
    strategy_dir = ROOT / "evals" / "strategy_report" / "results" / "strategy_reasoning_smoke4"

    case = read_json(case_path)
    chart_eval = load_result_json(chart_dir, case_id, ".eval.json")
    claim_eval = load_result_json(claim_dir, case_id, ".eval.json")
    strategy_eval = load_result_json(strategy_dir, case_id, ".eval.json")
    chart_inventory = load_result_json(chart_dir / "chart_inventory", case_id, ".charts.json")
    claim_numeric = load_result_json(claim_dir / "claim_numeric", case_id, ".claim_numeric.json")
    strategy_reasoning = load_result_json(strategy_dir / "strategy_reasoning", case_id, ".strategy_reasoning.json")

    charts = chart_inventory.get("charts") or []
    chart_samples = []
    for chart in charts[:6]:
        chart_samples.append(
            {
                "chart_id": chart.get("chart_id"),
                "page": chart.get("page"),
                "method": chart.get("detection_method"),
                "tier": chart.get("candidate_tier"),
                "score": chart.get("candidate_score"),
                "title": chart.get("title") or chart.get("caption") or "",
                "signals": chart.get("candidate_signals") or [],
                "warnings": chart.get("warnings") or [],
                "image_data": image_data_uri(chart.get("image_path")),
            }
        )

    baseline_modules = chart_eval.get("module_results") or claim_eval.get("module_results") or strategy_eval.get("module_results") or {}
    result = {
        "case_id": case_id,
        "case": compact_case(case),
        "source_document": case.get("source_document") or {},
        "chart_eval": compact_eval(chart_eval),
        "claim_eval": compact_eval(claim_eval),
        "strategy_eval": compact_eval(strategy_eval),
        "baseline_modules": compact_modules(baseline_modules),
        "chart_inventory": {
            "chart_count": chart_inventory.get("chart_count"),
            "audit": chart_inventory.get("audit") or {},
            "samples": chart_samples,
            "qa": compact_chart_qa((chart_eval.get("module_results") or {}).get("chart_qa") or {}),
        },
        "claim_numeric": compact_claim_numeric(claim_numeric),
        "strategy_reasoning": compact_strategy_reasoning(strategy_reasoning),
    }
    return repair_mojibake(result)


def compact_case(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "query": case.get("query"),
        "expected_report_type": case.get("expected_report_type"),
        "institution": case.get("institution"),
        "report_title": case.get("report_title"),
        "report_date": case.get("report_date"),
        "strategy_subtype": case.get("strategy_subtype"),
        "quality_tier": case.get("quality_tier"),
        "key_fact_count": len(case.get("key_facts") or []),
        "must_have_section_count": len(case.get("must_have_sections") or []),
        "chart_expectation_count": len(case.get("charts_and_tables_to_learn_from") or []),
    }


def compact_eval(result: dict[str, Any]) -> dict[str, Any]:
    if not result:
        return {}
    return {
        "overall_score": result.get("overall_score"),
        "grade": result.get("grade"),
        "gate": result.get("gate"),
        "dimension_scores": result.get("dimension_scores"),
        "dimension_score_normalized": result.get("dimension_score_normalized"),
        "candidate_report": result.get("candidate_report"),
        "mode": result.get("mode"),
        "top_issues": (result.get("issues") or [])[:6],
    }


def compact_modules(modules: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name in [
        "render_delivery",
        "section_coverage",
        "source_quality",
        "claim_citation_alignment",
        "numeric_entity_consistency",
        "strategy_reasoning_rule",
        "scenario_risk",
        "chart_qa",
        "compliance_redline",
    ]:
        item = modules.get(name) or {}
        rows.append(
            {
                "module": name,
                "score": item.get("score"),
                "issues": (item.get("issues") or [])[:3],
                "metrics": item.get("metrics") or {k: v for k, v in item.items() if k not in {"score", "issues"} and isinstance(v, (str, int, float, bool, list, dict))} if item else {},
            }
        )
    return rows


def compact_chart_qa(data: dict[str, Any]) -> dict[str, Any]:
    if not data:
        return {}
    return {
        "score": data.get("score"),
        "subscores": data.get("subscores") or {},
        "metrics": data.get("metrics") or {},
        "issues": (data.get("issues") or [])[:8],
        "chart_rows": [
            {
                "chart_id": item.get("chart_id"),
                "page": item.get("page"),
                "score": item.get("score"),
                "subscores": item.get("subscores") or {},
                "excluded": item.get("excluded_from_chart_score"),
                "skip_reason": item.get("skip_reason"),
                "vl_judged": item.get("vl_judged"),
                "issues": (item.get("issues") or [])[:3],
            }
            for item in (data.get("charts") or [])[:10]
        ],
    }


def compact_claim_numeric(data: dict[str, Any]) -> dict[str, Any]:
    if not data:
        return {}
    judgement = data.get("llm_judgement") or {}
    return {
        "score": data.get("score"),
        "subscores": data.get("subscores"),
        "models": data.get("models"),
        "candidate_claim_count": len((data.get("candidate_claims") or {}).get("claims") or []),
        "sample_claims": ((data.get("candidate_claims") or {}).get("claims") or [])[:5],
        "numeric_audit": data.get("numeric_audit"),
        "golden_fact_results": (judgement.get("golden_fact_results") or [])[:8],
        "issues": data.get("issues") or [],
    }


def compact_strategy_reasoning(data: dict[str, Any]) -> dict[str, Any]:
    if not data:
        return {}
    judgement = data.get("llm_judgement") or {}
    return {
        "score": data.get("score"),
        "subscores": data.get("subscores"),
        "models": data.get("models"),
        "programmatic_audit": data.get("programmatic_audit"),
        "chains": ((data.get("extraction") or {}).get("chains") or [])[:8],
        "chain_results": (judgement.get("chain_results") or [])[:8],
        "missing_expected_reasoning": judgement.get("missing_expected_reasoning") or [],
        "issues": data.get("issues") or [],
    }


def build_html(cases: list[dict[str, Any]]) -> str:
    payload = json.dumps(cases, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Strategy Report Verifier Pipeline Demo</title>
  <style>
    :root {{ --bg:#f5f7fa; --panel:#fff; --line:#d7dde8; --ink:#172033; --muted:#667085; --blue:#155eef; --green:#087443; --red:#b42318; --amber:#985900; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font-family:Arial, "Microsoft YaHei", sans-serif; }}
    header {{ position:sticky; top:0; z-index:2; height:58px; background:var(--panel); border-bottom:1px solid var(--line); display:flex; align-items:center; gap:12px; padding:0 18px; }}
    h1 {{ font-size:17px; margin:0 12px 0 0; }}
    select, button {{ height:34px; border:1px solid var(--line); border-radius:6px; background:#fff; padding:0 10px; }}
    main {{ padding:16px; max-width:1440px; margin:0 auto; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; margin-bottom:14px; overflow:hidden; }}
    .panel h2 {{ margin:0; padding:12px 14px; border-bottom:1px solid var(--line); font-size:16px; }}
    .content {{ padding:14px; }}
    .muted {{ color:var(--muted); font-size:12px; }}
    .grid {{ display:grid; gap:12px; }}
    .cols2 {{ grid-template-columns:1fr 1fr; }}
    .cols3 {{ grid-template-columns:repeat(3, 1fr); }}
    .cols4 {{ grid-template-columns:repeat(4, 1fr); }}
    .score {{ border:1px solid var(--line); border-radius:6px; background:#fbfcfe; padding:10px; }}
    .score strong {{ display:block; font-size:22px; margin-top:5px; }}
    .chiprow {{ display:flex; flex-wrap:wrap; gap:6px; }}
    .chip {{ border:1px solid var(--line); background:#f8fafc; border-radius:999px; padding:3px 8px; font-size:12px; }}
    .ok {{ border-color:#159947; color:var(--green); }}
    .bad {{ border-color:#d92d20; color:var(--red); }}
    .warn {{ border-color:#d98b00; color:var(--amber); }}
    pre {{ margin:0; white-space:pre-wrap; word-break:break-word; max-height:260px; overflow:auto; font-size:12px; line-height:1.45; background:#fbfcfe; border:1px solid var(--line); border-radius:6px; padding:10px; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-top:1px solid var(--line); padding:8px; vertical-align:top; text-align:left; }}
    th {{ color:var(--muted); background:#f8fafc; }}
    details {{ border:1px solid var(--line); border-radius:6px; background:#fbfcfe; margin:8px 0; }}
    summary {{ padding:8px 10px; cursor:pointer; color:#344054; }}
    details pre {{ border:0; border-top:1px solid var(--line); border-radius:0; }}
    .flow {{ display:grid; grid-template-columns:repeat(6, minmax(150px, 1fr)); gap:10px; }}
    .node {{ border:1px solid var(--line); border-radius:8px; background:#fff; padding:10px; min-height:82px; position:relative; }}
    .node b {{ display:block; margin-bottom:5px; }}
    .node::after {{ content:"→"; position:absolute; right:-12px; top:30px; color:var(--blue); font-weight:bold; }}
    .node:last-child::after {{ display:none; }}
    .stage {{ border-left:4px solid var(--blue); padding-left:10px; margin:10px 0 16px; }}
    .stage h3 {{ margin:0 0 6px; font-size:15px; }}
    .plain-intro {{ border:1px solid #b8ccff; background:#f3f7ff; border-radius:8px; padding:12px; margin-bottom:12px; }}
    .plain-intro h3 {{ margin:0 0 8px; font-size:16px; }}
    .plain-intro p {{ margin:5px 0; line-height:1.55; }}
    .plain-intro b {{ color:#0f3e9e; }}
    .aspect-list {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }}
    .aspect {{ border:1px solid var(--line); border-radius:8px; background:#fbfcfe; padding:10px; min-height:108px; }}
    .aspect b {{ display:block; margin-bottom:6px; }}
    .charts {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; }}
    .chart-card {{ border:1px solid var(--line); border-radius:6px; background:#fbfcfe; padding:8px; }}
    .chart-card img {{ width:100%; max-height:260px; object-fit:contain; background:#fff; border:1px solid var(--line); }}
    .chain {{ border:1px solid var(--line); border-radius:8px; padding:10px; margin-bottom:10px; background:#fbfcfe; }}
    .chain-flow {{ display:grid; grid-template-columns:repeat(5, 1fr); gap:8px; }}
    .step {{ background:#fff; border:1px solid var(--line); border-radius:6px; padding:8px; min-height:90px; }}
    @media print {{ header {{ position:static; }} main {{ max-width:none; }} .panel {{ break-inside:avoid; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Strategy Report Verifier Pipeline Demo</h1>
    <select id="caseSelect"></select>
    <button onclick="window.print()">打印 / 保存 PDF</button>
    <span class="muted">self-contained HTML · updated flowchart from VERIFIER_PIPELINE_OVERVIEW.md</span>
  </header>
  <main>
    <section class="panel">
      <h2>What The Verifier Checks</h2>
      <div class="content">
        <div class="aspect-list">
          <div class="aspect"><b>1. Delivery & Structure</b>PDF/HTML 是否可解析，章节是否覆盖 golden case 的 must-have sections，交付是否完整。</div>
          <div class="aspect"><b>2. Sources & Evidence</b>来源数量、来源提示、权威性、事实是否有可追溯支撑。</div>
          <div class="aspect"><b>3. Facts & Numbers</b>关键事实、数字、日期、单位、实体是否保留且语义正确。</div>
          <div class="aspect"><b>4. Strategy Reasoning</b>是否形成 thesis、机制解释、证据到结论、投资含义、风险边界。</div>
          <div class="aspect"><b>5. Scenario & Risk</b>是否说明情景、敏感性、反例、政策/市场/执行风险。</div>
          <div class="aspect"><b>6. Chart QA</b>是否找到正文图表，图表是否完整、清晰、金融语境合适，并与文本一致。</div>
          <div class="aspect"><b>7. Writing & Layout</b>可读性、版式、报告结构、表述是否适合正式策略研究。</div>
          <div class="aspect"><b>8. Compliance & Gate</b>是否触发红线表述，最终是否通过 facts/source/chart/compliance 等 gate。</div>
        </div>
      </div>
    </section>
    <section class="panel">
      <h2>Updated Overall Flowchart</h2>
      <div class="content">
        <div class="flow">
          <div class="node"><b>1. Golden Case</b>query, expected type, source pack, key facts, sections, chart expectations</div>
          <div class="node"><b>2. Candidate PDF/HTML</b>original public report now; generated report later via --candidate-report</div>
          <div class="node"><b>3. Parser</b>text, pages, headings, sections, numbers, dates, links, parse quality</div>
          <div class="node"><b>4. Baseline Rules</b>delivery, sections, sources, numeric/entity, risk, compliance</div>
          <div class="node"><b>5. Specialist Verifiers</b>chart extractor/VLM, Claim/Numeric LLM, Strategy Reasoning LLM</div>
          <div class="node"><b>6. Scoring</b>weighted dimensions, issues, gate, review dashboards</div>
        </div>
        <details><summary>Mermaid source copied into overview document</summary><pre>{html.escape(FLOWCHART_MERMAID)}</pre></details>
      </div>
    </section>
    <div id="caseRoot"></div>
  </main>
  <script>
    const cases = {payload};
    let current = 0;
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    const fmt = (v) => v === undefined || v === null ? '-' : (Number.isFinite(Number(v)) ? Number(v).toFixed(3) : String(v));
    const select = document.getElementById('caseSelect');
    select.innerHTML = cases.map((c,i)=>`<option value="${{i}}">${{esc(c.case_id)}} · ${{esc(c.case.report_title || '')}}</option>`).join('');
    select.onchange = () => {{ current = Number(select.value); render(); }};
    function scoreBox(label, value, note='') {{ return `<div class="score"><span class="muted">${{esc(label)}}</span><strong>${{fmt(value)}}</strong><span class="muted">${{esc(note)}}</span></div>`; }}
    function stageIntro(name, does, tech, flow) {{
      return `<div class="plain-intro">
        <h3>${{esc(name)}}</h3>
        <p><b>这个阶段在干什么：</b>${{esc(does)}}</p>
        <p><b>用了什么技术：</b>${{esc(tech)}}</p>
        <p><b>处理流程：</b>${{esc(flow)}}</p>
      </div>`;
    }}
    function issueChips(issues) {{ return (issues || []).slice(0,8).map(i => `<span class="chip ${{['high','blocker'].includes(i.severity)?'bad':['medium'].includes(i.severity)?'warn':''}}">${{esc(i.severity || '')}}: ${{esc(i.issue_type || '')}}</span>`).join('') || '<span class="chip ok">no major issues recorded</span>'; }}
    function moduleTable(rows) {{
      return `<table><thead><tr><th>Module</th><th>Score</th><th>Input</th><th>Output / logic</th><th>Issues</th></tr></thead><tbody>${{(rows||[]).map(r => `<tr><td><b>${{esc(r.module)}}</b></td><td>${{fmt(r.score)}}</td><td>parsed text + golden metadata</td><td><pre>${{esc(JSON.stringify(r.metrics, null, 2))}}</pre></td><td>${{issueChips(r.issues)}}</td></tr>`).join('')}}</tbody></table>`;
    }}
    function chartCards(charts) {{
      return `<div class="charts">${{(charts||[]).map(c => `<div class="chart-card">${{c.image_data ? `<img src="${{c.image_data}}" />` : ''}}<div class="muted">p${{c.page}} · ${{esc(c.method)}} · ${{esc(c.tier)}} · score ${{fmt(c.score)}}</div><b>${{esc(c.title || c.chart_id)}}</b><div class="chiprow">${{(c.signals||[]).map(s=>`<span class="chip">${{esc(s)}}</span>`).join('')}}</div></div>`).join('')}}</div>`;
    }}
    function chartQaSection(chartInventory, chartScore) {{
      const qa = chartInventory.qa || {{}};
      const subs = qa.subscores || {{}};
      const metrics = qa.metrics || {{}};
      const rows = (qa.chart_rows || []).map(r => `<tr><td>${{esc(r.chart_id)}}</td><td>${{esc(r.page)}}</td><td>${{fmt(r.score)}}</td><td>${{esc(r.excluded ? 'excluded' : 'scored')}}</td><td><pre>${{esc(JSON.stringify(r.subscores, null, 2))}}</pre></td><td>${{issueChips(r.issues)}}</td></tr>`).join('');
      return `
        ${{stageIntro('Stage 2B：Chart QA 图表质量评分', '这一步不是再找图，而是给已经找到的图表打分，判断它们是否像一张合格的金融研究图表。', '规则评分 + 可选 VLM Judge。规则负责标题、单位、来源、数字、清晰度等结构化检查；VLM 负责识别非图表、看图表是否清楚、是否和页面文本匹配。', '先读取 chart inventory；如果启用 VLM，就先做 visual gate，把目录、页脚、纯文字等非图表候选标记为跳过；然后对可评分图表分别计算子分；最后按固定权重汇总成 Chart QA 总分。')}}
        <div class="stage"><h3>Chart QA detailed logic</h3>
          <p>Chart QA has two layers. First, <code>chart_extractor.py</code> performs recall-first extraction: scan PDF pages, classify obvious non-body pages, detect visual objects, add title-anchor/fallback candidates, deduplicate overlaps, then render target chart crops and full-page context. Second, <code>chart_qa.py</code> scores the chart inventory. If VLM is enabled, <code>chart_judges.py</code> first applies a visual gate; non-visual candidates are kept in records but excluded from chart scoring.</p>
          <p>Subscore weights: inventory 15%, spec completeness 15%, data faithfulness 25%, chart-text alignment 20%, visual clarity 15%, financial appropriateness 10%. Data faithfulness and chart-text alignment are hard-threshold dimensions; if either falls below 0.5, chart issues become high severity.</p>
        </div>
        <div class="grid cols4">
          ${{scoreBox('Chart QA score', qa.score)}}
          ${{scoreBox('Chart dimension', chartScore)}}
          ${{scoreBox('Scorable charts', metrics.scorable_chart_count)}}
          ${{scoreBox('Non-visual skipped', metrics.non_visual_skipped_count)}}
          ${{scoreBox('inventory', subs.inventory)}}
          ${{scoreBox('data faithfulness', subs.data_faithfulness)}}
          ${{scoreBox('chart-text alignment', subs.chart_text_alignment)}}
          ${{scoreBox('visual clarity', subs.visual_clarity)}}
        </div>
        <details open><summary>Chart QA metrics and weights</summary><pre>${{esc(JSON.stringify({{weights: {{inventory:0.15, spec_completeness:0.15, data_faithfulness:0.25, chart_text_alignment:0.20, visual_clarity:0.15, financial_appropriateness:0.10}}, metrics, subscores: subs, issues: qa.issues || []}}, null, 2))}}</pre></details>
        <h4>Sample chart-level scoring rows</h4>
        <table><thead><tr><th>Chart</th><th>Page</th><th>Score</th><th>Status</th><th>Subscores</th><th>Issues</th></tr></thead><tbody>${{rows}}</tbody></table>
      `;
    }}
    function claimSection(data) {{
      const facts = (data.golden_fact_results || []).map(f => `<tr><td>${{esc(f.fact_id)}}</td><td>${{esc(f.decision)}}<br><span class="muted">${{esc(f.numeric_status)}}</span></td><td>${{fmt(f.score)}}</td><td>${{esc(f.reason || '')}}</td><td>${{esc(f.evidence_quote || '')}}</td></tr>`).join('');
      const claims = (data.sample_claims || []).map(c => `<tr><td>${{esc(c.claim_id)}}</td><td>${{esc(c.claim_type)}} / ${{esc(c.importance)}}</td><td>${{esc(c.claim)}}</td><td>${{esc((c.numbers || []).join(', '))}}</td></tr>`).join('');
      return `<div class="stage"><h3>Claim/Numeric LLM Verifier</h3><p class="muted">Input: parsed report text + golden key facts. Output: extracted claims, evidence packs, numeric audit, fact-level LLM decisions, and facts dimension score.</p></div>
      <div class="grid cols4">${{scoreBox('overall', data.score)}}${{scoreBox('claim coverage', data.subscores?.claim_coverage)}}${{scoreBox('numeric correctness', data.subscores?.numeric_correctness)}}${{scoreBox('claim discipline', data.subscores?.claim_discipline)}}</div>
      <details open><summary>Numeric audit</summary><pre>${{esc(JSON.stringify(data.numeric_audit, null, 2))}}</pre></details>
      <h4>Golden fact decisions</h4><table><thead><tr><th>Fact</th><th>Decision</th><th>Score</th><th>Reason</th><th>Evidence quote</th></tr></thead><tbody>${{facts}}</tbody></table>
      <h4>Sample extracted claims</h4><table><thead><tr><th>ID</th><th>Type</th><th>Claim</th><th>Numbers</th></tr></thead><tbody>${{claims}}</tbody></table>`;
    }}
    function strategySection(data) {{
      const chainResults = Object.fromEntries((data.chain_results || []).map(x => [x.chain_id, x]));
      const chains = (data.chains || []).map(c => {{
        const j = chainResults[c.chain_id] || {{}};
        return `<div class="chain"><div class="chiprow"><span class="chip">${{esc(c.chain_id)}}</span><span class="chip">${{esc(c.thesis_type)}}</span><span class="chip">${{esc(j.decision || 'no_decision')}} · ${{fmt(j.score)}}</span></div><p><b>Thesis:</b> ${{esc(c.thesis)}}</p><div class="chain-flow"><div class="step"><b>Facts</b>${{esc((c.supporting_facts||[]).join('\\n'))}}</div><div class="step"><b>Mechanism</b>${{esc(c.mechanism)}}</div><div class="step"><b>Implication</b>${{esc(c.investment_implication)}}</div><div class="step"><b>Risk</b>${{esc(c.risk_boundary)}}</div><div class="step"><b>Scenario</b>${{esc(c.scenario_or_counterargument)}}</div></div><p><b>LLM gaps:</b> ${{esc((j.gaps||[]).join('; '))}}</p><p><b>Suggested fix:</b> ${{esc(j.suggested_fix || '')}}</p></div>`;
      }}).join('');
      return `<div class="stage"><h3>Strategy Reasoning LLM Verifier</h3><p class="muted">Input: parsed report text + query/themes/sections/key facts. Output: reasoning chains and LLM scores for thesis, mechanism, evidence-to-conclusion, implication, risk boundary, overclaim control, and theme alignment.</p></div>
      <div class="grid cols4">${{scoreBox('overall', data.score)}}${{scoreBox('thesis clarity', data.subscores?.thesis_clarity)}}${{scoreBox('mechanism depth', data.subscores?.mechanism_depth)}}${{scoreBox('investment implication', data.subscores?.investment_implication)}}${{scoreBox('risk boundary', data.subscores?.scenario_risk_boundary)}}${{scoreBox('overclaim control', data.subscores?.overclaim_control)}}${{scoreBox('theme alignment', data.subscores?.theme_alignment)}}${{scoreBox('evidence→conclusion', data.subscores?.evidence_to_conclusion)}}</div>
      <details><summary>Programmatic reasoning audit</summary><pre>${{esc(JSON.stringify(data.programmatic_audit, null, 2))}}</pre></details>
      ${{chains}}`;
    }}
    function render() {{
      const c = cases[current];
      const chartScore = c.chart_eval.dimension_score_normalized?.charts;
      const factsScore = c.claim_eval.dimension_score_normalized?.facts;
      const strategyScore = c.strategy_eval.dimension_score_normalized?.strategy_reasoning;
      document.getElementById('caseRoot').innerHTML = `
        <section class="panel"><h2>${{esc(c.case_id)}} · ${{esc(c.case.report_title || '')}}</h2><div class="content">
          ${{stageIntro('Stage 0：输入准备', '这一步把“要评测什么”和“拿什么来评测”放到一起。Golden case 说明任务要求，candidate PDF 是实际被检查的报告。', '结构化 JSON metadata + 原始 PDF/HTML 文件路径。当前演示用原始公开报告当 candidate，未来可以换成生成报告。', '读取 golden case；定位 source_document 或 candidate_report；把 query、报告类型、key facts、must-have sections、图表预期等作为后续 verifier 的参照标准。')}}
          <div class="grid cols2"><div><h3>Stage 0 · Inputs</h3><pre>${{esc(JSON.stringify({{case: c.case, source_document: c.source_document}}, null, 2))}}</pre></div><div><h3>Aggregation Snapshot</h3><div class="grid cols3">${{scoreBox('chart dimension', chartScore)}}${{scoreBox('facts dimension', factsScore)}}${{scoreBox('strategy dimension', strategyScore)}}${{scoreBox('chart run overall', c.chart_eval.overall_score, c.chart_eval.grade)}}${{scoreBox('claim run overall', c.claim_eval.overall_score, c.claim_eval.grade)}}${{scoreBox('strategy run overall', c.strategy_eval.overall_score, c.strategy_eval.grade)}}</div></div></div>
        </div></section>
        <section class="panel"><h2>Stage 1 · Parser and Baseline Rule Checks</h2><div class="content">${{stageIntro('Stage 1：解析报告 + 基础规则检查', '这一步先把 PDF/HTML 变成机器能读的文本和结构，再做一轮便宜、稳定的基础检查。', 'PDF/HTML parser、文本抽取、数字/日期抽取、fuzzy matching、关键词/正则规则。', '解析候选报告；抽取正文、标题、章节、数字、日期、链接、来源提示；然后规则模块分别检查交付质量、章节覆盖、来源信号、粗粒度事实/数字一致性、风险情景、合规红线。')}}<div class="stage"><h3>What happens</h3><p>Parser converts PDF/HTML into normalized text, sections, numbers, dates, links and parse-quality metadata. Baseline rules then check delivery, required sections, source signals, rough fact/numeric overlap, risk/scenario, chart presence and compliance redlines.</p></div>${{moduleTable(c.baseline_modules)}}</div></section>
        <section class="panel"><h2>Stage 2 · Chart Extraction / Chart QA</h2><div class="content">${{stageIntro('Stage 2A：图表抽取', '这一步负责从报告正文里尽量找全所有真正的可视化图表，并把每张图裁成单独截图。', 'PDF vector drawing/image 检测、页面文本块、标题锚点、fallback 区域、bbox 去重、截图渲染。', '扫描 PDF 页面；识别视觉对象；结合标题和文本上下文扩展 bbox；去掉重复框和左右图合并框；输出 chart inventory，包括目标图截图、整页截图、页码、bbox、附近文本和 audit 记录。')}}<div class="stage"><h3>Extractor input and output</h3><p>Input: parsed PDF pages, text blocks, vector drawings, embedded images, expected chart hints from golden metadata. Output: chart inventory with target visual crops, page number, bbox, detection method, tier, score, nearby text, full-page context, and audit records for skipped/truncated candidates.</p></div><div class="grid cols3">${{scoreBox('extracted chart candidates', c.chart_inventory.chart_count)}}${{scoreBox('chart dimension', chartScore)}}${{scoreBox('truncated candidates', (c.chart_inventory.audit?.truncated_candidates||[]).length)}}</div>${{chartCards(c.chart_inventory.samples)}}${{chartQaSection(c.chart_inventory, chartScore)}}<details><summary>Chart extraction audit</summary><pre>${{esc(JSON.stringify(c.chart_inventory.audit, null, 2))}}</pre></details></div></section>
        <section class="panel"><h2>Stage 3 · Claim/Numeric LLM Verifier</h2><div class="content">${{stageIntro('Stage 3：事实与数字核查', '这一步检查报告里的关键事实和数字是否覆盖 golden case，数字、日期、单位和结论是否靠谱。', 'LLM claim extraction、证据片段检索、程序化 numeric audit、LLM judge。', '先用 flash 模型抽取候选报告中的重要 claims；再为每条 golden key fact 找候选证据片段；程序化检查数字是否出现和保留；最后用 pro 模型判断 covered、partially covered、missing、contradicted、numeric correctness 和 over-claim。')}}${{claimSection(c.claim_numeric)}}</div></section>
        <section class="panel"><h2>Stage 4 · Strategy Reasoning LLM Verifier</h2><div class="content">${{stageIntro('Stage 4：策略推理质量检查', '这一步判断报告是不是只在堆事实，还是形成了专业策略研究需要的推理链和投资含义。', 'LLM reasoning-chain extraction、主题/链路完整性 audit、LLM strategy judge。', '先抽取 thesis、supporting facts、mechanism、investment implication、risk boundary；再用程序化 audit 看链路是否完整、主题是否对齐；最后由 pro 模型给 thesis clarity、mechanism depth、evidence-to-conclusion、investment implication、risk boundary、overclaim control 等子分。')}}${{strategySection(c.strategy_reasoning)}}</div></section>
        <section class="panel"><h2>Stage 5 · Final Scoring and Gate Logic</h2><div class="content">${{stageIntro('Stage 5：总分聚合与是否通过', '这一步把所有模块的分数合成一张最终成绩单，并判断是否通过质量门槛。', '固定权重加权、规则分与 LLM 分融合、gate failure 规则。', '每个模块输出 0-1 标准分和 issues；scoring.py 按结构、来源、事实、策略推理、风险、图表、写作、合规八个维度加权；如果总分低、事实/来源/图表/合规低于阈值或出现红线，就 gate fail。')}}<div class="stage"><h3>Weighted aggregation</h3><p>Each module produces normalized scores and structured issues. <code>scoring.py</code> blends legacy rule scores with specialist LLM scores where enabled, then applies fixed dimension weights: structure 12, sources 18, facts 18, strategy_reasoning 16, scenario_risk 10, charts 14, writing_layout 7, compliance 5. Gate failures are triggered by low overall score, weak facts/source/compliance/chart dimensions, or redline issues.</p></div><div class="grid cols2"><pre>${{esc(JSON.stringify(c.claim_eval.gate || c.strategy_eval.gate || c.chart_eval.gate, null, 2))}}</pre><div><h3>Representative issues</h3><div class="chiprow">${{issueChips([...(c.chart_eval.top_issues||[]), ...(c.claim_eval.top_issues||[]), ...(c.strategy_eval.top_issues||[])])}}</div></div></div></div></section>
      `;
    }}
    render();
  </script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a self-contained verifier pipeline demo dashboard.")
    parser.add_argument("--out", type=Path, default=ROOT / "evals" / "strategy_report" / "results" / "verifier_pipeline_demo" / "index.html")
    args = parser.parse_args()
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    cases = []
    for entry in DEMO_CASES:
        item = collect_case(entry["case_id"])
        item["label"] = entry["label"]
        cases.append(item)
    write_text(out, build_html(cases))
    print(f"wrote {out} ({len(cases)} cases)")


if __name__ == "__main__":
    main()
