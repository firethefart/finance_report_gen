from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from chart_judges import DEFAULT_VL_MODEL, run_chart_vl_judges
from chart_extractor import extract_chart_candidates
from eval_utils import ROOT, extract_dates, extract_numbers, repo_path, write_json, write_text
from html_runtime_adapter_v2 import adapt_html_runtime_v2
from report_parser import parse_candidate_report
from scoring_v2 import aggregate_v2_scores, render_v2_markdown
from verifier_profiles import load_verifier_profile, profile_get
from v2_checks import run_v2_candidate_checks
from v2_llm_verifiers import run_v2_claim_numeric_llm_verifier, run_v2_compliance_llm_verifier, run_v2_strategy_reasoning_llm_verifier
from verifier_config import apply_model_config_to_profile


def run_one_v2(
    candidate_report: Path,
    out_dir: Path,
    report_id: str | None = None,
    report_title: str = "",
    report_institution: str = "",
    verifier_profile: dict[str, Any] | None = None,
    api_key_file: Path | None = None,
    enable_chart_vl_judge: bool | None = None,
    enable_claim_numeric_llm: bool | None = None,
    enable_strategy_reasoning_llm: bool | None = None,
    enable_compliance_llm: bool | None = None,
    extract_charts: bool | None = None,
    cache: bool = True,
) -> dict[str, Any]:
    profile = verifier_profile or {}
    candidate = repo_path(candidate_report)
    if candidate is None:
        raise ValueError("candidate_report is required")
    candidate = candidate.resolve()
    report_id = report_id or safe_report_id(candidate.stem)
    out_dir = repo_path(out_dir) or out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    adapter_manifest: dict[str, Any] = {}
    if candidate.suffix.lower() in {".html", ".htm"}:
        adapter_result = adapt_html_runtime_v2(
            html_path=candidate,
            out_dir=out_dir / "html_adapter" / report_id,
            report_id=report_id,
            max_visuals=int(profile_get(profile, "html_adapter.max_visuals", 80)),
            viewport_width=int(profile_get(profile, "html_adapter.viewport_width", 1440)),
            viewport_height=int(profile_get(profile, "html_adapter.viewport_height", 1100)),
            context_height=int(profile_get(profile, "html_adapter.context_height", 1200)),
        )
        adapter_manifest = adapter_result["manifest"]
        parsed = parsed_from_html_adapter(
            report_id,
            candidate,
            adapter_result,
            fallback_title=report_title,
            institution=report_institution,
        )
        chart_inventory = chart_inventory_from_html_adapter(report_id, adapter_result)
    else:
        parsed = parse_candidate_report(
            candidate,
            report_id=report_id,
            title=report_title,
            work_dir=out_dir / "parse_cache",
            render_pages=int(profile_get(profile, "execution.render_pages", 2)),
            cache=cache,
        )
        parsed["institution"] = report_institution
        chart_extract_enabled = bool(profile_get(profile, "execution.extract_charts", True)) if extract_charts is None else extract_charts
        chart_inventory = None
        if chart_extract_enabled:
            chart_inventory = extract_chart_candidates(
                candidate,
                report_id=report_id,
                fmt=parsed.get("format") or candidate.suffix.lower().lstrip("."),
                out_dir=out_dir,
                expected_charts=[],
                max_pages=int(profile_get(profile, "chart.max_pages", 20)),
                max_charts=int(profile_get(profile, "chart.max_charts", 8)),
                cache=cache,
            )
            parsed["chart_inventory"] = chart_inventory

    chart_vl_judges = None
    chart_vl_enabled = bool(profile_get(profile, "modules.enable_chart_vl_judge", False)) if enable_chart_vl_judge is None else enable_chart_vl_judge
    if chart_vl_enabled and chart_inventory and api_key_file:
        chart_vl_judges = run_chart_vl_judges(
            chart_inventory.get("charts") or [],
            parsed,
            api_key_file=api_key_file,
            out_dir=out_dir,
            model=profile_get(profile, "models.chart_vl", DEFAULT_VL_MODEL),
            max_charts=int(profile_get(profile, "chart.vl_max_charts", 4)),
            max_tokens=int(profile_get(profile, "chart.vl_max_tokens", 4200)),
            repair_max_tokens=int(profile_get(profile, "chart.vl_repair_max_tokens", 2600)),
            selection_strategy=profile_get(profile, "chart.vl_selection_strategy", "first_n"),
            gate_all=bool(profile_get(profile, "chart.vl_gate_all", False)),
            gate_max_charts=int(profile_get(profile, "chart.vl_gate_max_charts", 16)),
            gate_max_tokens=int(profile_get(profile, "chart.vl_gate_max_tokens", 900)),
        )

    module_results = run_v2_candidate_checks(
        parsed,
        chart_inventory=chart_inventory,
        chart_vl_judges=chart_vl_judges,
        chart_config=profile_get(profile, "chart", {}),
    )
    claim_llm_enabled = bool(profile_get(profile, "modules.enable_claim_numeric_llm", False)) if enable_claim_numeric_llm is None else enable_claim_numeric_llm
    strategy_llm_enabled = bool(profile_get(profile, "modules.enable_strategy_reasoning_llm", False)) if enable_strategy_reasoning_llm is None else enable_strategy_reasoning_llm
    compliance_llm_enabled = bool(profile_get(profile, "modules.enable_compliance_llm", False)) if enable_compliance_llm is None else enable_compliance_llm
    if claim_llm_enabled and api_key_file:
        claim_llm = run_v2_claim_numeric_llm_verifier(
            parsed,
            api_key_file=api_key_file,
            out_dir=out_dir,
            extract_model=profile_get(profile, "models.claim_extract", "deepseek/deepseek-v4-flash"),
            judge_model=profile_get(profile, "models.claim_judge", "deepseek/deepseek-v4-pro"),
            max_claims=int(profile_get(profile, "claim_numeric.max_claims", 18)),
            config=profile_get(profile, "claim_numeric", {}),
            cache=cache,
        )
        module_results["claim_numeric_llm"] = claim_llm
        module_results["claim_numeric_discipline"] = blend_module_results(
            module_results["claim_numeric_discipline"],
            claim_llm,
            rule_weight=float(profile_get(profile, "v2_scoring.fusion_weights.claim_numeric_rule", 0.35)),
            module_name="claim_numeric_discipline",
        )
    if strategy_llm_enabled and api_key_file:
        strategy_llm = run_v2_strategy_reasoning_llm_verifier(
            parsed,
            api_key_file=api_key_file,
            out_dir=out_dir,
            extract_model=profile_get(profile, "models.strategy_extract", "deepseek/deepseek-v4-flash"),
            judge_model=profile_get(profile, "models.strategy_judge", "deepseek/deepseek-v4-pro"),
            max_chains=int(profile_get(profile, "strategy_reasoning.max_chains", 10)),
            config=profile_get(profile, "strategy_reasoning", {}),
            cache=cache,
        )
        module_results["strategy_reasoning_llm"] = strategy_llm
        module_results["strategy_reasoning"] = blend_module_results(
            module_results["strategy_reasoning"],
            strategy_llm,
            rule_weight=float(profile_get(profile, "v2_scoring.fusion_weights.strategy_reasoning_rule", 0.25)),
            module_name="strategy_reasoning",
        )
    if compliance_llm_enabled and api_key_file:
        compliance_llm = run_v2_compliance_llm_verifier(
            parsed,
            module_results["compliance"],
            api_key_file=api_key_file,
            out_dir=out_dir,
            judge_model=profile_get(profile, "models.compliance_judge", profile_get(profile, "models.claim_judge", "deepseek/deepseek-v4-pro")),
            config=profile_get(profile, "compliance", {}),
            cache=cache,
        )
        module_results["compliance_llm"] = compliance_llm
        module_results["compliance"] = apply_compliance_llm_confirmation(module_results["compliance"], compliance_llm)
    result = aggregate_v2_scores(
        report_id=report_id,
        parsed=parsed,
        module_results=module_results,
        profile=profile,
        adapter_manifest=adapter_manifest,
    )
    if profile:
        result["verifier_profile"] = profile
    write_json(out_dir / f"{report_id}.v2.eval.json", result)
    write_text(out_dir / f"{report_id}.v2.eval.md", render_v2_markdown(result))
    if bool(profile_get(profile, "feedback.write_skill_feedback", False)):
        write_text(out_dir / f"{report_id}.skill_feedback.md", render_skill_feedback_markdown(result))
    return result


