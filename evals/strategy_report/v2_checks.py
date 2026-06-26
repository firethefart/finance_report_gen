from __future__ import annotations

import math
import re
from typing import Any

from chart_qa import chart_qa_v2_check
from checks import compliance_redline_check, render_delivery_check, scenario_risk_check, source_quality_check
from eval_utils import clamp, extract_numbers, issue, normalize_text


SECTION_GROUPS = {
    "executive_summary": ["summary", "executive", "key takeaways", "核心观点", "摘要", "要点"],
    "market_context": ["market", "macro", "industry", "policy", "市场", "宏观", "行业", "政策"],
    "evidence": ["data", "evidence", "source", "chart", "analysis", "forecast", "estimate", "数据", "证据", "来源", "图表", "分析", "预测", "测算"],
    "strategy": ["strategy", "thesis", "allocation", "implication", "positioning", "preference", "investors", "策略", "逻辑", "配置", "影响", "投资者", "建议"],
    "scenario_risk": ["scenario", "risk", "sensitivity", "uncertainty", "情景", "风险", "敏感性", "不确定"],
    "disclaimer": ["disclaimer", "important information", "risk disclosure", "免责声明", "风险提示"],
}

REASONING_TERMS = [
    "because",
    "driven by",
    "supported by",
    "underpinned by",
    "benefit from",
    "benefiting from",
    "reflects",
    "resulting in",
    "as a result",
    "due to",
    "reason for",
    "in other words",
    "suggests that",
    "means that",
    "requires",
    "relies on",
    "reliant on",
    "is linked to",
    "creates",
    "makes it",
    "fueled by",
    "therefore",
    "leads to",
    "leading to",
    "which would",
    "would reduce",
    "would increase",
    "could reduce",
    "could increase",
    "helps",
    "allowing",
    "enabling",
    "implies",
    "catalyst",
    "transmission",
    "mechanism",
    "由于",
    "驱动",
    "因此",
    "传导",
    "催化",
    "机制",
    "影响",
]

CLAIM_TERMS = [
    "we expect",
    "we believe",
    "forecast",
    "estimate",
    "may",
    "could",
    "预计",
    "认为",
    "测算",
    "预测",
    "可能",
    "有望",
]

STRATEGY_BOILERPLATE_TERMS = [
    "important information",
    "for informational purposes",
    "does not constitute",
    "not constitute",
    "not investment advice",
    "no representation",
    "no warranty",
    "past performance",
    "future results",
    "strictly incidental",
    "covered by such sanctions",
    "appropriate investment strategies depend",
    "免责声明",
    "不构成投资建议",
    "不作为投资建议",
    "过往业绩",
    "风险揭示书",
]


