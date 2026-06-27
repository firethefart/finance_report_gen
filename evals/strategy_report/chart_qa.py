from __future__ import annotations

from typing import Any

from eval_utils import clamp, contains_fuzzy, issue, mean, normalize_text


CHART_WEIGHTS = {
    "inventory": 0.15,
    "spec_completeness": 0.15,
    "data_faithfulness": 0.25,
    "chart_text_alignment": 0.20,
    "visual_clarity": 0.15,
    "financial_appropriateness": 0.10,
}


def chart_qa_v2_check(
    case: dict[str, Any],
    parsed: dict[str, Any],
    chart_inventory: dict[str, Any] | None = None,
    chart_vl_judges: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config or {}
    inventory = chart_inventory or parsed.get("chart_inventory") or {}
    charts = inventory.get("charts") or []
    expected = case.get("charts_and_tables_to_learn_from") or []
    judged = chart_vl_judges or {}
    chart_results = [score_chart(chart, expected, parsed, judged.get(chart.get("chart_id"))) for chart in charts]
    scorable_results = [result for result in chart_results if not result.get("excluded_from_chart_score")]
    scorable_charts = [chart for chart, result in zip(charts, chart_results) if not result.get("excluded_from_chart_score")]

    inventory_score = score_inventory(scorable_charts, expected)
    spec_score = mean([r["subscores"]["spec_completeness"] for r in scorable_results], default=0.55 if not expected else 0.25)
    data_score = mean([r["subscores"]["data_faithfulness"] for r in scorable_results], default=0.65 if not expected else 0.35)
    align_score = mean([r["subscores"]["chart_text_alignment"] for r in scorable_results], default=0.60 if not expected else 0.35)
    clarity_score = mean([r["subscores"]["visual_clarity"] for r in scorable_results], default=0.70 if not expected else 0.35)
    finance_score = mean([r["subscores"]["financial_appropriateness"] for r in scorable_results], default=0.65 if not expected else 0.35)
    subscores = {
        "inventory": round(inventory_score, 3),
        "spec_completeness": round(spec_score, 3),
        "data_faithfulness": round(data_score, 3),
        "chart_text_alignment": round(align_score, 3),
        "visual_clarity": round(clarity_score, 3),
        "financial_appropriateness": round(finance_score, 3),
    }
    dimension_score = sum(subscores[key] * weight for key, weight in CHART_WEIGHTS.items())
    chart_scores = [float(result.get("score") or 0.0) for result in scorable_results]
    mean_chart_score = mean(chart_scores, default=dimension_score)
    worst_k_count = min(
        max(1, int(config.get("aggregation_worst_k") or 2)),
        len(chart_scores),
    ) if chart_scores else 0
    worst_k_scores = sorted(chart_scores)[:worst_k_count] if worst_k_count else []
    worst_k_score = mean(worst_k_scores, default=mean_chart_score)
    mean_weight = clamp(float(config.get("aggregation_mean_weight", 0.70)))
    robust_chart_score = mean_weight * mean_chart_score + (1.0 - mean_weight) * worst_k_score

    full_judged_count = len([result for result in chart_results if result.get("vl_qa_level") == "full_checklist"])
    gate_only_count = len([result for result in chart_results if result.get("vl_qa_level") == "gate_only"])
    checked_count = full_judged_count + gate_only_count
    scorable_count = len(scorable_results)
    full_coverage = full_judged_count / scorable_count if scorable_count else 1.0
    gate_coverage = checked_count / len(chart_results) if chart_results else 1.0
    max_uncertainty_penalty = clamp(float(config.get("max_uncertainty_penalty", 0.08)))
    uncertainty_penalty = max_uncertainty_penalty * (1.0 - full_coverage) * (1.0 - 0.70 * gate_coverage)
    dimension_weight = clamp(float(config.get("aggregation_dimension_weight", 0.65)))
    score = dimension_weight * dimension_score + (1.0 - dimension_weight) * robust_chart_score
    score = max(0.0, score - uncertainty_penalty)

    blocker_types = {
        "text_contradiction",
        "incomplete_crop",
        "unreadable",
        "misleading_scale",
        "wrong_chart_type",
    }
    blocker_chart_ids = []
    for result in scorable_results:
        vl = result.get("vl_judge") or {}
        high_flags = [
            flag for flag in vl.get("hard_flags") or []
            if flag.get("severity") == "high" and flag.get("flag_type") in blocker_types
        ]
        if high_flags:
            blocker_chart_ids.append(result.get("chart_id"))
    blocker_cap = clamp(float(config.get("blocker_score_cap", 0.55)))
    if blocker_chart_ids:
        score = min(score, blocker_cap)
    issues: list[dict[str, Any]] = []
    for result in chart_results:
        issues.extend(result.get("issues") or [])
    if expected and inventory_score < 0.5:
        issues.append(issue("missing_chart", "high", "chart_inventory", "Expected benchmark charts are not sufficiently represented."))
    if data_score < 0.5:
        issues.append(issue("chart_data_error", "high", "charts", "Chart data faithfulness is below the hard threshold."))
    if align_score < 0.5:
        issues.append(issue("chart_text_misalignment", "high", "charts", "Chart-text alignment is below the hard threshold."))
    if full_coverage < float(config.get("full_coverage_warning_threshold", 0.25)) and scorable_count:
        issues.append(issue("chart_qa_coverage_low", "medium", "charts", "Too few scorable charts received the full VLM checklist."))
    if blocker_chart_ids:
        issues.append(issue("chart_blocker_present", "high", "charts", "At least one chart has a severe visual or chart-text QA flag.", evidence=", ".join(str(item) for item in blocker_chart_ids)))
    visual_coverage = visual_coverage_status(inventory, chart_results, checked_count, full_judged_count)
    if visual_coverage.get("status") == "visuals_found_none_scorable":
        issues.append(issue("visuals_found_none_scorable", "medium", "visual_inventory", "HTML adapter found visual objects, but none were accepted as scorable analytical charts."))
    if visual_coverage.get("status") == "no_scorable_visuals_after_vlm_gate":
        issues.append(issue("no_scorable_visuals_after_vlm_gate", "medium", "visual_inventory", "VLM fallback checked filtered visual objects, but did not promote any analytical chart/table candidates."))
    return {
        "score": round(score, 3),
        "subscores": subscores,
        "issues": issues,
        "metrics": {
            "chart_count": len(charts),
            "scorable_chart_count": len(scorable_results),
            "non_visual_skipped_count": len(chart_results) - len(scorable_results),
            "expected_chart_count": len(expected),
            "hard_threshold_passed": data_score >= 0.5 and align_score >= 0.5,
            "vl_judged_chart_count": checked_count,
            "vl_full_checklist_count": full_judged_count,
            "vl_gate_only_count": gate_only_count,
            "vl_gate_coverage": round(gate_coverage, 3),
            "vl_full_coverage": round(full_coverage, 3),
            "mean_chart_score": round(mean_chart_score, 3),
            "worst_k_count": worst_k_count,
            "worst_k_score": round(worst_k_score, 3),
            "robust_chart_score": round(robust_chart_score, 3),
            "dimension_score_before_robust_aggregation": round(dimension_score, 3),
            "uncertainty_penalty": round(uncertainty_penalty, 3),
            "blocker_chart_count": len(blocker_chart_ids),
            "blocker_chart_ids": blocker_chart_ids,
            "visual_coverage_status": visual_coverage.get("status"),
            "visual_object_count": visual_coverage.get("visual_object_count"),
            "visual_filter_drop_count": visual_coverage.get("visual_filter_drop_count"),
            "visual_filter_drop_reasons": visual_coverage.get("visual_filter_drop_reasons"),
            "visual_gate_fallback_candidate_count": visual_coverage.get("visual_gate_fallback_candidate_count"),
            "vlm_zero_chart_fallback_checked_count": visual_coverage.get("vlm_zero_chart_fallback_checked_count"),
            "vlm_zero_chart_fallback_promoted_count": visual_coverage.get("vlm_zero_chart_fallback_promoted_count"),
        },
        "charts": chart_results,
    }


def visual_coverage_status(
    inventory: dict[str, Any],
    chart_results: list[dict[str, Any]],
    checked_count: int,
    full_judged_count: int,
) -> dict[str, Any]:
    audit = inventory.get("audit") or {}
    raw_visual_count = int(audit.get("raw_visual_count") or audit.get("visual_count") or 0)
    chart_count = len(chart_results)
    scorable_count = len([result for result in chart_results if not result.get("excluded_from_chart_score")])
    fallback_checked = int(audit.get("vlm_zero_chart_fallback_checked_count") or 0)
    fallback_promoted = int(audit.get("vlm_zero_chart_fallback_promoted_count") or 0)
    if raw_visual_count <= 0:
        status = "no_visuals_found"
    elif chart_count <= 0 and fallback_checked > 0:
        status = "no_scorable_visuals_after_vlm_gate"
    elif chart_count <= 0:
        status = "visuals_found_none_scorable"
    elif fallback_promoted > 0:
        status = "scorable_visuals_found_by_vlm_fallback"
    elif checked_count <= 0:
        status = "scorable_visuals_found"
    elif full_judged_count >= max(1, scorable_count):
        status = "vlm_fully_judged"
    else:
        status = "vlm_partially_judged"
    return {
        "status": status,
        "visual_object_count": raw_visual_count,
        "visual_filter_drop_count": int(audit.get("visual_filter_drop_count") or max(0, raw_visual_count - chart_count)),
        "visual_filter_drop_reasons": audit.get("visual_filter_drop_reasons") or {},
        "visual_gate_fallback_candidate_count": int(audit.get("visual_gate_fallback_candidate_count") or 0),
        "vlm_zero_chart_fallback_checked_count": fallback_checked,
        "vlm_zero_chart_fallback_promoted_count": fallback_promoted,
    }


def score_inventory(charts: list[dict[str, Any]], expected: list[dict[str, Any]]) -> float:
    if not expected:
        return 1.0 if charts else 0.65
    if not charts:
        return 0.0
    matches = 0
    for item in expected:
        desc = item.get("title_or_description") or ""
        if any(chart.get("expected_match") == desc or contains_fuzzy(desc, chart_blob(chart), 0.40) for chart in charts):
            matches += 1
    return clamp(0.35 + 0.65 * (matches / len(expected)))


def vl_marks_nonvisual(vl: dict[str, Any]) -> bool:
    gate = vl.get("visual_gate") or {}
    if gate.get("decision") == "skip_checklist":
        return True
    if gate.get("is_visualization") is False:
        return True
    if vl.get("is_analytical_visual") is False and not (vl.get("universal_checklist") or vl.get("contextual_checklist")):
        return True
    return False


def visual_gate_reason(vl: dict[str, Any]) -> str:
    gate = vl.get("visual_gate") or {}
    reason = gate.get("reason") or vl.get("review_notes")
    if reason:
        return f"VLM visual gate skipped this candidate: {reason}"
    return "VLM visual gate skipped this candidate as a non-analytical visualization."


def build_chart_result(
    chart: dict[str, Any],
    title: str,
    nearby: str,
    page_text: str,
    source: str,
    unit: str,
    numbers: list[str],
    vl: dict[str, Any] | None,
    vl_judged: bool,
    vl_qa_level: str,
    subscores: dict[str, float],
    overall: float,
    issues: list[dict[str, Any]],
    excluded_from_chart_score: bool = False,
    skip_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "chart_id": chart.get("chart_id"),
        "page_chart_id": chart.get("page_chart_id"),
        "page": chart.get("page"),
        "bbox": chart.get("bbox"),
        "page_bbox": chart.get("page_bbox"),
        "title": title,
        "chart_kind_hint": chart.get("chart_kind_hint"),
        "source_format": chart.get("source_format"),
        "detection_method": chart.get("detection_method"),
        "object_index": chart.get("object_index"),
        "object_count_on_page": chart.get("object_count_on_page"),
        "object_role": chart.get("object_role"),
        "image_path": chart.get("image_path"),
        "page_image_path": chart.get("page_image_path"),
        "html_snippet": chart.get("html_snippet"),
        "nearby_text": nearby,
        "page_text": page_text,
        "page_text_blocks": chart.get("page_text_blocks") or [],
        "crop_quality": chart.get("crop_quality") or {},
        "warnings": chart.get("warnings") or [],
        "source_note": source,
        "unit_hint": unit,
        "numbers": numbers[:40],
        "dates": (chart.get("dates") or [])[:20],
        "expected_match": chart.get("expected_match"),
        "vl_judged": vl_judged,
        "vl_qa_level": vl_qa_level,
        "vl_judge": vl,
        "score": round(overall, 3),
        "subscores": subscores,
        "issues": issues,
        "excluded_from_chart_score": excluded_from_chart_score,
        "skip_reason": skip_reason,
    }


def score_chart(chart: dict[str, Any], expected: list[dict[str, Any]], parsed: dict[str, Any], vl: dict[str, Any] | None = None) -> dict[str, Any]:
    title = chart.get("title") or chart.get("caption") or ""
    nearby = chart.get("nearby_text") or ""
    page_text = chart.get("page_text") or nearby
    source = chart.get("source_note") or ""
    unit = chart.get("unit_hint") or ""
    numbers = chart.get("numbers") or []
    issues: list[dict[str, Any]] = []
    decorative = is_decorative_chart_candidate(chart)
    if not vl and is_high_confidence_nonanalytical_html_image(chart, decorative):
        reason = "Rule-only visual gate excluded a high-confidence decorative HTML image."
        issues.append(
            issue(
                "chart_extractor_false_positive",
                "low",
                chart.get("chart_id", "chart"),
                reason,
            )
        )
        return build_chart_result(
            chart=chart,
            title=title,
            nearby=nearby,
            page_text=page_text,
            source=source,
            unit=unit,
            numbers=numbers,
            vl=None,
            vl_judged=False,
            vl_qa_level="rule_only_visual_gate",
            subscores={
                "spec_completeness": 0.0,
                "data_faithfulness": 0.0,
                "chart_text_alignment": 0.0,
                "visual_clarity": 0.0,
                "financial_appropriateness": 0.0,
            },
            overall=0.0,
            issues=issues,
            excluded_from_chart_score=True,
            skip_reason=reason,
        )

    spec_parts = [
        1.0 if title else 0.0,
        1.0 if unit else 0.35 if numbers else 0.0,
        1.0 if source else 0.0,
        1.0 if chart.get("dates") else 0.55,
    ]
    spec = mean(spec_parts)
    if spec < 0.55:
        issues.append(issue("label_unit_error", "medium", chart.get("chart_id", "chart"), "Chart title, unit, date, or source metadata is incomplete."))

    data_rule = 0.30 if decorative else 0.45
    if numbers:
        data_rule += 0.12 if len(numbers) < 3 else 0.22
    if unit:
        data_rule += 0.10
    if chart.get("expected_match"):
        data_rule += 0.10
    if source:
        data_rule += 0.05
    data = clamp(data_rule)

    alignment = score_alignment_rule(chart, parsed)
    clarity = score_visual_clarity_rule(chart)
    finance = score_financial_appropriateness_rule(chart, expected)
    if decorative:
        alignment = min(alignment, 0.45)
        finance = min(finance, 0.35)
        issues.append(issue("decorative_chart", "medium", chart.get("chart_id", "chart"), "Visual candidate looks decorative or non-analytical rather than a financial chart/table."))
    vl_judged = False
    vl_qa_level = "rule_only"
    if vl and vl.get("ok"):
        vl_judged = True
        vl_qa_level = str(vl.get("qa_level") or "full_checklist")
        if vl_marks_nonvisual(vl):
            issues.append(
                issue(
                    "chart_extractor_false_positive",
                    "low",
                    chart.get("chart_id", "chart"),
                    visual_gate_reason(vl),
                )
            )
            return build_chart_result(
                chart=chart,
                title=title,
                nearby=nearby,
                page_text=page_text,
                source=source,
                unit=unit,
                numbers=numbers,
                vl=vl,
                vl_judged=vl_judged,
                vl_qa_level=vl_qa_level,
                subscores={
                    "spec_completeness": 0.0,
                    "data_faithfulness": 0.0,
                    "chart_text_alignment": 0.0,
                    "visual_clarity": 0.0,
                    "financial_appropriateness": 0.0,
                },
                overall=0.0,
                issues=issues,
                excluded_from_chart_score=True,
                skip_reason=visual_gate_reason(vl),
            )
        if vl_qa_level == "gate_only":
            return build_chart_result(
                chart,
                title,
                nearby,
                page_text,
                source,
                unit,
                numbers,
                vl,
                vl_judged,
                vl_qa_level,
                {
                    "spec_completeness": round(spec, 3),
                    "data_faithfulness": round(data, 3),
                    "chart_text_alignment": round(alignment, 3),
                    "visual_clarity": round(clarity, 3),
                    "financial_appropriateness": round(finance, 3),
                },
                0.18 * spec + 0.28 * data + 0.24 * alignment + 0.18 * clarity + 0.12 * finance,
                issues,
            )
        vl_subscores = vl.get("subscores") or {}
        checklist_scores = checklist_component_scores(vl)
        vl_metadata = num(vl_subscores.get("metadata_completeness_visual"), checklist_scores.get("metadata_completeness_visual", spec))
        vl_data = num(vl.get("data_faithfulness_score"), data)
        vl_alignment = num(vl_subscores.get("chart_text_alignment"), num(vl.get("chart_text_alignment_score"), alignment))
        vl_claim = num(vl_subscores.get("claim_support"), vl_alignment)
        vl_clarity = mean(
            [
                num(vl_subscores.get("crop_completeness"), checklist_scores.get("crop_completeness", clarity)),
                num(vl_subscores.get("readability"), num(vl.get("visual_clarity_score"), clarity)),
                num(vl_subscores.get("visual_professionalism"), clarity),
            ],
            default=clarity,
        )
        vl_finance = mean(
            [
                num(vl_subscores.get("chart_type_suitability"), finance),
                num(vl_subscores.get("decision_usefulness"), finance),
                num(vl.get("financial_appropriateness_score"), finance),
            ],
            default=finance,
        )
        spec = blend(spec, vl_metadata, 0.35)
        data = blend(data, vl_data, 0.30)
        alignment = blend(alignment, mean([vl_alignment, vl_claim], default=alignment), 0.50)
        clarity = blend(clarity, vl_clarity, 0.50)
        finance = blend(finance, vl_finance, 0.45)
        for flag in vl.get("hard_flags") or []:
            severity = flag.get("severity") or "medium"
            issues.append(
                issue(
                    flag.get("flag_type") or "chart_vl_flag",
                    severity,
                    chart.get("chart_id", "chart"),
                    flag.get("evidence") or "VLM checklist raised a hard flag.",
                )
            )
        for item in vl.get("issues") or []:
            issues.append(item)
        data, alignment, clarity, finance = apply_vl_caps(vl, data, alignment, clarity, finance)

    if data < 0.5:
        issues.append(issue("chart_data_error", "high", chart.get("chart_id", "chart"), "Chart data signals are too weak or potentially inconsistent."))
    if alignment < 0.5:
        issues.append(issue("chart_text_misalignment", "high", chart.get("chart_id", "chart"), "Full page text does not clearly explain the current visualization."))
    if clarity < 0.5:
        issues.append(issue("visual_readability_issue", "medium", chart.get("chart_id", "chart"), "Chart crop or visual rendering may not be readable."))
    subscores = {
        "spec_completeness": round(spec, 3),
        "data_faithfulness": round(data, 3),
        "chart_text_alignment": round(alignment, 3),
        "visual_clarity": round(clarity, 3),
        "financial_appropriateness": round(finance, 3),
    }
    overall = (
        0.18 * spec
        + 0.28 * data
        + 0.24 * alignment
        + 0.18 * clarity
        + 0.12 * finance
    )
    return build_chart_result(chart, title, nearby, page_text, source, unit, numbers, vl, vl_judged, vl_qa_level, subscores, overall, issues)


def score_alignment_rule(chart: dict[str, Any], parsed: dict[str, Any]) -> float:
    page_text = normalize_text(chart.get("page_text") or chart.get("nearby_text") or "")
    title = normalize_text(chart.get("title") or "")
    report_text = normalize_text(parsed.get("text") or "")
    explanation_terms = ["shows", "indicates", "suggests", "driven", "trend", "increase", "decline", "显示", "表明", "趋势", "上升", "下降", "反映"]
    page_explain = any(term in page_text for term in explanation_terms)
    page_title_ref = bool(title and title[:40] in page_text)
    global_ref = bool(title and title[:40] in report_text)
    number_ref = bool(set(chart.get("numbers") or []) & set(parsed.get("numbers") or []))
    return clamp(0.35 + 0.30 * page_explain + 0.15 * page_title_ref + 0.10 * global_ref + 0.10 * number_ref)


def score_visual_clarity_rule(chart: dict[str, Any]) -> float:
    image_path = chart.get("image_path")
    if not image_path:
        return 0.65 if chart.get("html_snippet") else 0.45
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            width, height = image.size
    except Exception:
        return 0.35
    area = width * height
    aspect = width / max(1, height)
    score = 0.45
    if area >= 120_000:
        score += 0.25
    if 0.45 <= aspect <= 3.8:
        score += 0.15
    if chart.get("title") or chart.get("nearby_text"):
        score += 0.15
    return clamp(score)


def score_financial_appropriateness_rule(chart: dict[str, Any], expected: list[dict[str, Any]]) -> float:
    blob = chart_blob(chart)
    finance_terms = [
        "rate",
        "yield",
        "gdp",
        "inflation",
        "earnings",
        "valuation",
        "allocation",
        "portfolio",
        "growth",
        "risk",
        "利率",
        "收益率",
        "通胀",
        "估值",
        "配置",
        "增长",
        "风险",
    ]
    score = 0.55 + 0.25 * any(term in blob for term in finance_terms)
    if expected and chart.get("expected_match"):
        score += 0.20
    return clamp(score)


def checklist_component_scores(vl: dict[str, Any]) -> dict[str, float]:
    items = (vl.get("universal_checklist") or []) + (vl.get("contextual_checklist") or [])
    by_id = {str(item.get("id")): num(item.get("score"), 0.0) for item in items if item.get("status") != "not_applicable"}
    groups = {
        "crop_completeness": ["U2"],
        "metadata_completeness_visual": ["U3", "U4", "U5"],
        "readability": ["U6"],
        "chart_type_suitability": ["U7"],
        "chart_text_alignment": ["U9"],
        "claim_support": ["U10"],
        "visual_professionalism": ["U8", "U11"],
        "decision_usefulness": ["U1", "U12"],
    }
    scores: dict[str, float] = {}
    for key, ids in groups.items():
        values = [by_id[item_id] for item_id in ids if item_id in by_id]
        if values:
            scores[key] = mean(values)
    contextual_values = [
        num(item.get("score"), 0.0)
        for item in vl.get("contextual_checklist") or []
        if item.get("status") != "not_applicable"
    ]
    if contextual_values:
        scores["contextual_mean"] = mean(contextual_values)
    return scores


def apply_vl_caps(vl: dict[str, Any], data: float, alignment: float, clarity: float, finance: float) -> tuple[float, float, float, float]:
    cap = 1.0
    for flag in vl.get("hard_flags") or []:
        if flag.get("severity") != "high":
            continue
        flag_type = flag.get("flag_type")
        if flag_type == "text_contradiction":
            cap = min(cap, 0.45)
        elif flag_type == "decorative_visual":
            cap = min(cap, 0.40)
        elif flag_type == "incomplete_crop":
            cap = min(cap, 0.50)
        elif flag_type == "unreadable":
            cap = min(cap, 0.55)
        elif flag_type in {"missing_critical_unit", "missing_critical_source", "misleading_scale", "wrong_chart_type"}:
            cap = min(cap, 0.70)
    if cap < 1.0:
        data = min(data, cap)
        alignment = min(alignment, cap)
        clarity = min(clarity, cap)
        finance = min(finance, cap)
    return data, alignment, clarity, finance


def is_decorative_chart_candidate(chart: dict[str, Any]) -> bool:
    blob = chart_blob(chart)
    numbers = chart.get("numbers") or []
    has_source = bool(chart.get("source_note"))
    has_unit = bool(chart.get("unit_hint"))
    chart_words = ["figure", "chart", "table", "exhibit", "source", "图", "表", "资料来源", "数据来源"]
    analytical_words = ["rate", "yield", "gdp", "inflation", "debt", "allocation", "portfolio", "risk", "market", "利率", "收益率", "通胀", "债", "配置", "风险"]
    has_chart_signal = any(word in blob for word in chart_words)
    has_analytical_signal = any(word in blob for word in analytical_words)
    if chart.get("detection_method") == "image_region" and not has_source and not has_unit and len(numbers) < 3:
        return True
    if not has_chart_signal and not has_analytical_signal and len(numbers) < 4:
        return True
    return False


def is_high_confidence_nonanalytical_html_image(chart: dict[str, Any], decorative: bool) -> bool:
    if chart.get("source_format") != "html_runtime":
        return False
    if str(chart.get("object_role") or "").lower() != "img":
        return False
    if chart.get("source_note") or chart.get("unit_hint") or chart.get("numbers"):
        return False
    blob = chart_blob(chart)
    analytical_terms = [
        "figure",
        "chart",
        "table",
        "exhibit",
        "source:",
        "data",
        "图",
        "表",
        "数据",
        "来源",
    ]
    return not any(term in blob for term in analytical_terms)


def chart_blob(chart: dict[str, Any]) -> str:
    return normalize_text(" ".join(str(chart.get(key) or "") for key in ["title", "caption", "nearby_text", "source_note", "chart_kind_hint"]))


def blend(rule_score: float, judge_score: float, rule_weight: float) -> float:
    return clamp(rule_weight * rule_score + (1 - rule_weight) * judge_score)


def num(value: Any, default: float) -> float:
    try:
        return clamp(float(value))
    except Exception:
        return default