def blend_module_results(rule_result: dict[str, Any], llm_result: dict[str, Any], rule_weight: float, module_name: str) -> dict[str, Any]:
    rule_score = float(rule_result.get("score") or 0.0)
    llm_score = llm_result.get("score")
    if not isinstance(llm_score, (int, float)):
        return {**rule_result, "llm_blend": {"enabled": True, "used": False, "reason": "llm_score_missing"}}
    rule_weight = max(0.0, min(1.0, rule_weight))
    score = rule_weight * rule_score + (1.0 - rule_weight) * float(llm_score)
    return {
        **rule_result,
        "score": round(max(0.0, min(1.0, score)), 3),
        "issues": (rule_result.get("issues") or []) + (llm_result.get("issues") or []),
        "llm_blend": {
            "module": module_name,
            "enabled": True,
            "used": True,
            "rule_weight": rule_weight,
            "llm_weight": round(1.0 - rule_weight, 3),
            "rule_score": round(rule_score, 3),
            "llm_score": round(float(llm_score), 3),
        },
        "rule_result": rule_result,
        "llm_result": llm_result,
    }


def apply_compliance_llm_confirmation(rule_result: dict[str, Any], llm_result: dict[str, Any]) -> dict[str, Any]:
    if not llm_result.get("module_complete"):
        return {**rule_result, "llm_confirmation": {"enabled": True, "used": False, "reason": llm_result.get("error") or "llm_incomplete"}, "llm_result": llm_result}
    confirmed = llm_result.get("confirmed_redline_issues") or []
    non_redline_issues = [item for item in rule_result.get("issues") or [] if item.get("location") != "redline"]
    issues = non_redline_issues + confirmed
    score = float(rule_result.get("score") or 0.0)
    if confirmed:
        score = min(score, float(llm_result.get("score") or 0.0), 0.5)
    elif rule_result.get("redline_candidates"):
        score = max(score, 0.9)
    return {
        **rule_result,
        "score": round(max(0.0, min(1.0, score)), 3),
        "issues": issues,
        "redline_issues": confirmed,
        "llm_confirmation": {
            "enabled": True,
            "used": True,
            "candidate_count": len(rule_result.get("redline_candidates") or []),
            "confirmed_redline_count": len(confirmed),
            "llm_score": llm_result.get("score"),
        },
        "llm_result": llm_result,
    }


