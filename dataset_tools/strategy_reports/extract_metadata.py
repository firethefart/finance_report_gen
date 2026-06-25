from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from common import append_jsonl, read_jsonl, sha256_file, utc_now_iso


MUST_HAVE_BY_SUBTYPE = {
    "annual_outlook": [
        "executive summary",
        "core investment thesis",
        "macro backdrop",
        "asset class views",
        "scenario analysis",
        "risks and limitations",
        "source list",
    ],
    "midyear_outlook": [
        "executive summary",
        "what changed since prior outlook",
        "market setup",
        "asset class views",
        "risks and counterarguments",
        "source list",
    ],
    "weekly_commentary": [
        "core view",
        "one key chart or evidence table",
        "market implication",
        "risk note",
        "source list",
    ],
    "thematic_strategy": [
        "theme definition",
        "investment thesis",
        "evidence and drivers",
        "industry or asset mapping",
        "scenario analysis",
        "risks",
        "source list",
    ],
    "asset_allocation": [
        "portfolio context",
        "asset allocation views",
        "risk-return rationale",
        "implementation notes",
        "risks",
        "source list",
    ],
    "ma_capital_markets_strategy": [
        "deal activity backdrop",
        "capital markets thesis",
        "sector or region drivers",
        "scenario analysis",
        "risks",
        "source list",
    ],
}


def read_pdf_text(path: Path, max_pages: int = 12) -> tuple[str, int, str]:
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:  # noqa: BLE001
                pass
        page_count = len(reader.pages)
        chunks: list[str] = []
        for page in reader.pages[:max_pages]:
            chunks.append(page.extract_text() or "")
        text = "\n".join(chunks).strip()
        quality = "excellent" if len(text) > 8000 else "good" if len(text) > 2500 else "fair" if len(text) > 500 else "poor"
        return text, page_count, quality
    except Exception:  # noqa: BLE001
        return "", 0, "failed"


def first_reasonable_title(text: str, fallback: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if 8 <= len(line) <= 150]
    skip = re.compile(r"^(contents|important|disclosure|for .* use only|marketing communication)$", re.I)
    for line in lines[:20]:
        if not skip.search(line):
            return line
    return fallback.removesuffix(".pdf").replace("-", " ").title()


def find_report_date(text: str) -> str | None:
    patterns = [
        r"\b(20[2-3][0-9])[-/\.](0?[1-9]|1[0-2])[-/\.](0?[1-9]|[12][0-9]|3[01])\b",
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+([0-9]{1,2},\s+)?(20[2-3][0-9])\b",
        r"\b(Q[1-4]\s+20[2-3][0-9])\b",
    ]
    for pat in patterns:
        match = re.search(pat, text, re.I)
        if match:
            return match.group(0)
    return None


def candidate_query(title: str, subtype: str) -> dict[str, Any]:
    if subtype == "annual_outlook":
        query = f"请基于公开资料写一份关于“{title}”主题的年度投资展望，重点分析宏观环境、资产配置含义、关键风险和情景变化。"
    elif subtype == "weekly_commentary":
        query = f"请围绕“{title}”写一份短篇市场策略评论，说明核心观点、关键证据、市场含义和风险。"
    elif subtype == "ma_capital_markets_strategy":
        query = f"请分析“{title}”所代表的资本市场和并购趋势，并说明对行业格局、融资环境和交易活动的影响。"
    else:
        query = f"请写一份关于“{title}”的策略研究报告，包含核心观点、证据链、情景分析、风险提示和来源。"
    return {
        "query": query,
        "language": "zh",
        "query_style": "analyst_request",
        "scope_constraints": ["Use public information", "Separate facts from forecasts", "Include risks and sources"],
    }


def extract_key_facts(text: str, max_facts: int = 8) -> list[dict[str, Any]]:
    sentences = re.split(r"(?<=[.!?。])\s+", re.sub(r"\s+", " ", text))
    facts = []
    skip = re.compile(
        r"(financial promotion|all investing involves risk|important information|disclosure|contents|table of contents|provided by)",
        re.I,
    )
    for sent in sentences:
        if len(sent) < 40 or len(sent) > 260:
            continue
        if skip.search(sent):
            continue
        has_number = re.search(r"\b\d+(\.\d+)?\s*(%|bps?|trillion|billion|million|year|years|x)\b", sent, re.I)
        has_signal = re.search(r"\b(inflation|growth|rates|yield|earnings|AI|market|equity|credit|bond|M&A|outlook|risk)\b", sent, re.I)
        if has_number or has_signal:
            fact_id = f"fact_{len(facts)+1:02d}"
            facts.append(
                {
                    "fact_id": fact_id,
                    "claim": sent.strip(),
                    "fact_type": "forecast" if re.search(r"\b(expect|forecast|outlook|project|estimate)\b", sent, re.I) else "market",
                    "value": has_number.group(0) if has_number else None,
                    "unit": None,
                    "time_window": None,
                    "source_ref": "primary_report_pdf",
                    "confidence": 0.65 if has_number else 0.55,
                    "why_it_matters": "Potentially material evidence for the strategy report case.",
                    "verification_hint": "Verify against the PDF chart/table or original cited data source before promoting to golden key fact.",
                }
            )
        if len(facts) >= max_facts:
            break
    return facts


def must_have_sections(subtype: str) -> list[dict[str, Any]]:
    sections = MUST_HAVE_BY_SUBTYPE.get(subtype, MUST_HAVE_BY_SUBTYPE["thematic_strategy"])
    return [
        {
            "section_name": name,
            "required": True,
            "purpose": f"Cover the {name} expected in a professional strategy report.",
            "required_points": [],
            "evaluation_focus": "Check completeness, evidence support, and strategy relevance.",
        }
        for name in sections
    ]


