from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from urllib.parse import quote

from eval_utils import ROOT, read_json, write_text


def collect_cases(results_dir: Path, out_file: Path) -> list[dict]:
    rows: list[dict] = []
    claim_dir = results_dir / "claim_numeric"
    for claim_path in sorted(claim_dir.glob("*.claim_numeric.json")):
        data = read_json(claim_path)
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
                "dimension_facts": (eval_data.get("dimension_scores") or {}).get("facts"),
                "dimension_facts_norm": (eval_data.get("dimension_score_normalized") or {}).get("facts"),
                "issues": data.get("issues") or [],
                "candidate_claims": (data.get("candidate_claims") or {}).get("claims") or [],
                "evidence_packs": data.get("evidence_packs") or [],
                "numeric_audit": data.get("numeric_audit") or {},
                "llm_judgement": data.get("llm_judgement") or {},
            }
        )
    return rows


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
    select, button {{ height:34px; border:1px solid var(--line); border-radius:6px; background:#fff; padding:0 10px; }}
    main {{ height:calc(100vh - 56px); display:grid; grid-template-columns: minmax(520px, 56vw) 1fr; }}
    .left {{ overflow:auto; padding:14px; }}
    .right {{ border-left:1px solid var(--line); background:#252932; }}
    iframe {{ width:100%; height:100%; border:0; background:#30343c; }}
    .panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; margin-bottom:12px; }}
    .panel h2 {{ font-size:15px; margin:0; padding:10px 12px; border-bottom:1px solid var(--line); }}
    .content {{ padding:12px; }}
    .score-grid {{ display:grid; grid-template-columns:repeat(4, minmax(100px, 1fr)); gap:8px; }}
    .score {{ border:1px solid var(--line); border-radius:6px; padding:8px; background:#fbfcfe; }}
    .score strong {{ display:block; font-size:20px; margin-top:4px; }}
    .muted {{ color:var(--muted); font-size:12px; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
    .chip {{ border:1px solid var(--line); background:#f8fafc; border-radius:999px; padding:3px 8px; font-size:12px; }}
    .bad {{ border-color:#d92d20; color:#b42318; }}
    .ok {{ border-color:#159947; color:#087443; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th, td {{ border-top:1px solid var(--line); padding:8px; vertical-align:top; text-align:left; }}
    th {{ background:#f8fafc; color:var(--muted); font-weight:600; }}
    details {{ border:1px solid var(--line); border-radius:6px; margin:8px 0; background:#fbfcfe; }}
    summary {{ cursor:pointer; padding:8px 10px; color:var(--muted); }}
    pre {{ margin:0; padding:10px; max-height:260px; overflow:auto; white-space:pre-wrap; word-break:break-word; font-size:12px; line-height:1.45; }}
    .fact {{ border:1px solid var(--line); border-radius:8px; margin-bottom:10px; background:#fff; }}
    .fact-head {{ padding:10px 12px; border-bottom:1px solid var(--line); display:flex; align-items:center; justify-content:space-between; gap:10px; }}
    .fact-body {{ padding:10px 12px; }}
    .quote {{ border-left:3px solid var(--accent); padding-left:8px; color:#344054; }}
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
    const fmt = (v) => v === undefined || v === null ? '-' : Number(v).toFixed ? Number(v).toFixed(3) : String(v);
    const select = document.getElementById('caseSelect');
    select.innerHTML = rows.map((r, i) => `<option value="${{i}}">${{esc(r.case_id)}} score=${{r.score}}</option>`).join('');
    function chip(text, cls='') {{ return `<span class="chip ${{cls}}">${{esc(text)}}</span>`; }}
    function renderScore(label, value) {{ return `<div class="score"><span class="muted">${{esc(label)}}</span><strong>${{fmt(value)}}</strong></div>`; }}
    function judgeMap(r) {{
      const out = {{}};
      for (const item of (r.llm_judgement.golden_fact_results || [])) out[item.fact_id] = item;
      return out;
    }}
    function render() {{
      const r = rows[index];
      select.value = String(index);
      document.getElementById('count').textContent = `${{index + 1}} / ${{rows.length}}`;
      document.getElementById('pdf').src = r.candidate_href || '';
      const judgements = judgeMap(r);
      const issues = (r.issues || []).map(i => chip(`${{i.severity}}: ${{i.issue_type}}`, ['high','blocker'].includes(i.severity) ? 'bad' : '')).join('');
      const facts = (r.evidence_packs || []).map(pack => {{
        const j = judgements[pack.fact_id] || {{}};
        const snippets = (pack.candidate_snippets || []).map(s => `<details><summary>snippet ${{s.rank}} · score ${{s.score}} · numbers ${{(s.numbers || []).join(', ')}}</summary><pre>${{esc(s.text)}}</pre></details>`).join('');
        const nums = (r.numeric_audit.fact_numeric_rows || []).find(n => n.fact_id === pack.fact_id) || {{}};
        const statusCls = ['covered','correct','acceptable'].includes(j.decision) || j.numeric_status === 'correct' ? 'ok' : (j.severity === 'major' || j.severity === 'critical' ? 'bad' : '');
        return `<div class="fact">
          <div class="fact-head">
            <strong>${{esc(pack.fact_id || '')}}</strong>
            <div class="chips">${{chip(j.decision || 'no_llm_decision', statusCls)}}${{chip('numeric: ' + (j.numeric_status || '-'), statusCls)}}${{chip('score: ' + (j.score ?? '-'))}}</div>
          </div>
          <div class="fact-body">
            <div class="quote">${{esc(pack.golden_claim || '')}}</div>
            <div class="chips" style="margin:8px 0;">${{chip('best evidence score: ' + pack.programmatic_best_score)}}${{chip('expected nums: ' + (pack.expected_numbers || []).join(', '))}}${{chip('preserved report: ' + (nums.preserved_in_report ?? '-'))}}${{chip('preserved evidence: ' + (nums.preserved_in_evidence_pack ?? '-'))}}</div>
            <p><strong>LLM reason:</strong> ${{esc(j.reason || '')}}</p>
            <p><strong>Evidence quote:</strong> ${{esc(j.evidence_quote || '')}}</p>
            <p><strong>Suggested fix:</strong> ${{esc(j.suggested_fix || '')}}</p>
            ${{snippets}}
          </div>
        </div>`;
      }}).join('');
      const claims = (r.candidate_claims || []).map(c => `<tr><td>${{esc(c.claim_id)}}</td><td>${{esc(c.claim_type)}}<br><span class="muted">${{esc(c.importance)}}</span></td><td>${{esc(c.claim)}}</td><td>${{esc((c.numbers || []).join(', '))}}</td></tr>`).join('');
      const overclaims = (r.llm_judgement.overclaim_results || []).map(o => `<tr><td>${{esc(o.candidate_claim_id)}}</td><td>${{esc(o.decision)}}</td><td>${{esc(o.severity)}}</td><td>${{esc(o.reason)}}</td></tr>`).join('');
      document.getElementById('left').innerHTML = `
        <section class="panel"><h2>总分与融合逻辑</h2><div class="content">
          <div class="score-grid">
            ${{renderScore('claim_numeric overall', r.score)}}
            ${{renderScore('claim coverage', r.subscores.claim_coverage)}}
            ${{renderScore('numeric correctness', r.subscores.numeric_correctness)}}
            ${{renderScore('claim discipline', r.subscores.claim_discipline)}}
          </div>
          <p class="muted">facts dimension after scoring fusion: ${{r.dimension_facts ?? '-'}} / normalized ${{r.dimension_facts_norm ?? '-'}}</p>
          <div class="chips">${{issues || chip('no issues', 'ok')}}</div>
          <details><summary>LLM overall reason / raw judgement</summary><pre>${{esc(JSON.stringify(r.llm_judgement, null, 2))}}</pre></details>
        </div></section>
        <section class="panel"><h2>程序化数字 Audit</h2><div class="content"><pre>${{esc(JSON.stringify(r.numeric_audit, null, 2))}}</pre></div></section>
        <section class="panel"><h2>Golden Fact 审查链路</h2><div class="content">${{facts}}</div></section>
        <section class="panel"><h2>候选报告抽取 Claims</h2><div class="content"><table><thead><tr><th>ID</th><th>Type</th><th>Claim</th><th>Numbers</th></tr></thead><tbody>${{claims}}</tbody></table></div></section>
        <section class="panel"><h2>Over-claim 检查</h2><div class="content"><table><thead><tr><th>Claim</th><th>Decision</th><th>Severity</th><th>Reason</th></tr></thead><tbody>${{overclaims}}</tbody></table></div></section>
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
    parser = argparse.ArgumentParser(description="Build Claim/Numeric LLM verifier dashboard.")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title", default="Claim/Numeric LLM Verifier Review")
    args = parser.parse_args()
    results_dir = args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = collect_cases(results_dir, out)
    write_text(out, build_html(rows, args.title))
    print(f"wrote {out} ({len(rows)} cases)")


if __name__ == "__main__":
    main()