def parsed_from_html_adapter(
    report_id: str,
    source_path: Path,
    adapter_result: dict[str, Any],
    fallback_title: str = "",
    institution: str = "",
) -> dict[str, Any]:
    text_payload = adapter_result["report_text"]
    visual_objects = adapter_result["visual_objects"]
    full_text = text_payload.get("text") or ""
    analysis_text, boundary = extract_html_analysis_text(full_text, source_path=source_path)
    headings = [item.get("text") if isinstance(item, dict) else str(item) for item in text_payload.get("headings") or []]
    headings = [h for h in headings if h]
    headings = [heading for heading in headings if normalize_heading(heading) in normalize_heading(analysis_text)]
    synthetic_headings = extract_numbered_section_headings(analysis_text) if len(headings) < 5 else []
    headings = headings + [heading for heading in synthetic_headings if heading not in headings]
    links = text_payload.get("links") or []
    sections = sectionize_from_headings(analysis_text, headings)
    visuals = visual_objects.get("visual_objects") or []
    parse_diagnostics = build_html_parse_diagnostics(text_payload, adapter_result.get("manifest") or {}, analysis_text, headings, links)
    return {
        "report_id": report_id,
        "path": str(source_path),
        "format": "html",
        "title": text_payload.get("title") or fallback_title or source_path.stem,
        "institution": institution,
        "text": full_text,
        "full_text": full_text,
        "analysis_text": analysis_text,
        "text_length": text_payload.get("text_length") or len(full_text),
        "analysis_text_length": len(analysis_text),
        "analysis_boundary": boundary,
        "html_parse_status": parse_diagnostics["html_parse_status"],
        "html_parse_diagnostics": parse_diagnostics,
        "report_likeness": parse_diagnostics["report_likeness"],
        "report_likeness_reasons": parse_diagnostics["report_likeness_reasons"],
        "headings": headings,
        "sections": sections,
        "links": links,
        "numbers": extract_numbers(analysis_text),
        "dates": extract_dates(analysis_text),
        "table_figure_hint_count": len(visuals),
        "source_hint_count": len(re.findall(r"source|sources|来源|资料来源|数据来源", analysis_text, flags=re.IGNORECASE)),
        "disclaimer_hint_count": len(re.findall(r"disclaimer|disclosures|risk considerations|risk disclosure|important information|免责声明|风险提示", full_text, flags=re.IGNORECASE)),
        "parse_quality": parse_diagnostics["parse_quality"],
        "html_stats": {
            "h1_h4_count": len(headings),
            "table_count": len([v for v in visuals if v.get("tag") == "table"]),
            "image_count": len([v for v in visuals if v.get("tag") in {"img", "svg", "canvas"}]),
            "links": links[:50],
        },
        "warnings": adapter_result["manifest"].get("warnings") or [],
    }


