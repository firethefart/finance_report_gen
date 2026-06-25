from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from urllib.parse import quote

from eval_utils import ROOT, read_json, write_text


def href_for(path: str | None, base_dir: Path) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    return quote(Path(os.path.relpath(p, base_dir)).as_posix(), safe="/:#?&=%")


def collect_rows(results_dir: Path, out_file: Path) -> list[dict]:
    rows = []
    data_dir = results_dir / "strategy_reasoning"
    for path in sorted(data_dir.glob("*.strategy_reasoning.json")):
        data = read_json(path)
        eval_path = results_dir / f"{data.get('case_id')}.eval.json"
        eval_data = read_json(eval_path) if eval_path.exists() else {}
        rows.append(
            {
                "case_id": data.get("case_id"),
                "score": data.get("score"),
                "subscores": data.get("subscores") or {},
                "models": data.get("models") or {},
                "candidate_report": eval_data.get("candidate_report"),
                "candidate_href": href_for(eval_data.get("candidate_report"), out_file.parent),
                "dimension_strategy": (eval_data.get("dimension_scores") or {}).get("strategy_reasoning"),
                "dimension_strategy_norm": (eval_data.get("dimension_score_normalized") or {}).get("strategy_reasoning"),
                "issues": data.get("issues") or [],
                "chains": (data.get("extraction") or {}).get("chains") or [],
                "expectation": data.get("expectation") or {},
                "programmatic_audit": data.get("programmatic_audit") or {},
                "llm_judgement": data.get("llm_judgement") or {},
            }
        )
    return rows


