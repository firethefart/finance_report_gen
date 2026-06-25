from __future__ import annotations

import argparse
import csv
import html
import json
import os
import shutil
from pathlib import Path
from typing import Any

from eval_utils import ROOT, read_json, write_json, write_text


def rel_href(path: Path, base: Path) -> str:
    try:
        return Path(os.path.relpath(path, base)).as_posix()
    except ValueError:
        return path.as_posix()


def short(value: Any, limit: int = 4000) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated {len(text) - limit} chars]"


def copy_asset(path_value: str | None, out_dir: Path, case_id: str, task_id: str) -> str:
    if not path_value:
        return ""
    src = Path(path_value)
    if not src.is_absolute():
        src = ROOT / src
    if not src.exists():
        return ""
    asset_dir = out_dir / "assets" / case_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix or ".jpg"
    dst = asset_dir / f"{task_id}_{src.stem[:48]}{suffix}"
    if not dst.exists():
        shutil.copy2(src, dst)
    return rel_href(dst, out_dir)


def base_case_fields(result: dict[str, Any]) -> dict[str, Any]:
    dims = result.get("dimension_score_normalized") or {}
    gate = result.get("gate") or {}
    return {
        "case_id": result.get("case_id"),
        "candidate_report": result.get("candidate_report"),
        "overall_score": result.get("overall_score"),
        "grade": result.get("grade"),
        "gate_passed": gate.get("passed"),
        "gate_failures": gate.get("failures") or [],
        "dimension_scores": dims,
    }


def chart_tasks(result: dict[str, Any], out_dir: Path) -> list[dict[str, Any]]:
    case = base_case_fields(result)
    chart_qa = ((result.get("module_results") or {}).get("chart_qa") or {})
    tasks = []
    for chart in chart_qa.get("charts") or []:
        if not chart.get("vl_judged"):
            continue
        task_id = f"{case['case_id']}__chart__{chart.get('chart_id')}"
        tasks.append(
            {
                "task_id": task_id,
                "task_type": "chart_qa_vlm",
                "priority": "P0",
                "case": case,
                "input": {
                    "target_image": copy_asset(chart.get("image_path"), out_dir, case["case_id"], "target_" + safe_id(task_id)),
                    "full_page_image": copy_asset(chart.get("page_image_path"), out_dir, case["case_id"], "page_" + safe_id(task_id)),
                    "page": chart.get("page"),
                    "bbox": chart.get("bbox"),
                    "page_bbox": chart.get("page_bbox"),
                    "detected_title": chart.get("title"),
                    "chart_kind_hint": chart.get("chart_kind_hint"),
                    "detection_method": chart.get("detection_method"),
                    "object_index": chart.get("object_index"),
                    "object_count_on_page": chart.get("object_count_on_page"),
                    "source_note": chart.get("source_note"),
                    "unit_hint": chart.get("unit_hint"),
                    "numbers": chart.get("numbers") or [],
                    "dates": chart.get("dates") or [],
                    "nearby_text": short(chart.get("nearby_text"), 2200),
                    "page_text": short(chart.get("page_text"), 4500),
                },
                "verifier_output": {
                    "chart_score": chart.get("score"),
                    "chart_subscores": chart.get("subscores") or {},
                    "issues": chart.get("issues") or [],
                    "excluded_from_chart_score": chart.get("excluded_from_chart_score"),
                    "skip_reason": chart.get("skip_reason"),
                    "vl_judge": chart.get("vl_judge") or {},
                },
                "feedback_form": feedback_form_defaults("chart_qa_vlm"),
            }
        )
    return tasks


