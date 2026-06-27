from __future__ import annotations

from pathlib import Path
from typing import Any


FEEDBACK_VERSION = "strategy_report_feedback_v0.1"


MODULE_LABELS = {
    "structure": "Structure and analytical flow",
    "delivery": "Delivery completeness",
    "sources": "Source and citation quality",
    "source_traceability": "Source traceability",
    "facts": "Factual and numeric grounding",
    "claim_numeric_discipline": "Claim and numeric discipline",
    "claim_numeric_llm": "Claim and numeric discipline",
    "strategy_reasoning": "Strategy reasoning",
    "strategy_reasoning_llm": "Strategy reasoning",
    "scenario_risk": "Scenario and risk analysis",
    "charts": "Charts and visual QA",
    "chart_qa": "Charts and visual QA",
    "visual_qa": "Charts and visual QA",
    "writing_layout": "Writing and layout",
    "compliance": "Compliance",
    "compliance_redline": "Compliance",
}


SKILL_AREAS = {
    "structure": "report_outline",
    "delivery": "report_completion",
    "sources": "source_policy",
    "source_traceability": "source_policy",
    "facts": "evidence_and_numbers",
    "claim_numeric_discipline": "evidence_and_numbers",
    "claim_numeric_llm": "evidence_and_numbers",
    "strategy_reasoning": "investment_thesis_reasoning",
    "strategy_reasoning_llm": "investment_thesis_reasoning",
    "scenario_risk": "risk_scenarios",
    "charts": "visual_generation",
    "chart_qa": "visual_generation",
    "visual_qa": "visual_generation",
    "writing_layout": "writing_style_and_layout",
    "compliance": "compliance_guardrails",
    "compliance_redline": "compliance_guardrails",
}


LOW_PRIORITY_MODULES = {"source_traceability", "claim_numeric_discipline", "claim_numeric_llm"}
SEVERITY_RANK = {"blocker": 0, "high": 1, "medium": 2, "low": 3}


def build_feedback_artifact(result: dict[str, Any], flavor: str | None = None) -> dict[str, Any]:
    report_id = str(result.get("report_id") or result.get("case_id") or "unknown_report")
    normalized = normalized_scores(result)
    gate = result.get("gate") or {}
    issues = normalize_issues(result.get("issues") or [])
    module_feedback = build_module_feedback(result, normalized)
    action_items = build_action_items(result, normalized, issues, module_feedback)
    strengths = infer_strengths(normalized, issues)
    weaknesses = infer_weaknesses(action_items, normalized, gate)
    runtime_notes = build_runtime_notes(result)
    score = result.get("overall_score", result.get("quality_score"))
    confidence = (result.get("evaluation_confidence") or {}).get("score")
    if confidence is None and runtime_notes.get("html_parse_status"):
        confidence = parse_quality_to_confidence(runtime_notes.get("parse_quality"))
    return {
        "feedback_version": FEEDBACK_VERSION,
        "report_id": report_id,
        "verifier_flavor": flavor or infer_flavor(result),
        "candidate_report": result.get("candidate_report"),
        "score_summary": {
            "overall_score": score,
            "grade": result.get("grade"),
            "gate_passed": bool(gate.get("passed")),
            "gate_failures": gate.get("failures") or [],
            "evaluation_confidence": confidence,
            "dimension_score_normalized": normalized,
        },
        "reader_summary": {
            "one_line_verdict": one_line_verdict(score, gate, runtime_notes),
            "strengths": strengths,
            "weaknesses": weaknesses,
            "recommended_next_step": recommended_next_step(action_items, gate, runtime_notes),
        },
        "runtime_notes": runtime_notes,
        "module_feedback": module_feedback,
        "action_items": action_items,
        "evidence_index": build_evidence_index(result, issues),
    }


def write_feedback_artifacts(result: dict[str, Any], out_dir: Path, flavor: str | None = None, stem: str | None = None) -> dict[str, str]:
    artifact = build_feedback_artifact(result, flavor=flavor)
    base = stem or str(artifact.get("report_id") or "report")
    json_path = out_dir / f"{base}.feedback.json"
    md_path = out_dir / f"{base}.feedback.md"
    json_path.write_text(to_pretty_json(artifact), encoding="utf-8")
    md_path.write_text(render_feedback_markdown(artifact), encoding="utf-8")
    return {
        "feedback_json": str(json_path),
        "feedback_markdown": str(md_path),
    }