def run_v2_candidate_checks(
    parsed: dict[str, Any],
    chart_inventory: dict[str, Any] | None = None,
    chart_vl_judges: dict[str, Any] | None = None,
    chart_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    case_stub = build_v2_case_stub(parsed)
    analysis_text = parsed.get("analysis_text") or parsed.get("text") or ""
    analytical_parsed = {
        **parsed,
        "text": analysis_text,
        "text_length": parsed.get("analysis_text_length") or len(analysis_text),
    }
    if chart_inventory:
        parsed = {**parsed, "chart_inventory": chart_inventory}
        analytical_parsed = {**analytical_parsed, "chart_inventory": chart_inventory}
    return {
        "delivery": render_delivery_check(case_stub, parsed),
        "structure": v2_structure_check(analytical_parsed),
        "source_traceability": source_quality_check(case_stub, analytical_parsed),
        "claim_numeric_discipline": v2_claim_numeric_discipline_check(analytical_parsed),
        "strategy_reasoning": v2_strategy_reasoning_check(analytical_parsed),
        "scenario_risk": scenario_risk_check(case_stub, analytical_parsed),
        "visual_qa": chart_qa_v2_check(case_stub, parsed, chart_inventory, chart_vl_judges, config=chart_config),
        "compliance": compliance_redline_check(case_stub, parsed),
    }


def build_v2_case_stub(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": parsed.get("report_id") or "candidate_only",
        "query": "",
        "expected_report_type": "candidate-only strategy research report",
        "strategy_subtype": "",
        "report_title": parsed.get("title") or "",
        "must_have_sections": [],
        "source_pack": [],
        "key_facts": [],
        "charts_and_tables_to_learn_from": [],
        "prohibited_mistakes": [],
        "evaluation_hooks": {"expected_themes": []},
        "institution": {"name": parsed.get("institution") or ""},
    }


def v2_structure_check(parsed: dict[str, Any]) -> dict[str, Any]:
    text = parsed.get("text") or ""
    headings = parsed.get("headings") or []
    combined = normalize_text("\n".join(headings) + "\n" + text)
    group_hits = {
        group: any(normalize_text(term) in combined for term in terms)
        for group, terms in SECTION_GROUPS.items()
    }
    if parsed.get("disclaimer_hint_count"):
        group_hits["disclaimer"] = True
    heading_score = clamp(len(headings) / 8)
    coverage_score = sum(1 for ok in group_hits.values() if ok) / len(group_hits)
    section_count = len(parsed.get("sections") or [])
    section_score = clamp(section_count / 8)
    score = 0.46 * coverage_score + 0.34 * heading_score + 0.20 * section_score
    report_likeness = parsed.get("report_likeness")
    if isinstance(report_likeness, (int, float)):
        # Keep the existing structure model, but cap it when the HTML body looks
        # more like navigation/landing content than a strategy report.
        score = min(score, 0.72 * clamp(float(report_likeness)) + 0.28 * score)
    issues: list[dict[str, Any]] = []
    for key, ok in group_hits.items():
        if not ok and key in {"executive_summary", "strategy", "scenario_risk"}:
            issues.append(issue("missing_section_signal", "medium", key, f"Candidate-only structure signal is weak for {key}."))
    if isinstance(report_likeness, (int, float)) and report_likeness < 0.35:
        issues.append(issue("low_report_likeness", "high", "html_body", "HTML body has weak strategy-report signals and may be navigation, landing, or boilerplate content."))
    if parsed.get("html_parse_status") in {"empty_text", "static_fallback", "low_confidence"}:
        severity = "high" if parsed.get("html_parse_status") == "empty_text" else "medium"
        issues.append(issue("html_parse_low_confidence", severity, "html_adapter", f"HTML parse status is {parsed.get('html_parse_status')}."))
    return {
        "score": round(score, 3),
        "issues": issues,
        "metrics": {
            "heading_count": len(headings),
            "section_count": section_count,
            "section_group_hits": group_hits,
            "analysis_boundary": parsed.get("analysis_boundary") or {},
            "html_parse_status": parsed.get("html_parse_status"),
            "parse_quality": parsed.get("parse_quality"),
            "report_likeness": parsed.get("report_likeness"),
            "report_likeness_reasons": parsed.get("report_likeness_reasons") or [],
        },
    }


def v2_claim_numeric_discipline_check(parsed: dict[str, Any]) -> dict[str, Any]:
    text = parsed.get("text") or ""
    raw_numbers = parsed.get("numbers") or extract_numbers(text)
    sentences = split_sentences(text)
    raw_numeric_sentences = [sentence for sentence in sentences if extract_numbers(sentence)]
    numeric_sentences = [
        sentence for sentence in raw_numeric_sentences if is_analytical_numeric_sentence(sentence)
    ]
    numbers = []
    seen_numbers: set[str] = set()
    for sentence in numeric_sentences:
        for number in extract_numbers(sentence):
            if number not in seen_numbers:
                seen_numbers.add(number)
                numbers.append(number)
    claim_sentences = [sentence for sentence in sentences if any(term in normalize_text(sentence) for term in CLAIM_TERMS)]
    numeric_with_context = [sentence for sentence in numeric_sentences if has_numeric_context(sentence)]
    explicit_units = [
        number
        for number in numbers
        if re.search(
            r"[%$€£¥元亿万]|bps|bp|bn|mn|trn|pct|trillion|billion|million|thousand|years?|months?|quarters?",
            str(number),
            flags=re.IGNORECASE,
        )
    ]
    source_near_numbers = [
        sentence
        for sentence in numeric_sentences
        if re.search(r"source|according to|based on|来源|资料|数据", sentence, flags=re.IGNORECASE)
    ]
    density_score = clamp(len(numeric_sentences) / 12)
    context_score = len(numeric_with_context) / len(numeric_sentences) if numeric_sentences else 0.55
    unit_score = clamp(len(explicit_units) / max(1, min(12, len(numbers))))
    source_score = clamp(len(source_near_numbers) / max(1, min(8, len(numeric_sentences))))
    claim_score = clamp(len(claim_sentences) / 10)
    score = 0.22 * density_score + 0.28 * context_score + 0.22 * unit_score + 0.16 * source_score + 0.12 * claim_score
    issues: list[dict[str, Any]] = []
    if numeric_sentences and context_score < 0.45:
        issues.append(issue("numeric_context_weak", "medium", "numbers", "Many numeric statements lack nearby unit, date, entity, or direction context."))
    if numbers and unit_score < 0.35:
        issues.append(issue("unit_signal_weak", "medium", "numbers", "Numeric values have weak explicit unit signals."))
    if claim_score < 0.25:
        issues.append(issue("claim_signal_weak", "low", "claims", "Few explicit forecast/view/claim sentences were detected."))
    return {
        "score": round(score, 3),
        "issues": issues,
        "metrics": {
            "number_count": len(numbers),
            "raw_number_count": len(raw_numbers),
            "numeric_sentence_count": len(numeric_sentences),
            "raw_numeric_sentence_count": len(raw_numeric_sentences),
            "filtered_numeric_sentence_count": len(raw_numeric_sentences) - len(numeric_sentences),
            "numeric_with_context_count": len(numeric_with_context),
            "explicit_unit_count": len(explicit_units),
            "source_near_number_count": len(source_near_numbers),
            "claim_sentence_count": len(claim_sentences),
        },
        "sample_numeric_sentences": numeric_sentences[:12],
        "sample_claim_sentences": claim_sentences[:12],
    }


def v2_strategy_reasoning_check(parsed: dict[str, Any]) -> dict[str, Any]:
    text = parsed.get("text") or ""
    archetype = infer_v2_strategy_archetype(parsed)
    sentences = unique_strategy_sentences(split_sentences(text))
    reasoning_sentences = matching_sentences(sentences, REASONING_TERMS)
    implication_terms = [
        "implication",
        "allocation",
        "position",
        "positioning",
        "recommend",
        "watch",
        "target",
        "opportunity set",
        "tilting portfolios",
        "tilt portfolios",
        "portfolio toward",
        "for investors",
        "overweight",
        "underweight",
        "we favor",
        "we prefer",
        "well placed",
        "stands out",
        "investors need",
        "investors should",
        "配置",
        "建议",
        "关注",
        "影响",
        "机会",
        "超配",
        "低配",
    ]
    risk_terms = [
        "risk",
        "downside",
        "uncertainty",
        "sensitivity",
        "vulnerable",
        "headwind",
        "风险",
        "下行",
        "不确定",
        "敏感",
    ]
    thesis_terms = [
        "we believe",
        "we expect",
        "we think",
        "we see",
        "we view",
        "we favor",
        "we prefer",
        "we remain",
        "is tilting",
        "are tilting",
        "our target",
        "target for",
        "our view",
        "our outlook",
        "our base case",
        "our conviction",
        "thesis",
        "stands out",
        "well placed",
        "we are overweight",
        "we are underweight",
        "we are neutral",
        "核心观点",
        "认为",
        "预计",
        "判断",
    ]
    thesis_sentences = matching_sentences(sentences, thesis_terms)
    implication_sentences = matching_sentences(sentences, implication_terms)
    risk_sentences = matching_sentences(sentences, risk_terms)
    signal_targets = strategy_signal_targets(archetype)
    thesis_score = soft_saturation(len(thesis_sentences), signal_targets["thesis"])
    mechanism_score = soft_saturation(len(reasoning_sentences), signal_targets["mechanism"])
    implication_score = soft_saturation(len(implication_sentences), signal_targets["implication"])
    risk_score = soft_saturation(len(risk_sentences), signal_targets["risk"])
    if archetype in {"brief_commentary", "chartbook"}:
        score = 0.34 * thesis_score + 0.22 * mechanism_score + 0.30 * implication_score + 0.14 * risk_score
    elif archetype == "weekly_review":
        score = 0.30 * thesis_score + 0.26 * mechanism_score + 0.28 * implication_score + 0.16 * risk_score
    else:
        score = 0.27 * thesis_score + 0.32 * mechanism_score + 0.24 * implication_score + 0.17 * risk_score
    issues: list[dict[str, Any]] = []
    if thesis_score < 0.35:
        issues.append(issue("weak_strategy_thesis", "medium", "strategy", "Main thesis/view signals are weak."))
    if mechanism_score < 0.35:
        issues.append(issue("missing_mechanism", "medium", "strategy", "Causal mechanism / transmission reasoning signals are thin."))
    if implication_score < 0.35:
        issues.append(issue("missing_investment_implication", "medium", "strategy", "Investment or strategic implications are not explicit enough."))
    return {
        "score": round(score, 3),
        "issues": issues,
        "metrics": {
            "report_archetype": archetype,
            "thesis_signal": round(thesis_score, 3),
            "mechanism_signal": round(mechanism_score, 3),
            "implication_signal": round(implication_score, 3),
            "risk_boundary_signal": round(risk_score, 3),
            "reasoning_sentence_count": len(reasoning_sentences),
            "thesis_sentence_count": len(thesis_sentences),
            "implication_sentence_count": len(implication_sentences),
            "risk_sentence_count": len(risk_sentences),
            "eligible_sentence_count": len(sentences),
            "signal_targets": signal_targets,
            "signal_curve": "one_minus_exp; target_count_maps_to_0.8",
        },
        "sample_reasoning_sentences": reasoning_sentences[:12],
        "sample_thesis_sentences": thesis_sentences[:8],
        "sample_implication_sentences": implication_sentences[:8],
    }


def infer_v2_strategy_archetype(parsed: dict[str, Any]) -> str:
    text = parsed.get("text") or ""
    title = parsed.get("title") or ""
    headings = " ".join(parsed.get("headings") or [])
    primary_headings = " ".join((parsed.get("headings") or [])[:6])
    metadata_blob = normalize_text(f"{title}\n{primary_headings}")
    intro_blob = normalize_text(text[:2500])
    page_count = parsed.get("page_count") or 0
    text_length = parsed.get("text_length") or len(text)
    if any(term in metadata_blob for term in ["6 张图", "chartbook", "in charts", "图看", "图表专题"]):
        return "chartbook"
    if any(term in metadata_blob for term in ["weekly", "周报", "周观点", "双周报", "market review", "market weekly", "定期报告"]):
        return "weekly_review"
    if any(term in metadata_blob for term in ["点评", "commentary", "快评", "brief", "首席观点"]) or text_length < 6500 or (
        page_count and page_count <= 8
    ):
        return "brief_commentary"
    if any(term in metadata_blob for term in ["深度", "专题", "白皮书", "deep dive"]) or text_length >= 18000 or (
        page_count and page_count >= 20
    ):
        return "deep_dive"
    if "executive summary" in intro_blob and page_count and page_count >= 12:
        return "deep_dive"
    return "standard_strategy"


def split_sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[。！？.!?])\s+|\n+", text or "")
    return [sentence.strip()[:1200] for sentence in raw if len(sentence.strip()) >= 25][:1000]