def claim_fact_tasks(result: dict[str, Any]) -> list[dict[str, Any]]:
    case = base_case_fields(result)
    module = ((result.get("module_results") or {}).get("claim_numeric_llm") or {})
    judgement = module.get("llm_judgement") or {}
    fact_results = {item.get("fact_id"): item for item in judgement.get("golden_fact_results") or []}
    numeric_rows = {item.get("fact_id"): item for item in (module.get("numeric_audit") or {}).get("fact_numeric_rows") or []}
    claims = (module.get("candidate_claims") or {}).get("claims") or []
    tasks = []
    for pack in module.get("evidence_packs") or []:
        fact_id = pack.get("fact_id")
        task_id = f"{case['case_id']}__claim_fact__{fact_id}"
        tasks.append(
            {
                "task_id": task_id,
                "task_type": "claim_numeric_fact",
                "priority": "P0",
                "case": case,
                "input": {
                    "fact_id": fact_id,
                    "golden_claim": pack.get("golden_claim"),
                    "fact_role": pack.get("fact_role"),
                    "expected_numbers": pack.get("expected_numbers") or [],
                    "expected_dates": pack.get("expected_dates") or [],
                    "candidate_claims": claims,
                    "evidence_snippets": pack.get("candidate_snippets") or [],
                    "numeric_audit_row": numeric_rows.get(fact_id) or {},
                },
                "verifier_output": {
                    "fact_judgement": fact_results.get(fact_id) or {},
                    "module_subscores": module.get("subscores") or {},
                    "module_score": module.get("score"),
                    "module_issues": module.get("issues") or [],
                },
                "feedback_form": feedback_form_defaults("claim_numeric_fact"),
            }
        )
    return tasks


def strategy_chain_tasks(result: dict[str, Any]) -> list[dict[str, Any]]:
    case = base_case_fields(result)
    module = ((result.get("module_results") or {}).get("strategy_reasoning_llm") or {})
    judgement = module.get("llm_judgement") or {}
    chain_results = {item.get("chain_id"): item for item in judgement.get("chain_results") or []}
    audit_rows = {item.get("chain_id"): item for item in (module.get("programmatic_audit") or {}).get("chain_rows") or []}
    tasks = []
    for chain in (module.get("extraction") or {}).get("chains") or []:
        chain_id = chain.get("chain_id")
        task_id = f"{case['case_id']}__strategy_chain__{chain_id}"
        tasks.append(
            {
                "task_id": task_id,
                "task_type": "strategy_reasoning_chain",
                "priority": "P0",
                "case": case,
                "input": {
                    "expectation": module.get("expectation") or {},
                    "chain": chain,
                    "programmatic_audit_row": audit_rows.get(chain_id) or {},
                },
                "verifier_output": {
                    "chain_judgement": chain_results.get(chain_id) or {},
                    "module_subscores": module.get("subscores") or {},
                    "module_score": module.get("score"),
                    "module_issues": module.get("issues") or [],
                },
                "feedback_form": feedback_form_defaults("strategy_reasoning_chain"),
            }
        )
    return tasks


def feedback_form_defaults(task_type: str) -> dict[str, Any]:
    common = {
        "reviewer_id": "",
        "review_status": "unreviewed",
        "critical_for_verifier_iteration": "",
        "expert_rationale": "",
    }
    forms = {
        "chart_qa_vlm": {
            "is_target_visual_correct": "",
            "is_visual_gate_correct": "",
            "crop_quality_0_5": "",
            "text_binding_quality_0_5": "",
            "checklist_coverage_quality_0_5": "",
            "score_reasonableness_0_5": "",
            "suggested_score_0_1": "",
            "main_error_type": "",
        },
        "claim_numeric_fact": {
            "coverage_decision_correct": "",
            "numeric_status_correct": "",
            "evidence_pack_sufficient": "",
            "unit_normalization_issue": "",
            "score_reasonableness_0_5": "",
            "suggested_fact_score_0_1": "",
            "main_error_type": "",
        },
        "strategy_reasoning_chain": {
            "chain_extraction_valid": "",
            "reasoning_score_reasonable": "",
            "thesis_quality_0_5": "",
            "mechanism_quality_0_5": "",
            "evidence_to_conclusion_quality_0_5": "",
            "investment_implication_quality_0_5": "",
            "risk_boundary_quality_0_5": "",
            "suggested_chain_score_0_1": "",
            "main_error_type": "",
        },
    }
    return {**common, **forms[task_type]}


