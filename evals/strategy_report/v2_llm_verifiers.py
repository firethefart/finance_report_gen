from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from claim_numeric_verifier import (
    DEFAULT_CLAIM_EXTRACT_MODEL,
    DEFAULT_CLAIM_JUDGE_MODEL,
    compact_text as compact_claim_text,
    extract_candidate_claims,
    numeric_normalization_policy,
    parse_numeric_values,
)
from eval_utils import ROOT, clamp, issue, mean, write_json
from strategy_reasoning_verifier import (
    DEFAULT_STRATEGY_EXTRACT_MODEL,
    DEFAULT_STRATEGY_JUDGE_MODEL,
    extract_reasoning_chains,
)
from v2_checks import build_v2_case_stub


TOOLS_DIR = ROOT / "dataset_tools" / "strategy_reports"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from llm_clients import OpenRouterClient  # noqa: E402
from verifier_config import make_verifier_client  # noqa: E402


CLAIM_V2_SYSTEM = """You are a senior financial strategy report verifier.
Evaluate the candidate report's own claim and numeric discipline without using any reference report.
Return strict JSON only. Be strict on units, dates, entities, source binding, over-claiming, and fact/opinion separation."""


STRATEGY_V2_SYSTEM = """You are a senior financial strategy research evaluator.
Evaluate the candidate report's own strategy reasoning quality without using any golden answer.
Return strict JSON only. Be strict about thesis clarity, mechanism depth, evidence-to-conclusion fit, actionable implication, scenario/risk boundary, and over-claim control."""


COMPLIANCE_V2_SYSTEM = """You are a senior financial compliance reviewer for institutional strategy research.
Confirm whether rule-detected redline candidates are true compliance violations in context.
Return strict JSON only. Be conservative about guaranteed returns, risk-free claims, imperative investment instructions, and unsupported certainty. Do not flag negated warnings or standard risk disclosures as violations."""


def run_v2_claim_numeric_llm_verifier(
    parsed: dict[str, Any],
    api_key_file: Path,
    out_dir: Path,
    extract_model: str = DEFAULT_CLAIM_EXTRACT_MODEL,
    judge_model: str = DEFAULT_CLAIM_JUDGE_MODEL,
    max_claims: int = 18,
    config: dict[str, Any] | None = None,
    cache: bool = True,
) -> dict[str, Any]:
    config = config or {}
    report_id = parsed.get("report_id") or "candidate_only"
    out_path = out_dir / "v2_claim_numeric" / f"{report_id}.v2_claim_numeric.json"
    if cache and out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))

    case_stub = build_v2_case_stub(parsed)
    client = make_verifier_client("llm", api_key_file, out_dir / "llm_logs" / "v2_claim_numeric")
    claims = extract_candidate_claims(client, case_stub, parsed, extract_model, max_claims=max_claims, config=config)
    numeric_profile = build_v2_numeric_profile(parsed)
    judgement = judge_v2_claim_numeric(client, parsed, claims, numeric_profile, judge_model, config=config)
    result = assemble_v2_claim_numeric(parsed, claims, numeric_profile, judgement, extract_model, judge_model)
    write_json(out_path, result)
    return result


