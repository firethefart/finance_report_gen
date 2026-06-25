from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

from eval_utils import ROOT


TOOLS_DIR = ROOT / "dataset_tools" / "strategy_reports"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from llm_clients import OpenRouterClient  # noqa: E402
from verifier_config import make_verifier_client  # noqa: E402


DEFAULT_VL_MODEL = "qwen/qwen3-vl-235b-a22b-instruct"
JUDGE_CACHE_VERSION = "visual_gate_v1"
GATE_CACHE_VERSION = "visual_gate_only_v2"


SYSTEM = """You are a financial chart QA evaluator.
Inspect the target chart crop, the full-page screenshot, and the nearby/full-page report text. Return strict JSON only.
Scores are continuous from 0 to 1. Penalize unreadable charts, missing units/sources, unsupported takeaways, and chart-text contradictions."""


UNIVERSAL_CHECKLIST = [
    ("U1", "Analytical purpose", "The visual answers a clear research question and is not decoration."),
    ("U2", "Crop/render completeness", "The target screenshot contains the full intended chart/table, not only a legend, footnote, sidebar, or cropped fragment."),
    ("U3", "Title and analytical framing", "The title/caption states what the chart is about, not just a generic label."),
    ("U4", "Unit, scale, and time window", "Units, percentages/bps/currency, axis scale, period, and date range are visible or stated nearby."),
    ("U5", "Source and methodology note", "Data source and important footnotes are visible or available in surrounding text."),
    ("U6", "Readability", "Axis labels, legends, series names, table headers, and key labels are readable at dashboard resolution."),
    ("U7", "Chart type suitability", "Chart form matches the analytical task: trend, comparison, distribution, allocation, scenario, correlation, or table lookup."),
    ("U8", "Visual professionalism", "Styling is restrained, non-cluttered, non-misleading, and suitable for institutional research."),
    ("U9", "Text binding", "Full-page text includes at least one relevant explanation of the current visual."),
    ("U10", "Claim support", "The matched text is supported by the visual and does not contradict it."),
    ("U11", "Risk of visual misdirection", "Scale, axis truncation, color emphasis, ordering, or missing baseline does not mislead the reader."),
    ("U12", "Decision usefulness", "The visual contributes to a strategic investment/research conclusion rather than restating obvious facts."),
]


def run_chart_vl_judges(
    charts: list[dict[str, Any]],
    parsed: dict[str, Any],
    api_key_file: Path,
    out_dir: Path,
    model: str = DEFAULT_VL_MODEL,
    max_charts: int = 3,
    max_tokens: int = 4200,
    repair_max_tokens: int = 2600,
    selection_strategy: str = "first_n",
    gate_all: bool = False,
    gate_max_charts: int = 16,
    gate_max_tokens: int = 900,
) -> dict[str, Any]:
    client = make_verifier_client("vlm", api_key_file, out_dir / "chart_vl_logs")
    cache_dir = out_dir / "chart_vl_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {}
    selected = select_chart_vl_candidates(charts, max_charts=max_charts, strategy=selection_strategy)
    selected_ids = {str(chart.get("chart_id")) for chart in selected}
    gate_selected = select_gate_candidates(charts, max_charts=gate_max_charts) if gate_all else []
    for chart in gate_selected:
        chart_id = str(chart.get("chart_id"))
        if chart_id in selected_ids:
            continue
        image_path = chart.get("image_path")
        if not image_path or not Path(image_path).exists():
            continue
        cache_path = cache_dir / f"{safe_name(chart_id)}.{GATE_CACHE_VERSION}.json"
        if cache_path.exists():
            result = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            result = judge_visual_gate_only(client, model, chart, max_tokens=gate_max_tokens)
            cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        results[chart_id] = result
    for chart in selected:
        image_path = chart.get("image_path")
        if not image_path or not Path(image_path).exists():
            continue
        cache_path = cache_dir / f"{safe_name(chart['chart_id'])}.{JUDGE_CACHE_VERSION}.json"
        if cache_path.exists():
            result = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            result = judge_one_chart(client, model, chart, parsed, max_tokens=max_tokens, repair_max_tokens=repair_max_tokens)
            cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        results[chart["chart_id"]] = result
    results["_selection_audit"] = {
        "strategy": selection_strategy,
        "max_charts": max_charts,
        "input_chart_count": len(charts),
        "gate_all": gate_all,
        "gate_max_charts": gate_max_charts,
        "gate_selected_chart_ids": [chart.get("chart_id") for chart in gate_selected],
        "selected_chart_ids": [chart.get("chart_id") for chart in selected],
        "selected_pages": [chart.get("page") for chart in selected],
        "selected_reasons": {chart.get("chart_id"): chart.get("_vl_selection_reason") for chart in selected},
    }
    return results


