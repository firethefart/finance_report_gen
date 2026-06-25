from __future__ import annotations

from typing import Any

from eval_utils import clamp, grade_for_score, weighted_score


DEFAULT_V2_WEIGHTS = {
    "delivery": 10,
    "structure": 14,
    "source_traceability": 14,
    "claim_numeric_discipline": 16,
    "strategy_reasoning": 18,
    "scenario_risk": 10,
    "visual_qa": 13,
    "compliance": 5,
}


def aggregate_v2_scores(
    report_id: str,
    parsed: dict[str, Any],
    module_results: dict[str, Any],
    profile: dict[str, Any] | None = None,
    adapter_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = profile or {}
    scoring = profile.get("v2_scoring") or profile.get("scoring") or {}
    weights = {**DEFAULT_V2_WEIGHTS, **(scoring.get("dimension_weights") or {})}
    normalized = {}
    for key in weights:
        module = module_results.get(key) or {}
        normalized[key] = clamp(float(module.get("score", 0.0))) if isinstance(module.get("score"), (int, float)) else 0.0
    overall = weighted_score(normalized, weights)
    issues = collect_v2_issues(module_results)
    redline_issues = (module_results.get("compliance") or {}).get("redline_issues") or []
    gate = build_v2_gate(overall, normalized, parsed, module_results, scoring, adapter_manifest or {})
    return {
        "verifier_version": "v2_candidate_only",
        "report_id": report_id,
        "candidate_report": parsed.get("path"),
        "input_format": parsed.get("format"),
        "overall_score": overall,
        "grade": grade_for_score(overall, redline_issues),
        "weights": weights,
        "dimension_scores": {key: round(normalized[key] * weights[key], 2) for key in weights},
        "dimension_score_normalized": {key: round(value, 3) for key, value in normalized.items()},
        "module_results": module_results,
        "adapter_manifest": adapter_manifest or {},
        "issues": issues,
        "redline_issues": redline_issues,
        "gate": gate,
    }


def collect_v2_issues(module_results: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for name, result in module_results.items():
        for item in result.get("issues") or []:
            issues.append({**item, "module": name})
    severity_rank = {"blocker": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(issues, key=lambda item: severity_rank.get(item.get("severity"), 9))[:80]


def build_v2_gate(
    overall: float,
    normalized: dict[str, float],
    parsed: dict[str, Any],
    module_results: dict[str, Any],
    scoring: dict[str, Any],
    adapter_manifest: dict[str, Any],
) -> dict[str, Any]:
    thresholds = scoring.get("gate_thresholds") or {}
    failures: list[str] = []
    if overall < float(thresholds.get("overall_min", 75)):
        failures.append("overall_score_below_threshold")
    if (parsed.get("text_length") or 0) < int(thresholds.get("text_length_min", 2500)):
        failures.append("text_too_short_for_strategy_report")
    if normalized.get("compliance", 0.0) < float(thresholds.get("compliance_min", 0.9)):
        failures.append("compliance_below_threshold")
    if normalized.get("visual_qa", 0.0) < float(thresholds.get("visual_min", 0.45)):
        failures.append("visual_qa_below_threshold")
    if normalized.get("strategy_reasoning", 0.0) < float(thresholds.get("strategy_reasoning_min", 0.45)):
        failures.append("strategy_reasoning_below_threshold")
    if (module_results.get("compliance") or {}).get("redline_issues"):
        failures.append("redline_issue_present")
    adapter_warnings = adapter_manifest.get("warnings") or []
    if "html_text_too_short_for_strategy_report" in adapter_warnings:
        failures.append("adapter_text_too_short")
    if "html_broken_visual_resources" in adapter_warnings and not adapter_manifest.get("visual_count"):
        failures.append("html_visual_resources_broken")
    return {"passed": not failures, "failures": failures}


def render_v2_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# Strategy Report Candidate-Only Verifier: {result['report_id']}",
        "",
        f"- Candidate: `{result['candidate_report']}`",
        f"- Format: `{result['input_format']}`",
        f"- Overall: **{result['overall_score']} / 100**",
        f"- Grade: **{result['grade']}**",
        f"- Gate: **{'PASS' if result['gate']['passed'] else 'FAIL'}**",
        "",
        "## Dimension Scores",
        "",
    ]
    weights = result.get("weights") or DEFAULT_V2_WEIGHTS
    for key, value in result["dimension_scores"].items():
        lines.append(f"- {key}: {value} / {weights[key]}")
    lines.extend(["", "## Gate Failures", ""])
    if result["gate"]["failures"]:
        lines.extend([f"- {failure}" for failure in result["gate"]["failures"]])
    else:
        lines.append("- None")
    lines.extend(["", "## Top Issues", ""])
    if result["issues"]:
        for item in result["issues"][:20]:
            lines.append(f"- [{item.get('severity')}] {item.get('module')}:{item.get('issue_type')} @ {item.get('location')}: {item.get('description')}")
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"
