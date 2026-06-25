from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from eval_utils import ROOT, canonical_number, clamp, extract_dates, extract_numbers, issue, mean, normalize_text, token_overlap, write_json


TOOLS_DIR = ROOT / "dataset_tools" / "strategy_reports"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from llm_clients import OpenRouterClient  # noqa: E402
from verifier_config import make_verifier_client  # noqa: E402


DEFAULT_CLAIM_EXTRACT_MODEL = "deepseek/deepseek-v4-flash"
DEFAULT_CLAIM_JUDGE_MODEL = "deepseek/deepseek-v4-pro"


CLAIM_EXTRACT_SYSTEM = """You extract important claims from institutional strategy research reports.
Return strict JSON only. Focus on claims that affect factual accuracy, numeric accuracy, strategy thesis, and investment implications."""


CLAIM_JUDGE_SYSTEM = """You are a senior financial strategy report verifier.
Judge candidate claims against a golden evaluation case. Return strict JSON only.
Be fair: the candidate can paraphrase. Be strict on numbers, units, direction, dates, and over-claiming."""


def run_claim_numeric_llm_verifier(
    case: dict[str, Any],
    parsed: dict[str, Any],
    api_key_file: Path,
    out_dir: Path,
    extract_model: str = DEFAULT_CLAIM_EXTRACT_MODEL,
    judge_model: str = DEFAULT_CLAIM_JUDGE_MODEL,
    max_claims: int = 18,
    config: dict[str, Any] | None = None,
    cache: bool = True,
) -> dict[str, Any]:
    out_path = out_dir / "claim_numeric" / f"{case['case_id']}.claim_numeric.json"
    if cache and out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))

    client = make_verifier_client("llm", api_key_file, out_dir / "llm_logs" / "claim_numeric")
    config = config or {}
    candidate_claims = extract_candidate_claims(client, case, parsed, extract_model, max_claims=max_claims, config=config)
    evidence_packs = build_evidence_packs(case, parsed, config=config)
    numeric_audit = build_numeric_audit(case, parsed, evidence_packs, config=config)
    llm_judgement = judge_claims(client, case, parsed, candidate_claims, evidence_packs, numeric_audit, judge_model, config=config)
    result = assemble_claim_numeric_result(case, candidate_claims, evidence_packs, numeric_audit, llm_judgement, extract_model, judge_model, config=config)
    result["config"] = config
    write_json(out_path, result)
    return result