def select_gate_candidates(charts: list[dict[str, Any]], max_charts: int) -> list[dict[str, Any]]:
    available = [chart for chart in charts if chart.get("image_path") and Path(chart.get("image_path")).exists()]
    if max_charts <= 0:
        return []
    return available[:max_charts]


def judge_visual_gate_only(
    client: OpenRouterClient,
    model: str,
    chart: dict[str, Any],
    max_tokens: int = 900,
) -> dict[str, Any]:
    prompt = (
        "Decide whether TARGET_SCREENSHOT is a genuine analytical financial visualization.\n"
        "Valid: chart, analytical table, diagram, infographic, or metric panel.\n"
        "Invalid: cover, table of contents, paragraph text, disclaimer, logo, footer, sidebar, or cropped fragment without an interpretable visualization.\n"
        "Return strict compact JSON only with this schema:\n"
        '{"visual_gate":{"is_visualization":true,"visualization_kind":"chart|table|diagram|infographic|metric_panel|not_visualization",'
        '"decision":"continue|skip_checklist","reason":"short","confidence":0.0},'
        '"crop_risk":"none|low|medium|high","review_priority":"low|medium|high"}'
    )
    target_path = Path(chart["image_path"])
    result = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": "You are a fast visual gate for financial-report chart QA. Return strict JSON only."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(target_path)}},
                ],
            },
        ],
        max_tokens=max_tokens,
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"chart_id": chart.get("chart_id"), "judge": "chart_visual_gate_only"},
    )
    if not result.get("ok") or not isinstance(result.get("json"), dict):
        return {"ok": False, "qa_level": "gate_only", "error": result.get("error") or "chart_visual_gate_failed", "raw": result}
    data = result["json"]
    data["ok"] = True
    data["qa_level"] = "gate_only"
    data["model"] = model
    data["usage"] = result.get("usage")
    data["elapsed_seconds"] = result.get("elapsed_seconds")
    return data


def select_chart_vl_candidates(charts: list[dict[str, Any]], max_charts: int, strategy: str = "first_n") -> list[dict[str, Any]]:
    if max_charts <= 0:
        return []
    available = [chart for chart in charts if chart.get("image_path") and Path(chart.get("image_path")).exists()]
    if strategy in {"first_n", "first", "legacy"}:
        selected = available[:max_charts]
        return [with_selection_reason(chart, "legacy_first_n") for chart in selected]
    ranked = sorted(available, key=chart_vl_priority_score, reverse=True)
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    selected_pages: set[str] = set()

    def add(chart: dict[str, Any], reason: str) -> None:
        chart_id = str(chart.get("chart_id"))
        if chart_id in selected_ids or len(selected) >= max_charts:
            return
        selected.append(with_selection_reason(chart, reason))
        selected_ids.add(chart_id)
        selected_pages.add(str(chart.get("page")))

    # First pass: maximize page diversity among the riskiest candidates.
    for chart in ranked:
        if str(chart.get("page")) not in selected_pages:
            add(chart, "risk_rank_page_diversity")
        if len(selected) >= max_charts:
            break
    # Second pass: fill with remaining high-risk candidates.
    for chart in ranked:
        add(chart, "risk_rank_fill")
        if len(selected) >= max_charts:
            break
    return selected


def with_selection_reason(chart: dict[str, Any], reason: str) -> dict[str, Any]:
    copied = dict(chart)
    copied["_vl_selection_reason"] = reason
    copied["_vl_priority_score"] = round(chart_vl_priority_score(chart), 3)
    return copied


