from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from eval_utils import ROOT


TOOLS_DIR = ROOT / "dataset_tools" / "strategy_reports"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from verifier_config import make_verifier_client  # noqa: E402


DEFAULT_MODEL = "deepseek/deepseek-v4-pro"


JUDGE_SYSTEM = """You are a senior financial strategy research evaluator.
Judge whether a candidate strategy report satisfies the golden case requirements.
Return strict JSON only. Be exacting but fair. Do not invent facts beyond the provided case and candidate excerpt."""


def build_judge_prompt(case: dict[str, Any], parsed: dict[str, Any], max_chars: int = 9000) -> str:
    compact_case = {
        "case_id": case.get("case_id"),
        "query": case.get("query"),
        "expected_report_type": case.get("expected_report_type"),
        "institution": case.get("institution"),
        "report_title": case.get("report_title"),
        "strategy_subtype": case.get("strategy_subtype"),
        "key_facts": (case.get("key_facts") or [])[:8],
        "must_have_sections": case.get("must_have_sections") or [],
        "prohibited_mistakes": case.get("prohibited_mistakes") or [],
        "reference_notes": case.get("reference_notes") or {},
        "evaluation_hooks": case.get("evaluation_hooks") or {},
    }
    compact_candidate = {
        "title": parsed.get("title"),
        "format": parsed.get("format"),
        "headings": (parsed.get("headings") or [])[:35],
        "parse_quality": parsed.get("parse_quality"),
        "text_excerpt": (parsed.get("text") or "")[:max_chars],
    }
    schema = {
        "strategy_reasoning": {"score": "0-1", "reason": "string"},
        "evidence_support": {"score": "0-1", "reason": "string"},
        "fact_accuracy": {"score": "0-1", "reason": "string"},
        "scenario_risk": {"score": "0-1", "reason": "string"},
        "chart_usefulness": {"score": "0-1", "reason": "string"},
        "writing_layout": {"score": "0-1", "reason": "string"},
        "compliance": {"score": "0-1", "reason": "string", "redline": False},
        "issues": [
            {
                "issue_type": "missing_source|wrong_source|factual_error|numerical_error|temporal_mismatch|entity_mismatch|reasoning_gap|over_claim|missing_counterfactual|missing_scenario|weak_strategy_thesis|chart_mismatch|chart_design_issue|label_unit_error|layout_issue|compliance_issue",
                "severity": "blocker|high|medium|low",
                "location": "short",
                "description": "short",
                "suggested_skill_patch": "short",
            }
        ],
    }
    return (
        "Evaluate this candidate report against the golden strategy-report case.\n"
        "Scoring scale: 1.0 publish-ready institutional quality, 0.7 adequate, 0.4 weak, 0.0 absent or wrong.\n"
        "Focus on strategy thesis, evidence support, fact/numeric accuracy, scenario/risk, charts, writing/layout, and compliance.\n"
        "Return JSON matching this schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}\n\n"
        "GOLDEN_CASE:\n"
        f"{json.dumps(compact_case, ensure_ascii=False, indent=2)}\n\n"
        "CANDIDATE_REPORT:\n"
        f"{json.dumps(compact_candidate, ensure_ascii=False, indent=2)}"
    )


def run_llm_judge(
    case: dict[str, Any],
    parsed: dict[str, Any],
    api_key_file: Path,
    out_dir: Path,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    client = make_verifier_client("llm", api_key_file, out_dir / "llm_logs")
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": build_judge_prompt(case, parsed)},
    ]
    result = client.chat(
        model=model,
        messages=messages,
        max_tokens=4200,
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"case_id": case.get("case_id"), "judge": "strategy_report_eval"},
    )
    if not result.get("ok") or not isinstance(result.get("json"), dict):
        return {
            "ok": False,
            "model": model,
            "error": result.get("error") or "llm_judge_failed",
            "raw": result,
        }
    data = result["json"]
    data["ok"] = True
    data["model"] = model
    data["usage"] = result.get("usage")
    return data