def judge_v2_claim_numeric(
    client: OpenRouterClient,
    parsed: dict[str, Any],
    claims: dict[str, Any],
    numeric_profile: dict[str, Any],
    model: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    prompt = build_v2_claim_numeric_prompt(parsed, claims, numeric_profile, config)
    raw = client.chat(
        model=model,
        messages=[{"role": "system", "content": CLAIM_V2_SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=int(config.get("judge_max_tokens") or 5200),
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"case_id": parsed.get("report_id"), "judge": "v2_claim_numeric_candidate_only"},
    )
    if not raw.get("ok") or not isinstance(raw.get("json"), dict):
        return {"ok": False, "model": model, "error": raw.get("error") or "v2_claim_numeric_judge_failed", "raw": raw}
    data = raw["json"]
    data["ok"] = True
    data["model"] = model
    data["usage"] = raw.get("usage")
    data["elapsed_seconds"] = raw.get("elapsed_seconds")
    return data


def build_v2_claim_numeric_prompt(parsed: dict[str, Any], claims: dict[str, Any], numeric_profile: dict[str, Any], config: dict[str, Any]) -> str:
    payload = {
        "report": {
            "report_id": parsed.get("report_id"),
            "title": parsed.get("title"),
            "format": parsed.get("format"),
            "headings": (parsed.get("headings") or [])[:35],
            "text_excerpt": compact_claim_text(parsed.get("text") or "", int(config.get("candidate_text_chars") or 16000)),
        },
        "extracted_claims": (claims.get("claims") or [])[: int(config.get("max_claims_for_judge") or 18)],
        "numeric_profile": numeric_profile,
        "numeric_normalization_policy": numeric_normalization_policy(config),
    }
    schema = {
        "overall": {"score": 0.0, "reason": "short"},
        "numeric_grounding": {"score": 0.0, "reason": "numbers have entity/date/unit/context"},
        "unit_and_scale_clarity": {"score": 0.0, "reason": "units and scale are clear"},
        "source_binding": {"score": 0.0, "reason": "claims/numbers are traceable to source notes or evidence"},
        "claim_discipline": {"score": 0.0, "reason": "claims separate facts, forecasts, opinions, and implications"},
        "overclaim_control": {"score": 0.0, "reason": "avoids unsupported certainty"},
        "claim_results": [
            {
                "claim_id": "candidate_claim_001",
                "decision": "well_grounded|partially_grounded|weakly_grounded|unsupported|overclaimed",
                "numeric_status": "correctly_contextualized|minor_context_gap|major_context_gap|not_numeric",
                "severity": "none|minor|major|critical",
                "score": 0.0,
                "evidence_quote": "short quote from report text",
                "reason": "short",
                "suggested_fix": "short",
            }
        ],
        "issues": [
            {
                "issue_type": "numeric_context_weak|unit_signal_weak|source_binding_weak|claim_overstated|fact_opinion_blur|unsupported_claim",
                "severity": "blocker|high|medium|low",
                "location": "claim_id or section",
                "description": "short",
                "suggested_skill_patch": "short",
            }
        ],
    }
    return (
        "Evaluate whether this candidate strategy report handles factual and numeric claims professionally.\n"
        "Do not compare with a reference report. Judge only internal discipline: context, units, source binding, uncertainty, and over-claim control.\n"
        "Score continuously from 0 to 1. Penalize major numbers without units/entities/dates, unsupported claims, and certainty language.\n"
        "Use extracted_claims as candidates, but you may also use the report text excerpt when judging.\n"
        "Return compact JSON. Include at most 8 claim_results and at most 8 issues. Keep every reason/evidence/suggested_fix under 20 Chinese characters or 18 English words.\n"
        "Do not include markdown, analysis prose, or any text outside the JSON object.\n"
        "Return strict JSON only, matching this schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def build_v2_numeric_profile(parsed: dict[str, Any]) -> dict[str, Any]:
    text = parsed.get("text") or ""
    values = parse_numeric_values(text)
    return {
        "number_count": len(parsed.get("numbers") or []),
        "normalized_numeric_value_count": len(values),
        "sample_normalized_values": values[:80],
        "source_hint_count": parsed.get("source_hint_count") or 0,
        "date_count": len(parsed.get("dates") or []),
    }


def assemble_v2_claim_numeric(
    parsed: dict[str, Any],
    claims: dict[str, Any],
    numeric_profile: dict[str, Any],
    judgement: dict[str, Any],
    extract_model: str,
    judge_model: str,
) -> dict[str, Any]:
    if judgement.get("ok"):
        subscores = {
            "numeric_grounding": nested_score(judgement, "numeric_grounding"),
            "unit_and_scale_clarity": nested_score(judgement, "unit_and_scale_clarity"),
            "source_binding": nested_score(judgement, "source_binding"),
            "claim_discipline": nested_score(judgement, "claim_discipline"),
            "overclaim_control": nested_score(judgement, "overclaim_control"),
        }
        overall = nested_score(judgement, "overall") or weighted_mean(
            subscores,
            {
                "numeric_grounding": 0.28,
                "unit_and_scale_clarity": 0.20,
                "source_binding": 0.20,
                "claim_discipline": 0.18,
                "overclaim_control": 0.14,
            },
        )
    else:
        subscores = {
            "numeric_grounding": 0.45,
            "unit_and_scale_clarity": 0.45,
            "source_binding": clamp((parsed.get("source_hint_count") or 0) / 8),
            "claim_discipline": 0.50,
            "overclaim_control": 0.55,
        }
        overall = weighted_mean(subscores, {})
    issues = normalize_llm_issues(judgement.get("issues") or [], default_type="claim_numeric_issue")
    return {
        "ok": bool(claims.get("claims")),
        "module_complete": bool(judgement.get("ok")),
        "score": round(clamp(overall), 3),
        "subscores": {key: round(clamp(value), 3) for key, value in subscores.items()},
        "issues": issues,
        "candidate_claims": claims,
        "numeric_profile": numeric_profile,
        "llm_judgement": judgement,
        "models": {"claim_extraction": extract_model, "claim_judge": judge_model},
    }


def run_v2_strategy_reasoning_llm_verifier(
    parsed: dict[str, Any],
    api_key_file: Path,
    out_dir: Path,
    extract_model: str = DEFAULT_STRATEGY_EXTRACT_MODEL,
    judge_model: str = DEFAULT_STRATEGY_JUDGE_MODEL,
    max_chains: int = 10,
    config: dict[str, Any] | None = None,
    cache: bool = True,
) -> dict[str, Any]:
    config = config or {}
    report_id = parsed.get("report_id") or "candidate_only"
    out_path = out_dir / "v2_strategy_reasoning" / f"{report_id}.v2_strategy_reasoning.json"
    if cache and out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))

    case_stub = build_v2_case_stub(parsed)
    client = make_verifier_client("llm", api_key_file, out_dir / "llm_logs" / "v2_strategy_reasoning")
    extraction = extract_reasoning_chains(client, case_stub, parsed, extract_model, max_chains=max_chains, config=config)
    judgement = judge_v2_strategy_reasoning(client, parsed, extraction, judge_model, config=config) if extraction.get("chains") else {"ok": False, "model": judge_model, "skipped": True, "error": "no_reasoning_chains_extracted"}
    result = assemble_v2_strategy_reasoning(parsed, extraction, judgement, extract_model, judge_model)
    write_json(out_path, result)
    return result


def run_v2_compliance_llm_verifier(
    parsed: dict[str, Any],
    rule_compliance: dict[str, Any],
    api_key_file: Path,
    out_dir: Path,
    judge_model: str = DEFAULT_CLAIM_JUDGE_MODEL,
    config: dict[str, Any] | None = None,
    cache: bool = True,
) -> dict[str, Any]:
    config = config or {}
    report_id = parsed.get("report_id") or "candidate_only"
    out_path = out_dir / "v2_compliance" / f"{report_id}.v2_compliance.json"
    if cache and out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
    candidates = (rule_compliance.get("redline_candidates") or [])[: int(config.get("max_candidates") or 12)]
    if not candidates:
        result = {
            "ok": True,
            "module_complete": True,
            "score": 1.0,
            "confirmed_redline_issues": [],
            "candidate_results": [],
            "llm_judgement": {"ok": True, "skipped": True, "reason": "no_redline_candidates"},
            "model": judge_model,
        }
        write_json(out_path, result)
        return result
    client = make_verifier_client("llm", api_key_file, out_dir / "llm_logs" / "v2_compliance")
    judgement = judge_v2_compliance(client, parsed, rule_compliance, candidates, judge_model, config)
    result = assemble_v2_compliance(rule_compliance, candidates, judgement, judge_model)
    write_json(out_path, result)
    return result


def judge_v2_compliance(
    client: OpenRouterClient,
    parsed: dict[str, Any],
    rule_compliance: dict[str, Any],
    candidates: list[dict[str, Any]],
    model: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    payload = {
        "report": {
            "report_id": parsed.get("report_id"),
            "title": parsed.get("title"),
            "format": parsed.get("format"),
            "headings": (parsed.get("headings") or [])[:25],
        },
        "rule_compliance_metrics": rule_compliance.get("metrics") or {},
        "redline_candidates": candidates,
        "review_policy": [
            "A true redline includes guaranteed return, promise of principal protection, risk-free investment claim, sure profit, must-buy instruction, or equivalent certainty language.",
            "If the phrase is quoted, negated, used in a warning, or part of a standard risk disclosure, mark it as not_violation or ambiguous rather than violation.",
            "Evaluate only the provided context; do not infer facts outside the report.",
        ],
    }
    schema = {
        "overall": {"score": 0.0, "reason": "short"},
        "candidate_results": [
            {
                "matched_text": "string",
                "decision": "violation|not_violation|ambiguous",
                "severity": "blocker|high|medium|low|none",
                "confidence": 0.0,
                "evidence_quote": "short quote from context",
                "reason": "short",
            }
        ],
        "confirmed_redline_count": 0,
        "review_notes": "short",
    }
    raw = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": COMPLIANCE_V2_SYSTEM},
            {
                "role": "user",
                "content": (
                    "Confirm whether each redline candidate is a real compliance violation in context.\n"
                    "Return compact strict JSON only. Keep evidence and reasons short.\n"
                    f"SCHEMA:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
                    f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
                ),
            },
        ],
        max_tokens=int(config.get("judge_max_tokens") or 3600),
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"case_id": parsed.get("report_id"), "judge": "v2_compliance_redline_confirmation"},
    )
    if not raw.get("ok") or not isinstance(raw.get("json"), dict):
        return {"ok": False, "model": model, "error": raw.get("error") or "v2_compliance_judge_failed", "raw": raw}
    data = raw["json"]
    data["ok"] = True
    data["model"] = model
    data["usage"] = raw.get("usage")
    data["elapsed_seconds"] = raw.get("elapsed_seconds")
    return data