def chart_vl_priority_score(chart: dict[str, Any]) -> float:
    score = 0.0
    if likely_nonvisual_page_artifact(chart):
        score -= 3.0
    if not (chart.get("title") or chart.get("caption")):
        score += 1.2
    if not chart.get("source_note"):
        score += 1.0
    if not chart.get("unit_hint") and chart.get("numbers"):
        score += 0.9
    if not chart.get("dates"):
        score += 0.45
    if chart.get("warnings"):
        score += 0.7 + 0.1 * min(5, len(chart.get("warnings") or []))
    crop = chart.get("crop_quality") or {}
    if crop.get("oversized_visual") or crop.get("narrow_crop") or crop.get("low_confidence"):
        score += 1.2
    method = str(chart.get("detection_method") or "").lower()
    if any(term in method for term in ["fallback", "page_body", "merged", "broad"]):
        score += 0.8
    role = str(chart.get("object_role") or "").lower()
    if any(term in role for term in ["page", "body", "visual"]):
        score += 0.25
    try:
        object_count = int(chart.get("object_count_on_page") or 0)
    except Exception:
        object_count = 0
    if object_count >= 2:
        score += 0.35
    nearby = str(chart.get("nearby_text") or "")
    if len(nearby) < 80:
        score += 0.45
    if chart.get("expected_match"):
        score += 0.35
    page = chart.get("page")
    if page in {0, 1, "0", "1"}:
        score -= 0.15
    return score


def likely_nonvisual_page_artifact(chart: dict[str, Any]) -> bool:
    title = str(chart.get("title") or chart.get("caption") or "").strip().lower()
    nearby_head = str(chart.get("nearby_text") or "").strip().lower()[:240]
    role_blob = " ".join(str(chart.get(key) or "") for key in ["object_role", "chart_kind_hint"]).lower()
    strong_terms = [
        "table of contents",
        "contents",
        "图表目录",
        "目录",
    ]
    if any(term in title for term in strong_terms) or any(term in nearby_head for term in ["table of contents", "图表目录"]):
        return True
    legal_terms = ["disclaimer", "important information", "risk disclosure", "免责声明", "重要声明", "风险提示", "法律声明"]
    if any(term in title for term in legal_terms) or any(term in role_blob for term in ["footer", "sidebar", "legal"]):
        return True
    if str(chart.get("page")) in {"0", "1"} and any(term in title for term in ["证券研究报告", "research report", "strategy research"]):
        if not any(term in title for term in ["图", "figure", "chart", "table"]):
            return True
    return title in {"cover", "toc", "contents", "目录", "图表目录"}


def judge_one_chart(client: OpenRouterClient, model: str, chart: dict[str, Any], parsed: dict[str, Any], max_tokens: int = 4200, repair_max_tokens: int = 2600) -> dict[str, Any]:
    prompt = build_prompt(chart, parsed)
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    target_path = Path(chart["image_path"])
    content.append({"type": "text", "text": "TARGET_VISUAL_SCREENSHOT: evaluate this visualization as the primary object."})
    content.append({"type": "image_url", "image_url": {"url": image_to_data_url(target_path)}})
    page_image_path = chart.get("page_image_path")
    if page_image_path and Path(page_image_path).exists() and Path(page_image_path).resolve() != target_path.resolve():
        content.append({"type": "text", "text": "FULL_PAGE_SCREENSHOT: use this for page layout and surrounding context."})
        content.append({"type": "image_url", "image_url": {"url": image_to_data_url(Path(page_image_path))}})
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": content},
    ]
    result = client.chat(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"chart_id": chart.get("chart_id"), "judge": "chart_vl_qa"},
    )
    if result.get("ok") and not isinstance(result.get("json"), dict) and result.get("content"):
        result = repair_chart_json(client, model, chart.get("chart_id"), result.get("content") or "", max_tokens=repair_max_tokens)
    if not result.get("ok") or not isinstance(result.get("json"), dict):
        return {"ok": False, "error": result.get("error") or "chart_vl_judge_failed", "raw": result}
    data = result["json"]
    data["ok"] = True
    data["qa_level"] = "full_checklist"
    data["model"] = model
    data["usage"] = result.get("usage")
    data["raw_response_content"] = result.get("content")
    data["http_status"] = result.get("http_status")
    data["elapsed_seconds"] = result.get("elapsed_seconds")
    return data