RELATED_CARD_RE = re.compile(
    r"\s(?:WEALTH MANAGEMENT|GLOBAL CAPITAL MARKETS|INVESTMENT MANAGEMENT|RESEARCH)\s+"
    r"[A-Z][A-Za-z0-9’'&,\-–— ]{8,100}"
)

HTML_BOUNDARY_MARKERS = [
    " Discover More ",
    " Disclosures: ",
    " Risk Considerations ",
    " Important Information ",
    " View Disclosures",
]


def extract_html_analysis_text(full_text: str, source_path: Path | None = None) -> tuple[str, dict[str, Any]]:
    text = re.sub(r"\s+", " ", full_text or "").strip()
    article_text, article_meta = extract_article_like_text(source_path) if source_path else ("", {})
    if is_article_text_usable(article_text, text):
        bounded, marker_boundary = trim_html_boilerplate(article_text)
        return bounded, {
            "mode": "article_container" if not marker_boundary.get("marker") else "article_container_trimmed",
            "full_text_length": len(text),
            "analysis_text_length": len(bounded),
            "trimmed_char_count": max(0, len(text) - len(bounded)),
            "marker": marker_boundary.get("marker", ""),
            "article_extraction": article_meta,
        }
    bounded, boundary = trim_html_boilerplate(text)
    return bounded, boundary


def trim_html_boilerplate(text: str) -> tuple[str, dict[str, Any]]:
    text = re.sub(r"\s+", " ", text or "").strip()
    candidates: list[tuple[int, str]] = []
    minimum = max(1800, int(len(text) * 0.20))
    for marker in HTML_BOUNDARY_MARKERS:
        position = text.find(marker, minimum)
        if position >= 0:
            candidates.append((position, marker.strip()))
    related_matches = [match for match in RELATED_CARD_RE.finditer(text) if match.start() >= minimum]
    if len(related_matches) >= 2:
        candidates.append((related_matches[0].start(), "related_content_cards"))
    if not candidates:
        return text, {
            "mode": "full_text",
            "full_text_length": len(text),
            "analysis_text_length": len(text),
            "trimmed_char_count": 0,
            "marker": "",
        }
    position, marker = min(candidates, key=lambda item: item[0])
    analysis_text = text[:position].strip()
    return analysis_text, {
        "mode": "trimmed",
        "full_text_length": len(text),
        "analysis_text_length": len(analysis_text),
        "trimmed_char_count": len(text) - len(analysis_text),
        "marker": marker,
    }


def extract_article_like_text(source_path: Path | None) -> tuple[str, dict[str, Any]]:
    if not source_path or not source_path.exists():
        return "", {"used": False, "reason": "source_missing"}
    try:
        html = source_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        return "", {"used": False, "reason": f"read_failed: {exc!r}"}
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    selectors = [
        "article",
        "main",
        "[role='main']",
        ".article",
        ".article-body",
        ".content",
        ".content-body",
        ".report",
        ".report-body",
        ".research",
        ".insight",
        ".story",
    ]
    candidates: list[dict[str, Any]] = []
    for selector in selectors:
        for node in soup.select(selector):
            text = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
            if len(text) < 600:
                continue
            link_text = sum(len(a.get_text(" ", strip=True)) for a in node.find_all("a"))
            node_count = max(1, len(node.find_all(True)))
            density = len(text) / node_count
            candidates.append(
                {
                    "selector": selector,
                    "text": text,
                    "text_length": len(text),
                    "link_text_ratio": round(link_text / max(1, len(text)), 3),
                    "density": round(density, 2),
                    "score": len(text) * max(0.25, 1.0 - min(0.75, link_text / max(1, len(text)))) + min(2500, density * 20),
                }
            )
    if not candidates:
        return "", {"used": False, "reason": "no_article_like_container"}
    best = max(candidates, key=lambda item: item["score"])
    return best["text"], {
        "used": True,
        "selector": best["selector"],
        "text_length": best["text_length"],
        "link_text_ratio": best["link_text_ratio"],
        "density": best["density"],
        "candidate_count": len(candidates),
    }


def is_article_text_usable(article_text: str, full_text: str) -> bool:
    if len(article_text) < 1800:
        return False
    if not full_text:
        return True
    if len(article_text) < max(1800, int(len(full_text) * 0.18)):
        return False
    if len(article_text) > int(len(full_text) * 1.25):
        return False
    return True