def build_html(rows: list[dict], title: str) -> str:
    payload = json.dumps(rows, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{ --bg:#f6f7f9; --panel:#fff; --line:#d9dee7; --ink:#172033; --muted:#667085; --accent:#155eef; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font-family:Arial, "Microsoft YaHei", sans-serif; }}
    header {{ height:56px; padding:0 16px; background:var(--panel); border-bottom:1px solid var(--line); display:flex; align-items:center; gap:10px; }}
    h1 {{ font-size:16px; margin:0 12px 0 0; }}
    button, select {{ height:34px; border:1px solid var(--line); border-radius:6px; background:#fff; padding:0 10px; }}
    main {{ height:calc(100vh - 56px); display:grid; grid-template-columns:minmax(580px, 58vw) 1fr; }}
    .left {{ overflow:auto; padding:14px; }}
    .right {{ border-left:1px solid var(--line); background:#252932; }}
    iframe {{ width:100%; height:100%; border:0; background:#30343c; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; margin-bottom:12px; }}
    .panel h2 {{ font-size:15px; margin:0; padding:10px 12px; border-bottom:1px solid var(--line); }}
    .content {{ padding:12px; }}
    .score-grid {{ display:grid; grid-template-columns:repeat(4,minmax(120px,1fr)); gap:8px; }}
    .score {{ border:1px solid var(--line); border-radius:6px; padding:8px; background:#fbfcfe; }}
    .score strong {{ display:block; font-size:20px; margin-top:4px; }}
    .muted {{ color:var(--muted); font-size:12px; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
    .chip {{ border:1px solid var(--line); background:#f8fafc; border-radius:999px; padding:3px 8px; font-size:12px; }}
    .bad {{ border-color:#d92d20; color:#b42318; }}
    .ok {{ border-color:#159947; color:#087443; }}
    .chain {{ border:1px solid var(--line); border-radius:8px; margin-bottom:10px; background:#fff; }}
    .chain-head {{ padding:10px 12px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:10px; }}
    .chain-body {{ padding:10px 12px; }}
    .flow {{ display:grid; grid-template-columns:repeat(5,1fr); gap:8px; margin-top:10px; }}
    .step {{ border:1px solid var(--line); border-radius:6px; padding:8px; background:#fbfcfe; min-height:96px; }}
    .step b {{ display:block; margin-bottom:5px; color:#344054; }}
    details {{ border:1px solid var(--line); border-radius:6px; margin:8px 0; background:#fbfcfe; }}
    summary {{ cursor:pointer; padding:8px 10px; color:var(--muted); }}
    pre {{ margin:0; padding:10px; max-height:280px; overflow:auto; white-space:pre-wrap; word-break:break-word; font-size:12px; line-height:1.45; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-top:1px solid var(--line); padding:8px; vertical-align:top; text-align:left; }}
    th {{ background:#f8fafc; color:var(--muted); }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(title)}</h1>
    <button id="prev">上一例</button>
    <button id="next">下一例</button>
    <select id="caseSelect"></select>
    <span class="muted" id="count"></span>
  </header>
  <main>
    <section class="left" id="left"></section>
    <section class="right"><iframe id="pdf"></iframe></section>
  </main>
  <script>
    const rows = {payload};
    let index = 0;
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    const fmt = (v) => v === undefined || v === null ? '-' : Number(v).toFixed(3);
    const select = document.getElementById('caseSelect');
    select.innerHTML = rows.map((r,i)=>`<option value="${{i}}">${{esc(r.case_id)}} score=${{r.score}}</option>`).join('');
    function chip(text, cls='') {{ return `<span class="chip ${{cls}}">${{esc(text)}}</span>`; }}
    function score(label, value) {{ return `<div class="score"><span class="muted">${{esc(label)}}</span><strong>${{fmt(value)}}</strong></div>`; }}
    function chainJudgementMap(r) {{
      const out = {{}};
      for (const item of (r.llm_judgement.chain_results || [])) out[item.chain_id] = item;
      return out;
    }}
    function render() {{
      const r = rows[index];
      select.value = String(index);
      document.getElementById('count').textContent = `${{index+1}} / ${{rows.length}}`;
      document.getElementById('pdf').src = r.candidate_href || '';
      const judgement = chainJudgementMap(r);
      const issues = (r.issues || []).map(i => chip(`${{i.severity}}: ${{i.issue_type}}`, ['high','blocker'].includes(i.severity) ? 'bad' : '')).join('');
      const chains = (r.chains || []).map(c => {{
        const j = judgement[c.chain_id] || {{}};
        const cls = ['strong','adequate'].includes(j.decision) ? 'ok' : (['weak','unsupported'].includes(j.decision) ? 'bad' : '');
        return `<div class="chain">
          <div class="chain-head">
            <strong>${{esc(c.chain_id)}} · ${{esc(c.thesis_type)}} · ${{esc(c.importance)}}</strong>
            <div class="chips">${{chip(j.decision || 'no_llm_decision', cls)}}${{chip('score: ' + (j.score ?? '-'), cls)}}</div>
          </div>
          <div class="chain-body">
            <p><strong>Thesis:</strong> ${{esc(c.thesis)}}</p>
            <div class="flow">
              <div class="step"><b>Facts</b>${{esc((c.supporting_facts || []).join('\\n'))}}</div>
              <div class="step"><b>Mechanism</b>${{esc(c.mechanism)}}</div>
              <div class="step"><b>Implication</b>${{esc(c.investment_implication)}}</div>
              <div class="step"><b>Risk Boundary</b>${{esc(c.risk_boundary)}}</div>
              <div class="step"><b>Scenario / Counter</b>${{esc(c.scenario_or_counterargument)}}</div>
            </div>
            <p><strong>LLM strengths:</strong> ${{esc((j.strengths || []).join('; '))}}</p>
            <p><strong>LLM gaps:</strong> ${{esc((j.gaps || []).join('; '))}}</p>
            <p><strong>Evidence quote:</strong> ${{esc(j.evidence_quote || '')}}</p>
            <p><strong>Suggested fix:</strong> ${{esc(j.suggested_fix || '')}}</p>
            <details><summary>source context</summary><pre>${{esc(c.source_context || '')}}</pre></details>
          </div>
        </div>`;
      }}).join('');
      const themeRows = (r.programmatic_audit.theme_rows || []).map(t => `<tr><td>${{esc(t.theme)}}</td><td>${{fmt(t.hit)}}</td><td>${{esc(t.matched)}}</td></tr>`).join('');
      const chainRows = (r.programmatic_audit.chain_rows || []).map(t => `<tr><td>${{esc(t.chain_id)}}</td><td>${{fmt(t.completeness)}}</td><td>${{fmt(t.supporting_fact_text_overlap)}}</td><td>${{esc(JSON.stringify(t.completeness_bits))}}</td></tr>`).join('');
      document.getElementById('left').innerHTML = `
        <section class="panel"><h2>总分与出分逻辑</h2><div class="content">
          <div class="score-grid">
            ${{score('overall', r.score)}}
            ${{score('thesis clarity', r.subscores.thesis_clarity)}}
            ${{score('mechanism depth', r.subscores.mechanism_depth)}}
            ${{score('evidence -> conclusion', r.subscores.evidence_to_conclusion)}}
            ${{score('investment implication', r.subscores.investment_implication)}}
            ${{score('scenario/risk boundary', r.subscores.scenario_risk_boundary)}}
            ${{score('overclaim control', r.subscores.overclaim_control)}}
            ${{score('theme alignment', r.subscores.theme_alignment)}}
          </div>
          <p class="muted">strategy dimension after scoring fusion: ${{r.dimension_strategy ?? '-'}} / normalized ${{r.dimension_strategy_norm ?? '-'}}</p>
          <div class="chips">${{issues || chip('no issues', 'ok')}}</div>
          <details><summary>LLM raw judgement</summary><pre>${{esc(JSON.stringify(r.llm_judgement, null, 2))}}</pre></details>
        </div></section>
        <section class="panel"><h2>Golden Expectation</h2><div class="content"><pre>${{esc(JSON.stringify(r.expectation, null, 2))}}</pre></div></section>
        <section class="panel"><h2>Programmatic Audit</h2><div class="content">
          <table><thead><tr><th>Theme</th><th>Hit</th><th>Matched</th></tr></thead><tbody>${{themeRows}}</tbody></table>
          <table><thead><tr><th>Chain</th><th>Completeness</th><th>Evidence overlap</th><th>Bits</th></tr></thead><tbody>${{chainRows}}</tbody></table>
        </div></section>
        <section class="panel"><h2>Reasoning Chains</h2><div class="content">${{chains}}</div></section>
      `;
    }}
    document.getElementById('prev').onclick = () => {{ index = (index - 1 + rows.length) % rows.length; render(); }};
    document.getElementById('next').onclick = () => {{ index = (index + 1) % rows.length; render(); }};
    select.onchange = () => {{ index = Number(select.value); render(); }};
    render();
  </script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Strategy Reasoning LLM verifier dashboard.")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title", default="Strategy Reasoning LLM Verifier Review")
    args = parser.parse_args()
    results_dir = args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    out = args.out if args.out.is_absolute() else ROOT / args.out
    rows = collect_rows(results_dir, out)
    write_text(out, build_html(rows, args.title))
    print(f"wrote {out} ({len(rows)} cases)")


if __name__ == "__main__":
    main()
