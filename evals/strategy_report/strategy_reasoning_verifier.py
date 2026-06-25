from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from eval_utils import ROOT, clamp, issue, mean, normalize_text, token_overlap, write_json


TOOLS_DIR = ROOT / "dataset_tools" / "strategy_reports"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from llm_clients import OpenRouterClient  # noqa: E402
from verifier_config import make_verifier_client  # noqa: E402


DEFAULT_STRATEGY_EXTRACT_MODEL = "deepseek/deepseek-v4-flash"
DEFAULT_STRATEGY_JUDGE_MODEL = "deepseek/deepseek-v4-pro"


EXTRACT_SYSTEM = """You extract strategy reasoning chains from institutional financial strategy reports.
Return strict JSON only. Focus on thesis, mechanism, evidence, investment implication, and risk boundary."""


JUDGE_SYSTEM = """You are a senior financial strategy research evaluator.
Judge the quality of strategy reasoning against a golden case. Return strict JSON only.
Be fair to paraphrases, but strict about reasoning gaps, unsupported conclusions, missing investment implication, and missing risk boundaries."""


def run_strategy_reasoning_llm_verifier(
    case: dict[str, Any],
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
    out_path = out_dir / "strategy_reasoning" / f"{case['case_id']}.strategy_reasoning.json"
    if cache and out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))

    client = make_verifier_client("llm", api_key_file, out_dir / "llm_logs" / "strategy_reasoning")
    extraction = extract_reasoning_chains(client, case, parsed, extract_model, max_chains=max_chains, config=config)
    expectation = build_strategy_expectation(case, config=config)
    programmatic = programmatic_reasoning_audit(case, parsed, extraction, expectation)
    if extraction.get("ok") is True and extraction.get("chains"):
        judgement = judge_reasoning(client, case, parsed, extraction, expectation, programmatic, judge_model, config=config)
    else:
        judgement = {
            "ok": False,
            "model": judge_model,
            "skipped": True,
            "error": "strategy_extraction_incomplete; judge skipped to avoid scoring fallback/empty chains",
        }
    result = assemble_result(case, extraction, expectation, programmatic, judgement, extract_model, judge_model, config=config)
    write_json(out_path, result)
    return result