def assemble_v2_compliance(
    rule_compliance: dict[str, Any],
    candidates: list[dict[str, Any]],
    judgement: dict[str, Any],
    judge_model: str,
) -> dict[str, Any]:
    candidate_results = judgement.get("candidate_results") if judgement.get("ok") else []
    if not isinstance(candidate_results, list):
        candidate_results = []
    confirmed: list[dict[str, Any]] = []
    for idx, result in enumerate(candidate_results):
        decision = str(result.get("decision") or "").lower()
        severity = str(result.get("severity") or "").lower()
        if decision == "violation" and severity in {"blocker", "high"}:
            source_candidate = candidates[min(idx, len(candidates) - 1)] if candidates else {}
            confirmed.append(
                issue(
                    "compliance_issue",
                    "blocker",
                    "redline",
                    result.get("reason") or "LLM confirmed compliance redline.",
                    evidence=result.get("evidence_quote") or source_candidate.get("context") or source_candidate.get("matched_text") or "",
                )
            )
    if judgement.get("ok"):
        score = nested_score(judgement, "overall")
        if score == 0.0 and confirmed:
            score = 0.0
        elif score == 0.0:
            score = 1.0
    else:
        confirmed = rule_compliance.get("redline_issues") or []
        score = 0.5 if confirmed else 0.75
    return {
        "ok": bool(judgement.get("ok")),
        "module_complete": bool(judgement.get("ok")),
        "score": round(clamp(score), 3),
        "issues": confirmed,
        "confirmed_redline_issues": confirmed,
        "candidate_results": candidate_results,
        "input_candidates": candidates,
        "llm_judgement": judgement,
        "model": judge_model,
    }