def render_feedback_markdown(feedback: dict[str, Any]) -> str:
    summary = feedback.get("score_summary") or {}
    reader = feedback.get("reader_summary") or {}
    runtime = feedback.get("runtime_notes") or {}
    lines = [
        f"# Verifier Feedback: {feedback.get('report_id')}",
        "",
        f"- Verifier flavor: `{feedback.get('verifier_flavor')}`",
        f"- Candidate: `{feedback.get('candidate_report')}`",
        f"- Overall score: **{summary.get('overall_score', 'n/a')} / 100**",
        f"- Grade: **{summary.get('grade', 'n/a')}**",
        f"- Gate: **{'PASS' if summary.get('gate_passed') else 'FAIL'}**",
        f"- Evaluation confidence: **{summary.get('evaluation_confidence', 'n/a')}**",
        "",
        "## Executive summary",
        "",
        reader.get("one_line_verdict") or "No concise verdict was generated.",
        "",
        "### Strengths",
        "",
    ]
    lines.extend(render_bullets(reader.get("strengths") or ["No clear strengths were detected from this run."]))
    lines.extend(["", "### Main weaknesses", ""])
    lines.extend(render_bullets(reader.get("weaknesses") or ["No material weaknesses were detected from this run."]))
    lines.extend(["", "### Recommended next step", "", f"- {reader.get('recommended_next_step') or 'No immediate skill change is required.'}"])
    lines.extend(["", "## Score snapshot", ""])
    for key, value in (summary.get("dimension_score_normalized") or {}).items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Highest-priority action items", ""])
    action_items = feedback.get("action_items") or []
    if not action_items:
        lines.append("- No action item was generated.")
    for index, item in enumerate(action_items[:10], start=1):
        lines.extend(
            [
                f"{index}. **[{item.get('priority')}] {item.get('skill_area')}**",
                f"   - Problem: {item.get('problem')}",
                f"   - Recommendation: {item.get('recommendation')}",
                f"   - Evidence: {item.get('evidence')}",
                f"   - Source module: `{item.get('module')}`; confidence: `{item.get('confidence')}`",
            ]
        )
    lines.extend(["", "## Module feedback", ""])
    for item in feedback.get("module_feedback") or []:
        lines.append(f"- **{item.get('label')}** (`{item.get('module')}`): score `{item.get('score', 'n/a')}`, status `{item.get('status')}`. {item.get('plain_language_summary')}")
    lines.extend(["", "## Runtime and parse notes", ""])
    runtime_lines = render_runtime_notes(runtime)
    lines.extend(runtime_lines if runtime_lines else ["- No runtime notes."])
    gate_failures = summary.get("gate_failures") or []
    lines.extend(["", "## Gate failures", ""])
    lines.extend(render_bullets(gate_failures or ["None."]))
    return "\n".join(lines) + "\n"


def normalized_scores(result: dict[str, Any]) -> dict[str, float]:
    raw = result.get("dimension_score_normalized") or {}
    normalized: dict[str, float] = {}
    for key, value in raw.items():
        if isinstance(value, (int, float)):
            normalized[str(key)] = round(float(value), 3)
    return normalized


def normalize_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for item in issues:
        if isinstance(item, dict):
            normalized.append(item)
    return sorted(normalized, key=lambda item: SEVERITY_RANK.get(str(item.get("severity")), 9))


def build_module_feedback(result: dict[str, Any], normalized: dict[str, float]) -> list[dict[str, Any]]:
    issues = result.get("issues") or []
    by_module: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        module = str(issue.get("module") or issue.get("location") or "unknown")
        by_module.setdefault(module, []).append(issue)
    feedback = []
    for module, score in sorted(normalized.items(), key=lambda pair: pair[1]):
        module_issues = by_module.get(module) or []
        feedback.append(
            {
                "module": module,
                "label": MODULE_LABELS.get(module, module.replace("_", " ").title()),
                "score": round(score, 3),
                "status": module_status(score),
                "issue_count": len(module_issues),
                "plain_language_summary": module_summary(module, score, module_issues),
                "top_issues": [compact_issue(item) for item in module_issues[:5]],
            }
        )
    return feedback