def feedback_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Strategy Verifier Atomic Alignment Feedback",
        "type": "object",
        "required": ["task_id", "task_type", "reviewer_id", "review_status", "expert_rationale"],
        "properties": {
            "task_id": {"type": "string"},
            "task_type": {"enum": ["chart_qa_vlm", "claim_numeric_fact", "strategy_reasoning_chain"]},
            "reviewer_id": {"type": "string"},
            "review_status": {"enum": ["unreviewed", "reviewed", "skip_unclear_input"]},
            "critical_for_verifier_iteration": {"enum": ["", "yes", "no"]},
            "expert_rationale": {"type": "string"},
            "suggested_score_0_1": {"type": ["number", "string"], "minimum": 0, "maximum": 1},
            "suggested_fact_score_0_1": {"type": ["number", "string"], "minimum": 0, "maximum": 1},
            "suggested_chain_score_0_1": {"type": ["number", "string"], "minimum": 0, "maximum": 1},
        },
        "additionalProperties": True,
    }


def safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)[:160]


def score_for_sampling(task: dict[str, Any]) -> float:
    output = task.get("verifier_output") or {}
    if task["task_type"] == "chart_qa_vlm":
        return float(output.get("chart_score") or 0)
    judgement = output.get("fact_judgement") or output.get("chain_judgement") or {}
    try:
        return float(judgement.get("score") or 0)
    except Exception:
        return 0.0