def extract_reasoning_chains(
    client: OpenRouterClient,
    case: dict[str, Any],
    parsed: dict[str, Any],
    model: str,
    max_chains: int,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = client.chat(
        model=model,
        messages=[{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": build_extract_prompt(case, parsed, max_chains, config=config)}],
        max_tokens=int((config or {}).get("extract_max_tokens") or 4200),
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"case_id": case.get("case_id"), "judge": "strategy_reasoning_extraction"},
    )
    if raw.get("ok") and not isinstance(raw.get("json"), dict) and raw.get("content"):
        raw = repair_json(client, raw.get("content") or "", model, case.get("case_id"))
    if not raw.get("ok") or not isinstance(raw.get("json"), dict):
        return {"ok": False, "model": model, "chains": fallback_chains(parsed), "error": raw.get("error") or "strategy_reasoning_extraction_failed", "raw": raw}
    chains = raw["json"].get("reasoning_chains")
    if not isinstance(chains, list):
        chains = []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(chains[:max_chains], start=1):
        if not isinstance(item, dict):
            continue
        thesis = str(item.get("thesis") or "").strip()
        if not thesis:
            continue
        normalized.append(
            {
                "chain_id": item.get("chain_id") or f"reasoning_chain_{index:03d}",
                "thesis": thesis[:700],
                "thesis_type": normalize_thesis_type(item.get("thesis_type")),
                "supporting_facts": listish(item.get("supporting_facts"), limit=8, chars=260),
                "mechanism": str(item.get("mechanism") or "")[:900],
                "investment_implication": str(item.get("investment_implication") or "")[:700],
                "risk_boundary": str(item.get("risk_boundary") or "")[:700],
                "scenario_or_counterargument": str(item.get("scenario_or_counterargument") or "")[:700],
                "source_context": str(item.get("source_context") or "")[:1000],
                "importance": normalize_importance(item.get("importance")),
            }
        )
    return {"ok": True, "model": model, "chains": normalized, "usage": raw.get("usage")}


def build_extract_prompt(case: dict[str, Any], parsed: dict[str, Any], max_chains: int, config: dict[str, Any] | None = None) -> str:
    config = config or {}
    rubric = build_language_rubric(case, config)
    payload = {
        "case_id": case.get("case_id"),
        "query": case.get("query"),
        "query_language": case.get("query_language"),
        "expected_report_type": case.get("expected_report_type"),
        "strategy_subtype": case.get("strategy_subtype"),
        "report_title": case.get("report_title"),
        "rubric_for_extraction": rubric,
        "headings": (parsed.get("headings") or [])[:35],
        "candidate_text": compact_text(parsed.get("text") or "", int(config.get("candidate_text_chars") or 19000)),
    }
    schema = {
        "reasoning_chains": [
            {
                "chain_id": "reasoning_chain_001",
                "thesis": "main strategic claim",
                "thesis_type": "industry_structure|asset_allocation|sector_rotation|policy_implication|company_selection|macro_market|risk_management|other",
                "supporting_facts": ["facts/data/events used as support"],
                "mechanism": "why facts lead to thesis; concise",
                "investment_implication": "what readers should do/watch; concise",
                "risk_boundary": "when thesis may fail or uncertainty; concise",
                "scenario_or_counterargument": "scenario, sensitivity, counterargument, or alternative view; concise",
                "source_context": "short quote/context from report; <=80 words",
                "importance": "critical|major|minor",
            }
        ]
    }
    return (
        f"Extract up to {max_chains} strategy reasoning chains from the candidate report.\n"
        "A reasoning chain should connect facts/data/events -> mechanism -> market/industry impact -> investment implication -> risk boundary.\n"
        "Prefer complete chains, but include important partial chains if they are central to the report.\n"
        "For Chinese reports, accept Chinese-native expressions of thesis, policy logic, allocation logic, catalysts, and risk boundaries; do not require English section labels.\n"
        "Use the provided rubric to decide which chains are strategically important.\n"
        "Be concise. Do not explain outside JSON. Keep each field short so the JSON can finish completely.\n"
        "Return strict JSON matching this schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}\n\nINPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def repair_json(client: OpenRouterClient, malformed: str, model: str, case_id: str | None) -> dict[str, Any]:
    schema = {"reasoning_chains": [{"chain_id": "reasoning_chain_001", "thesis": "...", "thesis_type": "industry_structure|asset_allocation|sector_rotation|policy_implication|company_selection|macro_market|risk_management|other", "supporting_facts": [], "mechanism": "...", "investment_implication": "...", "risk_boundary": "...", "scenario_or_counterargument": "...", "source_context": "...", "importance": "critical|major|minor"}]}
    return client.chat(
        model=model,
        messages=[
            {"role": "system", "content": "Repair malformed JSON. Return strict JSON only."},
            {"role": "user", "content": f"Repair this malformed JSON into the schema below without adding new content.\nSCHEMA:\n{json.dumps(schema, ensure_ascii=False)}\n\nMALFORMED:\n{malformed[:9000]}"},
        ],
        max_tokens=3800,
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"case_id": case_id, "judge": "strategy_reasoning_json_repair"},
    )


def judge_reasoning(
    client: OpenRouterClient,
    case: dict[str, Any],
    parsed: dict[str, Any],
    extraction: dict[str, Any],
    expectation: dict[str, Any],
    programmatic: dict[str, Any],
    model: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = client.chat(
        model=model,
        messages=[{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": build_judge_prompt(case, parsed, extraction, expectation, programmatic, config=config)}],
        max_tokens=int((config or {}).get("judge_max_tokens") or 5600),
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"case_id": case.get("case_id"), "judge": "strategy_reasoning_judge"},
    )
    if raw.get("ok") and not isinstance(raw.get("json"), dict) and raw.get("content"):
        raw = repair_judge_json(client, raw.get("content") or "", model, case.get("case_id"))
    if not raw.get("ok") or not isinstance(raw.get("json"), dict):
        return {"ok": False, "model": model, "error": raw.get("error") or "strategy_reasoning_judge_failed", "raw": raw}
    data = raw["json"]
    data["ok"] = True
    data["model"] = model
    data["usage"] = raw.get("usage")
    return data


def build_judge_prompt(
    case: dict[str, Any],
    parsed: dict[str, Any],
    extraction: dict[str, Any],
    expectation: dict[str, Any],
    programmatic: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> str:
    config = config or {}
    rubric = build_language_rubric(case, config)
    compact_case = {
        "case_id": case.get("case_id"),
        "query": case.get("query"),
        "query_language": case.get("query_language"),
        "expected_report_type": case.get("expected_report_type"),
        "strategy_subtype": case.get("strategy_subtype"),
        "must_have_sections": case.get("must_have_sections") or [],
        "key_facts": (case.get("key_facts") or [])[:10],
        "prohibited_mistakes": case.get("prohibited_mistakes") or [],
        "evaluation_hooks": case.get("evaluation_hooks") or {},
    }
    schema = {
        "overall": {"score": "0-1", "reason": "summary"},
        "thesis_clarity": {"score": "0-1", "reason": "whether main thesis is clear and relevant"},
        "mechanism_depth": {"score": "0-1", "reason": "quality of causal/structural explanation"},
        "evidence_to_conclusion": {"score": "0-1", "reason": "whether evidence supports conclusion without leaps"},
        "investment_implication": {"score": "0-1", "reason": "actionable strategy meaning"},
        "scenario_risk_boundary": {"score": "0-1", "reason": "risk, scenarios, counterarguments, uncertainty"},
        "overclaim_control": {"score": "0-1", "reason": "avoids unsupported certainty"},
        "theme_alignment": {"score": "0-1", "reason": "alignment with golden query/themes"},
        "chain_results": [
            {
                "chain_id": "reasoning_chain_001",
                "decision": "strong|adequate|partial|weak|unsupported",
                "score": "0-1",
                "strengths": ["short"],
                "gaps": ["short"],
                "evidence_quote": "quote from provided context",
                "suggested_fix": "short",
            }
        ],
        "missing_expected_reasoning": ["important expected reasoning missing"],
        "issues": [
            {
                "issue_type": "weak_strategy_thesis|missing_mechanism|reasoning_gap|over_claim|missing_investment_implication|missing_risk_boundary|theme_mismatch|facts_without_strategy|strategy_without_evidence",
                "severity": "blocker|high|medium|low",
                "location": "chain_id or section",
                "description": "short",
                "suggested_skill_patch": "short",
            }
        ],
    }
    payload = {
        "golden_case": compact_case,
        "candidate_report": {"title": parsed.get("title"), "format": parsed.get("format"), "headings": (parsed.get("headings") or [])[:35]},
        "language_adapted_rubric": rubric,
        "score_anchors": config.get("score_anchors") or {},
        "expected_strategy_reasoning": expectation,
        "extracted_reasoning_chains": extraction.get("chains") or [],
        "programmatic_reasoning_audit": programmatic,
    }
    return (
        "Evaluate the candidate's strategy reasoning quality.\n"
        "Judge whether the report answers the user's strategic question with professional reasoning, not just facts.\n"
        "Reward clear thesis, causal mechanism, evidence-to-conclusion logic, investment implication, scenario/risk boundary, and theme alignment.\n"
        "Penalize fact dumps, unsupported strategy conclusions, missing risk boundaries, and over-claiming.\n"
        "Apply the language-adapted rubric. For Chinese strategy reports, judge native Chinese research conventions fairly while still requiring a complete reasoning chain.\n"
        "Use score anchors consistently: reserve 0.9+ for complete professional reasoning; use 0.5-0.7 for partial but useful reasoning; use below 0.5 when the report is mostly descriptive.\n"
        "Be concise. Keep reasons, strengths, gaps, and suggested fixes short. Do not include markdown or commentary outside JSON.\n"
        "Return strict JSON matching this schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}\n\nINPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def repair_judge_json(client: OpenRouterClient, malformed: str, model: str, case_id: str | None) -> dict[str, Any]:
    schema = {
        "overall": {"score": "0-1", "reason": "summary"},
        "thesis_clarity": {"score": "0-1", "reason": "short"},
        "mechanism_depth": {"score": "0-1", "reason": "short"},
        "evidence_to_conclusion": {"score": "0-1", "reason": "short"},
        "investment_implication": {"score": "0-1", "reason": "short"},
        "scenario_risk_boundary": {"score": "0-1", "reason": "short"},
        "overclaim_control": {"score": "0-1", "reason": "short"},
        "theme_alignment": {"score": "0-1", "reason": "short"},
        "chain_results": [],
        "missing_expected_reasoning": [],
        "issues": [],
    }
    return client.chat(
        model=model,
        messages=[
            {"role": "system", "content": "Repair malformed JSON. Return strict JSON only. Preserve existing scores and judgements where visible."},
            {"role": "user", "content": f"Repair this malformed strategy reasoning judgement into the schema below without adding unsupported new analysis. If a field is truncated or missing, fill it conservatively from visible content.\nSCHEMA:\n{json.dumps(schema, ensure_ascii=False)}\n\nMALFORMED:\n{malformed[:16000]}"},
        ],
        max_tokens=4200,
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"case_id": case_id, "judge": "strategy_reasoning_judge_json_repair"},
    )


def build_strategy_expectation(case: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    hooks = case.get("evaluation_hooks") or {}
    expected_themes = hooks.get("expected_themes") or []
    must_sections = case.get("must_have_sections") or []
    key_facts = case.get("key_facts") or []
    required_angles = []
    for section in must_sections[:10]:
        name = section.get("section_name")
        if name:
            required_angles.append({"source": "must_have_section", "text": name, "purpose": section.get("purpose") or ""})
    for fact in key_facts[:8]:
        claim = fact.get("claim") or fact.get("fact")
        if claim:
            required_angles.append({"source": "key_fact", "text": claim, "why_it_matters": fact.get("why_it_matters") or ""})
    return {
        "query": case.get("query"),
        "strategy_subtype": case.get("strategy_subtype"),
        "language_adapted_rubric": build_language_rubric(case, config),
        "expected_themes": expected_themes,
        "required_reasoning_angles": required_angles,
        "prohibited_mistakes": case.get("prohibited_mistakes") or [],
    }


def build_language_rubric(case: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    universal = listish(config.get("universal_rubric") or [], limit=12, chars=600)
    zh = listish(config.get("zh_rubric") or [], limit=12, chars=600)
    locale = str(config.get("rubric_locale") or "auto").lower()
    query_language = str(case.get("query_language") or "").lower()
    text_blob = " ".join(
        str(value or "")
        for value in [case.get("query"), case.get("report_title"), case.get("expected_report_type"), case.get("strategy_subtype")]
    )
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", text_blob))
    use_zh = locale in {"zh", "cn", "chinese"} or (locale == "auto" and (query_language.startswith("zh") or has_cjk))
    return {
        "locale": "zh" if use_zh else "en",
        "universal": universal,
        "locale_specific": zh if use_zh else [],
    }


def programmatic_reasoning_audit(
    case: dict[str, Any],
    parsed: dict[str, Any],
    extraction: dict[str, Any],
    expectation: dict[str, Any],
) -> dict[str, Any]:
    text = parsed.get("text") or ""
    chains = extraction.get("chains") or []
    theme_scores = []
    for theme in expectation.get("expected_themes") or []:
        theme_scores.append({"theme": theme, "hit": token_overlap(str(theme), text), "matched": token_overlap(str(theme), text) >= 0.35})
    chain_rows = []
    for chain in chains:
        completeness_bits = {
            "has_thesis": bool(chain.get("thesis")),
            "has_supporting_facts": bool(chain.get("supporting_facts")),
            "has_mechanism": len(chain.get("mechanism") or "") >= 30,
            "has_investment_implication": len(chain.get("investment_implication") or "") >= 20,
            "has_risk_boundary": len(chain.get("risk_boundary") or "") >= 20,
            "has_scenario_or_counterargument": len(chain.get("scenario_or_counterargument") or "") >= 20,
        }
        completeness = sum(1 for value in completeness_bits.values() if value) / len(completeness_bits)
        evidence_overlap = max([token_overlap(fact, text) for fact in chain.get("supporting_facts") or [""]], default=0.0)
        chain_rows.append(
            {
                "chain_id": chain.get("chain_id"),
                "thesis": chain.get("thesis"),
                "thesis_type": chain.get("thesis_type"),
                "completeness": round(completeness, 3),
                "completeness_bits": completeness_bits,
                "supporting_fact_text_overlap": round(evidence_overlap, 3),
            }
        )
    return {
        "theme_alignment_programmatic": round(mean([row["hit"] for row in theme_scores], default=0.55), 3),
        "theme_rows": theme_scores,
        "chain_count": len(chains),
        "avg_chain_completeness": round(mean([row["completeness"] for row in chain_rows], default=0.0), 3),
        "chain_rows": chain_rows,
        "notes": ["Programmatic audit measures coverage/completeness only; LLM judge handles semantic reasoning quality."],
    }


def assemble_result(
    case: dict[str, Any],
    extraction: dict[str, Any],
    expectation: dict[str, Any],
    programmatic: dict[str, Any],
    judgement: dict[str, Any],
    extract_model: str,
    judge_model: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if judgement.get("ok"):
        subs = {
            "thesis_clarity": nested_score(judgement, "thesis_clarity"),
            "mechanism_depth": nested_score(judgement, "mechanism_depth"),
            "evidence_to_conclusion": nested_score(judgement, "evidence_to_conclusion"),
            "investment_implication": nested_score(judgement, "investment_implication"),
            "scenario_risk_boundary": nested_score(judgement, "scenario_risk_boundary"),
            "overclaim_control": nested_score(judgement, "overclaim_control"),
            "theme_alignment": nested_score(judgement, "theme_alignment"),
        }
        overall = nested_score(judgement, "overall") or weighted_reasoning_score(subs, weights=config.get("subscore_weights"))
    else:
        subs = {
            "thesis_clarity": min(1.0, (extraction.get("chains") and 0.65) or 0.2),
            "mechanism_depth": programmatic.get("avg_chain_completeness", 0.0),
            "evidence_to_conclusion": programmatic.get("theme_alignment_programmatic", 0.0),
            "investment_implication": programmatic.get("avg_chain_completeness", 0.0),
            "scenario_risk_boundary": 0.45,
            "overclaim_control": 0.55,
            "theme_alignment": programmatic.get("theme_alignment_programmatic", 0.0),
        }
        overall = weighted_reasoning_score(subs, weights=config.get("subscore_weights"))
    issues = normalize_issues(judgement.get("issues") or [])
    if subs["mechanism_depth"] < 0.55:
        issues.append(issue("missing_mechanism", "medium", "strategy_reasoning", "Reasoning chains lack enough causal or structural mechanism."))
    if subs["investment_implication"] < 0.55:
        issues.append(issue("missing_investment_implication", "medium", "strategy_reasoning", "Strategy implications are weak or not actionable."))
    return {
        "ok": bool(extraction.get("ok") and extraction.get("chains") and judgement.get("ok")),
        "module_complete": bool(extraction.get("ok") and extraction.get("chains") and judgement.get("ok")),
        "fallback_used": extraction.get("ok") is not True,
        "case_id": case.get("case_id"),
        "score": round(clamp(overall), 3),
        "subscores": {key: round(clamp(value), 3) for key, value in subs.items()},
        "issues": issues[:30],
        "models": {"strategy_extraction": extract_model, "strategy_judge": judge_model},
        "config": config,
        "extraction": extraction,
        "expectation": expectation,
        "programmatic_audit": programmatic,
        "llm_judgement": judgement,
    }


def weighted_reasoning_score(subs: dict[str, float], weights: dict[str, Any] | None = None) -> float:
    default_weights = {
        "thesis_clarity": 0.16,
        "mechanism_depth": 0.18,
        "evidence_to_conclusion": 0.18,
        "investment_implication": 0.17,
        "scenario_risk_boundary": 0.12,
        "overclaim_control": 0.09,
        "theme_alignment": 0.10,
    }
    merged = {**default_weights, **(weights or {})}
    total = sum(float(value) for value in merged.values() if float(value) > 0)
    if total <= 0:
        return 0.0
    return sum(clamp(subs.get(key, 0.0)) * float(weight) for key, weight in merged.items()) / total


def fallback_chains(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    chunks = text_chunks(parsed.get("text") or "")
    out = []
    for chunk in chunks:
        low = normalize_text(chunk)
        if not any(term in low for term in ["we believe", "we expect", "recommend", "implication", "suggest", "建议", "认为", "预计", "配置", "影响"]):
            continue
        out.append(
            {
                "chain_id": f"fallback_chain_{len(out) + 1:03d}",
                "thesis": chunk[:500],
                "thesis_type": "other",
                "supporting_facts": [],
                "mechanism": "",
                "investment_implication": "",
                "risk_boundary": "",
                "scenario_or_counterargument": "",
                "source_context": chunk[:1000],
                "importance": "major",
            }
        )
        if len(out) >= 8:
            break
    return out


def text_chunks(text: str, target_chars: int = 850) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", text or "") if part.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) <= target_chars:
            current = f"{current}\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    return chunks[:80]


def compact_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[: int(max_chars * 0.72)]}\n\n[... middle omitted for token control ...]\n\n{text[-int(max_chars * 0.18):]}"


def normalize_thesis_type(value: Any) -> str:
    allowed = {"industry_structure", "asset_allocation", "sector_rotation", "policy_implication", "company_selection", "macro_market", "risk_management", "other"}
    normalized = normalize_text(str(value or ""))
    return normalized if normalized in allowed else "other"


def normalize_importance(value: Any) -> str:
    normalized = normalize_text(str(value or ""))
    return normalized if normalized in {"critical", "major", "minor"} else "major"


def listish(value: Any, limit: int, chars: int) -> list[str]:
    if isinstance(value, list):
        return [str(item)[:chars] for item in value if str(item).strip()][:limit]
    if isinstance(value, str) and value.strip():
        return [value[:chars]]
    return []


def nested_score(data: dict[str, Any], key: str) -> float:
    value = data.get(key)
    score = value.get("score") if isinstance(value, dict) else value
    try:
        return clamp(float(score))
    except (TypeError, ValueError):
        return 0.0


def normalize_issues(items: list[Any]) -> list[dict[str, Any]]:
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append(
            issue(
                str(item.get("issue_type") or "strategy_reasoning_issue"),
                str(item.get("severity") or "medium"),
                str(item.get("location") or "strategy_reasoning"),
                str(item.get("description") or "")[:450],
                suggested_skill_patch=str(item.get("suggested_skill_patch") or "")[:350],
            )
        )
    return out
