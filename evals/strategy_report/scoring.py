from __future__ import annotations

from typing import Any
from pathlib import Path

from eval_utils import clamp, grade_for_score, issue, weighted_score


WEIGHTS = {
    "structure": 12,
    "sources": 18,
    "facts": 18,
    "strategy_reasoning": 16,
    "scenario_risk": 10,
    "charts": 14,
    "writing_layout": 7,
    "compliance": 5,
}


def aggregate_scores(
    case: dict[str, Any],
    parsed: dict[str, Any],
    rule_results: dict[str, Any],
    llm_result: dict[str, Any] | None = None,
    scoring_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    llm = llm_result if llm_result and llm_result.get("ok") else {}
    scoring_profile = scoring_profile or {}
    weights = {**WEIGHTS, **(scoring_profile.get("dimension_weights") or {})}
    dimension_scores = {
        "structure": blend(rule_results["section_coverage"]["score"], rule_results["render_delivery"]["score"], 0.78),
        "sources": blend(rule_results["source_quality"]["score"], nested_score(llm, "evidence_support"), 0.68),
        "facts": blend(
            fact_rule_score(rule_results, scoring_profile),
            nested_score(llm, "fact_accuracy"),
            0.72,
        ),
        "strategy_reasoning": blend(strategy_reasoning_score(rule_results, scoring_profile), nested_score(llm, "strategy_reasoning"), 0.35),
        "scenario_risk": blend(rule_results["scenario_risk"]["score"], nested_score(llm, "scenario_risk"), 0.55),
        "charts": blend(rule_results["chart_qa"]["score"], nested_score(llm, "chart_usefulness"), 0.78),
        "writing_layout": blend(rule_results["render_delivery"]["score"], nested_score(llm, "writing_layout"), 0.55),
        "compliance": blend(rule_results["compliance_redline"]["score"], nested_score(llm, "compliance"), 0.72),
    }
    overall = weighted_score(dimension_scores, weights)
    issues = collect_issues(rule_results, llm)
    redline_issues = rule_results["compliance_redline"].get("redline_issues") or []
    if llm and ((llm.get("compliance") or {}).get("redline") is True):
        redline_issues.append(issue("compliance_issue", "blocker", "llm_compliance", "LLM judge detected a compliance redline."))
    score_diagnostics = build_score_diagnostics(rule_results, scoring_profile)
    gate = build_gate_result(overall, dimension_scores, redline_issues, scoring_profile, score_diagnostics)
    return {
        "case_id": case.get("case_id"),
        "candidate_report": parsed.get("path"),
        "mode": infer_mode(case, parsed),
        "overall_score": overall,
        "grade": grade_for_score(overall, redline_issues),
        "weights": weights,
        "dimension_scores": {key: round(value * weights[key], 2) for key, value in dimension_scores.items()},
        "dimension_score_normalized": {key: round(value, 3) for key, value in dimension_scores.items()},
        "score_diagnostics": score_diagnostics,
        "module_results": rule_results,
        "llm_judge": llm_result or {"ok": False, "skipped": True},
        "redline_issues": redline_issues,
        "issues": issues,
        "gate": gate,
    }


def blend(rule_score: float, llm_score: float | None, rule_weight: float) -> float:
    if llm_score is None:
        return clamp(rule_score)
    return clamp(rule_weight * rule_score + (1 - rule_weight) * llm_score)


def fact_rule_score(rule_results: dict[str, Any], scoring_profile: dict[str, Any] | None = None) -> float:
    legacy = 0.52 * rule_results["claim_citation_alignment"]["score"] + 0.48 * rule_results["numeric_entity_consistency"]["score"]
    claim_numeric = rule_results.get("claim_numeric_llm")
    if isinstance(claim_numeric, dict) and isinstance(claim_numeric.get("score"), (int, float)):
        fusion = (scoring_profile or {}).get("fusion_weights") or {}
        legacy_weight = float(fusion.get("fact_legacy", 0.42))
        llm_weight = float(fusion.get("fact_claim_numeric_llm", 0.58))
        total = max(0.0001, legacy_weight + llm_weight)
        return clamp((legacy_weight * legacy + llm_weight * float(claim_numeric["score"])) / total)
    return clamp(legacy)


def build_score_diagnostics(rule_results: dict[str, Any], scoring_profile: dict[str, Any] | None = None) -> dict[str, Any]:
    legacy_facts = 0.52 * rule_results["claim_citation_alignment"]["score"] + 0.48 * rule_results["numeric_entity_consistency"]["score"]
    claim_numeric = rule_results.get("claim_numeric_llm") or {}
    claim_subscores = claim_numeric.get("subscores") or {}
    strategy = rule_results.get("strategy_reasoning_llm") or {}
    strategy_extraction = strategy.get("extraction") or {}
    strategy_chains = strategy_extraction.get("chains") or []
    return {
        "facts": {
            "legacy_fact_rules": round(clamp(legacy_facts), 3),
            "claim_numeric_llm": claim_numeric.get("score"),
            "claim_coverage": claim_subscores.get("claim_coverage"),
            "numeric_correctness": claim_subscores.get("numeric_correctness"),
            "claim_discipline": claim_subscores.get("claim_discipline"),
            "fusion_weights": ((scoring_profile or {}).get("fusion_weights") or {}),
        },
        "strategy_reasoning": {
            "legacy_strategy_rule": rule_results.get("strategy_reasoning_rule", {}).get("score"),
            "strategy_reasoning_llm": strategy.get("score"),
            "extraction_ok": strategy_extraction.get("ok"),
            "judge_ok": (strategy.get("llm_judgement") or {}).get("ok"),
            "chain_count": len(strategy_chains),
        },
    }


def strategy_reasoning_score(rule_results: dict[str, Any], scoring_profile: dict[str, Any] | None = None) -> float:
    legacy = rule_results["strategy_reasoning_rule"]["score"]
    llm_reasoning = rule_results.get("strategy_reasoning_llm")
    if isinstance(llm_reasoning, dict) and isinstance(llm_reasoning.get("score"), (int, float)):
        fusion = (scoring_profile or {}).get("fusion_weights") or {}
        legacy_weight = float(fusion.get("strategy_legacy", 0.35))
        llm_weight = float(fusion.get("strategy_reasoning_llm", 0.65))
        total = max(0.0001, legacy_weight + llm_weight)
        return clamp((legacy_weight * legacy + llm_weight * float(llm_reasoning["score"])) / total)
    return clamp(legacy)


def infer_mode(case: dict[str, Any], parsed: dict[str, Any]) -> str:
    source_path = (case.get("source_document") or {}).get("file_path")
    if not source_path:
        return "candidate_report"
    try:
        if Path(parsed.get("path", "")).resolve() == Path(source_path).resolve():
            return "calibration_source_as_candidate"
    except Exception:
        pass
    if str(source_path).replace("/", "\\").lower() in str(parsed.get("path", "")).replace("/", "\\").lower():
        return "calibration_source_as_candidate"
    return "candidate_report"


def nested_score(llm: dict[str, Any], key: str) -> float | None:
    value = llm.get(key)
    if isinstance(value, dict):
        score = value.get("score")
        if isinstance(score, (int, float)):
            return clamp(float(score))
        if isinstance(score, str):
            try:
                return clamp(float(score))
            except ValueError:
                return None
    return None


def collect_issues(rule_results: dict[str, Any], llm: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for result in rule_results.values():
        issues.extend(result.get("issues") or [])
    if llm:
        issues.extend(llm.get("issues") or [])
    severity_rank = {"blocker": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(issues, key=lambda item: severity_rank.get(item.get("severity"), 9))[:60]


def build_gate_result(
    overall: float,
    dim: dict[str, float],
    redline_issues: list[dict[str, Any]],
    scoring_profile: dict[str, Any] | None = None,
    score_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thresholds = (scoring_profile or {}).get("gate_thresholds") or {}
    diagnostics = score_diagnostics or {}
    fact_diag = diagnostics.get("facts") or {}
    strategy_diag = diagnostics.get("strategy_reasoning") or {}
    failures: list[str] = []
    if overall < float(thresholds.get("overall_min", 80)):
        failures.append("overall_score_below_80")
    if redline_issues:
        failures.append("redline_issue_present")
    if dim.get("sources", 0.0) < float(thresholds.get("sources_min", 0.7)):
        failures.append("source_quality_below_70pct")
    if dim.get("facts", 0.0) < float(thresholds.get("facts_min", 0.85)):
        failures.append("fact_dimension_below_threshold")
    claim_coverage = fact_diag.get("claim_coverage")
    if isinstance(claim_coverage, (int, float)) and claim_coverage < float(thresholds.get("fact_coverage_min", 0.75)):
        failures.append("fact_coverage_below_threshold")
    numeric_correctness = fact_diag.get("numeric_correctness")
    if isinstance(numeric_correctness, (int, float)) and numeric_correctness < float(thresholds.get("numeric_correctness_min", 0.85)):
        failures.append("numeric_correctness_below_threshold")
    claim_discipline = fact_diag.get("claim_discipline")
    if isinstance(claim_discipline, (int, float)) and claim_discipline < float(thresholds.get("claim_discipline_min", 0.65)):
        failures.append("claim_discipline_below_threshold")
    if strategy_diag.get("extraction_ok") is False or strategy_diag.get("judge_ok") is False:
        failures.append("strategy_reasoning_module_incomplete")
    if strategy_diag.get("extraction_ok") is True and strategy_diag.get("chain_count") == 0:
        failures.append("strategy_reasoning_no_chains")
    if dim.get("compliance", 0.0) < float(thresholds.get("compliance_min", 0.95)):
        failures.append("compliance_not_full_or_near_full")
    if dim.get("charts", 0.0) < float(thresholds.get("charts_min", 0.55)):
        failures.append("chart_qa_materially_weak")
    return {"passed": not failures, "failures": failures}


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# Strategy Report Eval: {result['case_id']}",
        "",
        f"- Candidate: `{result['candidate_report']}`",
        f"- Mode: `{result['mode']}`",
        f"- Overall: **{result['overall_score']} / 100**",
        f"- Grade: **{result['grade']}**",
        f"- Gate: **{'PASS' if result['gate']['passed'] else 'FAIL'}**",
        "",
        "## Dimension Scores",
        "",
    ]
    weights = result.get("weights") or WEIGHTS
    for key, value in result["dimension_scores"].items():
        lines.append(f"- {key}: {value} / {weights[key]}")
    lines.extend(["", "## Gate Failures", ""])
    if result["gate"]["failures"]:
        lines.extend([f"- {failure}" for failure in result["gate"]["failures"]])
    else:
        lines.append("- None")
    lines.extend(["", "## Top Issues", ""])
    if result["issues"]:
        for item in result["issues"][:15]:
            lines.append(f"- [{item.get('severity')}] {item.get('issue_type')} @ {item.get('location')}: {item.get('description')}")
    else:
        lines.append("- None")
    return "\n".join(lines) + "\n"
