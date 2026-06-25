from __future__ import annotations

import re
from typing import Any

from eval_utils import canonical_number, clamp, contains_fuzzy, extract_numbers, issue, mean, normalize_text, token_overlap
from chart_qa import chart_qa_v2_check


AUTHORITY_HINTS = [
    "sec.gov",
    "federalreserve.gov",
    "imf.org",
    "worldbank.org",
    "bis.org",
    "bloomberg",
    "reuters",
    "exchange",
    "gov",
    "公告",
    "交易所",
    "监管",
    "央行",
    "统计局",
    "goldman",
    "j.p. morgan",
    "jpmorgan",
    "morgan stanley",
    "blackrock",
    "ubs",
    "citi",
    "deutsche",
    "fidelity",
    "vanguard",
    "中信",
    "华泰",
    "国泰君安",
    "广发",
    "招商证券",
    "申万宏源",
]
SCENARIO_TERMS = ["base case", "upside", "downside", "scenario", "sensitivity", "bear", "bull", "基准", "上行", "下行", "情景", "敏感性"]
RISK_TERMS = ["risk", "uncertainty", "volatility", "policy", "execution", "market", "data limitation", "风险", "不确定", "波动", "政策", "执行", "市场", "数据"]
THESIS_TERMS = ["we believe", "we expect", "thesis", "catalyst", "implication", "recommend", "position", "认为", "预计", "核心观点", "催化", "影响", "配置", "建议"]
REDLINE_PATTERNS = [
    r"\bguaranteed return\b",
    r"\brisk[- ]?free\b",
    r"\bmust buy\b",
    r"\bsure profit\b",
    r"必涨",
    r"稳赚",
    r"无风险",
    r"保证收益",
    r"保本保收益",
]


def run_rule_checks(case: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "render_delivery": render_delivery_check(case, parsed),
        "section_coverage": section_coverage_check(case, parsed),
        "source_quality": source_quality_check(case, parsed),
        "claim_citation_alignment": claim_citation_alignment_check(case, parsed),
        "numeric_entity_consistency": numeric_entity_consistency_check(case, parsed),
        "strategy_reasoning_rule": strategy_reasoning_rule_check(case, parsed),
        "scenario_risk": scenario_risk_check(case, parsed),
        "chart_qa": chart_qa_check(case, parsed),
        "compliance_redline": compliance_redline_check(case, parsed),
    }