def judge_v2_strategy_reasoning(
    client: OpenRouterClient,
    parsed: dict[str, Any],
    extraction: dict[str, Any],
    model: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    raw = client.chat(
        model=model,
        messages=[{"role": "system", "content": STRATEGY_V2_SYSTEM}, {"role": "user", "content": build_v2_strategy_prompt(parsed, extraction, config)}],
        max_tokens=int(config.get("judge_max_tokens") or 5600),
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"case_id": parsed.get("report_id"), "judge": "v2_strategy_reasoning_candidate_only"},
    )
    if not raw.get("ok") or not isinstance(raw.get("json"), dict):
        return {"ok": False, "model": model, "error": raw.get("error") or "v2_strategy_reasoning_judge_failed", "raw": raw}
    data = raw["json"]
    data["ok"] = True
    data["model"] = model
    data["usage"] = raw.get("usage")
    data["elapsed_seconds"] = raw.get("elapsed_seconds")
    return data


def build_v2_strategy_prompt(parsed: dict[str, Any], extraction: dict[str, Any], config: dict[str, Any]) -> str:
    archetype = infer_v2_report_archetype(parsed)
    rubric = strategy_archetype_rubric(archetype)
    payload = {
        "report": {
            "report_id": parsed.get("report_id"),
            "title": parsed.get("title"),
            "format": parsed.get("format"),
            "headings": (parsed.get("headings") or [])[:35],
            "text_excerpt": compact_claim_text(parsed.get("text") or "", int(config.get("candidate_text_chars") or 17000)),
            "archetype": archetype,
            "archetype_rubric": rubric,
        },
        "extracted_reasoning_chains": extraction.get("chains") or [],
    }
    schema = {
        "overall": {"score": 0.0, "reason": "short"},
        "thesis_clarity": {"score": 0.0, "reason": "main thesis and strategic question are clear"},
        "mechanism_depth": {"score": 0.0, "reason": "facts/events connect to mechanism and impact"},
        "evidence_to_conclusion": {"score": 0.0, "reason": "conclusions follow evidence"},
        "investment_implication": {"score": 0.0, "reason": "reader gets actionable strategic implication"},
        "scenario_risk_boundary": {"score": 0.0, "reason": "risk/scenario/counterargument boundaries are clear"},
        "overclaim_control": {"score": 0.0, "reason": "avoids unsupported certainty"},
        "report_coherence": {"score": 0.0, "reason": "chains form a coherent report narrative"},
        "chain_results": [
            {
                "chain_id": "reasoning_chain_001",
                "decision": "strong|adequate|partial|weak|unsupported",
                "score": 0.0,
                "strengths": ["short"],
                "gaps": ["short"],
                "evidence_quote": "short quote",
                "suggested_fix": "short",
            }
        ],
        "issues": [
            {
                "issue_type": "weak_strategy_thesis|missing_mechanism|reasoning_gap|missing_investment_implication|missing_risk_boundary|over_claim|facts_without_strategy",
                "severity": "blocker|high|medium|low",
                "location": "chain_id or section",
                "description": "short",
                "suggested_skill_patch": "short",
            }
        ],
    }
    return (
        "Evaluate the candidate report's strategy reasoning quality without a reference answer.\n"
        "First apply the report archetype rubric. Do not judge a short commentary, weekly review, or chartbook as if it were a long deep-dive report.\n"
        "A high-quality strategy report should connect facts/data/events -> mechanism -> market or industry impact -> investment implication -> risk/scenario boundary, but the expected depth depends on report archetype.\n"
        "For brief/commentary/chartbook reports, reward concise but explicit thesis-evidence-implication links and do not require many full-length reasoning chains.\n"
        "For chartbook reports, the strategic conclusion may be distributed across chart titles, captions, and figure-level takeaways; evaluate whether visuals collectively support a strategy view.\n"
        "For weekly/market reviews, accept timely market diagnosis plus allocation/watchlist implication as adequate reasoning when risk boundaries are present.\n"
        "For deep-dive reports, require fuller mechanism depth, scenario/risk analysis, and coherent narrative.\n"
        "For Chinese reports, accept Chinese-native research writing; do not require English labels.\n"
        "Score continuously from 0 to 1. Penalize lists of facts without strategy, conclusions without evidence, missing risk boundaries, and vague implications.\n"
        "Return compact JSON. Include at most 6 chain_results and at most 8 issues. Keep every reason/evidence/suggested_fix under 20 Chinese characters or 18 English words.\n"
        "Do not include markdown, analysis prose, or any text outside the JSON object.\n"
        "Return strict JSON only, matching this schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def assemble_v2_strategy_reasoning(
    parsed: dict[str, Any],
    extraction: dict[str, Any],
    judgement: dict[str, Any],
    extract_model: str,
    judge_model: str,
) -> dict[str, Any]:
    archetype = infer_v2_report_archetype(parsed)
    if judgement.get("ok"):
        subscores = {
            "thesis_clarity": nested_score(judgement, "thesis_clarity"),
            "mechanism_depth": nested_score(judgement, "mechanism_depth"),
            "evidence_to_conclusion": nested_score(judgement, "evidence_to_conclusion"),
            "investment_implication": nested_score(judgement, "investment_implication"),
            "scenario_risk_boundary": nested_score(judgement, "scenario_risk_boundary"),
            "overclaim_control": nested_score(judgement, "overclaim_control"),
            "report_coherence": nested_score(judgement, "report_coherence"),
        }
        overall = nested_score(judgement, "overall") or weighted_mean(
            subscores,
            strategy_archetype_weights(archetype),
        )
    else:
        chain_count = len(extraction.get("chains") or [])
        subscores = {
            "thesis_clarity": 0.55 if chain_count else 0.15,
            "mechanism_depth": 0.45 if chain_count else 0.10,
            "evidence_to_conclusion": 0.45 if chain_count else 0.10,
            "investment_implication": 0.40 if chain_count else 0.10,
            "scenario_risk_boundary": 0.35,
            "overclaim_control": 0.55,
            "report_coherence": 0.40 if chain_count else 0.10,
        }
        overall = weighted_mean(subscores, strategy_archetype_weights(archetype))
    issues = normalize_llm_issues(judgement.get("issues") or [], default_type="strategy_reasoning_issue")
    overall = adjust_strategy_score_for_archetype(overall, subscores, extraction, parsed, archetype)
    return {
        "ok": bool(extraction.get("chains")),
        "module_complete": bool(extraction.get("ok") and extraction.get("chains") and judgement.get("ok")),
        "score": round(clamp(overall), 3),
        "subscores": {key: round(clamp(value), 3) for key, value in subscores.items()},
        "issues": issues,
        "report_archetype": archetype,
        "archetype_rubric": strategy_archetype_rubric(archetype),
        "extraction": extraction,
        "llm_judgement": judgement,
        "models": {"strategy_extraction": extract_model, "strategy_judge": judge_model},
    }