def repair_chart_json(client: OpenRouterClient, model: str, chart_id: str | None, malformed: str, max_tokens: int = 2600) -> dict[str, Any]:
    schema = {
        "ok": True,
        "chart_id": chart_id or "chart_id",
        "visual_gate": {"is_visualization": True, "visualization_kind": "chart|table|diagram|not_visualization", "decision": "continue|skip_checklist", "reason": "short", "confidence": 0.0},
        "chart_type": "line|bar|table|mixed|unknown",
        "is_analytical_visual": True,
        "visible_metadata": {"title": {"value": "", "confidence": 0.0}, "unit": {"value": "", "confidence": 0.0}, "time_window": {"value": "", "confidence": 0.0}, "source": {"value": "", "confidence": 0.0}},
        "key_values": [],
        "matched_text_spans": [],
        "universal_checklist": [],
        "contextual_checklist": [],
        "subscores": {"crop_completeness": 0.0, "metadata_completeness_visual": 0.0, "readability": 0.0, "chart_type_suitability": 0.0, "chart_text_alignment": 0.0, "claim_support": 0.0, "visual_professionalism": 0.0, "decision_usefulness": 0.0},
        "hard_flags": [],
        "overall_vlm_visual_score": 0.0,
        "confidence": 0.0,
        "review_notes": "short",
        "data_faithfulness_score": 0.0,
        "chart_text_alignment_score": 0.0,
        "binding_confidence": 0.0,
        "visual_clarity_score": 0.0,
        "financial_appropriateness_score": 0.0,
        "issues": [],
    }
    return client.chat(
        model=model,
        messages=[
            {"role": "system", "content": "Repair malformed chart QA JSON. Return strict JSON only. Preserve visible scores and decisions; shorten long evidence fields."},
            {"role": "user", "content": f"Repair into this schema without adding unsupported new analysis.\nSCHEMA:\n{json.dumps(schema, ensure_ascii=False)}\n\nMALFORMED:\n{malformed[:12000]}"},
        ],
        max_tokens=max_tokens,
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"chart_id": chart_id, "judge": "chart_vl_qa_json_repair"},
    )