def prohibited_mistakes(subtype: str) -> list[dict[str, Any]]:
    mistakes = [
        ("Treat institution forecasts or scenarios as historical facts.", "high", "facts"),
        ("Make personalized investment recommendations or guarantee returns.", "blocker", "compliance"),
        ("Use charts without titles, units, dates, or source notes.", "high", "charts"),
        ("Omit downside risks or counterarguments for the core thesis.", "high", "scenario_risk"),
        ("Cite the primary PDF for claims that require updated market data without noting the date.", "medium", "sources"),
    ]
    if subtype in {"annual_outlook", "midyear_outlook"}:
        mistakes.append(("Fail to discuss asset-class or market implications.", "high", "strategy_reasoning"))
    if subtype == "ma_capital_markets_strategy":
        mistakes.append(("Confuse announced deal activity with completed transactions.", "high", "facts"))
    return [
        {
            "mistake": text,
            "severity": severity,
            "why_it_matters": "This would materially reduce benchmark validity for strategy-report generation.",
            "related_eval_dimension": dim,
        }
        for text, severity, dim in mistakes
    ]


def build_case(row: dict[str, Any], index: int) -> dict[str, Any]:
    path = Path(row["file_path"])
    text, page_count, parse_quality = read_pdf_text(path)
    title = row.get("guessed_title") or first_reasonable_title(text, path.name)
    subtype = row.get("strategy_subtype") or "thematic_strategy"
    report_date = find_report_date(text)
    quality_tier = row.get("quality_tier", "C")
    return {
        "case_id": f"strategy_case_{index:04d}",
        "source_pdf": {
            "file_path": str(path),
            "file_name": path.name,
            "sha256": row.get("sha256") or sha256_file(path),
            "file_size_bytes": path.stat().st_size,
            "page_count": page_count or row.get("page_count"),
            "parse_method": "text",
            "parse_quality": parse_quality,
        },
        "institution": {
            "name": row.get("institution"),
            "business_type": row.get("business_type"),
            "country_or_region": row.get("country_or_region"),
            "official_url": None,
        },
        "report_title": title,
        "report_date": report_date,
        "publication_period": report_date,
        "authors_or_team": [],
        "strategy_subtype": subtype,
        "secondary_tags": [],
        "classification_rationale": f"Subtype inferred from seed hint, filename, and first pages: {subtype}.",
        "quality_tier": quality_tier,
        "quality_rationale": row.get("quality_rationale"),
        "candidate_query": candidate_query(title, subtype),
        "expected_report_type": {
            "type": subtype,
            "depth": "institutional_style" if quality_tier == "A" else "standard_report",
            "output_format": "webpage",
            "expected_time_horizon": None,
            "target_reader": "financial research evaluator",
        },
        "source_pack": [
            {
                "name": "Primary strategy research PDF",
                "type": "primary_report_pdf",
                "url_or_path": str(path),
                "date": report_date,
                "required": True,
                "observed_in_pdf": True,
                "notes": "Primary report used to infer benchmark metadata.",
            },
            {
                "name": "Original download URL",
                "type": "institution_page",
                "url_or_path": row.get("pdf_url"),
                "date": None,
                "required": False,
                "observed_in_pdf": False,
                "notes": "Download source captured in manifest.",
            },
        ],
        "key_facts": extract_key_facts(text),
        "must_have_sections": must_have_sections(subtype),
        "prohibited_mistakes": prohibited_mistakes(subtype),
        "reference_notes": {
            "what_to_learn": ["Use the report as a style and structure reference for this strategy subtype."],
            "style_notes": ["Review section hierarchy, chart placement, and executive summary style manually."],
            "strong_sections": [],
            "weaknesses_or_cautions": ["This metadata was extracted automatically and needs human QA before golden-set promotion."],
            "do_not_copy": ["Do not copy long passages verbatim from the source PDF."],
        },
        "charts_and_tables_to_learn_from": [],
        "evaluation_hooks": {
            "automatic_checks": ["render_check", "source_check", "claim_citation_check", "compliance_check"],
            "human_review_focus": ["strategy thesis quality", "key fact validity", "must-have section fit", "chart exemplars"],
            "likely_failure_modes": ["facts_low_confidence", "query_too_broad", "sections_not_inferable"],
            "skill_patch_targets": ["research", "strategy_writing", "visualization", "qa"],
        },
        "extraction_confidence": {
            "overall": 0.7 if parse_quality in {"excellent", "good"} else 0.5,
            "classification": 0.75,
            "key_facts": 0.55,
            "source_pack": 0.75,
            "query": 0.7,
        },
        "extraction_notes": f"Automatically extracted at {utc_now_iso()}; requires human review before use as final golden metadata.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract initial benchmark metadata JSON from screened strategy PDFs.")
    parser.add_argument("--screening", type=Path, default=Path("dataset_build/manifests/screening_manifest.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("dataset_build/extracted_meta/candidate_cases.jsonl"))
    parser.add_argument("--tiers", default="A,B")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--reset-manifest", action="store_true")
    args = parser.parse_args()
    if args.reset_manifest:
        args.out.unlink(missing_ok=True)

    allowed_tiers = {tier.strip() for tier in args.tiers.split(",") if tier.strip()}
    rows = [row for row in read_jsonl(args.screening) if row.get("quality_tier") in allowed_tiers]
    if args.limit is not None:
        rows = rows[: args.limit]
    cases = [build_case(row, idx + 1) for idx, row in enumerate(rows)]
    append_jsonl(args.out, cases)
    print(f"extracted={len(cases)} out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