def build_html_parse_diagnostics(
    text_payload: dict[str, Any],
    adapter_manifest: dict[str, Any],
    analysis_text: str,
    headings: list[str],
    links: list[dict[str, Any]],
) -> dict[str, Any]:
    text = analysis_text or ""
    lower = text.lower()
    text_length = len(text)
    link_text_chars = sum(len(str(link.get("text") or "")) for link in links if isinstance(link, dict))
    link_density = link_text_chars / max(1, int(text_payload.get("text_length") or text_length or 1))
    strategy_terms = [
        "outlook",
        "strategy",
        "allocation",
        "portfolio",
        "market",
        "macro",
        "risk",
        "scenario",
        "forecast",
        "investment",
        "equity",
        "fixed income",
        "credit",
        "inflation",
        "growth",
        "policy",
        "earnings",
        "valuation",
        "配置",
        "策略",
        "市场",
        "宏观",
        "风险",
        "情景",
        "投资",
        "权益",
        "债券",
        "通胀",
        "增长",
        "政策",
    ]
    navigation_terms = [
        "home",
        "menu",
        "subscribe",
        "sign in",
        "contact us",
        "privacy",
        "cookie",
        "all rights reserved",
        "首页",
        "导航",
        "登录",
        "注册",
        "联系我们",
    ]
    strategy_hits = sum(1 for term in strategy_terms if term in lower)
    navigation_hits = sum(1 for term in navigation_terms if term in lower)
    score = 0.0
    reasons: list[str] = []
    if text_length >= 6000:
        score += 0.28
        reasons.append("long_enough_report_body")
    elif text_length >= 2500:
        score += 0.18
        reasons.append("moderate_report_body")
    elif text_length >= 1000:
        score += 0.08
        reasons.append("short_but_readable_body")
    else:
        reasons.append("body_too_short")
    heading_count = len(headings)
    if heading_count >= 6:
        score += 0.18
        reasons.append("multiple_report_headings")
    elif heading_count >= 3:
        score += 0.10
        reasons.append("some_report_headings")
    if strategy_hits >= 8:
        score += 0.28
        reasons.append("strong_strategy_term_coverage")
    elif strategy_hits >= 4:
        score += 0.18
        reasons.append("moderate_strategy_term_coverage")
    elif strategy_hits >= 2:
        score += 0.08
        reasons.append("weak_strategy_term_coverage")
    if re.search(r"\b20\d{2}\b|[%$]|bps|bp|trillion|billion|million|万亿|亿元|基点|%", text, flags=re.IGNORECASE):
        score += 0.12
        reasons.append("numeric_or_time_signals")
    if link_density <= 0.18:
        score += 0.10
        reasons.append("low_navigation_link_density")
    elif link_density >= 0.45:
        score -= 0.18
        reasons.append("high_navigation_link_density")
    if navigation_hits >= 6 and text_length < 5000:
        score -= 0.20
        reasons.append("navigation_or_landing_page_signals")
    warnings = adapter_manifest.get("warnings") or []
    browser_status = (adapter_manifest.get("browser_status") or {}).get("status") or ""
    if "html_text_too_short_for_strategy_report" in warnings:
        score = min(score, 0.42)
    report_likeness = round(max(0.0, min(1.0, score)), 3)
    if text_length >= 2500 and report_likeness >= 0.5:
        parse_quality = "good"
    elif text_length >= 1000 and report_likeness >= 0.3:
        parse_quality = "fair"
    else:
        parse_quality = "poor"
    if not text.strip():
        html_parse_status = "empty_text"
    elif browser_status and browser_status != "ok":
        html_parse_status = "static_fallback"
    elif parse_quality == "poor":
        html_parse_status = "low_confidence"
    else:
        html_parse_status = "ok"
    return {
        "html_parse_status": html_parse_status,
        "parse_quality": parse_quality,
        "report_likeness": report_likeness,
        "report_likeness_reasons": reasons,
        "analysis_text_length": text_length,
        "heading_count": heading_count,
        "link_count": len(links),
        "link_text_density": round(link_density, 3),
        "strategy_term_hit_count": strategy_hits,
        "navigation_term_hit_count": navigation_hits,
        "adapter_warnings": warnings,
        "browser_status": browser_status,
    }


def extract_numbered_section_headings(text: str) -> list[str]:
    matches = list(
        re.finditer(
            r"(?:^|(?<=[.!?])\s+)\b([1-9])\s+([A-Z][^.!?]{8,140})",
            text or "",
        )
    )
    by_number: dict[int, str] = {}
    for match in matches:
        number = int(match.group(1))
        candidate = re.sub(r"\s+", " ", match.group(2)).strip()
        if re.match(r"source\s*[:：]", candidate, flags=re.IGNORECASE):
            continue
        words = candidate.split()
        if len(words) > 14:
            candidate = " ".join(words[:14])
        if 3 <= len(candidate.split()) <= 14:
            by_number.setdefault(number, f"{number} {candidate}")
    sequence: list[str] = []
    expected = 1
    while expected in by_number:
        sequence.append(by_number[expected])
        expected += 1
    return sequence if len(sequence) >= 2 else []


