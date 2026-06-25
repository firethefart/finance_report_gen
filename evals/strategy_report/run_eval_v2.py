from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

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
    analysis_text, boundary = extract_html_analysis_text(full_text)
    headings = [item.get("text") if isinstance(item, dict) else str(item) for item in text_payload.get("headings") or []]
    headings = [h for h in headings if h]
    headings = [heading for heading in headings if normalize_heading(heading) in normalize_heading(analysis_text)]
    synthetic_headings = extract_numbered_section_headings(analysis_text) if len(headings) < 5 else []
    headings = headings + [heading for heading in synthetic_headings if heading not in headings]
    links = text_payload.get("links") or []
    sections = sectionize_from_headings(analysis_text, headings)
    visuals = visual_objects.get("visual_objects") or []
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
        "headings": headings,
        "sections": sections,
        "links": links,
        "numbers": extract_numbers(analysis_text),
        "dates": extract_dates(analysis_text),
        "table_figure_hint_count": len(visuals),
        "source_hint_count": len(re.findall(r"source|sources|来源|资料来源|数据来源", analysis_text, flags=re.IGNORECASE)),
        "disclaimer_hint_count": len(re.findall(r"disclaimer|disclosures|risk considerations|risk disclosure|important information|免责声明|风险提示", full_text, flags=re.IGNORECASE)),
        "parse_quality": "good" if len(analysis_text) >= 2500 else "fair",
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


def extract_html_analysis_text(full_text: str) -> tuple[str, dict[str, Any]]:
    text = re.sub(r"\s+", " ", full_text or "").strip()
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
    for index, visual in enumerate(visual_payload.get("visual_objects") or [], start=1):
        nearby = visual.get("nearby_text") or ""
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
        "skipped_visuals": visual_payload.get("skipped_visuals") or [],
        "audit": {
            "visual_count": len(charts),
            "skipped_visual_count": visual_payload.get("skipped_visual_count") or 0,
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