def render_delivery_check(case: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    score_parts: list[float] = []
    quality = parsed.get("parse_quality")
    if quality in {"excellent", "good"}:
        score_parts.append(1.0)
    elif quality == "fair":
        score_parts.append(0.65)
        issues.append(issue("layout_issue", "medium", "parse", "Candidate report text extraction is only fair."))
    else:
        score_parts.append(0.25)
        issues.append(issue("layout_issue", "high", "parse", "Candidate report could not be parsed with enough usable text."))
    score_parts.append(1.0 if (parsed.get("text_length") or 0) >= 4000 else 0.45)
    if parsed.get("format") == "pdf":
        score_parts.append(1.0 if parsed.get("page_count") else 0.3)
        score_parts.append(1.0 if parsed.get("render_images") else 0.65)
    else:
        stats = parsed.get("html_stats") or {}
        score_parts.append(1.0 if stats.get("h1_h4_count", 0) > 0 else 0.6)
        score_parts.append(1.0 if stats.get("table_count", 0) or stats.get("image_count", 0) else 0.75)
    return {"score": round(mean(score_parts), 3), "issues": issues, "metrics": {"parse_quality": quality}}


def section_coverage_check(case: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    text = parsed.get("text") or ""
    heading_text = "\n".join(parsed.get("headings") or [])
    musts = [s for s in case.get("must_have_sections") or [] if s.get("required", True)]
    matched: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    for section in musts:
        name = section.get("section_name") or ""
        found = contains_fuzzy(name, heading_text, 0.36) or contains_fuzzy(name, text, 0.5)
        point_scores = []
        for point in section.get("required_points") or []:
            point_scores.append(1.0 if contains_fuzzy(str(point), text, 0.5) else 0.0)
        score = 1.0 if found else (mean(point_scores) * 0.65 if point_scores else 0.0)
        matched.append({"section_name": name, "found": found, "score": round(score, 3)})
        if score < 0.45:
            issues.append(issue("missing_section", "medium", name, "Required strategy report section is not clearly present."))
    coverage = mean([m["score"] for m in matched], default=0.0)
    generic = generic_section_coverage(text, heading_text)
    return {"score": round(0.72 * coverage + 0.28 * generic, 3), "issues": issues, "matched_sections": matched, "generic_coverage": generic}


def generic_section_coverage(text: str, headings: str) -> float:
    combined = f"{headings}\n{text}"
    checks = [
        ["summary", "executive", "key takeaways", "摘要", "要点", "核心观点"],
        ["evidence", "source", "data", "chart", "facts", "证据", "数据", "来源"],
        ["strategy", "thesis", "implication", "allocation", "策略", "推理", "配置", "影响"],
        SCENARIO_TERMS,
        RISK_TERMS,
        ["appendix", "disclaimer", "important information", "references", "免责声明", "附录"],
    ]
    hits = [any(term.lower() in normalize_text(combined) for term in group) for group in checks]
    return sum(hits) / len(hits)


def source_quality_check(case: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    links = parsed.get("links") or []
    traceable_links = [link for link in links if is_traceable_source_link(link)]
    source_pack = case.get("source_pack") or []
    raw_text = parsed.get("text") or ""
    text = normalize_text(raw_text)
    source_hints = parsed.get("source_hint_count") or 0
    source_evidence = extract_source_evidence(parsed, source_pack=source_pack, links=traceable_links)
    required_sources = [s for s in source_pack if s.get("required", True)]
    authority_hits = 0
    for source in source_pack:
        blob = normalize_text(" ".join(str(v) for v in source.values() if v is not None))
        authority_hits += int(any(h in blob for h in AUTHORITY_HINTS))
        authority_hits += int(bool(source.get("observed_in_pdf") or source.get("source_path") or source.get("url_or_path")))
    for link in traceable_links:
        href = normalize_text(link.get("href", ""))
        authority_hits += int(any(h in href for h in AUTHORITY_HINTS))
    evidence_authority_hits = sum(1 for item in source_evidence if item.get("authority_hit"))
    institution_blob = normalize_text(" ".join(str(v) for v in (case.get("institution") or {}).values() if v is not None))
    publisher_provenance = 1.0 if institution_blob and institution_blob in text else (0.75 if institution_blob else 0.0)
    source_evidence_count = len(source_evidence)
    sufficiency = clamp((len(traceable_links) + len(source_pack) + source_evidence_count / 3 + source_hints / 10) / max(3, len(required_sources)))
    traceability = 1.0 if source_pack else clamp((len(traceable_links) + source_hints + source_evidence_count) / 8)
    authority = clamp((authority_hits + evidence_authority_hits) / max(2, min(8, len(source_pack) + len(traceable_links) + source_evidence_count)))
    fact_view_split = 1.0 if any(x in text for x in ["we believe", "we expect", "assumption", "假设", "认为", "预计", "测算"]) else 0.55
    score = (
        0.28 * sufficiency
        + 0.26 * traceability
        + 0.20 * authority
        + 0.12 * publisher_provenance
        + 0.14 * fact_view_split
    )
    issues: list[dict[str, str]] = []
    if traceability < 0.45:
        issues.append(issue("missing_source", "high", "sources", "Few traceable sources or source hints were found."))
    if source_evidence_count == 0 and (source_hints or traceable_links):
        issues.append(issue("missing_source", "medium", "sources", "Source signals were detected but no readable source evidence snippets were extracted."))
    if authority < 0.25 and (required_sources or source_evidence_count):
        issues.append(issue("missing_source", "medium", "sources", "Authority source signals are weak."))
    return {
        "score": round(score, 3),
        "issues": issues,
        "metrics": {
            "links": len(links),
            "traceable_source_links": len(traceable_links),
            "source_pack": len(source_pack),
            "source_hints": source_hints,
            "authority_hits": authority_hits,
            "source_evidence_count": source_evidence_count,
            "source_evidence_authority_hits": evidence_authority_hits,
            "sufficiency_signal": round(sufficiency, 3),
            "traceability_signal": round(traceability, 3),
            "authority_signal": round(authority, 3),
            "publisher_provenance_signal": round(publisher_provenance, 3),
        },
        "source_evidence": source_evidence[:30],
    }


SOURCE_EVIDENCE_RE = re.compile(
    r"(?:\b(?:source|sources|data source)\b\s*[:：\-]\s*.{1,220}"
    r"|\b(?:based on|according to)\b\s+.{1,220}"
    r"|(?:资料来源|数据来源|信息来源|来源)\s*[:：\-]\s*.{1,220})",
    re.IGNORECASE,
)

SOURCE_LINK_EXCLUDE_RE = re.compile(
    r"(?:/bio(?:\.html)?/|/footer/|global entities|worldwide entities|"
    r"/investment-management/?$|"
    r"privacy|cookie|terms|disclaimer|accessibility|contact|careers|"
    r"linkedin|facebook|instagram|youtube|twitter|x\.com)",
    re.IGNORECASE,
)


def is_traceable_source_link(link: dict[str, Any]) -> bool:
    href = str(link.get("href") or "").strip()
    label = str(link.get("text") or link.get("label") or "").strip()
    blob = f"{label} {href}"
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
        return False
    if SOURCE_LINK_EXCLUDE_RE.search(blob):
        return False
    normalized_href = normalize_text(href)
    if normalized_href.startswith("file:"):
        return bool(matched_authority_terms(label))
    if re.search(r"^https?://", href, flags=re.IGNORECASE):
        path = re.sub(r"^https?://[^/]+/?", "", href, flags=re.IGNORECASE).strip("/")
        if not path and not matched_authority_terms(blob):
            return False
        return True
    return bool(matched_authority_terms(blob))


AUTHORITY_EVIDENCE_TERMS = [
    "wind",
    "bloomberg",
    "reuters",
    "factset",
    "markit",
    "ceic",
    "haver",
    "fred",
    "imf",
    "world bank",
    "bis",
    "federal reserve",
    "sec",
    "exchange",
    "统计局",
    "央行",
    "人民银行",
    "交易所",
    "证监会",
    "财政部",
    "海关总署",
    "同花顺",
    "万得",
    "中证",
    "上交所",
    "深交所",
    "北交所",
]


def extract_source_evidence(
    parsed: dict[str, Any],
    source_pack: list[dict[str, Any]] | None = None,
    links: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(kind: str, text: str, location: str = "", href: str = "") -> None:
        clean = re.sub(r"\s+", " ", str(text or "")).strip()
        if not clean and not href:
            return
        key = f"{kind}:{clean[:180]}:{href}"
        if key in seen:
            return
        seen.add(key)
        authority_terms = matched_authority_terms(f"{clean} {href}")
        evidence.append(
            {
                "kind": kind,
                "location": location,
                "text": clean[:360],
                "href": href,
                "authority_hit": bool(authority_terms),
                "authority_terms": authority_terms[:8],
            }
        )

    raw_text = parsed.get("text") or ""
    for index, match in enumerate(SOURCE_EVIDENCE_RE.finditer(raw_text), start=1):
        add("text_source_statement", match.group(0), location=f"text_match_{index:03d}")
        if len(evidence) >= 40:
            break

    for index, link in enumerate(links or [], start=1):
        href = str(link.get("href") or "")
        label = str(link.get("text") or link.get("label") or href)
        add("link", label, location=f"link_{index:03d}", href=href)

    for index, source in enumerate(source_pack or [], start=1):
        blob = " ".join(str(value) for value in source.values() if value is not None)
        add("source_pack", blob, location=f"source_pack_{index:03d}", href=str(source.get("url_or_path") or source.get("source_path") or ""))

    chart_inventory = parsed.get("chart_inventory") or {}
    for chart in (chart_inventory.get("charts") or [])[:80]:
        note = chart.get("source_note") or ""
        if note:
            add("chart_source_note", note, location=str(chart.get("chart_id") or "chart"))
        nearby = chart.get("nearby_text") or ""
        if nearby and re.search(SOURCE_EVIDENCE_RE, nearby):
            match = re.search(SOURCE_EVIDENCE_RE, nearby)
            if match:
                add("chart_nearby_source", match.group(0), location=str(chart.get("chart_id") or "chart"))
    return evidence


def matched_authority_terms(text: str) -> list[str]:
    normalized = normalize_text(text)
    hits: list[str] = []
    for term in AUTHORITY_EVIDENCE_TERMS + AUTHORITY_HINTS:
        value = normalize_text(term)
        if value and value in normalized and term not in hits:
            hits.append(term)
    return hits


def claim_citation_alignment_check(case: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    facts = case.get("key_facts") or []
    text = parsed.get("text") or ""
    results: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    for fact in facts:
        claim = fact.get("claim") or fact.get("fact") or ""
        excerpt = fact.get("source_excerpt") or ""
        overlap = max(token_overlap(claim, text), token_overlap(excerpt, text) if excerpt else 0.0)
        numbers = extract_numbers(claim)
        preserved_numbers = number_preservation(numbers, parsed.get("numbers") or [])
        supported = overlap >= 0.44 or (overlap >= 0.25 and preserved_numbers >= 0.6)
        score = 0.72 * clamp(overlap / 0.55) + 0.28 * preserved_numbers
        results.append({"fact_id": fact.get("fact_id"), "claim": claim[:180], "score": round(score, 3), "supported": supported, "overlap": round(overlap, 3)})
        if not supported:
            issues.append(issue("missing_evidence", "medium", fact.get("fact_id") or "key_fact", "Key fact is not clearly supported by candidate text.", evidence=claim[:260]))
    return {"score": round(mean([r["score"] for r in results], default=0.6), 3), "issues": issues, "claim_results": results}


def numeric_entity_consistency_check(case: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    facts = case.get("key_facts") or []
    parsed_numbers = parsed.get("numbers") or []
    expected_numbers: list[str] = []
    for fact in facts:
        expected_numbers.extend(extract_numbers(fact.get("claim") or fact.get("fact") or ""))
        if fact.get("value") is not None:
            expected_numbers.append(str(fact["value"]))
    num_score = number_preservation(expected_numbers, parsed_numbers)
    text = parsed.get("text") or ""
    entities = [
        (case.get("institution") or {}).get("name") or "",
        case.get("report_title") or "",
        case.get("strategy_subtype") or "",
    ]
    entity_scores = [1.0 if contains_fuzzy(entity, text, 0.38) else 0.0 for entity in entities if entity]
    ent_score = mean(entity_scores, default=0.75)
    issues: list[dict[str, str]] = []
    if expected_numbers and num_score < 0.72:
        issues.append(issue("numerical_error", "high", "key_facts", "Important numbers from the golden case are missing or not preserved."))
    if ent_score < 0.5:
        issues.append(issue("entity_mismatch", "medium", "entities", "Institution, title, or subtype identity is weakly represented."))
    return {
        "score": round(0.68 * num_score + 0.32 * ent_score, 3),
        "issues": issues,
        "metrics": {"expected_numbers": expected_numbers[:80], "parsed_number_count": len(parsed_numbers), "entity_score": round(ent_score, 3)},
    }


def strategy_reasoning_rule_check(case: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    text = normalize_text(parsed.get("text") or "")
    theme_terms = case.get("evaluation_hooks", {}).get("expected_themes") or []
    theme_hit = mean([1.0 if normalize_text(term) in text else 0.0 for term in theme_terms], default=0.65)
    thesis_hit = clamp(sum(1 for term in THESIS_TERMS if normalize_text(term) in text) / 5)
    mechanism_terms = ["because", "driven by", "therefore", "leads to", "implication", "由于", "驱动", "因此", "传导", "影响"]
    mechanism_hit = clamp(sum(1 for term in mechanism_terms if term in text) / 5)
    score = 0.4 * theme_hit + 0.35 * thesis_hit + 0.25 * mechanism_hit
    issues = []
    if score < 0.45:
        issues.append(issue("weak_strategy_thesis", "medium", "strategy reasoning", "Rule signals for thesis, themes, or mechanism are weak."))
    return {"score": round(score, 3), "issues": issues, "metrics": {"theme_hit": round(theme_hit, 3), "thesis_hit": round(thesis_hit, 3), "mechanism_hit": round(mechanism_hit, 3)}}


def scenario_risk_check(case: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    text = normalize_text(parsed.get("text") or "")
    scenario = clamp(sum(1 for term in SCENARIO_TERMS if normalize_text(term) in text) / 3)
    risk = clamp(sum(1 for term in RISK_TERMS if normalize_text(term) in text) / 5)
    prohibited = case.get("prohibited_mistakes") or []
    prohibited_covered = mean([1.0 if not contains_fuzzy(m.get("mistake", ""), text, 0.75) else 0.75 for m in prohibited], default=0.8)
    score = 0.42 * scenario + 0.42 * risk + 0.16 * prohibited_covered
    issues: list[dict[str, str]] = []
    if scenario < 0.45:
        issues.append(issue("missing_scenario", "medium", "scenario", "Base/upside/downside or sensitivity analysis is not explicit enough."))
    if risk < 0.45:
        issues.append(issue("compliance_issue", "medium", "risk", "Risk categories or uncertainty boundaries are thin."))
    return {"score": round(score, 3), "issues": issues, "metrics": {"scenario_signal": round(scenario, 3), "risk_signal": round(risk, 3)}}


def chart_qa_check(case: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    if parsed.get("chart_inventory"):
        return chart_qa_v2_check(case, parsed, parsed.get("chart_inventory"))
    expected = case.get("charts_and_tables_to_learn_from") or []
    text = normalize_text(parsed.get("text") or "")
    chart_count = parsed.get("table_figure_hint_count") or 0
    stats = parsed.get("html_stats") or {}
    visual_count = chart_count + stats.get("table_count", 0) + stats.get("image_count", 0)
    existence = 1.0 if visual_count > 0 else (0.55 if not expected else 0.25)
    title_unit_source = mean(
        [
            1.0 if any(t in text for t in group) else 0.0
            for group in [["figure", "chart", "table", "图", "表"], ["source", "资料来源", "数据来源"], ["%", "bps", "unit", "单位", "$", "bn"]]
        ],
        default=0.0,
    )
    expected_match = mean([1.0 if contains_fuzzy(c.get("title_or_description", ""), text, 0.45) else 0.0 for c in expected], default=0.75)
    score = 0.42 * existence + 0.34 * title_unit_source + 0.24 * expected_match
    issues: list[dict[str, str]] = []
    if expected and expected_match < 0.35:
        issues.append(issue("chart_mismatch", "medium", "charts", "Expected chart/table themes are not clearly present."))
    if visual_count > 0 and title_unit_source < 0.45:
        issues.append(issue("label_unit_error", "medium", "charts", "Chart/table title, unit, or source signals are incomplete."))
    return {"score": round(score, 3), "issues": issues, "metrics": {"visual_count": visual_count, "expected_chart_count": len(expected)}}


def compliance_redline_check(case: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    text = parsed.get("text") or ""
    issues: list[dict[str, str]] = []
    redline_candidates = find_redline_candidates(text)
    blocker_candidates = [candidate for candidate in redline_candidates if candidate.get("rule_decision") == "blocker"]
    for candidate in blocker_candidates:
        issues.append(
            issue(
                "compliance_issue",
                "blocker",
                "redline",
                "Forbidden investment certainty or guarantee wording found.",
                evidence=candidate.get("context") or candidate.get("matched_text") or "",
            )
        )
    disclaimer = 1.0 if (parsed.get("disclaimer_hint_count") or 0) > 0 else 0.67
    caution = 1.0 if any(term in normalize_text(text) for term in ["may", "could", "risk", "uncertain", "assumption", "可能", "风险", "不确定", "假设"]) else 0.55
    redline = 0.0 if issues else 1.0
    score = 0.5 * redline + 0.3 * disclaimer + 0.2 * caution
    if disclaimer < 0.6:
        issues.append(issue("compliance_issue", "medium", "disclaimer", "Disclaimer or limitations are not clearly detected."))
    return {
        "score": round(score, 3),
        "issues": issues,
        "redline_issues": [i for i in issues if i["severity"] == "blocker"],
        "redline_candidates": redline_candidates,
        "metrics": {
            "redline_candidate_count": len(redline_candidates),
            "rule_blocker_count": len(blocker_candidates),
            "disclaimer_detected": disclaimer >= 0.6,
            "caution_detected": caution >= 0.6,
        },
    }


def find_redline_candidates(text: str, window: int = 140) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    for pattern in REDLINE_PATTERNS:
        for match in re.finditer(pattern, text or "", flags=re.IGNORECASE):
            key = (match.start(), match.end(), match.group(0).lower())
            if key in seen:
                continue
            seen.add(key)
            start = max(0, match.start() - window)
            end = min(len(text), match.end() + window)
            context = re.sub(r"\s+", " ", text[start:end]).strip()
            decision, reason = classify_redline_candidate(match.group(0), context)
            candidates.append(
                {
                    "matched_text": match.group(0),
                    "pattern": pattern,
                    "start": match.start(),
                    "end": match.end(),
                    "context": context,
                    "rule_decision": decision,
                    "rule_reason": reason,
                }
            )
    return sorted(candidates, key=lambda item: item["start"])


def classify_redline_candidate(matched_text: str, context: str) -> tuple[str, str]:
    normalized = normalize_text(context)
    match_norm = normalize_text(matched_text)
    negation_terms = [
        "not risk-free",
        "not risk free",
        "not guaranteed",
        "no guarantee",
        "does not guarantee",
        "cannot guarantee",
        "不保证",
        "不能保证",
        "并非无风险",
        "不是无风险",
        "并不无风险",
        "不代表无风险",
        "不构成",
        "风险自担",
        "入市有风险",
    ]
    if any(normalize_text(term) in normalized for term in negation_terms):
        return "needs_review", "The redline term appears inside a caution, disclaimer, or negated context."
    hard_terms = ["guaranteed return", "must buy", "sure profit", "必涨", "稳赚", "保证收益", "保本保收益"]
    if any(normalize_text(term) in match_norm for term in hard_terms):
        return "blocker", "Direct guaranteed-return or imperative investment wording."
    promotional_terms = ["buy", "recommend", "return", "profit", "yield", "product", "investment", "买入", "推荐", "收益", "产品", "投资", "可获得"]
    if any(normalize_text(term) in normalized for term in promotional_terms):
        return "needs_review", "Potential redline term appears near investment or return language."
    return "needs_review", "Potential redline term requires contextual confirmation."


def number_preservation(expected_numbers: list[str], observed_numbers: list[str]) -> float:
    expected = [canonical_number(x) for x in expected_numbers if canonical_number(x)]
    if not expected:
        return 0.8
    observed = {canonical_number(x) for x in observed_numbers if canonical_number(x)}
    hits = 0
    for num in expected:
        if num in observed or any(num and (num in other or other in num) for other in observed):
            hits += 1
    return hits / len(expected)