def build_action_items(
    result: dict[str, Any],
    normalized: dict[str, float],
    issues: list[dict[str, Any]],
    module_feedback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for issue in issues[:12]:
        module = str(issue.get("module") or infer_module_from_issue(issue))
        if module in LOW_PRIORITY_MODULES and len(items) >= 6:
            continue
        items.append(
            action_item(
                module=module,
                severity=str(issue.get("severity") or "medium"),
                problem=str(issue.get("description") or issue.get("issue_type") or "Verifier detected a quality issue."),
                evidence=issue_evidence(issue),
                confidence=issue.get("confidence", "medium"),
                issue_type=str(issue.get("issue_type") or ""),
            )
        )
    existing_modules = {item["module"] for item in items}
    for module_item in module_feedback:
        module = str(module_item.get("module"))
        score = module_item.get("score")
        if not isinstance(score, (int, float)) or score >= 0.68 or module in existing_modules:
            continue
        items.append(
            action_item(
                module=module,
                severity="high" if score < 0.5 else "medium",
                problem=f"{module_item.get('label')} is under target with normalized score {score}.",
                evidence=module_item.get("plain_language_summary") or "Low module score.",
                confidence="medium",
                issue_type="low_dimension_score",
            )
        )
    for failure in (result.get("gate") or {}).get("failures") or []:
        module = module_from_gate_failure(str(failure))
        if module in existing_modules and len(items) >= 8:
            continue
        items.append(
            action_item(
                module=module,
                severity="high",
                problem=f"Quality gate failed: {failure}.",
                evidence=f"Gate failure `{failure}` was emitted by the verifier.",
                confidence="high",
                issue_type="gate_failure",
            )
        )
    items = sorted(items, key=lambda item: (priority_rank(item.get("priority")), SEVERITY_RANK.get(item.get("severity"), 9)))
    return items[:12]


def action_item(module: str, severity: str, problem: str, evidence: str, confidence: Any, issue_type: str) -> dict[str, Any]:
    severity = severity if severity in SEVERITY_RANK else "medium"
    return {
        "priority": priority_for(module, severity),
        "severity": severity,
        "skill_area": SKILL_AREAS.get(module, module.replace("_", "_")),
        "module": module,
        "issue_type": issue_type,
        "problem": problem,
        "recommendation": recommendation_for(module, issue_type),
        "evidence": evidence,
        "confidence": confidence if confidence is not None else "medium",
    }


def recommendation_for(module: str, issue_type: str = "") -> str:
    if module in {"structure", "delivery"}:
        return "Tighten the generation skeleton: require an executive summary, thesis, evidence sections, explicit conclusion, and final delivery checklist."
    if module in {"strategy_reasoning", "strategy_reasoning_llm"}:
        return "Strengthen thesis-to-mechanism-to-portfolio-implication chains; each major claim should end with a decision-useful implication."
    if module == "scenario_risk":
        return "Add scenario boundaries, downside cases, risk triggers, and conditions that would invalidate the thesis."
    if module in {"charts", "chart_qa", "visual_qa"}:
        return "Improve visual generation rules: every analytical visual needs a clear title, units/time window/source note, readable labels, and nearby explanatory text."
    if module in {"facts", "claim_numeric_discipline", "claim_numeric_llm", "sources", "source_traceability"}:
        return "Make claims more evidence-bound: keep numbers traceable, avoid unsupported precision, and pair important conclusions with source or context cues."
    if module in {"compliance", "compliance_redline"}:
        return "Harden compliance guardrails: avoid guaranteed-return language, imperative investment instructions, and unsupported certainty."
    if "gate" in issue_type:
        return "Inspect this gate failure first, then patch the corresponding generation step or verifier configuration if the failure is not aligned with human review."
    return "Review the associated skill prompt and add a concrete generation/checklist constraint for this failure mode."


def build_runtime_notes(result: dict[str, Any]) -> dict[str, Any]:
    module_results = result.get("module_results") or {}
    chart_metrics = {}
    for key in ("chart_qa", "visual_qa", "charts"):
        candidate = module_results.get(key) or {}
        if isinstance(candidate, dict) and candidate.get("metrics"):
            chart_metrics = candidate.get("metrics") or {}
            break
    evaluation_confidence = result.get("evaluation_confidence") or {}
    return {
        "html_parse_status": result.get("html_parse_status") or evaluation_confidence.get("html_parse_status"),
        "parse_quality": result.get("parse_quality"),
        "report_likeness": result.get("report_likeness") or evaluation_confidence.get("report_likeness"),
        "analysis_text_length": evaluation_confidence.get("analysis_text_length"),
        "visual_coverage_status": chart_metrics.get("visual_coverage_status"),
        "visual_object_count": chart_metrics.get("visual_object_count"),
        "scorable_chart_count": chart_metrics.get("scorable_chart_count") or chart_metrics.get("chart_count"),
        "vlm_timing": result.get("vlm_timing") or {},
    }


def build_evidence_index(result: dict[str, Any], issues: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "top_issue_count": len(issues),
        "top_issues": [compact_issue(item) for item in issues[:12]],
        "gate_failures": (result.get("gate") or {}).get("failures") or [],
        "vlm_timing": result.get("vlm_timing") or {},
    }


def infer_strengths(normalized: dict[str, float], issues: list[dict[str, Any]]) -> list[str]:
    issue_modules = {str(item.get("module")) for item in issues[:20]}
    strengths = []
    for module, score in sorted(normalized.items(), key=lambda pair: pair[1], reverse=True):
        if score >= 0.82 and module not in issue_modules:
            strengths.append(f"{MODULE_LABELS.get(module, module)} is strong relative to this run (score {score}).")
        if len(strengths) >= 4:
            break
    return strengths


def infer_weaknesses(action_items: list[dict[str, Any]], normalized: dict[str, float], gate: dict[str, Any]) -> list[str]:
    weaknesses = [f"{item.get('skill_area')}: {item.get('problem')}" for item in action_items[:4]]
    if gate.get("failures") and not weaknesses:
        weaknesses.append("The quality gate failed; inspect gate failures before scaling this sample.")
    if not weaknesses:
        low = [(module, score) for module, score in normalized.items() if score < 0.7]
        weaknesses.extend([f"{MODULE_LABELS.get(module, module)} is below target (score {score})." for module, score in low[:3]])
    return weaknesses


def recommended_next_step(action_items: list[dict[str, Any]], gate: dict[str, Any], runtime: dict[str, Any]) -> str:
    vlm = runtime.get("vlm_timing") or {}
    if vlm.get("client_error") or vlm.get("call_error_count"):
        return "Stabilize VLM/API invocation first, then rerun the sample before judging skill quality."
    if runtime.get("html_parse_status") in {"empty_text", "low_confidence"}:
        return "Fix HTML parsing/runtime coverage before using this sample for skill iteration decisions."
    if action_items:
        top = action_items[0]
        return f"Patch `{top.get('skill_area')}` first: {top.get('recommendation')}"
    if gate.get("failures"):
        return "Review gate failures and decide whether the skill or gate threshold should change."
    return "Use this sample as a positive reference or regression check; no urgent patch is indicated."


def one_line_verdict(score: Any, gate: dict[str, Any], runtime: dict[str, Any]) -> str:
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        numeric_score = 0.0
    if runtime.get("html_parse_status") in {"empty_text", "low_confidence"}:
        return "The verifier produced a result, but parse confidence is weak; treat score comparison cautiously."
    if gate.get("passed") and numeric_score >= 85:
        return "The report is broadly production-usable, with feedback focused on refinement rather than repair."
    if gate.get("passed"):
        return "The report passes the quality gate, but the action items identify useful skill improvements."
    return "The report does not clear the quality gate; address the highest-priority feedback before large-scale use."


def module_summary(module: str, score: float, issues: list[dict[str, Any]]) -> str:
    if score >= 0.82 and not issues:
        return "This area looks strong and does not require immediate skill changes."
    if issues:
        top = issues[0]
        return str(top.get("description") or top.get("issue_type") or "Verifier found issues in this area.")
    if score < 0.5:
        return "This area is materially weak even without a specific extracted issue; inspect the module details."
    if score < 0.68:
        return "This area is below target and should be improved before scaling."
    return "This area is acceptable but still has room for refinement."


def module_status(score: float) -> str:
    if score >= 0.82:
        return "strong"
    if score >= 0.68:
        return "acceptable"
    if score >= 0.5:
        return "needs_improvement"
    return "weak"


def compact_issue(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "module": item.get("module"),
        "severity": item.get("severity"),
        "issue_type": item.get("issue_type"),
        "location": item.get("location"),
        "description": item.get("description"),
    }


def issue_evidence(issue: dict[str, Any]) -> str:
    parts = []
    if issue.get("location"):
        parts.append(f"location={issue.get('location')}")
    if issue.get("module"):
        parts.append(f"module={issue.get('module')}")
    if issue.get("issue_type"):
        parts.append(f"issue_type={issue.get('issue_type')}")
    return "; ".join(parts) or "Verifier issue record."


def infer_module_from_issue(issue: dict[str, Any]) -> str:
    text = " ".join(str(issue.get(key) or "") for key in ("issue_type", "description", "location")).lower()
    if "chart" in text or "visual" in text:
        return "visual_qa"
    if "risk" in text or "scenario" in text:
        return "scenario_risk"
    if "source" in text or "citation" in text:
        return "sources"
    if "compliance" in text or "redline" in text:
        return "compliance"
    if "strategy" in text or "thesis" in text:
        return "strategy_reasoning"
    return "structure"


def module_from_gate_failure(failure: str) -> str:
    lower = failure.lower()
    if "visual" in lower or "chart" in lower:
        return "visual_qa"
    if "strategy" in lower:
        return "strategy_reasoning"
    if "source" in lower:
        return "source_traceability"
    if "fact" in lower or "numeric" in lower or "claim" in lower:
        return "claim_numeric_discipline"
    if "compliance" in lower or "redline" in lower:
        return "compliance"
    if "text" in lower or "report_likeness" in lower or "adapter" in lower:
        return "delivery"
    return "structure"


def priority_for(module: str, severity: str) -> str:
    if severity in {"blocker", "high"} and module not in LOW_PRIORITY_MODULES:
        return "P0"
    if severity in {"blocker", "high"}:
        return "P1"
    if module in {"strategy_reasoning", "scenario_risk", "visual_qa", "charts", "chart_qa"}:
        return "P1"
    if severity == "medium":
        return "P2"
    return "P3"


def priority_rank(value: Any) -> int:
    return {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(str(value), 9)


def parse_quality_to_confidence(parse_quality: Any) -> float | None:
    return {"good": 0.9, "fair": 0.65, "poor": 0.35}.get(str(parse_quality or "").lower())


def infer_flavor(result: dict[str, Any]) -> str:
    if result.get("verifier_version") == "v2_candidate_only" or result.get("report_id"):
        return "candidate_only_no_reference"
    return "v1_reference"


def render_bullets(items: list[Any]) -> list[str]:
    return [f"- {item}" for item in items]


def render_runtime_notes(runtime: dict[str, Any]) -> list[str]:
    lines = []
    for key in ("html_parse_status", "parse_quality", "report_likeness", "analysis_text_length", "visual_coverage_status", "visual_object_count", "scorable_chart_count"):
        if runtime.get(key) is not None:
            lines.append(f"- `{key}`: {runtime.get(key)}")
    vlm = runtime.get("vlm_timing") or {}
    if vlm:
        lines.append(
            "- VLM: "
            f"calls={vlm.get('api_call_attempt_count', vlm.get('vlm_call_count', 0))}, "
            f"errors={vlm.get('call_error_count', vlm.get('vlm_failed_count', 0))}, "
            f"budget_skips={vlm.get('budget_skipped_count', 0)}, "
            f"wall_seconds={vlm.get('vlm_wall_seconds', 'n/a')}"
        )
    return lines


def to_pretty_json(data: dict[str, Any]) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