def infer_v2_report_archetype(parsed: dict[str, Any]) -> str:
    text = parsed.get("text") or ""
    title = parsed.get("title") or ""
    headings = " ".join(parsed.get("headings") or [])
    blob = f"{title}\n{headings}\n{text[:2500]}".lower()
    page_count = parsed.get("page_count") or 0
    text_length = parsed.get("text_length") or len(text)
    chart_count = len(((parsed.get("chart_inventory") or {}).get("charts") or []))
    chart_ratio = chart_count / max(1, page_count or 1)
    if any(term in blob for term in ["6 张图", "chartbook", "charts", "图看", "图表专题"]) or (chart_count >= 5 and chart_ratio >= 0.55 and text_length < 14000):
        return "chartbook"
    if any(term in blob for term in ["weekly", "周报", "周观点", "双周报", "market review", "market weekly", "定期报告"]):
        return "weekly_review"
    if any(term in blob for term in ["点评", "commentary", "快评", "brief", "首席观点"]) or text_length < 6500 or (page_count and page_count <= 8):
        return "brief_commentary"
    if any(term in blob for term in ["深度", "专题", "outlook", "展望", "白皮书", "deep dive"]) or text_length >= 18000 or (page_count and page_count >= 20):
        return "deep_dive"
    return "standard_strategy"


