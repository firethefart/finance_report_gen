from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import mimetypes
import shutil
from pathlib import Path
from typing import Any

from eval_utils import ROOT, read_json, write_json, write_text
from export_alignment_review_tasks import (
    base_case_fields,
    claim_fact_tasks,
    copy_asset,
    safe_id,
    short,
    strategy_chain_tasks,
    write_jsonl,
)


TASK_LABELS = {
    "chart_qa_vlm": "图表 QA / VLM 判断",
    "claim_numeric_fact": "事实与数字核查",
    "strategy_reasoning_chain": "策略推理链判断",
    "claim_discipline_overclaim": "过度宣称 / 表述纪律",
    "rule_issue_review": "规则类问题复核",
}


TASK_SCENARIOS = {
    "chart_qa_vlm": "你正在复核一次图表质量判断。请同时看目标图截图、整页截图和页面文本，判断 VLM 的 gate、checklist、分数和理由是否合理。",
    "claim_numeric_fact": "你正在复核一条 golden key fact 是否被候选报告正确覆盖。请重点看证据片段、数字/单位/日期是否匹配，以及 LLM 给出的 covered/missing 判断是否过严或过松。",
    "strategy_reasoning_chain": "你正在复核一条策略推理链。请判断抽取出的 thesis、机制、投资含义、风险边界是否成立，以及 LLM 对该链条的评分是否符合专业策略研究标准。",
    "claim_discipline_overclaim": "你正在复核一个候选 claim 是否存在过度宣称、确定性措辞或事实/观点混淆。请判断 verifier 的 acceptable/problematic 判定是否合理。",
    "rule_issue_review": "你正在复核一个合规红线 issue。请重点查看 verifier 提取的违规文本，判断它是否真的包含不适合金融研究报告的绝对化、保证性或误导性表述，以及严重性是否合适。",
}


FIELD_HELP = {
    "review_status": "选择 reviewed 表示已完成；skip_unclear_input 表示输入材料不足，无法判断。",
    "expert_rationale": "请用一句话说明判断依据。例如：证据片段没有覆盖该数字，因此 LLM 过于乐观。",
    "is_target_visual_correct": "目标截图是否确实是需要评估的图表/表格，而不是目录、注释、边栏或残缺图片。",
    "is_visual_gate_correct": "VLM 对是否为有效可视化的判断是否正确。",
    "crop_quality_0_5": "0=完全错图；3=主体可见但有裁切/多图混入；5=完整清晰。",
    "text_binding_quality_0_5": "0=文本完全不相关；3=弱相关；5=页面文本准确解释当前图。",
    "checklist_coverage_quality_0_5": "0=漏掉关键维度；3=基本覆盖；5=检查项全面且证据充分。",
    "coverage_decision_correct": "LLM 对 golden fact 是否覆盖的判断是否正确。",
    "numeric_status_correct": "数字、单位、日期、实体匹配判断是否正确；无数字则选 not_applicable。",
    "evidence_pack_sufficient": "证据片段是否足够让你判断该 fact。",
    "unit_normalization_issue": "是否存在单位换算、百分比/bps、亿/万等归一化问题。",
    "chain_extraction_valid": "抽取出的推理链是否是报告中真实存在且完整的策略推理。",
    "reasoning_score_reasonable": "LLM 对推理链的总体分数是否合理。",
    "thesis_quality_0_5": "观点是否清晰、有策略含义。",
    "mechanism_quality_0_5": "因果机制是否充分解释从事实到结论的传导。",
    "evidence_to_conclusion_quality_0_5": "证据是否足以支撑结论，是否存在跳跃。",
    "investment_implication_quality_0_5": "是否明确落到配置、行业、资产、组合或交易含义。",
    "risk_boundary_quality_0_5": "是否说明反例、风险边界或情景条件。",
    "overclaim_decision_correct": "LLM 对 claim 是否过度宣称/可接受的判断是否正确。",
    "claim_severity_correct": "LLM 给出的严重性是否合适。",
    "redline_violation_correct": "verifier 标出的文本是否真的构成合规红线风险；yes=明显违规，partial=有风险但需结合语境，no=误报，unsure=材料不足。",
    "severity_correct": "issue 的 severity 是否合适。",
    "score_reasonableness_0_5": "0=完全不合理；3=大体可接受；5=非常合理。",
    "suggested_score_0_1": "如果你认为 verifier 分数应调整，填 0.0-1.0。",
    "main_error_type": "选择最主要错误类型，用于后续聚类改进。",
}


def chart_tasks_v2(result: dict[str, Any], out_dir: Path) -> list[dict[str, Any]]:
    from export_alignment_review_tasks import chart_tasks as chart_tasks_v1

    filtered = []
    for task in chart_tasks_v1(result, out_dir):
        output = task.get("verifier_output") or {}
        vl = output.get("vl_judge") or {}
        gate = vl.get("visual_gate") or {}
        if gate.get("decision") == "skip_checklist":
            continue
        if gate.get("is_visualization") is False:
            continue
        if vl.get("is_analytical_visual") is False:
            continue
        if output.get("excluded_from_chart_score"):
            continue
        task["feedback_form"] = feedback_form_defaults_v2("chart_qa_vlm")
        filtered.append(task)
    return filtered