def normalize_heading(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def chart_inventory_from_html_adapter(report_id: str, adapter_result: dict[str, Any]) -> dict[str, Any]:
    visual_payload = adapter_result["visual_objects"]
    text_payload = adapter_result["report_text"]
    report_text = text_payload.get("text") or ""
    charts = []
    skipped_visuals = list(visual_payload.get("skipped_visuals") or [])
    for index, visual in enumerate(visual_payload.get("visual_objects") or [], start=1):
        nearby = visual.get("nearby_text") or ""
        visual_role = infer_visual_role(visual, nearby)
        if should_skip_html_visual(visual, nearby, visual_role):
            skipped_visuals.append(
                {
                    "reason": "decorative_or_navigation_visual",
                    "visual_id": visual.get("visual_id"),
                    "tag": visual.get("tag"),
                    "visual_role": visual_role,
                    "nearby_text": nearby[:300],
                }
            )
            continue
        chart_id = f"{report_id}_html_visual_{index:03d}"
        charts.append(
            {
                "chart_id": chart_id,
                "page_chart_id": chart_id,
                "page": "html",
                "bbox": visual.get("bbox"),
                "page_bbox": visual.get("bbox"),
                "title": visual.get("section_heading") or infer_visual_title(nearby),
                "caption": infer_visual_title(nearby),
                "chart_kind_hint": infer_visual_kind(visual),
                "source_format": "html_runtime",
                "detection_method": "html_runtime_dom_bbox",
                "object_index": visual.get("object_index") or index,
                "object_count_on_page": visual.get("object_count") or len(visual_payload.get("visual_objects") or []),
                "object_role": visual.get("tag"),
                "visual_role": visual_role,
                "image_path": visual.get("target_image_path"),
                "page_image_path": visual.get("context_image_path") or visual.get("full_page_image_path"),
                "full_page_image_path": visual.get("full_page_image_path"),
                "nearby_text": nearby,
                "page_text": report_text[:8000],
                "page_text_blocks": build_text_blocks(report_text),
                "crop_quality": {"source": "html_runtime_dom_bbox", "oversized_visual": bool(visual.get("oversized_visual"))},
                "warnings": visual.get("warnings") or [],
                "source_note": infer_source_note(nearby),
                "unit_hint": infer_unit_hint(nearby),
                "numbers": visual.get("numbers") or extract_numbers(nearby),
                "dates": extract_dates(nearby),
                "expected_match": None,
            }
        )
    return {
        "report_id": report_id,
        "source_path": visual_payload.get("source_path"),
        "source_format": "html_runtime",
        "charts": charts,
        "skipped_visuals": skipped_visuals,
        "audit": {
            "visual_count": len(charts),
            "raw_visual_count": len(visual_payload.get("visual_objects") or []),
            "skipped_visual_count": len(skipped_visuals),
        },
    }


def sectionize_from_headings(text: str, headings: list[str]) -> list[dict[str, str]]:
    if not headings:
        chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", text or "") if len(chunk.strip()) > 120]
        return [{"heading": f"chunk_{i + 1}", "text": chunk[:2400]} for i, chunk in enumerate(chunks[:24])]
    sections = []
    normalized = text or ""
    lowered = normalized.lower()
    positions = []
    for heading in headings:
        idx = lowered.find(heading.lower())
        if idx >= 0:
            positions.append((idx, heading))
    positions = sorted(set(positions))
    for i, (start, heading) in enumerate(positions[:32]):
        end = positions[i + 1][0] if i + 1 < len(positions) else min(len(normalized), start + 3200)
        sections.append({"heading": heading, "text": normalized[start:end].strip()[:3200]})
    return sections


def build_text_blocks(text: str) -> list[dict[str, Any]]:
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n|(?<=。)\s+|(?<=\.)\s+", text or "") if len(chunk.strip()) > 80]
    return [{"block_id": f"html_text_{i + 1:03d}", "text": chunk[:900]} for i, chunk in enumerate(chunks[:80])]


def infer_visual_title(text: str) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in re.split(r"\n|。|\. ", text) if line.strip()]
    return lines[0][:160] if lines else text[:160]


def infer_visual_kind(visual: dict[str, Any]) -> str:
    tag = visual.get("tag")
    if tag == "table":
        return "table"
    if tag == "canvas":
        return "canvas_chart"
    if tag == "svg":
        return "svg_chart"
    class_name = str(visual.get("class_name") or "").lower()
    if any(term in class_name for term in ["kpi", "metric", "card"]):
        return "metric_panel"
    return "html_visual"