def unique_strategy_sentences(sentences: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        normalized = normalize_text(sentence)
        if any(term in normalized for term in STRATEGY_BOILERPLATE_TERMS):
            continue
        fingerprint = re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique.append(sentence)
    return unique


def matching_sentences(sentences: list[str], terms: list[str]) -> list[str]:
    return [
        sentence
        for sentence in sentences
        if any(term in normalize_text(sentence) for term in terms)
    ]


def strategy_signal_targets(archetype: str) -> dict[str, int]:
    if archetype == "brief_commentary":
        return {"thesis": 3, "mechanism": 7, "implication": 4, "risk": 4}
    if archetype == "chartbook":
        return {"thesis": 3, "mechanism": 7, "implication": 5, "risk": 5}
    if archetype == "weekly_review":
        return {"thesis": 3, "mechanism": 8, "implication": 5, "risk": 5}
    return {"thesis": 4, "mechanism": 10, "implication": 4, "risk": 4}


def soft_saturation(count: int, target: int) -> float:
    if count <= 0:
        return 0.0
    target = max(1, target)
    return clamp(1.0 - math.exp(-math.log(5.0) * count / target))


def has_numeric_context(sentence: str) -> bool:
    normalized = normalize_text(sentence)
    has_unit = bool(
        re.search(r"[%$¥元亿万]|bps|bn|mn|trn|pct|percentage|percent", sentence, flags=re.IGNORECASE)
    )
    has_date = bool(re.search(r"\b20\d{2}\b|年|季度|quarter|q[1-4]", sentence, flags=re.IGNORECASE))
    has_direction = any(
        term in normalized
        for term in ["increase", "decrease", "growth", "decline", "up", "down", "提升", "下降", "增长", "回落", "上升"]
    )
    has_entity = len(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Z][A-Za-z&.\-]{2,}", sentence)) >= 1
    return sum([has_unit, has_date, has_direction, has_entity]) >= 2


def is_analytical_numeric_sentence(sentence: str) -> bool:
    normalized = normalize_text(sentence)
    numbers = extract_numbers(sentence)
    if not numbers:
        return False
    if re.search(r"\b[A-Z]{2,}\d{3,}(?:-\d+)*(?:/\d+)?\b", sentence):
        return False
    if any(
        term in normalized
        for term in [
            "volume ",
            "edited by",
            "isbn",
            "copyright",
            "all rights reserved",
            "page ",
            "页码",
        ]
    ):
        return False
    has_explicit_unit = bool(
        re.search(
            r"[%$€£¥元亿万]|bps?|pct|trillion|billion|million|thousand|bn|mn|trn|"
            r"years?|months?|quarters?|倍|个百分点|个基点",
            sentence,
            flags=re.IGNORECASE,
        )
    )
    bare_values = [numeric_scalar(number) for number in numbers]
    bare_values = [value for value in bare_values if value is not None]
    if bare_values and all(1900 <= value <= 2100 for value in bare_values) and not has_explicit_unit:
        return False
    if bare_values and all(abs(value) <= 3 for value in bare_values) and not has_explicit_unit:
        return False
    if len(numbers) >= 8:
        non_year_values = [value for value in bare_values if not 1900 <= value <= 2100]
        if not has_explicit_unit and len(non_year_values) <= 2:
            return False
    return True


def numeric_scalar(value: str) -> float | None:
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", value or "")
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None