def build_prompt(chart: dict[str, Any], parsed: dict[str, Any]) -> str:
    schema = {
        "ok": True,
        "chart_id": "string",
        "visual_gate": {
            "is_visualization": True,
            "visualization_kind": "chart|table|diagram|infographic|metric_panel|not_visualization",
            "decision": "continue|skip_checklist",
            "reason": "short reason for whether this is a real analytical visualization",
            "confidence": 0.0,
        },
        "chart_type": "line|bar|stacked_bar|area|scatter|table|matrix|multi_panel|mixed|unknown",
        "is_analytical_visual": True,
        "target_visual_description": "short description of what is visible in the target screenshot",
        "main_takeaway_from_visual": "one sentence",
        "visible_metadata": {
            "title": {"value": "string", "confidence": 0.0},
            "unit": {"value": "string", "confidence": 0.0},
            "time_window": {"value": "string", "confidence": 0.0},
            "source": {"value": "string", "confidence": 0.0},
        },
        "key_values": ["string"],
        "matched_text_spans": [
            {
                "span_id": "t001",
                "text": "short quote from page text",
                "relevance": 0.0,
                "relationship": "explains|mentions|supports|contradicts|unrelated",
                "reason": "why this span explains the current visualization",
            }
        ],
        "universal_checklist": [
            {
                "id": "U1",
                "label": "Analytical purpose",
                "score": 0.0,
                "status": "pass|partial|fail|not_applicable",
                "evidence": "specific visible or textual evidence",
                "severity_if_failed": "none|low|medium|high",
            }
        ],
        "contextual_checklist": [
            {
                "id": "C1",
                "label": "context-specific criterion",
                "score": 0.0,
                "status": "pass|partial|fail|not_applicable",
                "evidence": "specific evidence",
                "severity_if_failed": "none|low|medium|high",
            }
        ],
        "subscores": {
            "crop_completeness": 0.0,
            "metadata_completeness_visual": 0.0,
            "readability": 0.0,
            "chart_type_suitability": 0.0,
            "chart_text_alignment": 0.0,
            "claim_support": 0.0,
            "visual_professionalism": 0.0,
            "decision_usefulness": 0.0,
        },
        "hard_flags": [
            {
                "flag_type": "decorative_visual|incomplete_crop|unreadable|missing_critical_unit|missing_critical_source|text_contradiction|misleading_scale|wrong_chart_type",
                "severity": "low|medium|high",
                "evidence": "why this flag applies",
            }
        ],
        "overall_vlm_visual_score": 0.0,
        "confidence": 0.0,
        "review_notes": "short reviewer-facing explanation",
        "data_faithfulness_score": 0.0,
        "chart_text_alignment_score": 0.0,
        "binding_confidence": 0.0,
        "visual_clarity_score": 0.0,
        "financial_appropriateness_score": 0.0,
        "issues": [
            {
                "issue_type": "chart_data_error|chart_text_misalignment|label_unit_error|chart_design_issue|visual_readability_issue|decorative_chart",
                "severity": "high|medium|low",
                "location": "chart_id or nearby text",
                "description": "short",
                "suggested_skill_patch": "short",
            }
        ],
    }
    context = {
        "chart_id": chart.get("chart_id"),
        "page": chart.get("page"),
        "target_image_path": chart.get("image_path"),
        "full_page_image_path": chart.get("page_image_path"),
        "bbox": chart.get("bbox"),
        "page_bbox": chart.get("page_bbox"),
        "rule_title": chart.get("title"),
        "rule_source_note": chart.get("source_note"),
        "rule_unit_hint": chart.get("unit_hint"),
        "expected_match": chart.get("expected_match"),
        "nearby_text": (chart.get("nearby_text") or "")[:1600],
        "full_page_text": (chart.get("page_text") or chart.get("nearby_text") or "")[:5000],
        "page_text_blocks": (chart.get("page_text_blocks") or [])[:40],
        "report_title": parsed.get("title"),
    }
    checklist = [{"id": item_id, "label": label, "what_to_check": detail} for item_id, label, detail in UNIVERSAL_CHECKLIST]
    return (
        "Evaluate TARGET_VISUAL_SCREENSHOT as the current visualization in a financial strategy report.\n"
        "Use FULL_PAGE_SCREENSHOT only for page layout and context. Score the target visualization, not unrelated page elements.\n"
        "FIRST run visual_gate before any checklist work. Decide whether the target screenshot is a real analytical visualization: chart, table, diagram, infographic, or metric panel.\n"
        "If the target is a table of contents, section divider, cover page, pure paragraph text, disclaimer, logo/sidebar/footer, or other non-analytical page artifact, set visual_gate.decision='skip_checklist', visual_gate.is_visualization=false, is_analytical_visual=false, leave universal_checklist/contextual_checklist empty, set subscores to 0, add a high decorative_visual or wrong_chart_type hard_flag, and stop. Do not spend tokens on U1-U12.\n"
        "Apply every universal checklist item U1-U12 and add exactly 2 contextual checklist items specific to this visual type and page situation.\n"
        "For chart-text alignment, first identify matched_text_spans from PAGE_TEXT_BLOCKS/full_page_text, then judge whether those spans explain, support, or contradict the visual.\n"
        "Do not perform exact data-faithfulness grading unless the relevant values are plainly visible. Exact numeric faithfulness is handled by structured checks outside the VLM.\n"
        "Penalize incomplete crops, unreadable labels, missing critical units/source, decorative visuals, misleading chart forms, and contradictions with matched text.\n"
        "When multiple charts appear on one page, do not assume nearby text belongs to this chart. Search the full page text blocks for the best match.\n"
        "Return strict JSON only. Scores are continuous from 0 to 1. Keep every evidence/reason/review field under 25 words.\n"
        f"Universal checklist:\n{json.dumps(checklist, ensure_ascii=False)}\n\n"
        f"Return JSON matching this schema:\n{json.dumps(schema, ensure_ascii=False)}\n\n"
        f"Context:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


def image_to_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
