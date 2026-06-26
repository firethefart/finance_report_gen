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
    disabled_dimensions = set(scoring.get("disabled_dimensions") or [])
    for key in disabled_dimensions:
        weights[key] = 0
    normalized = {}
    for key in weights:
        module = module_results.get(key) or {}
        normalized[key] = clamp(float(module.get("score", 0.0))) if isinstance(module.get("score"), (int, float)) else 0.0
    overall = weighted_score(normalized, weights)
    issues = collect_v2_issues(module_results)
    redline_issues = (module_results.get("compliance") or {}).get("redline_issues") or []
    gate = build_v2_gate(overall, normalized, parsed, module_results, scoring, adapter_manifest or {})
    evaluation_confidence = estimate_evaluation_confidence(parsed, module_results, adapter_manifest or {})
    return {
        "verifier_version": "v2_candidate_only",
        "report_id": report_id,
        "candidate_report": parsed.get("path"),
        "input_format": parsed.get("format"),
        "overall_score": overall,
        "quality_score": overall,
        "evaluation_confidence": evaluation_confidence,
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
    disabled_gates = set(scoring.get("disabled_gates") or [])
    failures: list[str] = []

    def threshold_enabled(name: str) -> bool:
        if name in disabled_gates:
            return False
        return thresholds.get(name, "__missing__") is not None

    def optional_threshold_enabled(name: str) -> bool:
        if name in disabled_gates:
            return False
        return thresholds.get(name) is not None

    if threshold_enabled("overall_min") and overall < float(thresholds.get("overall_min", 75)):
        failures.append("overall_score_below_threshold")
    if threshold_enabled("text_length_min") and (parsed.get("text_length") or 0) < int(thresholds.get("text_length_min", 2500)):
        failures.append("text_too_short_for_strategy_report")
    if threshold_enabled("compliance_min") and normalized.get("compliance", 0.0) < float(thresholds.get("compliance_min", 0.9)):
        failures.append("compliance_below_threshold")
    if threshold_enabled("visual_min") and normalized.get("visual_qa", 0.0) < float(thresholds.get("visual_min", 0.45)):
        failures.append("visual_qa_below_threshold")
    if threshold_enabled("strategy_reasoning_min") and normalized.get("strategy_reasoning", 0.0) < float(thresholds.get("strategy_reasoning_min", 0.45)):
        failures.append("strategy_reasoning_below_threshold")
    if threshold_enabled("report_likeness_min") and float(parsed.get("report_likeness") or 0.0) < float(thresholds.get("report_likeness_min", 0.35)):
        failures.append("report_likeness_below_threshold")
    if "redline_issue_present" not in disabled_gates and (module_results.get("compliance") or {}).get("redline_issues"):
        failures.append("redline_issue_present")
    if optional_threshold_enabled("source_traceability_min") and normalized.get("source_traceability", 0.0) < float(thresholds.get("source_traceability_min", 0.0)):
        failures.append("source_traceability_below_threshold")
    if optional_threshold_enabled("claim_numeric_min") and normalized.get("claim_numeric_discipline", 0.0) < float(thresholds.get("claim_numeric_min", 0.0)):
        failures.append("claim_numeric_below_threshold")
    adapter_warnings = adapter_manifest.get("warnings") or []
    if "adapter_text_too_short" not in disabled_gates and "html_text_too_short_for_strategy_report" in adapter_warnings:
        failures.append("adapter_text_too_short")
    if "html_visual_resources_broken" not in disabled_gates and "html_broken_visual_resources" in adapter_warnings and not adapter_manifest.get("visual_count"):
        failures.append("html_visual_resources_broken")
    return {
        "passed": not failures,
        "failures": failures,
        "disabled_gates": sorted(disabled_gates),
    }


def estimate_evaluation_confidence(
    parsed: dict[str, Any],
    module_results: dict[str, Any],
    adapter_manifest: dict[str, Any],
) -> dict[str, Any]:
    score = 1.0
    reasons: list[str] = []
    status = parsed.get("html_parse_status") or ""
    if status == "empty_text":
        score -= 0.55
        reasons.append("empty_text")
    elif status == "static_fallback":
        score -= 0.18
        reasons.append("browser_static_fallback")
    elif status == "low_confidence":
        score -= 0.25
        reasons.append("low_confidence_html_parse")
    if (parsed.get("analysis_text_length") or 0) < 2000:
        score -= 0.20
        reasons.append("short_analysis_text")
    if float(parsed.get("report_likeness") or 0.0) < 0.35:
        score -= 0.20
        reasons.append("low_report_likeness")
    warnings = adapter_manifest.get("warnings") or []
    if any(str(item).startswith("html_browser_") for item in warnings):
        score -= 0.10
        reasons.append("browser_runtime_warning")
    if "html_no_visual_objects" in warnings:
        score -= 0.06
        reasons.append("no_visual_objects")
    module_errors = [
        name
        for name, result in module_results.items()
        if isinstance(result, dict) and (result.get("module_error") or result.get("error"))
    ]
    if module_errors:
        score -= min(0.25, 0.08 * len(module_errors))
        reasons.append("module_errors:" + ",".join(module_errors[:4]))
    return {
        "score": round(clamp(score), 3),
        "reasons": reasons,
        "html_parse_status": status,
        "report_likeness": parsed.get("report_likeness"),
        "analysis_text_length": parsed.get("analysis_text_length"),
    }


def render_v2_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# Strategy Report Candidate-Only Verifier: {result['report_id']}",
        "",
        f"- Candidate: `{result['candidate_report']}`",
        f"- Format: `{result['input_format']}`",
        f"- Overall: **{result['overall_score']} / 100**",
        f"- Evaluation confidence: **{(result.get('evaluation_confidence') or {}).get('score', 'n/a')}**",
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