def strategy_archetype_rubric(archetype: str) -> dict[str, Any]:
    rubrics = {
        "brief_commentary": {
            "expected_depth": "concise",
            "adequate_reasoning": "clear thesis, 1-3 supporting facts, short mechanism, direct implication, at least one risk/uncertainty cue",
            "do_not_penalize": "few sections, short narrative, fewer complete chains",
        },
        "weekly_review": {
            "expected_depth": "medium",
            "adequate_reasoning": "market diagnosis, drivers, rotation/allocation/watchlist implication, near-term risk boundary",
            "do_not_penalize": "event-driven structure and recurring data tables",
        },
        "chartbook": {
            "expected_depth": "visual-led",
            "adequate_reasoning": "chart titles/captions and text jointly form evidence-to-conclusion logic with strategic takeaway",
            "do_not_penalize": "reasoning distributed across figures rather than long paragraphs",
        },
        "deep_dive": {
            "expected_depth": "high",
            "adequate_reasoning": "multi-step mechanism, evidence chain, scenarios, investment implication, risk/counterargument",
            "do_not_penalize": "",
        },
        "standard_strategy": {
            "expected_depth": "standard",
            "adequate_reasoning": "clear thesis, evidence, mechanism, implication, and risk boundary",
            "do_not_penalize": "",
        },
    }
    return rubrics.get(archetype, rubrics["standard_strategy"])


