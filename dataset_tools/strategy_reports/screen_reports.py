from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from common import append_jsonl, is_pdf_file, read_jsonl, utc_now_iso


SUBTYPE_KEYWORDS = {
    "annual_outlook": ["annual outlook", "investment outlook", "market outlook 2026", "economic and market outlook"],
    "midyear_outlook": ["midyear", "mid-year"],
    "quarterly_outlook": ["quarterly", "q1", "q2", "q3", "q4"],
    "weekly_commentary": ["weekly commentary", "weekly investment"],
    "thematic_strategy": ["theme", "thematic", "ai", "sustainable", "geopolitical"],
    "asset_allocation": ["asset allocation", "portfolio", "implementation guide"],
    "ma_capital_markets_strategy": ["m&a", "capital markets", "outlook"],
    "rates_fx_credit_strategy": ["fixed income", "credit", "rates", "yield"],
}


def extract_pdf_text(path: Path, max_pages: int = 3) -> tuple[str, int, str, str | None]:
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
        parse_quality = "good" if len(text) > 1500 else "fair" if len(text) > 300 else "poor"
        pdf_title = None
        if reader.metadata and reader.metadata.title:
            pdf_title = str(reader.metadata.title).strip()
        return text, page_count, parse_quality, pdf_title
    except Exception:  # noqa: BLE001
        return "", 0, "failed", None


def guess_subtype(file_name: str, text: str, fallback: str | None) -> str:
    if fallback and fallback != "mixed":
        return fallback
    haystack = f"{file_name} {text[:3000]}".lower()
    scores: dict[str, int] = {}
    for subtype, keywords in SUBTYPE_KEYWORDS.items():
        scores[subtype] = sum(1 for kw in keywords if kw in haystack)
    best, score = max(scores.items(), key=lambda item: item[1])
    if score > 0:
        return best
    return fallback or "thematic_strategy"


def extract_title(text: str, file_name: str, pdf_title: str | None = None) -> str:
    if pdf_title and 8 <= len(pdf_title) <= 160:
        return re.sub(r"\s+", " ", pdf_title).strip()
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if 8 <= len(line) <= 140]
    for line in lines[:12]:
        if not re.search(r"^(contents|disclosures|important information)$", line, re.I):
            return line
    return file_name.removesuffix(".pdf").replace("-", " ").title()


def quality_tier(file_size: int, page_count: int, parse_quality: str, subtype: str) -> tuple[str, str]:
    if parse_quality == "failed" or page_count == 0:
        return "Reject", "PDF text could not be parsed."
    if parse_quality == "poor":
        return "C", "PDF parsed poorly; likely needs OCR or manual review."
    score = 0
    if file_size >= 500_000:
        score += 1
    if page_count >= 8:
        score += 1
    if page_count >= 20:
        score += 1
    if subtype in {"annual_outlook", "midyear_outlook", "asset_allocation", "ma_capital_markets_strategy"}:
        score += 1
    if parse_quality == "good":
        score += 1
    if score >= 4:
        return "A", "Strong candidate by size, parse quality, subtype, and depth."
    if score >= 2:
        return "B", "Usable candidate but needs metadata QA."
    return "C", "Archive candidate; likely too short or thin for golden set."


def main() -> int:
    parser = argparse.ArgumentParser(description="Screen downloaded strategy report PDFs.")
    parser.add_argument("--manifest", type=Path, default=Path("dataset_build/manifests/download_manifest.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("dataset_build/manifests/screening_manifest.jsonl"))
    parser.add_argument("--reset-manifest", action="store_true")
    args = parser.parse_args()
    if args.reset_manifest:
        args.out.unlink(missing_ok=True)

    rows = []
    for item in read_jsonl(args.manifest):
        path_str = item.get("file_path")
        if not path_str:
            continue
        path = Path(path_str)
        if not path.exists() or not is_pdf_file(path):
            continue
        text, page_count, parse_quality, pdf_title = extract_pdf_text(path)
        subtype = guess_subtype(path.name, text, item.get("subtype_hint"))
        tier, rationale = quality_tier(path.stat().st_size, page_count, parse_quality, subtype)
        rows.append(
            {
                "screened_at": utc_now_iso(),
                "institution": item.get("institution"),
                "business_type": item.get("business_type"),
                "country_or_region": item.get("country_or_region"),
                "file_path": str(path),
                "file_name": path.name,
                "pdf_url": item.get("pdf_url") or item.get("url"),
                "sha256": item.get("sha256"),
                "file_size_bytes": path.stat().st_size,
                "page_count": page_count,
                "parse_quality": parse_quality,
                "guessed_title": extract_title(text, path.name, pdf_title),
                "strategy_subtype": subtype,
                "quality_tier": tier,
                "quality_rationale": rationale,
            }
        )
    append_jsonl(args.out, rows)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["quality_tier"]] = counts.get(row["quality_tier"], 0) + 1
    print(f"screened={len(rows)} counts={counts}")
    print(f"manifest={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