def infer_visual_role(visual: dict[str, Any], nearby: str) -> str:
    tag = str(visual.get("tag") or "").lower()
    class_name = str(visual.get("class_name") or "").lower()
    text = (nearby or "").lower()
    role = str(visual.get("role") or "").lower()
    combined = " ".join([class_name, text[:500], role])
    if tag == "table":
        return "table"
    if any(term in combined for term in ["logo", "avatar", "author", "profile", "share", "social", "footer", "header", "nav", "breadcrumb"]):
        return "decorative"
    if any(term in combined for term in ["hero", "banner", "cover"]):
        return "hero"
    if any(term in combined for term in ["chart", "figure", "exhibit", "plot", "graph", "data", "source", "unit", "legend", "axis", "kpi", "metric"]):
        return "analytical_visual"
    if tag in {"canvas", "svg"} and (extract_numbers(nearby) or len(nearby) > 160):
        return "analytical_visual"
    if tag == "img" and (infer_source_note(nearby) or len(extract_numbers(nearby)) >= 2):
        return "analytical_visual"
    if tag == "img":
        return "image_unknown"
    return "unknown"


def should_skip_html_visual(visual: dict[str, Any], nearby: str, visual_role: str) -> bool:
    tag = str(visual.get("tag") or "").lower()
    bbox = visual.get("bbox") or {}
    width = float(bbox.get("width") or 0)
    height = float(bbox.get("height") or 0)
    if visual_role == "decorative":
        return True
    if visual_role == "hero" and not infer_source_note(nearby) and len(extract_numbers(nearby)) < 2:
        return True
    if tag in {"img", "svg"} and visual_role in {"image_unknown", "unknown"} and not infer_source_note(nearby) and len(extract_numbers(nearby)) < 2:
        return True
    if width and height and width < 120 and height < 80 and tag != "table":
        return True
    return False


def render_skill_feedback_markdown(result: dict[str, Any]) -> str:
    normalized = result.get("dimension_score_normalized") or {}
    issues = result.get("issues") or []
    gate = result.get("gate") or {}
    priority_modules = {
        "structure": "内容结构",
        "strategy_reasoning": "策略推理",
        "scenario_risk": "情景/风险",
        "visual_qa": "图表/版式",
        "delivery": "交付完整性",
        "compliance": "合规表达",
    }
    low_priority_modules = {"source_traceability", "claim_numeric_discipline", "claim_numeric_llm"}
    lines = [
        f"# Skill Iteration Feedback: {result.get('report_id')}",
        "",
        f"- Overall: **{result.get('overall_score')} / 100**",
        f"- Evaluation confidence: **{(result.get('evaluation_confidence') or {}).get('score', 'n/a')}**",
        f"- Grade: **{result.get('grade')}**",
        f"- Quality gate: **{'PASS' if gate.get('passed') else 'FAIL'}**",
        f"- Candidate: `{result.get('candidate_report')}`",
        "",
        "## Dimension snapshot",
        "",
    ]
    for key, label in priority_modules.items():
        if key in normalized:
            lines.append(f"- {label} (`{key}`): {normalized[key]:.3f}")
    parse_diag = result.get("evaluation_confidence") or {}
    adapter = result.get("adapter_manifest") or {}
    lines.extend(
        [
            "",
            "## Parse and evaluation confidence",
            "",
            f"- HTML parse status: `{parse_diag.get('html_parse_status') or 'n/a'}`",
            f"- Report-likeness: `{parse_diag.get('report_likeness', 'n/a')}`",
            f"- Analysis text length: `{parse_diag.get('analysis_text_length', 'n/a')}`",
            f"- Browser status: `{(adapter.get('browser_status') or {}).get('status', 'n/a')}`",
        ]
    )
    if parse_diag.get("reasons"):
        lines.append(f"- Confidence notes: {', '.join(parse_diag.get('reasons') or [])}")
    lines.extend(["", "## Highest-impact feedback", ""])
    primary = [item for item in issues if item.get("module") not in low_priority_modules]
    if not primary:
        lines.append("- No high-priority content/layout issues were detected.")
    else:
        for item in primary[:8]:
            lines.append(
                f"- [{item.get('severity')}] {item.get('module')} / {item.get('issue_type')}: "
                f"{item.get('description')} (`{item.get('location')}`)"
            )
    lines.extend(["", "## Suggested skill patch themes", ""])
    themes = infer_skill_patch_themes(primary, normalized)
    if themes:
        lines.extend([f"- {theme}" for theme in themes])
    else:
        lines.append("- Keep current report-generation behavior; no obvious patch theme from this run.")
    low_priority = [item for item in issues if item.get("module") in low_priority_modules]
    lines.extend(["", "## Low-priority source/fact notes", ""])
    if low_priority:
        for item in low_priority[:8]:
            lines.append(f"- [{item.get('severity')}] {item.get('module')}: {item.get('description')}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Gate failures", ""])
    if gate.get("failures"):
        lines.extend([f"- {failure}" for failure in gate.get("failures")])
    else:
        lines.append("- None.")
    return "\n".join(lines) + "\n"