def sample_tasks(tasks: list[dict[str, Any]], max_per_type: int) -> list[dict[str, Any]]:
    selected = []
    for task_type in ["chart_qa_vlm", "claim_numeric_fact", "strategy_reasoning_chain"]:
        group = [task for task in tasks if task["task_type"] == task_type]
        group.sort(key=lambda t: (score_for_sampling(t), t["case"]["case_id"], t["task_id"]))
        if len(group) <= max_per_type:
            selected.extend(group)
            continue
        low = group[: max_per_type // 3]
        high = group[-max_per_type // 3 :]
        remaining_n = max_per_type - len(low) - len(high)
        step = max(1, len(group) // max(1, remaining_n))
        mid = [group[i] for i in range(len(low), len(group) - len(high), step)][:remaining_n]
        selected.extend(low + mid + high)
    selected.sort(key=lambda t: (t["task_type"], t["case"]["case_id"], t["task_id"]))
    return selected


def build_tasks(results_dir: Path, out_dir: Path, max_per_type: int) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for eval_path in sorted(results_dir.glob("*.eval.json")):
        result = read_json(eval_path)
        tasks.extend(chart_tasks(result, out_dir))
        tasks.extend(claim_fact_tasks(result))
        tasks.extend(strategy_chain_tasks(result))
    return sample_tasks(tasks, max_per_type=max_per_type)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def flatten_for_csv(task: dict[str, Any]) -> dict[str, Any]:
    output = task.get("verifier_output") or {}
    case = task.get("case") or {}
    judgement = output.get("fact_judgement") or output.get("chain_judgement") or {}
    return {
        "task_id": task.get("task_id"),
        "task_type": task.get("task_type"),
        "case_id": case.get("case_id"),
        "overall_score": case.get("overall_score"),
        "gate_passed": case.get("gate_passed"),
        "verifier_score": output.get("chart_score") or judgement.get("score") or output.get("module_score"),
        "verifier_decision": judgement.get("decision") or (output.get("vl_judge") or {}).get("visual_gate", {}).get("decision"),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["task_id", "task_type", "case_id", "overall_score", "gate_passed", "verifier_score", "verifier_decision"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(flatten_for_csv(row))


def write_feedback_template(path: Path, rows: list[dict[str, Any]]) -> None:
    all_fields = [
        "task_id",
        "task_type",
        "reviewer_id",
        "review_status",
        "critical_for_verifier_iteration",
        "expert_rationale",
        "is_target_visual_correct",
        "is_visual_gate_correct",
        "crop_quality_0_5",
        "text_binding_quality_0_5",
        "checklist_coverage_quality_0_5",
        "coverage_decision_correct",
        "numeric_status_correct",
        "evidence_pack_sufficient",
        "unit_normalization_issue",
        "chain_extraction_valid",
        "reasoning_score_reasonable",
        "thesis_quality_0_5",
        "mechanism_quality_0_5",
        "evidence_to_conclusion_quality_0_5",
        "investment_implication_quality_0_5",
        "risk_boundary_quality_0_5",
        "score_reasonableness_0_5",
        "suggested_score_0_1",
        "suggested_fact_score_0_1",
        "suggested_chain_score_0_1",
        "main_error_type",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=all_fields)
        writer.writeheader()
        for task in rows:
            form = task.get("feedback_form") or {}
            writer.writerow({"task_id": task["task_id"], "task_type": task["task_type"], **form})


def build_html(tasks: list[dict[str, Any]], title: str) -> str:
    payload = json.dumps(tasks, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin:0; font-family:Arial, "Microsoft YaHei", sans-serif; background:#f5f7fa; color:#172033; }}
    header {{ height:56px; display:flex; gap:10px; align-items:center; padding:0 14px; background:#fff; border-bottom:1px solid #d8dee8; }}
    select, button {{ height:34px; border:1px solid #d8dee8; border-radius:6px; background:#fff; padding:0 10px; }}
    main {{ display:grid; grid-template-columns: minmax(620px, 58vw) 1fr; height:calc(100vh - 56px); }}
    .left {{ overflow:auto; padding:14px; }}
    .right {{ overflow:auto; padding:14px; border-left:1px solid #d8dee8; background:#fff; }}
    .panel {{ border:1px solid #d8dee8; border-radius:8px; background:#fff; margin-bottom:12px; overflow:hidden; }}
    .panel h2 {{ margin:0; padding:10px 12px; font-size:15px; border-bottom:1px solid #d8dee8; }}
    .content {{ padding:12px; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
    .chip {{ border:1px solid #d8dee8; background:#f8fafc; border-radius:999px; padding:3px 8px; font-size:12px; }}
    pre {{ white-space:pre-wrap; word-break:break-word; max-height:420px; overflow:auto; background:#fbfcfe; border:1px solid #e4e7ec; border-radius:6px; padding:10px; }}
    img {{ max-width:100%; border:1px solid #d8dee8; border-radius:6px; background:#f2f4f7; }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    td, th {{ border-top:1px solid #e4e7ec; padding:8px; text-align:left; vertical-align:top; }}
    th {{ color:#667085; background:#f8fafc; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
    @media(max-width:1100px) {{ main, .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
<header>
  <strong>{html.escape(title)}</strong>
  <button id="prev">上一个</button>
  <button id="next">下一个</button>
  <select id="type"></select>
  <select id="task"></select>
  <span id="count"></span>
</header>
<main>
  <section class="left" id="main"></section>
  <aside class="right" id="side"></aside>
</main>
<script>
const allTasks = {payload};
let tasks = allTasks.slice();
let idx = 0;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const types = ['all', ...new Set(allTasks.map(t => t.task_type))];
document.querySelector('#type').innerHTML = types.map(t => `<option value="${{t}}">${{t}}</option>`).join('');
function renderSelect() {{
  document.querySelector('#task').innerHTML = tasks.map((t,i)=>`<option value="${{i}}">${{esc(t.task_type)}} | ${{esc(t.case.case_id)}} | ${{esc(t.task_id).slice(0,90)}}</option>`).join('');
}}
function chips(items) {{ return (items || []).map(x => `<span class="chip">${{esc(x)}}</span>`).join(''); }}
function jsonBlock(obj) {{ return `<pre>${{esc(JSON.stringify(obj, null, 2))}}</pre>`; }}
function checklistRows(vl) {{
  const rows = [...(vl?.universal_checklist || []), ...(vl?.contextual_checklist || [])];
  return `<table><thead><tr><th>ID</th><th>Item</th><th>Score</th><th>Evidence</th></tr></thead><tbody>${{rows.map(x=>`<tr><td>${{esc(x.id)}}</td><td>${{esc(x.label || x.item || x.check)}}</td><td>${{esc(x.score)}}</td><td>${{esc(x.evidence || x.reason || '')}}</td></tr>`).join('')}}</tbody></table>`;
}}
function render() {{
  if (!tasks.length) return;
  const t = tasks[idx];
  document.querySelector('#task').value = idx;
  document.querySelector('#count').textContent = `${{idx+1}} / ${{tasks.length}} (all ${{allTasks.length}})`;
  const input = t.input || {{}};
  const out = t.verifier_output || {{}};
  let visual = '';
  if (t.task_type === 'chart_qa_vlm') {{
    visual = `<div class="grid"><div><h3>Target chart</h3>${{input.target_image ? `<img src="${{input.target_image}}">` : 'missing image'}}</div><div><h3>Full page</h3>${{input.full_page_image ? `<img src="${{input.full_page_image}}">` : 'missing page image'}}</div></div>`;
  }}
  document.querySelector('#main').innerHTML = `
    <section class="panel"><h2>Task</h2><div class="content">
      <div class="chips">${{chips([t.task_type, t.priority, t.case.case_id, 'overall '+t.case.overall_score, 'gate '+t.case.gate_passed])}}</div>
      <p><b>task_id:</b> ${{esc(t.task_id)}}</p>
    </div></section>
    <section class="panel"><h2>Atomic Input</h2><div class="content">${{visual}}${{jsonBlock(input)}}</div></section>
    <section class="panel"><h2>Verifier Output</h2><div class="content">${{t.task_type === 'chart_qa_vlm' ? checklistRows(out.vl_judge || {{}}) : ''}}${{jsonBlock(out)}}</div></section>
  `;
  document.querySelector('#side').innerHTML = `
    <section class="panel"><h2>Feedback Form</h2><div class="content">${{jsonBlock(t.feedback_form)}}</div></section>
    <section class="panel"><h2>Case Context</h2><div class="content">${{jsonBlock(t.case)}}</div></section>
  `;
}}
document.querySelector('#type').onchange = e => {{
  tasks = e.target.value === 'all' ? allTasks.slice() : allTasks.filter(t => t.task_type === e.target.value);
  idx = 0; renderSelect(); render();
}};
document.querySelector('#task').onchange = e => {{ idx = Number(e.target.value); render(); }};
document.querySelector('#prev').onclick = () => {{ idx = (idx - 1 + tasks.length) % tasks.length; render(); }};
document.querySelector('#next').onclick = () => {{ idx = (idx + 1) % tasks.length; render(); }};
renderSelect(); render();
</script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Export atomic human-alignment review tasks from strategy verifier results.")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-per-type", type=int, default=35)
    parser.add_argument("--title", default="Strategy Verifier Atomic Alignment Review")
    args = parser.parse_args()
    results_dir = args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = build_tasks(results_dir, out_dir, max_per_type=args.max_per_type)
    write_jsonl(out_dir / "tasks.jsonl", tasks)
    write_json(out_dir / "tasks.json", tasks)
    write_csv(out_dir / "tasks.csv", tasks)
    write_feedback_template(out_dir / "feedback_template.csv", tasks)
    write_json(out_dir / "feedback_schema.json", feedback_schema())
    manifest = {
        "source_results_dir": str(results_dir),
        "task_count": len(tasks),
        "task_type_counts": {task_type: len([t for t in tasks if t["task_type"] == task_type]) for task_type in sorted({t["task_type"] for t in tasks})},
        "max_per_type": args.max_per_type,
    }
    write_json(out_dir / "manifest.json", manifest)
    write_text(out_dir / "index.html", build_html(tasks, args.title))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