def claim_overclaim_tasks(result: dict[str, Any]) -> list[dict[str, Any]]:
    case = base_case_fields(result)
    module = ((result.get("module_results") or {}).get("claim_numeric_llm") or {})
    claims = (module.get("candidate_claims") or {}).get("claims") or []
    claims_by_id = {claim.get("claim_id"): claim for claim in claims}
    tasks = []
    for item in (module.get("llm_judgement") or {}).get("overclaim_results") or []:
        claim_id = item.get("candidate_claim_id")
        task_id = f"{case['case_id']}__overclaim__{claim_id}"
        tasks.append(
            {
                "task_id": task_id,
                "task_type": "claim_discipline_overclaim",
                "priority": "P1",
                "case": case,
                "input": {
                    "candidate_claim": claims_by_id.get(claim_id) or {"claim_id": claim_id},
                    "module_context": {
                        "claim_discipline_score": (module.get("subscores") or {}).get("claim_discipline"),
                        "module_score": module.get("score"),
                    },
                },
                "verifier_output": {
                    "overclaim_judgement": item,
                    "module_issues": module.get("issues") or [],
                },
                "feedback_form": feedback_form_defaults_v2("claim_discipline_overclaim"),
            }
        )
    return tasks


def rule_issue_tasks(result: dict[str, Any]) -> list[dict[str, Any]]:
    case = base_case_fields(result)
    modules = result.get("module_results") or {}
    specs = [
        ("compliance_redline", "合规红线"),
    ]
    tasks = []
    for module_name, module_label in specs:
        module = modules.get(module_name) or {}
        issues = (module.get("issues") or []) + (module.get("redline_issues") or [])
        seen = set()
        for index, issue in enumerate(issues):
            evidence = (issue.get("evidence") or "").strip()
            if issue.get("location") != "redline" or not evidence:
                continue
            key = json.dumps(issue, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            task_id = f"{case['case_id']}__rule__{module_name}_{index + 1}"
            tasks.append(
                {
                    "task_id": task_id,
                    "task_type": "rule_issue_review",
                    "priority": "P1",
                    "case": case,
                    "input": {
                        "module_name": module_name,
                        "module_label": module_label,
                        "module_score": module.get("score"),
                        "module_metrics": module.get("metrics") or {},
                        "violation_text": evidence,
                        "matched_sections": [],
                        "generic_coverage": None,
                    },
                    "verifier_output": {
                        "issue": issue,
                        "module_score": module.get("score"),
                    },
                    "feedback_form": feedback_form_defaults_v2("rule_issue_review"),
                }
            )
    return tasks


def feedback_form_defaults_v2(task_type: str) -> dict[str, Any]:
    common = {
        "reviewer_id": "",
        "review_status": "unreviewed",
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
            "suggested_score_0_1": "",
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
            "score_reasonableness_0_5": "",
            "suggested_score_0_1": "",
            "main_error_type": "",
        },
        "claim_discipline_overclaim": {
            "overclaim_decision_correct": "",
            "claim_severity_correct": "",
            "score_reasonableness_0_5": "",
            "suggested_score_0_1": "",
            "main_error_type": "",
        },
        "rule_issue_review": {
            "redline_violation_correct": "",
            "severity_correct": "",
            "score_reasonableness_0_5": "",
            "suggested_score_0_1": "",
            "main_error_type": "",
        },
    }
    return {**common, **forms[task_type]}