def infer_skill_patch_themes(primary_issues: list[dict[str, Any]], normalized: dict[str, float]) -> list[str]:
    themes: list[str] = []
    if normalized.get("structure", 1.0) < 0.65:
        themes.append("Strengthen report skeleton: explicit summary, market context, strategy conclusion, and risk/scenario sections.")
    if normalized.get("strategy_reasoning", 1.0) < 0.65:
        themes.append("Make thesis → mechanism → investment implication chains explicit instead of only describing facts.")
    if normalized.get("scenario_risk", 1.0) < 0.65:
        themes.append("Add scenario boundaries, downside risks, and conditions under which the thesis may fail.")
    if normalized.get("visual_qa", 1.0) < 0.60:
        themes.append("Improve chart/table binding: titles, units, source notes, and nearby explanatory text.")
    issue_types = {item.get("issue_type") for item in primary_issues}
    if "missing_investment_implication" in issue_types:
        themes.append("End key sections with actionable allocation, positioning, watchlist, or decision-usefulness implications.")
    if "missing_section_signal" in issue_types:
        themes.append("Use clearer section headings so readers and verifier can identify the analytical flow.")
    return themes[:8]


def infer_source_note(text: str) -> str:
    match = re.search(r"(source|sources|资料来源|数据来源|来源)[:：]?\s*([^\n。.;]{1,120})", text or "", flags=re.IGNORECASE)
    return match.group(0)[:180] if match else ""


def infer_unit_hint(text: str) -> str:
    match = re.search(r"(unit|单位)[:：]?\s*([^\n。.;]{1,80})|[%$￥元亿万]|bps|bp|bn|mn", text or "", flags=re.IGNORECASE)
    return match.group(0)[:100] if match else ""


def safe_report_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_\-]+", "_", value).strip("_")
    return cleaned[:80] or "candidate_report"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run candidate-only strategy report verifier V2.")
    parser.add_argument("--candidate-report", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "evals" / "strategy_report" / "results" / "v2_smoke")
    parser.add_argument("--report-id", default=None)
    parser.add_argument("--verifier-profile", default="v2_html_smoke")
    parser.add_argument("--api-key-file", type=Path, default=ROOT / "api_key.txt")
    parser.add_argument("--enable-chart-vl-judge", action="store_true")
    parser.add_argument("--enable-claim-numeric-llm", action="store_true")
    parser.add_argument("--enable-strategy-reasoning-llm", action="store_true")
    parser.add_argument("--enable-compliance-llm", action="store_true")
    parser.add_argument("--no-extract-charts", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    profile = apply_model_config_to_profile(load_verifier_profile(args.verifier_profile))
    result = run_one_v2(
        candidate_report=args.candidate_report,
        out_dir=args.out_dir,
        report_id=args.report_id,
        verifier_profile=profile,
        api_key_file=args.api_key_file,
        enable_chart_vl_judge=args.enable_chart_vl_judge or bool(profile_get(profile, "modules.enable_chart_vl_judge", False)),
        enable_claim_numeric_llm=args.enable_claim_numeric_llm or bool(profile_get(profile, "modules.enable_claim_numeric_llm", False)),
        enable_strategy_reasoning_llm=args.enable_strategy_reasoning_llm or bool(profile_get(profile, "modules.enable_strategy_reasoning_llm", False)),
        enable_compliance_llm=args.enable_compliance_llm or bool(profile_get(profile, "modules.enable_compliance_llm", False)),
        extract_charts=not args.no_extract_charts,
        cache=not args.no_cache,
    )
    print(f"{result['report_id']}: {result['overall_score']} {result['grade']} gate={result['gate']['passed']}")
    write_json(
        args.out_dir / "summary.json",
        {
            "count": 1,
            "results": [
                {
                    "report_id": result["report_id"],
                    "overall_score": result["overall_score"],
                    "grade": result["grade"],
                    "gate_passed": result["gate"]["passed"],
                    "gate_failures": result["gate"]["failures"],
                }
            ],
        },
    )


if __name__ == "__main__":
    main()