def extract_candidate_claims(
    client: OpenRouterClient,
    case: dict[str, Any],
    parsed: dict[str, Any],
    model: str,
    max_claims: int,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    prompt = build_claim_extract_prompt(case, parsed, max_claims=max_claims, config=config)
    raw = client.chat(
        model=model,
        messages=[{"role": "system", "content": CLAIM_EXTRACT_SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=int(config.get("extract_max_tokens") or 3600),
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"case_id": case.get("case_id"), "judge": "claim_extraction"},
    )
    if raw.get("ok") and not isinstance(raw.get("json"), dict) and raw.get("content"):
        raw = repair_claim_json(client, raw.get("content") or "", model, case.get("case_id"))
    if not raw.get("ok") or not isinstance(raw.get("json"), dict):
        return {"ok": False, "model": model, "claims": fallback_candidate_claims(parsed), "error": raw.get("error") or "claim_extraction_failed", "raw": raw}
    data = raw["json"]
    claims = data.get("claims")
    if not isinstance(claims, list):
        claims = []
    normalized = []
    for index, item in enumerate(claims[:max_claims], start=1):
        if not isinstance(item, dict):
            continue
        claim_text = str(item.get("claim") or "").strip()
        if not claim_text:
            continue
        normalized.append(
            {
                "claim_id": item.get("claim_id") or f"candidate_claim_{index:03d}",
                "claim": claim_text[:700],
                "claim_type": normalize_claim_type(item.get("claim_type")),
                "importance": normalize_importance(item.get("importance")),
                "section": str(item.get("section") or "")[:120],
                "numbers": extract_numbers(claim_text)[:20],
                "normalized_numbers": parse_numeric_values(claim_text)[:20],
                "dates": extract_dates(claim_text)[:12],
                "entities": listish(item.get("entities"))[:12],
                "nearby_context": str(item.get("nearby_context") or "")[:900],
            }
        )
    return {"ok": True, "model": model, "claims": normalized, "usage": raw.get("usage")}


def repair_claim_json(client: OpenRouterClient, malformed_content: str, model: str, case_id: str | None) -> dict[str, Any]:
    schema = {"claims": [{"claim_id": "candidate_claim_001", "claim": "...", "claim_type": "fact|numeric|policy|transaction|forecast|opinion|recommendation|risk", "importance": "critical|major|minor", "section": "...", "entities": [], "nearby_context": "..."}]}
    return client.chat(
        model=model,
        messages=[
            {"role": "system", "content": "Repair malformed JSON. Return strict JSON only, with no markdown."},
            {
                "role": "user",
                "content": (
                    "Repair the following malformed claim extraction result into valid JSON matching this schema. "
                    "Do not add new claims; preserve the original claim content as much as possible.\n"
                    f"SCHEMA:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
                    f"MALFORMED_CONTENT:\n{malformed_content[:9000]}"
                ),
            },
        ],
        max_tokens=3600,
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"case_id": case_id, "judge": "claim_extraction_json_repair"},
    )


def build_claim_extract_prompt(case: dict[str, Any], parsed: dict[str, Any], max_claims: int, config: dict[str, Any] | None = None) -> str:
    config = config or {}
    payload = {
        "case_id": case.get("case_id"),
        "query": case.get("query"),
        "expected_report_type": case.get("expected_report_type"),
        "strategy_subtype": case.get("strategy_subtype"),
        "report_title": case.get("report_title"),
        "candidate_title": parsed.get("title"),
        "headings": (parsed.get("headings") or [])[:30],
        "numeric_normalization_policy": numeric_normalization_policy(config),
        "candidate_text": compact_text(parsed.get("text") or "", int(config.get("candidate_text_chars") or 18000)),
    }
    schema = {
        "claims": [
            {
                "claim_id": "candidate_claim_001",
                "claim": "single important claim",
                "claim_type": "fact|numeric|policy|transaction|forecast|opinion|recommendation|risk",
                "importance": "critical|major|minor",
                "section": "where it appears",
                "entities": ["entity names"],
                "nearby_context": "short evidence/context from candidate report",
            }
        ]
    }
    return (
        f"Extract up to {max_claims} important claims from the candidate strategy report.\n"
        "Prefer claims that contain numbers, dates, entities, policy/transaction facts, forecasts, and actionable strategy conclusions.\n"
        "Do not extract boilerplate disclaimers unless they are material to compliance.\n"
        "Preserve numbers together with their units and direction words. Keep claims concise and atomic.\n"
        "Return strict JSON matching this schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def judge_claims(
    client: OpenRouterClient,
    case: dict[str, Any],
    parsed: dict[str, Any],
    candidate_claims: dict[str, Any],
    evidence_packs: list[dict[str, Any]],
    numeric_audit: dict[str, Any],
    model: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    prompt = build_claim_judge_prompt(case, parsed, candidate_claims, evidence_packs, numeric_audit, config=config)
    raw = client.chat(
        model=model,
        messages=[{"role": "system", "content": CLAIM_JUDGE_SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=int(config.get("judge_max_tokens") or 5200),
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"case_id": case.get("case_id"), "judge": "claim_numeric_alignment"},
    )
    if raw.get("ok") and not isinstance(raw.get("json"), dict) and raw.get("content"):
        raw = repair_claim_judge_json(client, raw.get("content") or "", model, case.get("case_id"), config=config)
    if not raw.get("ok") or not isinstance(raw.get("json"), dict):
        return {"ok": False, "model": model, "error": raw.get("error") or "claim_judge_failed", "raw": raw}
    data = raw["json"]
    data["ok"] = True
    data["model"] = model
    data["usage"] = raw.get("usage")
    return data


def build_claim_judge_prompt(
    case: dict[str, Any],
    parsed: dict[str, Any],
    candidate_claims: dict[str, Any],
    evidence_packs: list[dict[str, Any]],
    numeric_audit: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> str:
    config = config or {}
    compact_case = {
        "case_id": case.get("case_id"),
        "query": case.get("query"),
        "expected_report_type": case.get("expected_report_type"),
        "strategy_subtype": case.get("strategy_subtype"),
        "key_facts": compact_key_facts_for_judge(case.get("key_facts") or [], config),
        "prohibited_mistakes": case.get("prohibited_mistakes") or [],
        "evaluation_hooks": case.get("evaluation_hooks") or {},
    }
    payload = {
        "golden_case": compact_case,
        "candidate_report": {
            "title": parsed.get("title"),
            "format": parsed.get("format"),
            "headings": (parsed.get("headings") or [])[:30],
        },
        "candidate_extracted_claims": compact_candidate_claims(candidate_claims, config),
        "numeric_normalization_policy": numeric_normalization_policy(config),
        "programmatic_evidence_packs": compact_evidence_packs_for_judge(evidence_packs, config),
        "programmatic_numeric_audit": compact_numeric_audit_for_judge(numeric_audit, config),
    }
    schema = {
        "overall": {
            "score": "0-1",
            "reason": "short explanation of claim/numeric reliability",
        },
        "claim_coverage": {"score": "0-1", "reason": "coverage of golden key facts"},
        "numeric_correctness": {"score": "0-1", "reason": "numeric/unit/date correctness"},
        "claim_discipline": {"score": "0-1", "reason": "fact/opinion separation and over-claim control"},
        "golden_fact_results": [
            {
                "fact_id": "fact_001",
                "decision": "covered|partially_covered|missing|contradicted|not_enough_evidence",
                "numeric_status": "correct|minor_mismatch|major_error|not_numeric|not_enough_evidence",
                "severity": "none|minor|major|critical",
                "score": "0-1",
                "matched_candidate_claim_ids": ["candidate_claim_001"],
                "evidence_quote": "short quote from provided evidence/context",
                "reason": "why",
                "suggested_fix": "how to improve the candidate report",
            }
        ],
        "overclaim_results": [
            {
                "candidate_claim_id": "candidate_claim_001",
                "decision": "acceptable|over_claimed|unsupported|contradicted",
                "severity": "none|minor|major|critical",
                "reason": "why",
            }
        ],
        "issues": [
            {
                "issue_type": "missing_evidence|factual_error|numerical_error|entity_mismatch|temporal_mismatch|over_claim|reasoning_gap",
                "severity": "blocker|high|medium|low",
                "location": "fact_id or candidate_claim_id",
                "description": "short",
                "suggested_skill_patch": "short",
            }
        ],
    }
    return (
        "Evaluate claim and numeric reliability for this candidate strategy report.\n"
        "Use only the provided golden case, extracted candidate claims, evidence snippets, and numeric audit.\n"
        "Treat candidate_extracted_claims as a non-exhaustive index, not the source of truth. The evidence snippets and numeric audit are the primary basis for coverage decisions.\n"
        "A paraphrase can be correct. Do not require exact wording. Be strict about numeric value, unit, date, direction, and magnitude.\n"
        "If evidence snippets show the candidate contains the right fact even if candidate_claim extraction missed it, count it as covered and leave matched_candidate_claim_ids empty or partial.\n"
        "For forecasts/opinions, judge whether they are framed as judgement/assumption, not unsupported certainty.\n"
        "Use normalized numeric matches for magnitude/unit checks, but still inspect surrounding text for direction and context.\n"
        "Be concise. Do not include markdown or commentary outside JSON.\n"
        "Return strict JSON matching this schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def compact_candidate_claims(candidate_claims: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    limit = int(config.get("judge_max_candidate_claims") or 12)
    compacted: list[dict[str, Any]] = []
    for item in (candidate_claims.get("claims") or [])[:limit]:
        compacted.append(
            {
                "claim_id": item.get("claim_id"),
                "claim": item.get("claim"),
                "claim_type": item.get("claim_type"),
                "importance": item.get("importance"),
                "numbers": item.get("numbers") or [],
                "normalized_numbers": (item.get("normalized_numbers") or [])[:8],
                "dates": item.get("dates") or [],
                "entities": item.get("entities") or [],
                "nearby_context": (item.get("nearby_context") or "")[:450],
            }
        )
    return compacted


def compact_key_facts_for_judge(key_facts: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    allowed_roles = set(config.get("included_fact_roles") or ["core_fact", "numeric_fact", "strategy_fact"])
    out = []
    max_facts = int(config.get("judge_max_key_facts") or 10)
    for fact in key_facts:
        role = infer_fact_evaluation_role(fact)
        if role not in allowed_roles:
            continue
        out.append(
            {
                "fact_id": fact.get("fact_id"),
                "claim": fact.get("claim") or fact.get("fact"),
                "fact_type": fact.get("fact_type"),
                "evaluation_role": role,
                "value": fact.get("value"),
                "unit": fact.get("unit"),
                "time_window": fact.get("time_window"),
                "why_it_matters": fact.get("why_it_matters"),
                "verification_hint": fact.get("verification_hint"),
            }
        )
        if len(out) >= max_facts:
            break
    return out


def compact_evidence_packs_for_judge(evidence_packs: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    max_facts = int(config.get("judge_max_key_facts") or len(evidence_packs))
    top_k = int(config.get("judge_top_k_evidence") or 3)
    snippet_chars = int(config.get("judge_snippet_chars") or 700)
    compacted: list[dict[str, Any]] = []
    for pack in evidence_packs[:max_facts]:
        snippets = []
        for snippet in (pack.get("candidate_snippets") or [])[:top_k]:
            diagnostics = snippet.get("diagnostics") or {}
            snippets.append(
                {
                    "snippet_id": snippet.get("snippet_id"),
                    "rank": snippet.get("rank"),
                    "score": snippet.get("score"),
                    "chunk_index": snippet.get("chunk_index"),
                    "text": (snippet.get("text") or "")[:snippet_chars],
                    "numbers": (snippet.get("numbers") or [])[:12],
                    "normalized_numbers": (snippet.get("normalized_numbers") or [])[:8],
                    "dates": (snippet.get("dates") or [])[:6],
                    "diagnostics": {
                        "token_overlap": diagnostics.get("token_overlap"),
                        "hint_overlap": diagnostics.get("hint_overlap"),
                        "number_similarity": diagnostics.get("number_similarity"),
                        "date_similarity": diagnostics.get("date_similarity"),
                    },
                }
            )
        compacted.append(
            {
                "fact_id": pack.get("fact_id"),
                "golden_claim": pack.get("golden_claim"),
                "fact_type": pack.get("fact_type"),
                "importance_hint": pack.get("importance_hint"),
                "expected_numbers": pack.get("expected_numbers") or [],
                "expected_normalized_numbers": (pack.get("expected_normalized_numbers") or [])[:8],
                "expected_dates": pack.get("expected_dates") or [],
                "verification_hint": pack.get("verification_hint"),
                "programmatic_best_score": pack.get("programmatic_best_score"),
                "candidate_snippets": snippets,
            }
        )
    return compacted


def compact_numeric_audit_for_judge(numeric_audit: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    match_limit = int(config.get("judge_numeric_match_limit") or 6)
    rows = []
    for row in numeric_audit.get("fact_numeric_rows") or []:
        rows.append(
            {
                "fact_id": row.get("fact_id"),
                "expected_numbers": row.get("expected_numbers") or [],
                "expected_dates": row.get("expected_dates") or [],
                "preserved_in_report": row.get("preserved_in_report"),
                "preserved_in_evidence_pack": row.get("preserved_in_evidence_pack"),
                "normalized_matches_evidence": (row.get("normalized_matches_evidence") or [])[:match_limit],
            }
        )
    return {
        "report_number_count": numeric_audit.get("report_number_count"),
        "report_date_count": numeric_audit.get("report_date_count"),
        "expected_number_count": numeric_audit.get("expected_number_count"),
        "overall_number_preservation": numeric_audit.get("overall_number_preservation"),
        "numeric_match_threshold": numeric_audit.get("numeric_match_threshold"),
        "fact_numeric_rows": rows,
        "notes": numeric_audit.get("notes") or [],
    }


def repair_claim_judge_json(client: OpenRouterClient, malformed_content: str, model: str, case_id: str | None, config: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = {
        "overall": {"score": "0-1", "reason": "short"},
        "claim_coverage": {"score": "0-1", "reason": "short"},
        "numeric_correctness": {"score": "0-1", "reason": "short"},
        "claim_discipline": {"score": "0-1", "reason": "short"},
        "golden_fact_results": [],
        "overclaim_results": [],
        "issues": [],
    }
    return client.chat(
        model=model,
        messages=[
            {"role": "system", "content": "Repair malformed JSON. Return strict JSON only. Preserve visible scores and decisions."},
            {
                "role": "user",
                "content": (
                    "Repair this malformed claim/numeric judgement into valid JSON matching the schema. "
                    "Do not invent new evidence; if a field is missing, fill conservatively from visible content.\n"
                    f"SCHEMA:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
                    f"MALFORMED_CONTENT:\n{malformed_content[:14000]}"
                ),
            },
        ],
        max_tokens=int((config or {}).get("judge_repair_max_tokens") or 3600),
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"case_id": case_id, "judge": "claim_numeric_alignment_json_repair"},
    )


def build_evidence_packs(case: dict[str, Any], parsed: dict[str, Any], config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = config or {}
    chunk_chars = int(config.get("chunk_chars") or 900)
    top_k = int(config.get("top_k_evidence") or 5)
    neighbor_window = int(config.get("neighbor_window") or 1)
    weights = {
        "token_overlap": 0.50,
        "number_similarity": 0.35,
        "hint_overlap": 0.10,
        "date_similarity": 0.05,
        **(config.get("weights") or {}),
    }
    chunks = text_chunks(parsed.get("text") or "", target_chars=chunk_chars)
    packs: list[dict[str, Any]] = []
    max_key_facts = int(config.get("max_key_facts") or 12)
    allowed_roles = set(config.get("included_fact_roles") or ["core_fact", "numeric_fact", "strategy_fact"])
    filtered_facts = [fact for fact in (case.get("key_facts") or []) if infer_fact_evaluation_role(fact) in allowed_roles]
    for fact in filtered_facts[:max_key_facts]:
        claim = fact.get("claim") or fact.get("fact") or ""
        fact_role = infer_fact_evaluation_role(fact)
        hint = fact.get("verification_hint") or ""
        retrieval_query = " ".join(part for part in [claim, hint, str(fact.get("why_it_matters") or "")] if part).strip()
        expected_text = build_expected_numeric_text(fact, claim)
        expected_numbers = extract_numbers(expected_text)
        expected_numeric_values = parse_numeric_values(expected_text)
        expected_dates = sorted(set(extract_dates(claim) + extract_dates(str(fact.get("time_window") or ""))))
        scored: list[tuple[float, int, str, dict[str, Any]]] = []
        for index, chunk in enumerate(chunks):
            expanded = expand_chunk_context(chunks, index, neighbor_window)
            overlap = token_overlap(retrieval_query, expanded)
            hint_overlap = token_overlap(hint, expanded) if hint else 0.0
            number_score = number_similarity(expected_numbers, extract_numbers(expanded), expected_text, expanded) if expected_numbers else 0.0
            date_score = date_similarity(expected_dates, extract_dates(expanded)) if expected_dates else 0.0
            score = (
                float(weights["token_overlap"]) * overlap
                + float(weights["number_similarity"]) * number_score
                + float(weights["hint_overlap"]) * hint_overlap
                + float(weights["date_similarity"]) * date_score
            )
            diagnostics = {
                "token_overlap": round(overlap, 3),
                "hint_overlap": round(hint_overlap, 3),
                "number_similarity": round(number_score, 3),
                "date_similarity": round(date_score, 3),
                "has_expected_numbers": bool(expected_numbers),
                "has_expected_dates": bool(expected_dates),
                "weights": weights,
            }
            if score > 0 or overlap > 0 or number_score > 0 or hint_overlap > 0 or date_score > 0:
                scored.append((score, index, expanded, diagnostics))
        if not scored and chunks:
            scored.append(
                (
                    0.0,
                    0,
                    expand_chunk_context(chunks, 0, neighbor_window),
                    {
                        "token_overlap": 0.0,
                        "hint_overlap": 0.0,
                        "number_similarity": 0.0,
                        "date_similarity": 0.0,
                        "fallback": "no_positive_retrieval_score",
                        "weights": weights,
                    },
                )
            )
        top = sorted(scored, key=lambda item: (item[0], -item[1]), reverse=True)[:top_k]
        snippets = [
            {
                "snippet_id": f"{fact.get('fact_id') or 'fact'}_snippet_{rank:02d}",
                "rank": rank,
                "score": round(score, 3),
                "chunk_index": index,
                "text": snippet[:1200],
                "numbers": extract_numbers(snippet)[:30],
                "normalized_numbers": parse_numeric_values(snippet)[:30],
                "dates": extract_dates(snippet)[:10],
                "diagnostics": diagnostics,
            }
            for rank, (score, index, snippet, diagnostics) in enumerate(top, start=1)
        ]
        packs.append(
            {
                "fact_id": fact.get("fact_id"),
                "golden_claim": claim,
                "fact_type": fact.get("fact_type"),
                "evaluation_role": fact_role,
                "importance_hint": infer_fact_importance(fact),
                "expected_numbers": expected_numbers,
                "expected_normalized_numbers": expected_numeric_values,
                "expected_dates": expected_dates,
                "expected_numeric_source_text": expected_text,
                "retrieval_query": retrieval_query,
                "verification_hint": hint,
                "programmatic_best_score": round(top[0][0], 3) if top else 0.0,
                "candidate_snippets": snippets,
            }
        )
    return packs


def build_expected_numeric_text(fact: dict[str, Any], claim: str) -> str:
    parts = [claim]
    value = fact.get("value")
    unit = fact.get("unit")
    if value is not None and str(value).strip():
        parts.append(f"{value}{unit or ''}")
    time_window = fact.get("time_window")
    if time_window:
        parts.append(str(time_window))
    return " ".join(str(part) for part in parts if str(part).strip())


def infer_fact_evaluation_role(fact: dict[str, Any]) -> str:
    explicit = str(fact.get("evaluation_role") or "").strip()
    if explicit:
        return explicit
    claim = normalize_text(str(fact.get("claim") or fact.get("fact") or ""))
    fact_type = normalize_text(str(fact.get("fact_type") or ""))
    metadata_terms = [
        "disclaimer",
        "for informational purposes",
        "not a solicitation",
        "past performance",
        "does not guarantee future",
        "series",
        "part of",
        "midyear outlook",
        "source report",
        "publication",
        "author",
        "copyright",
    ]
    compliance_terms = ["solicitation", "past performance", "informational purposes", "disclaimer"]
    if any(term in claim for term in compliance_terms):
        return "compliance_context"
    if any(term in claim for term in metadata_terms):
        return "metadata_only"
    if fact_type in {"numeric", "financial_metric"} or extract_numbers(claim):
        return "numeric_fact"
    if any(term in claim for term in ["recommend", "overweight", "underweight", "allocation", "配置", "建议", "看好", "低配", "高配"]):
        return "strategy_fact"
    return "core_fact"


def numeric_normalization_policy(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    return {
        "match_threshold": float(config.get("numeric_match_threshold") or 0.82),
        "supported_units": {
            "cny": ["元", "万元", "亿元", "万亿元", "人民币"],
            "usd": ["美元", "万美元", "亿美元"],
            "generic_amount": ["万", "亿", "万亿", "mn", "bn", "tn", "million", "billion", "trillion"],
            "rates": ["%", "pct", "个百分点", "percentage points", "bp", "bps", "基点"],
            "multiples": ["x", "times", "倍"],
        },
        "judge_instruction": "Treat scale-equivalent values as numeric matches when units convert cleanly, but still verify direction, date, entity, and context.",
    }


def build_numeric_audit(case: dict[str, Any], parsed: dict[str, Any], evidence_packs: list[dict[str, Any]], config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    match_threshold = float(config.get("numeric_match_threshold") or 0.82)
    parsed_numbers = parsed.get("numbers") or []
    parsed_numeric_values = parse_numeric_values(parsed.get("text") or " ".join(parsed_numbers))
    fact_rows = []
    for pack in evidence_packs:
        expected = pack.get("expected_numbers") or []
        expected_values = pack.get("expected_normalized_numbers") or parse_numeric_values(" ".join(expected))
        snippets_numbers: list[str] = []
        snippets_text: list[str] = []
        for snippet in pack.get("candidate_snippets") or []:
            snippets_numbers.extend(snippet.get("numbers") or [])
            snippets_text.append(snippet.get("text") or "")
        snippet_values = parse_numeric_values(" ".join(snippets_text or snippets_numbers))
        fact_rows.append(
            {
                "fact_id": pack.get("fact_id"),
                "expected_numbers": expected,
                "expected_normalized_numbers": expected_values,
                "preserved_in_report": round(number_similarity(expected, parsed_numbers, " ".join(expected), parsed.get("text") or ""), 3),
                "preserved_in_evidence_pack": round(number_similarity(expected, snippets_numbers, " ".join(expected), " ".join(snippets_text)), 3),
                "normalized_matches_report": match_numeric_values(expected_values, parsed_numeric_values, threshold=match_threshold),
                "normalized_matches_evidence": match_numeric_values(expected_values, snippet_values, threshold=match_threshold),
                "expected_dates": pack.get("expected_dates") or [],
            }
        )
    all_expected = [num for row in fact_rows for num in row["expected_numbers"]]
    all_expected_text = " ".join(all_expected)
    return {
        "report_number_count": len(parsed_numbers),
        "report_date_count": len(parsed.get("dates") or []),
        "expected_number_count": len(all_expected),
        "overall_number_preservation": round(number_similarity(all_expected, parsed_numbers, all_expected_text, parsed.get("text") or ""), 3),
        "report_normalized_number_count": len(parsed_numeric_values),
        "numeric_match_threshold": match_threshold,
        "fact_numeric_rows": fact_rows,
        "notes": [
            "Programmatic audit now checks raw number presence plus normalized numeric/unit/magnitude similarity; LLM judge handles semantic use, direction, and context.",
        ],
    }


def assemble_claim_numeric_result(
    case: dict[str, Any],
    candidate_claims: dict[str, Any],
    evidence_packs: list[dict[str, Any]],
    numeric_audit: dict[str, Any],
    llm_judgement: dict[str, Any],
    extract_model: str,
    judge_model: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    if llm_judgement.get("ok"):
        coverage = nested_score(llm_judgement, "claim_coverage")
        numeric = nested_score(llm_judgement, "numeric_correctness")
        discipline = nested_score(llm_judgement, "claim_discipline")
        overall = nested_score(llm_judgement, "overall") or weighted_claim_numeric_score(coverage, numeric, discipline, config)
    else:
        coverage = mean([pack.get("programmatic_best_score", 0.0) for pack in evidence_packs], default=0.0)
        numeric = numeric_audit.get("overall_number_preservation", 0.0)
        discipline = 0.55
        overall = weighted_claim_numeric_score(coverage, numeric, discipline, config)

    issues = normalize_llm_issues(llm_judgement.get("issues") or [])
    if numeric < 0.72 and numeric_audit.get("expected_number_count"):
        issues.append(issue("numerical_error", "high", "numeric_audit", "Important expected numbers are weakly preserved or semantically uncertain."))
    if coverage < 0.58 and evidence_packs:
        issues.append(issue("missing_evidence", "medium", "key_facts", "Golden key facts are not sufficiently covered by candidate evidence."))
    result = {
        "ok": bool(candidate_claims.get("claims")),
        "case_id": case.get("case_id"),
        "score": round(clamp(overall), 3),
        "subscores": {
            "claim_coverage": round(clamp(coverage), 3),
            "numeric_correctness": round(clamp(numeric), 3),
            "claim_discipline": round(clamp(discipline), 3),
        },
        "issues": issues[:30],
        "models": {"claim_extraction": extract_model, "claim_judge": judge_model},
        "scoring_config": {"subscore_weights": config.get("subscore_weights") or {}},
        "candidate_claims": candidate_claims,
        "evidence_packs": evidence_packs,
        "numeric_audit": numeric_audit,
        "llm_judgement": llm_judgement,
    }
    return result


def weighted_claim_numeric_score(coverage: float, numeric: float, discipline: float, config: dict[str, Any] | None = None) -> float:
    weights = {
        "claim_coverage": 0.45,
        "numeric_correctness": 0.35,
        "claim_discipline": 0.20,
        **((config or {}).get("subscore_weights") or {}),
    }
    total = sum(float(value) for value in weights.values() if float(value) > 0)
    if total <= 0:
        return 0.0
    return (
        clamp(coverage) * float(weights["claim_coverage"])
        + clamp(numeric) * float(weights["numeric_correctness"])
        + clamp(discipline) * float(weights["claim_discipline"])
    ) / total


def text_chunks(text: str, target_chars: int = 900) -> list[str]:
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
    if not chunks and text:
        chunks = [text[i : i + target_chars] for i in range(0, min(len(text), 24000), target_chars)]
    return chunks[:80]


def fallback_candidate_claims(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    chunks = text_chunks(parsed.get("text") or "", target_chars=520)
    claims: list[dict[str, Any]] = []
    for chunk in chunks:
        nums = extract_numbers(chunk)
        if len(nums) < 2:
            continue
        claims.append(
            {
                "claim_id": f"fallback_claim_{len(claims) + 1:03d}",
                "claim": chunk[:500],
                "claim_type": "numeric",
                "importance": "major",
                "section": "",
                "numbers": nums[:20],
                "dates": extract_dates(chunk)[:10],
                "entities": [],
                "nearby_context": chunk[:900],
            }
        )
        if len(claims) >= 12:
            break
    return claims


def compact_text(text: str, max_chars: int) -> str:
    text = text or ""
    if len(text) <= max_chars:
        return text
    head = text[: int(max_chars * 0.72)]
    tail = text[-int(max_chars * 0.18) :]
    return f"{head}\n\n[... middle omitted for token control ...]\n\n{tail}"


def number_preservation(expected: list[str], observed: list[str]) -> float:
    expected_clean = [canonical_number(value) for value in expected if canonical_number(value)]
    if not expected_clean:
        return 0.75
    observed_blob = " ".join(canonical_number(value) for value in observed)
    hits = 0
    for value in expected_clean:
        if value and value in observed_blob:
            hits += 1
    return hits / len(expected_clean)


NUMERIC_VALUE_RE = re.compile(
    r"(?<![\w.])(?P<num>[-+]?\d+(?:,\d{3})*(?:\.\d+)?)(?:\s*(?P<unit>%|pct|ppts?|percentage points?|bps|bp|个基点|基点|个百分点|x|times|倍|万亿元|万亿|亿元|万元|亿美元|万美元|元|美元|人民币|亿|万|tn|trn|bn|mn|billion|million|trillion))?",
    re.IGNORECASE,
)


UNIT_ALIASES = {
    "%": ("percent", 1.0),
    "pct": ("percent", 1.0),
    "ppt": ("percent_point", 1.0),
    "ppts": ("percent_point", 1.0),
    "percentage point": ("percent_point", 1.0),
    "percentage points": ("percent_point", 1.0),
    "bps": ("bps", 1.0),
    "bp": ("bps", 1.0),
    "个基点": ("bps", 1.0),
    "基点": ("bps", 1.0),
    "个百分点": ("percent_point", 1.0),
    "x": ("multiple", 1.0),
    "times": ("multiple", 1.0),
    "倍": ("multiple", 1.0),
    "元": ("cny", 1.0),
    "人民币": ("cny", 1.0),
    "万元": ("cny", 10000.0),
    "万亿元": ("cny", 1000000000000.0),
    "亿": ("generic_amount", 100000000.0),
    "万": ("generic_amount", 10000.0),
    "万亿": ("generic_amount", 1000000000000.0),
    "亿元": ("cny", 100000000.0),
    "美元": ("usd", 1.0),
    "万美元": ("usd", 10000.0),
    "亿美元": ("usd", 100000000.0),
    "mn": ("generic_amount", 1000000.0),
    "million": ("generic_amount", 1000000.0),
    "bn": ("generic_amount", 1000000000.0),
    "billion": ("generic_amount", 1000000000.0),
    "tn": ("generic_amount", 1000000000000.0),
    "trn": ("generic_amount", 1000000000000.0),
    "trillion": ("generic_amount", 1000000000000.0),
}


def parse_numeric_values(text: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    seen: set[tuple[float, str, str]] = set()
    for match in NUMERIC_VALUE_RE.finditer(text or ""):
        raw = match.group(0).strip()
        number_text = match.group("num")
        unit_text = (match.group("unit") or "").lower()
        if number_text.startswith("-") and match.start() > 0 and (text or "")[match.start() - 1] in "%0123456789":
            number_text = number_text[1:]
            raw = raw[1:].strip()
        try:
            number = float(number_text.replace(",", ""))
        except ValueError:
            continue
        unit_class, multiplier = UNIT_ALIASES.get(unit_text, ("plain", 1.0))
        normalized_value = number * multiplier
        key = (round(normalized_value, 6), unit_class, raw)
        if key in seen:
            continue
        seen.add(key)
        values.append(
            {
                "raw": raw,
                "number": number,
                "unit": unit_text,
                "unit_class": unit_class,
                "normalized_value": normalized_value,
            }
        )
    return values


def number_similarity(expected: list[str], observed: list[str], expected_text: str = "", observed_text: str = "") -> float:
    if not expected:
        return 0.75
    raw_score = number_preservation(expected, observed)
    expected_values = parse_numeric_values(expected_text or " ".join(expected))
    observed_values = parse_numeric_values(observed_text or " ".join(observed))
    if not expected_values:
        return raw_score
    matches = match_numeric_values(expected_values, observed_values)
    normalized_score = sum(1 for item in matches if item.get("matched")) / len(expected_values)
    return max(raw_score, normalized_score)


def match_numeric_values(expected_values: list[dict[str, Any]], observed_values: list[dict[str, Any]], threshold: float = 0.82) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for expected in expected_values:
        best: dict[str, Any] | None = None
        for observed in observed_values:
            score = numeric_match_score(expected, observed)
            if best is None or score > best["score"]:
                best = {"score": score, "observed": observed}
        rows.append(
            {
                "expected": expected,
                "matched": bool(best and best["score"] >= threshold),
                "score": round(best["score"], 3) if best else 0.0,
                "observed": best["observed"] if best else None,
            }
        )
    return rows


def numeric_match_score(expected: dict[str, Any], observed: dict[str, Any]) -> float:
    expected_value = float(expected.get("normalized_value") or 0.0)
    observed_value = float(observed.get("normalized_value") or 0.0)
    if expected_value == 0 and observed_value == 0:
        value_score = 1.0
    else:
        denom = max(abs(expected_value), abs(observed_value), 1.0)
        rel = abs(expected_value - observed_value) / denom
        value_score = 1.0 if rel <= 0.002 else 0.92 if rel <= 0.01 else 0.75 if rel <= 0.05 else 0.0
    unit_score = 1.0 if expected.get("unit_class") == observed.get("unit_class") else compatible_unit_score(expected, observed)
    return 0.78 * value_score + 0.22 * unit_score


def compatible_unit_score(expected: dict[str, Any], observed: dict[str, Any]) -> float:
    pair = {expected.get("unit_class"), observed.get("unit_class")}
    if "plain" in pair:
        return 0.65
    if pair <= {"generic_amount", "cny"} or pair <= {"generic_amount", "usd"}:
        return 0.72
    return 0.0


def date_similarity(expected_dates: list[str], observed_dates: list[str]) -> float:
    if not expected_dates:
        return 0.75
    observed_blob = normalize_text(" ".join(observed_dates))
    hits = sum(1 for value in expected_dates if normalize_text(value) in observed_blob)
    return hits / len(expected_dates)


def expand_chunk_context(chunks: list[str], index: int, neighbor_window: int) -> str:
    start = max(0, index - max(0, neighbor_window))
    end = min(len(chunks), index + max(0, neighbor_window) + 1)
    return "\n\n".join(chunks[start:end])


def normalize_claim_type(value: Any) -> str:
    allowed = {"fact", "numeric", "policy", "transaction", "forecast", "opinion", "recommendation", "risk"}
    normalized = normalize_text(str(value or ""))
    return normalized if normalized in allowed else "fact"


def normalize_importance(value: Any) -> str:
    normalized = normalize_text(str(value or ""))
    return normalized if normalized in {"critical", "major", "minor"} else "major"


def listish(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item)[:120] for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value[:120]]
    return []


def infer_fact_importance(fact: dict[str, Any]) -> str:
    claim = fact.get("claim") or fact.get("fact") or ""
    if extract_numbers(claim):
        return "critical_numeric"
    if any(term in normalize_text(claim) for term in ["recommend", "建议", "关注", "配置"]):
        return "major_strategy"
    return "major_fact"


def nested_score(data: dict[str, Any], key: str) -> float:
    value = data.get(key)
    if isinstance(value, dict):
        score = value.get("score")
    else:
        score = value
    try:
        return clamp(float(score))
    except (TypeError, ValueError):
        return 0.0


def normalize_llm_issues(items: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized.append(
            issue(
                str(item.get("issue_type") or "claim_numeric_issue"),
                str(item.get("severity") or "medium"),
                str(item.get("location") or "claim_numeric"),
                str(item.get("description") or "")[:400],
                suggested_skill_patch=str(item.get("suggested_skill_patch") or "")[:300],
            )
        )
    return normalized