def strategy_archetype_weights(archetype: str) -> dict[str, float]:
    if archetype == "chartbook":
        return {
            "thesis_clarity": 0.20,
            "mechanism_depth": 0.12,
            "evidence_to_conclusion": 0.24,
            "investment_implication": 0.16,
            "scenario_risk_boundary": 0.10,
            "overclaim_control": 0.10,
            "report_coherence": 0.08,
        }
    if archetype == "brief_commentary":
        return {
            "thesis_clarity": 0.22,
            "mechanism_depth": 0.14,
            "evidence_to_conclusion": 0.20,
            "investment_implication": 0.18,
            "scenario_risk_boundary": 0.10,
            "overclaim_control": 0.10,
            "report_coherence": 0.06,
        }
    if archetype == "weekly_review":
        return {
            "thesis_clarity": 0.18,
            "mechanism_depth": 0.16,
            "evidence_to_conclusion": 0.20,
            "investment_implication": 0.18,
            "scenario_risk_boundary": 0.12,
            "overclaim_control": 0.08,
            "report_coherence": 0.08,
        }
    return {
        "thesis_clarity": 0.16,
        "mechanism_depth": 0.20,
        "evidence_to_conclusion": 0.18,
        "investment_implication": 0.16,
        "scenario_risk_boundary": 0.14,
        "overclaim_control": 0.08,
        "report_coherence": 0.08,
    }


def adjust_strategy_score_for_archetype(
    overall: float,
    subscores: dict[str, float],
    extraction: dict[str, Any],
    parsed: dict[str, Any],
    archetype: str,
) -> float:
    chain_count = len(extraction.get("chains") or [])
    if archetype in {"brief_commentary", "weekly_review", "chartbook"} and chain_count:
        thesis = subscores.get("thesis_clarity", 0.0)
        evidence = subscores.get("evidence_to_conclusion", 0.0)
        implication = subscores.get("investment_implication", 0.0)
        overclaim = subscores.get("overclaim_control", 0.0)
        compact_quality = weighted_mean(
            {
                "thesis_clarity": thesis,
                "evidence_to_conclusion": evidence,
                "investment_implication": implication,
                "overclaim_control": overclaim,
            },
            {"thesis_clarity": 0.30, "evidence_to_conclusion": 0.30, "investment_implication": 0.25, "overclaim_control": 0.15},
        )
        if compact_quality >= 0.68 and overall < compact_quality:
            overall = 0.55 * overall + 0.45 * compact_quality
    if archetype == "chartbook" and ((parsed.get("chart_inventory") or {}).get("charts")):
        overall = max(overall, min(0.72, overall + 0.05))
    return overall


def nested_score(data: dict[str, Any], key: str) -> float:
    value = data.get(key)
    score = value.get("score") if isinstance(value, dict) else value
    try:
        return clamp(float(score))
    except (TypeError, ValueError):
        return 0.0


def weighted_mean(subscores: dict[str, float], weights: dict[str, float]) -> float:
    if not weights:
        return mean(list(subscores.values()), default=0.0)
    total = sum(weights.values()) or 1.0
    return sum(clamp(subscores.get(key, 0.0)) * weight for key, weight in weights.items()) / total


def normalize_llm_issues(items: list[Any], default_type: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append(
            issue(
                str(item.get("issue_type") or default_type),
                str(item.get("severity") or "medium"),
                str(item.get("location") or default_type),
                str(item.get("description") or "")[:500],
                suggested_skill_patch=str(item.get("suggested_skill_patch") or "")[:400],
            )
        )
    return out[:40]