def normalize_task_forms(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for task in tasks:
        task["feedback_form"] = feedback_form_defaults_v2(task["task_type"])
    return tasks


def score_for_sampling(task: dict[str, Any]) -> float:
    output = task.get("verifier_output") or {}
    if task["task_type"] == "chart_qa_vlm":
        return float(output.get("chart_score") or 0)
    if task["task_type"] == "claim_numeric_fact":
        return _float((output.get("fact_judgement") or {}).get("score"))
    if task["task_type"] == "strategy_reasoning_chain":
        return _float((output.get("chain_judgement") or {}).get("score"))
    if task["task_type"] == "claim_discipline_overclaim":
        severity = (output.get("overclaim_judgement") or {}).get("severity")
        return {"critical": 0, "blocker": 0, "high": 0.2, "medium": 0.4, "low": 0.6, "none": 1}.get(str(severity), 0.5)
    if task["task_type"] == "rule_issue_review":
        severity = (output.get("issue") or {}).get("severity")
        return {"blocker": 0, "high": 0.2, "medium": 0.5, "low": 0.8}.get(str(severity), 0.6)
    return 0.5


def _float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def sample_tasks(tasks: list[dict[str, Any]], max_per_type: int) -> list[dict[str, Any]]:
    selected = []
    order = ["chart_qa_vlm", "claim_numeric_fact", "strategy_reasoning_chain", "claim_discipline_overclaim", "rule_issue_review"]
    for task_type in order:
        group = [task for task in tasks if task["task_type"] == task_type]
        group.sort(key=lambda t: (score_for_sampling(t), t["case"]["case_id"], t["task_id"]))
        if len(group) <= max_per_type:
            selected.extend(group)
            continue
        low_n = max(1, max_per_type // 3)
        high_n = max(1, max_per_type // 3)
        low = group[:low_n]
        high = group[-high_n:]
        remaining_n = max_per_type - len(low) - len(high)
        middle_pool = group[low_n : len(group) - high_n]
        if remaining_n > 0 and middle_pool:
            step = max(1, len(middle_pool) // remaining_n)
            mid = [middle_pool[i] for i in range(0, len(middle_pool), step)][:remaining_n]
        else:
            mid = []
        selected.extend(low + mid + high)
    selected.sort(key=lambda t: (t["task_type"], t["case"]["case_id"], t["task_id"]))
    return selected


def build_tasks(results_dir: Path, out_dir: Path, max_per_type: int) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for eval_path in sorted(results_dir.glob("*.eval.json")):
        result = read_json(eval_path)
        tasks.extend(chart_tasks_v2(result, out_dir))
        tasks.extend(claim_fact_tasks(result))
        tasks.extend(strategy_chain_tasks(result))
        tasks.extend(rule_issue_tasks(result))
    return sample_tasks(normalize_task_forms(tasks), max_per_type=max_per_type)


def feedback_schema_v2() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Strategy Verifier Atomic Alignment Feedback V2",
        "type": "array",
        "items": {
            "type": "object",
            "required": ["task_id", "task_type", "feedback"],
            "properties": {
                "task_id": {"type": "string"},
                "task_type": {"enum": list(TASK_LABELS)},
                "feedback": {"type": "object"},
            },
        },
    }


def flat_task_row(task: dict[str, Any]) -> dict[str, Any]:
    output = task.get("verifier_output") or {}
    judgement = output.get("fact_judgement") or output.get("chain_judgement") or output.get("overclaim_judgement") or {}
    issue = output.get("issue") or {}
    return {
        "task_id": task["task_id"],
        "task_type": task["task_type"],
        "task_label": TASK_LABELS[task["task_type"]],
        "priority": task["priority"],
        "case_id": task["case"]["case_id"],
        "overall_score": task["case"]["overall_score"],
        "verifier_score": output.get("chart_score") or judgement.get("score") or output.get("module_score"),
        "verifier_decision": judgement.get("decision") or issue.get("issue_type") or (output.get("vl_judge") or {}).get("visual_gate", {}).get("decision"),
    }


def write_csvs(out_dir: Path, tasks: list[dict[str, Any]]) -> None:
    fields = list(flat_task_row(tasks[0]).keys())
    with (out_dir / "tasks.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for task in tasks:
            writer.writerow(flat_task_row(task))
    feedback_fields = [
        "task_id",
        "task_type",
        "reviewer_id",
        "review_status",
        "expert_rationale",
        "main_error_type",
        "suggested_score_0_1",
    ]
    extra = sorted({key for task in tasks for key in task["feedback_form"] if key not in feedback_fields})
    with (out_dir / "feedback_template.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=feedback_fields + extra)
        writer.writeheader()
        for task in tasks:
            writer.writerow({"task_id": task["task_id"], "task_type": task["task_type"], **task["feedback_form"]})


def build_html(tasks: list[dict[str, Any]], title: str) -> str:
    payload = json.dumps(tasks, ensure_ascii=False)
    labels = json.dumps(TASK_LABELS, ensure_ascii=False)
    scenarios = json.dumps(TASK_SCENARIOS, ensure_ascii=False)
    help_text = json.dumps(FIELD_HELP, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{ --bg:#f4f6f8; --panel:#fff; --line:#d8dee8; --ink:#172033; --muted:#667085; --accent:#155eef; --good:#087443; --bad:#b42318; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Arial, "Microsoft YaHei", "PingFang SC", sans-serif; background:var(--bg); color:var(--ink); }}
    header {{ height:62px; display:flex; gap:10px; align-items:center; padding:0 14px; background:#fff; border-bottom:1px solid var(--line); }}
    header strong {{ white-space:nowrap; }}
    select, button, input, textarea {{ border:1px solid var(--line); border-radius:6px; background:#fff; color:var(--ink); }}
    select, button, input {{ height:34px; padding:0 10px; }}
    button.primary {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
    main {{ display:grid; grid-template-columns:minmax(680px, 58vw) 1fr; height:calc(100vh - 62px); }}
    .left, .right {{ overflow:auto; padding:14px; }}
    .right {{ border-left:1px solid var(--line); background:#fff; }}
    .panel {{ border:1px solid var(--line); border-radius:8px; background:#fff; margin-bottom:12px; overflow:hidden; }}
    .panel h2 {{ margin:0; padding:10px 12px; font-size:15px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:10px; }}
    .content {{ padding:12px; }}
    .panel-guide {{ margin:0 0 10px; padding:8px 10px; border-left:3px solid #2f6fed; background:#f5f8ff; color:#233250; border-radius:6px; line-height:1.55; }}
    .annotation-guide {{ margin-top:10px; padding:10px 12px; background:#fffdf3; border:1px solid #f6d776; border-radius:8px; color:#594a05; line-height:1.6; }}
    .annotation-guide ol {{ margin:6px 0 0 20px; padding:0; }}
    .violation-text {{ border:1px solid #fecdca; background:#fff3f2; color:#7a271a; border-radius:8px; padding:10px; white-space:pre-wrap; word-break:break-word; font-weight:600; }}
    .notice {{ background:#eef4ff; border:1px solid #b2ccff; padding:10px 12px; border-radius:8px; margin-bottom:12px; color:#163b70; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:6px; }}
    .chip {{ border:1px solid var(--line); background:#f8fafc; border-radius:999px; padding:3px 8px; font-size:12px; }}
    .chip.good {{ color:var(--good); border-color:#7cd6a0; background:#f0fdf4; }}
    .chip.bad {{ color:var(--bad); border-color:#fecdca; background:#fff3f2; }}
    .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
    .kv {{ display:grid; grid-template-columns:minmax(240px, 34%) minmax(0, 1fr); gap:0; border:1px solid var(--line); border-radius:8px; overflow:hidden; }}
    .kv div {{ padding:8px; border-bottom:1px solid var(--line); min-width:0; overflow-wrap:anywhere; word-break:break-word; }}
    .kv div:nth-child(odd) {{ background:#f8fafc; color:var(--muted); }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    td, th {{ border-top:1px solid #e4e7ec; padding:8px; text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); background:#f8fafc; }}
    img {{ max-width:100%; border:1px solid var(--line); border-radius:6px; background:#f2f4f7; }}
    pre {{ white-space:pre-wrap; word-break:break-word; max-height:260px; overflow:auto; background:#fbfcfe; border:1px solid #e4e7ec; border-radius:6px; padding:10px; }}
    .form-row {{ margin-bottom:12px; }}
    .form-row label {{ display:flex; align-items:center; gap:6px; font-weight:600; margin-bottom:5px; }}
    .help {{ position:relative; display:inline-flex; align-items:center; justify-content:center; width:18px; height:18px; border-radius:50%; background:#dbeafe; border:1px solid #84adff; color:#174ea6; font-size:12px; font-weight:800; cursor:help; flex:0 0 auto; }}
    .help:hover::after {{ content:attr(data-help); position:absolute; left:24px; top:-8px; z-index:20; width:320px; padding:10px 12px; border:1px solid #2f6fed; border-radius:8px; background:#102a56; color:#fff; font-size:13px; font-weight:500; line-height:1.55; box-shadow:0 10px 28px rgba(16,24,40,.24); }}
    .help:hover::before {{ content:''; position:absolute; left:18px; top:2px; border-width:7px; border-style:solid; border-color:transparent #102a56 transparent transparent; z-index:21; }}
    .form-row select, .form-row input, .form-row textarea {{ width:100%; }}
    .form-row textarea {{ min-height:80px; padding:8px; resize:vertical; }}
    details {{ border:1px solid var(--line); border-radius:6px; margin:8px 0; background:#fbfcfe; }}
    summary {{ padding:8px 10px; cursor:pointer; }}
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
  <button class="primary" id="download">导出标注 JSON</button>
  <button id="clear">清空本地标注</button>
  <span id="count"></span>
</header>
<main>
  <section class="left">
    <div class="notice">
      <b>标注说明：</b>每页是一个原子评测任务。请只基于本页输入材料判断 verifier 输出是否合理；右侧表单会自动保存到浏览器本地，完成后点击“导出标注 JSON”。
    </div>
    <div id="main"></div>
  </section>
  <aside class="right" id="side"></aside>
</main>
<script>
const allTasks = {payload};
const taskLabels = {labels};
const taskScenarios = {scenarios};
const fieldHelp = {help_text};
const storageKey = 'strategy_alignment_v2_pdf21_feedback_patch2';
let feedback = JSON.parse(localStorage.getItem(storageKey) || '{{}}');
let tasks = allTasks.slice();
let idx = 0;
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const val = x => x === undefined || x === null || x === '' ? '-' : x;
const typeSel = document.querySelector('#type');
typeSel.innerHTML = ['all', ...new Set(allTasks.map(t=>t.task_type))].map(t => `<option value="${{t}}">${{t === 'all' ? '全部任务' : taskLabels[t]}}</option>`).join('');
function save() {{ localStorage.setItem(storageKey, JSON.stringify(feedback)); }}
function renderSelect() {{
  document.querySelector('#task').innerHTML = tasks.map((t,i)=>`<option value="${{i}}">${{esc(taskLabels[t.task_type])}} | ${{esc(t.case.case_id)}} | ${{esc(t.task_id).slice(0,70)}}</option>`).join('');
}}
function chip(text, cls='') {{ return `<span class="chip ${{cls}}">${{esc(text)}}</span>`; }}
function chips(items) {{ return (items || []).map(x => chip(x)).join(''); }}
function formatValue(v) {{
  if (v === undefined || v === null || v === '') return '无';
  if (Array.isArray(v)) return v.length ? v.map(x => typeof x === 'object' ? JSON.stringify(x) : String(x)).join('\\n') : '无';
  if (typeof v === 'object') return Object.keys(v).length ? JSON.stringify(v, null, 2) : '无';
  return String(v);
}}
function kv(obj) {{ return `<div class="kv">${{Object.entries(obj||{{}}).map(([k,v])=>`<div>${{esc(k)}}</div><div>${{esc(formatValue(v))}}</div>`).join('')}}</div>`; }}
function table(rows, headers) {{
  return `<table><thead><tr>${{headers.map(h=>`<th>${{esc(h[1])}}</th>`).join('')}}</tr></thead><tbody>${{(rows||[]).map(r=>`<tr>${{headers.map(h=>`<td>${{esc(formatValue(r[h[0]]))}}</td>`).join('')}}</tr>`).join('')}}</tbody></table>`;
}}
function scoreTable(obj) {{ return kv(obj || {{}}); }}
function panelGuide(text) {{ return `<div class="panel-guide">${{esc(text)}}</div>`; }}
function taskAnnotationGuide(taskType) {{
  const common = [
    '先看“输入材料”卡片，确认本页给出的材料是否足够支持判断。',
    '再看“Verifier 输出”卡片，判断模型结论、分数和理由是否与输入材料一致。',
    '最后填写右侧表单：优先选择结构化选项，再用“专家理由”写一句最关键的依据。'
  ];
  const typeTips = {{
    chart_qa_vlm:'图表任务请同时看目标图、整页图和页面文本；如果目标图本身不对，优先指出截图/定位问题。',
    claim_numeric_fact:'事实核查任务请重点比较 golden fact、证据片段、候选 claims，以及数字/单位/日期是否一致。',
    strategy_reasoning_chain:'推理链任务请判断 thesis、机制、证据到结论、投资含义、风险边界是否构成完整专业推理。',
    rule_issue_review:'合规红线任务只判断高亮触发文本是否真的构成绝对化、保证性或误导性表述。',
    claim_discipline_overclaim:'过度宣称任务需要更长上下文，本轮默认不导出。'
  }};
  return `<div class="annotation-guide"><b>简单标注引导</b><ol>${{common.map(x=>`<li>${{esc(x)}}</li>`).join('')}}</ol><p>${{esc(typeTips[taskType] || '')}}</p></div>`;
}}
function snippetCards(rows) {{
  return (rows||[]).map(s => {{
    const text = s.text || '';
    const preview = text.split(/\\s+/).slice(0, 80).join(' ');
    return `<details><summary>片段 ${{esc(s.rank)}} | 检索分 ${{esc(s.score)}} | 数字 ${{esc(formatValue(s.numbers))}}<br><span class="muted">${{esc(preview)}}</span></summary><pre>${{esc(text)}}</pre></details>`;
  }}).join('') || '<p class="muted">无证据片段</p>';
}}
function renderChart(t) {{
  const i=t.input, o=t.verifier_output, vl=o.vl_judge||{{}}, gate=vl.visual_gate||{{}};
  const checks=[...(vl.universal_checklist||[]),...(vl.contextual_checklist||[])];
  return `
    <section class="panel"><h2>输入材料：图表与上下文</h2><div class="content">
      ${{panelGuide('这张卡片展示本次 Chart QA 的输入：目标可视化截图、整页截图、图表元数据和页面文本。专家应先确认目标图是否真的是需要评价的金融可视化。')}}
      <div class="grid"><div><h3>目标图表截图</h3>${{i.target_image ? `<img src="${{i.target_image}}">` : '无截图'}}</div><div><h3>整页截图</h3>${{i.full_page_image ? `<img src="${{i.full_page_image}}">` : '无整页截图'}}</div></div>
      <h3>图表元数据</h3>${{kv({{页码:i.page, 图表类型:i.chart_kind_hint, 检测方法:i.detection_method, 序号:(i.object_index||'-')+'/'+(i.object_count_on_page||'-'), 标题:i.detected_title, 单位:i.unit_hint, 来源:i.source_note, 数字:(i.numbers||[]).slice(0,20).join(', ')}})}}
      <details><summary>附近文本</summary><pre>${{esc(i.nearby_text)}}</pre></details>
      <details><summary>全页文本</summary><pre>${{esc(i.page_text)}}</pre></details>
    </div></section>
    <section class="panel"><h2>Verifier 输出：VLM 图表判断</h2><div class="content">
      ${{panelGuide('这张卡片展示 VLM Judge 对图表的判断，包括是否继续检查、图表子分、逐条 checklist 和文字理由。专家需要判断这些结论是否与左侧截图和文本一致。')}}
      <div class="chips">${{chip('gate: '+val(gate.decision), gate.decision === 'continue' ? 'good' : 'bad')}}${{chip('score: '+val(o.chart_score))}}${{chip('visual: '+val(gate.is_visualization))}}</div>
      <h3>Gate 理由</h3><p>${{esc(gate.reason||'')}}</p>
      <h3>图表子分</h3>${{scoreTable(o.chart_subscores)}}
      <h3>Checklist</h3>${{table(checks, [['id','ID'],['label','检查项'],['score','分数'],['status','状态'],['evidence','证据']])}}
      <h3>VLM 摘要</h3>${{kv({{图表类型:vl.chart_type, 主体描述:vl.target_visual_description, 主要结论:vl.main_takeaway_from_visual, 置信度:vl.confidence, 备注:vl.review_notes}})}}
      <h3>Issues</h3>${{table(o.issues||[], [['issue_type','类型'],['severity','严重性'],['location','位置'],['description','描述'],['suggested_skill_patch','建议']])}}
    </div></section>`;
}}
function renderClaimFact(t) {{
  const i=t.input, o=t.verifier_output, j=o.fact_judgement||{{}};
  return `
    <section class="panel"><h2>输入材料：Golden Fact 与证据</h2><div class="content">
      ${{panelGuide('这张卡片展示待核查的 golden fact、检索到的证据片段、候选 claims 和程序化数字 audit。专家应判断这些材料是否足够支持 verifier 的事实覆盖结论。')}}
      <h3>Golden Fact</h3>${{kv({{fact_id:i.fact_id, 角色:i.fact_role, 事实:i.golden_claim, 期望数字:(i.expected_numbers||[]).join(', '), 期望日期:(i.expected_dates||[]).join(', ')}})}}
      <h3>证据片段</h3>${{snippetCards(i.evidence_snippets||[])}}
      <h3>候选 Claims</h3>${{table(i.candidate_claims||[], [['claim_id','ID'],['claim_type','类型'],['importance','重要性'],['claim','Claim'],['numbers','数字']])}}
      <h3>程序化数字 Audit</h3>${{kv(i.numeric_audit_row||{{}})}}
    </div></section>
    <section class="panel"><h2>Verifier 输出：Fact Judge</h2><div class="content">
      ${{panelGuide('这张卡片展示 LLM 对该 golden fact 的覆盖判断、数字状态、证据引用和模块问题。专家需要判断 decision、numeric status 和分数是否合理。')}}
      <div class="chips">${{chip('decision: '+val(j.decision))}}${{chip('numeric: '+val(j.numeric_status))}}${{chip('score: '+val(j.score))}}</div>
      ${{kv({{证据引用:j.evidence_quote, 理由:j.reason, 修改建议:j.suggested_fix, 匹配claim:(j.matched_candidate_claim_ids||[]).join(', ')}})}}
      <h3>模块子分</h3>${{scoreTable(o.module_subscores)}}
      <h3>模块 Issues</h3>${{table(o.module_issues||[], [['issue_type','类型'],['severity','严重性'],['location','位置'],['description','描述']])}}
    </div></section>`;
}}
function renderStrategy(t) {{
  const i=t.input, o=t.verifier_output, c=i.chain||{{}}, j=o.chain_judgement||{{}};
  return `
    <section class="panel"><h2>输入材料：策略推理链</h2><div class="content">
      ${{panelGuide('这张卡片展示从报告中抽取出的策略推理链，包括观点、机制、投资含义、风险边界和支撑事实。专家应先判断这条链本身是否完整、真实、专业。')}}
      ${{kv({{chain_id:c.chain_id, 类型:c.thesis_type, 重要性:c.importance, Thesis:c.thesis, 机制:c.mechanism, 投资含义:c.investment_implication, 风险边界:c.risk_boundary, 情景或反例:c.scenario_or_counterargument}})}}
      <h3>Supporting facts</h3><pre>${{esc(formatValue(c.supporting_facts))}}</pre>
      <details><summary>原文上下文</summary><pre>${{esc(c.source_context||'缺失')}}</pre></details>
      <details><summary>Golden expectation</summary>${{kv(i.expectation && Object.keys(i.expectation).length ? i.expectation : {{状态:'缺失'}})}}</details>
    </div></section>
    <section class="panel"><h2>Verifier 输出：推理链 Judge</h2><div class="content">
      ${{panelGuide('这张卡片展示 LLM 对策略推理链的专业性评分和理由。专家需要判断它是否正确识别了推理链的优点、缺口和分数区间。')}}
      <div class="chips">${{chip('decision: '+val(j.decision))}}${{chip('score: '+val(j.score))}}</div>
      ${{kv({{优势:(j.strengths||[]).join('; '), 缺口:(j.gaps||[]).join('; '), 证据引用:j.evidence_quote, 修改建议:j.suggested_fix}})}}
      <h3>模块子分</h3>${{scoreTable(o.module_subscores)}}
      <h3>模块 Issues</h3>${{table(o.module_issues||[], [['issue_type','类型'],['severity','严重性'],['location','位置'],['description','描述']])}}
    </div></section>`;
}}
function renderOverclaim(t) {{
  const i=t.input, o=t.verifier_output, c=i.candidate_claim||{{}}, j=o.overclaim_judgement||{{}};
  return `
    <section class="panel"><h2>输入材料：候选 Claim</h2><div class="content">${{kv({{claim_id:c.claim_id, 类型:c.claim_type, 重要性:c.importance, 章节:c.section, Claim:c.claim, 数字:(c.numbers||[]).join(', ')}})}}</div></section>
    <section class="panel"><h2>Verifier 输出：过度宣称判断</h2><div class="content">
      ${{panelGuide('这张卡片展示 LLM 对候选 claim 是否过度宣称的判断。本轮正式导出默认跳过该类任务，因为当前保存上下文不足以稳定复核。')}}
      <div class="chips">${{chip('decision: '+val(j.decision))}}${{chip('severity: '+val(j.severity))}}</div>
      ${{kv({{理由:j.reason, claim_discipline_score:i.module_context?.claim_discipline_score, module_score:i.module_context?.module_score}})}}
      <h3>模块 Issues</h3>${{table(o.module_issues||[], [['issue_type','类型'],['severity','严重性'],['location','位置'],['description','描述']])}}
    </div></section>`;
}}
function renderRuleIssue(t) {{
  const i=t.input, o=t.verifier_output, issue=o.issue||{{}};
  return `
    <section class="panel"><h2>输入材料：规则模块上下文</h2><div class="content">
      ${{panelGuide('这张卡片只展示 verifier 认为触发合规红线的文本段。专家应判断这段文本是否真的包含保证收益、绝对安全、确定性承诺等不适合金融研究报告的表述。')}}
      <h3>完整触发文本</h3><div class="violation-text">${{esc(i.violation_text || '缺失')}}</div>
      ${{kv({{模块:i.module_label, module_name:i.module_name, 模块分:o.module_score}})}}
      <h3>Metrics</h3>${{kv(i.module_metrics||{{}})}}
      <h3>复核重点</h3><p>本任务仅保留合规红线类样本，请判断 verifier 标出的违规文本是否真的存在合规风险。</p>
    </div></section>
    <section class="panel"><h2>Verifier 输出：规则 Issue</h2><div class="content">
      ${{panelGuide('这张卡片展示 verifier 对合规红线的结构化判断，包括严重性、触发位置、描述和证据。专家主要判断是否误报，以及严重性是否过高或过低。')}}
      ${{kv({{类型:issue.issue_type, 严重性:issue.severity, 位置:issue.location, 描述:issue.description, 证据:issue.evidence, 修改建议:issue.suggested_skill_patch}})}}
    </div></section>`;
}}
function formField(name, value) {{
  const help = fieldHelp[name] || '请按你的专业判断填写。';
  const selectOptions = {{
    review_status:['unreviewed','reviewed','skip_unclear_input'],
    is_target_visual_correct:['','yes','partial','no','unsure'],
    is_visual_gate_correct:['','yes','no','unsure'],
    coverage_decision_correct:['','yes','partial','no','unsure'],
    numeric_status_correct:['','yes','no','not_applicable','unsure'],
    evidence_pack_sufficient:['','yes','partial','no'],
    unit_normalization_issue:['','yes','no','unsure'],
    chain_extraction_valid:['','yes','partial','no'],
    reasoning_score_reasonable:['','yes','partial','no','unsure'],
    overclaim_decision_correct:['','yes','partial','no','unsure'],
    claim_severity_correct:['','yes','partial','no','unsure'],
    redline_violation_correct:['','yes','partial','no','unsure'],
    severity_correct:['','yes','partial','no','unsure'],
    main_error_type:['','no_error','wrong_target','bad_crop','non_visual_not_filtered','missed_context','missing_relevant_evidence','wrong_evidence','numeric_mismatch_missed','numeric_false_alarm','unit_conversion_error','bad_chain_extraction','missed_reasoning','score_too_high','score_too_low','checklist_gap','evidence_wrong','rule_false_positive','rule_false_negative','severity_wrong','too_strict','too_lenient','other']
  }};
  const label = fieldLabel(name);
  if (name === 'expert_rationale') return `<div class="form-row"><label>${{label}} <span class="help" title="${{esc(help)}}" data-help="${{esc(help)}}">?</span></label><textarea data-field="${{name}}">${{esc(value||'')}}</textarea></div>`;
  if (selectOptions[name]) return `<div class="form-row"><label>${{label}} <span class="help" title="${{esc(help)}}" data-help="${{esc(help)}}">?</span></label><select data-field="${{name}}">${{selectOptions[name].map(x=>`<option value="${{x}}" ${{String(value||'')===x?'selected':''}}>${{x||'请选择'}}</option>`).join('')}}</select></div>`;
  return `<div class="form-row"><label>${{label}} <span class="help" title="${{esc(help)}}" data-help="${{esc(help)}}">?</span></label><input data-field="${{name}}" value="${{esc(value||'')}}"/></div>`;
}}
function fieldLabel(name) {{
  const map = {{
    reviewer_id:'标注人', review_status:'标注状态', expert_rationale:'专家理由',
    is_target_visual_correct:'目标图是否正确', is_visual_gate_correct:'Visual gate 是否正确', crop_quality_0_5:'裁剪质量 0-5', text_binding_quality_0_5:'文本绑定质量 0-5', checklist_coverage_quality_0_5:'Checklist 覆盖质量 0-5',
    coverage_decision_correct:'覆盖判断是否正确', numeric_status_correct:'数字判断是否正确', evidence_pack_sufficient:'证据是否充分', unit_normalization_issue:'是否有单位归一化问题',
    chain_extraction_valid:'推理链抽取是否有效', reasoning_score_reasonable:'推理评分是否合理', thesis_quality_0_5:'Thesis 质量 0-5', mechanism_quality_0_5:'机制质量 0-5', evidence_to_conclusion_quality_0_5:'证据到结论质量 0-5', investment_implication_quality_0_5:'投资含义质量 0-5', risk_boundary_quality_0_5:'风险边界质量 0-5',
    overclaim_decision_correct:'过度宣称判断是否正确', claim_severity_correct:'严重性是否正确', redline_violation_correct:'合规红线判断是否正确', severity_correct:'严重性是否正确',
    score_reasonableness_0_5:'分数合理性 0-5', suggested_score_0_1:'建议分数 0-1', main_error_type:'主要错误类型'
  }};
  return map[name] || name;
}}
function renderForm(t) {{
  const current = {{...t.feedback_form, ...(feedback[t.task_id]?.feedback || {{}})}};
  return `<section class="panel"><h2>专家反馈表单 <span>${{feedback[t.task_id] ? '已本地保存' : '未填写'}}</span></h2><div class="content">${{Object.entries(current).map(([k,v])=>formField(k,v)).join('')}}<button class="primary" id="saveOne">保存当前任务</button></div></section>`;
}}
function bindForm(t) {{
  document.querySelector('#saveOne').onclick = () => {{
    const values = {{}};
    document.querySelectorAll('[data-field]').forEach(el => values[el.dataset.field] = el.value);
    feedback[t.task_id] = {{task_id:t.task_id, task_type:t.task_type, case_id:t.case.case_id, saved_at:new Date().toISOString(), feedback:values}};
    save();
    render();
  }};
}}
function render() {{
  if (!tasks.length) return;
  const t = tasks[idx];
  document.querySelector('#task').value = idx;
  document.querySelector('#count').textContent = `${{idx+1}} / ${{tasks.length}}（总计 ${{allTasks.length}}，已标 ${{Object.keys(feedback).length}}）`;
  const renderers = {{chart_qa_vlm:renderChart, claim_numeric_fact:renderClaimFact, strategy_reasoning_chain:renderStrategy, claim_discipline_overclaim:renderOverclaim, rule_issue_review:renderRuleIssue}};
  document.querySelector('#main').innerHTML = `
    <section class="panel"><h2>任务卡片</h2><div class="content">
      <div class="chips">${{chip(taskLabels[t.task_type])}}${{chip(t.priority)}}${{chip(t.case.case_id)}}${{chip('overall '+t.case.overall_score)}}${{chip('gate '+t.case.gate_passed, t.case.gate_passed?'good':'bad')}}</div>
      <p><b>场景说明：</b>${{esc(taskScenarios[t.task_type])}}</p>
      ${{taskAnnotationGuide(t.task_type)}}
      <p><b>task_id：</b>${{esc(t.task_id)}}</p>
    </div></section>
    ${{renderers[t.task_type](t)}}
  `;
  document.querySelector('#side').innerHTML = renderForm(t);
  bindForm(t);
}}
document.querySelector('#type').onchange = e => {{
  tasks = e.target.value === 'all' ? allTasks.slice() : allTasks.filter(t=>t.task_type===e.target.value);
  idx = 0; renderSelect(); render();
}};
document.querySelector('#task').onchange = e => {{ idx = Number(e.target.value); render(); }};
document.querySelector('#prev').onclick = () => {{ idx = (idx - 1 + tasks.length) % tasks.length; render(); }};
document.querySelector('#next').onclick = () => {{ idx = (idx + 1) % tasks.length; render(); }};
document.querySelector('#download').onclick = () => {{
  const data = Object.values(feedback);
  const blob = new Blob([JSON.stringify(data, null, 2)], {{type:'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'alignment_feedback_' + new Date().toISOString().replace(/[:.]/g,'-') + '.json';
  a.click();
  URL.revokeObjectURL(a.href);
}};
document.querySelector('#clear').onclick = () => {{
  if (confirm('确认清空本地已保存标注？')) {{ feedback = {{}}; save(); render(); }}
}};
renderSelect(); render();
</script>
</body>
</html>"""


def _asset_to_data_uri(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def inline_image_assets(tasks: list[dict[str, Any]], out_dir: Path) -> list[dict[str, Any]]:
    standalone_tasks = json.loads(json.dumps(tasks, ensure_ascii=False))
    cache: dict[str, str | None] = {}
    for task in standalone_tasks:
        input_data = task.get("input") or {}
        for key in ("target_image", "full_page_image"):
            value = input_data.get(key)
            if not value or str(value).startswith("data:"):
                continue
            asset_path = (out_dir / str(value)).resolve()
            cache_key = str(asset_path)
            if cache_key not in cache:
                cache[cache_key] = _asset_to_data_uri(asset_path)
            if cache[cache_key]:
                input_data[key] = cache[cache_key]
    return standalone_tasks


def export(out_dir: Path, tasks: list[dict[str, Any]], title: str, source_results_dir: Path, max_per_type: int) -> None:
    write_jsonl(out_dir / "tasks.jsonl", tasks)
    write_json(out_dir / "tasks.json", tasks)
    write_csvs(out_dir, tasks)
    write_json(out_dir / "feedback_schema.json", feedback_schema_v2())
    manifest = {
        "version": "v2",
        "source_results_dir": str(source_results_dir),
        "task_count": len(tasks),
        "task_type_counts": {task_type: len([t for t in tasks if t["task_type"] == task_type]) for task_type in sorted({t["task_type"] for t in tasks})},
        "max_per_type": max_per_type,
        "annotation_mode": "pure_html_localstorage_download_json",
    }
    write_json(out_dir / "manifest.json", manifest)
    write_text(out_dir / "index_with_assets.html", build_html(tasks, title))
    standalone_tasks = inline_image_assets(tasks, out_dir)
    write_text(out_dir / "index.html", build_html(standalone_tasks, title))
    write_text(out_dir / "index_standalone.html", build_html(standalone_tasks, f"{title} - Standalone"))
    readme = (
        "# Strategy Verifier Atomic Alignment Export V2\n\n"
        "`index.html` embeds screenshots as data URIs and can be opened as a single local file.\n\n"
        "`index_with_assets.html` is the lighter folder-based version and expects the sibling `assets/` folder to be present.\n\n"
        "`index_standalone.html` is kept as an explicit alias of the single-file version.\n\n"
        "Open `index.html`, annotate tasks in the right-side form, then click `导出标注 JSON`.\n\n"
        "The page stores draft feedback in browser localStorage. No server is required.\n\n"
        f"Task counts: `{manifest['task_type_counts']}`\n"
    )
    write_text(out_dir / "README.md", readme)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Export v2 atomic human-alignment tasks with an offline annotation UI.")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--max-per-type", type=int, default=35)
    parser.add_argument("--title", default="Strategy Verifier Atomic Alignment Review V2")
    args = parser.parse_args()
    results_dir = args.results_dir if args.results_dir.is_absolute() else ROOT / args.results_dir
    out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    if out_dir.exists():
        for child in out_dir.iterdir():
            if child.is_file():
                child.unlink()
            elif child.name == "assets":
                shutil.rmtree(child)
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = build_tasks(results_dir, out_dir, args.max_per_type)
    export(out_dir, tasks, args.title, results_dir, args.max_per_type)


if __name__ == "__main__":
    main()
