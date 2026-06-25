from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import fitz
from bs4 import BeautifulSoup

from eval_utils import ROOT, extract_dates, extract_numbers, normalize_text, repo_path


TOOLS_DIR = ROOT / "dataset_tools" / "strategy_reports"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from document_extractors import extract_document  # noqa: E402


TABLE_RE = re.compile(r"\b(table|exhibit|figure|chart|图表|表\s*\d+|图\s*\d+)\b", re.IGNORECASE)
SOURCE_RE = re.compile(r"\b(source|sources|资料来源|数据来源|来源|according to|based on)\b", re.IGNORECASE)
DISCLAIMER_RE = re.compile(
    r"(not investment advice|important information|risk disclosure|past performance|forward-looking|"
    r"does not guarantee|for informational purposes|投资建议|风险提示|免责声明|不构成.*建议|过往业绩|不保证)",
    re.IGNORECASE,
)


def parse_candidate_report(
    path: Path,
    report_id: str,
    title: str = "",
    fmt: str | None = None,
    work_dir: Path | None = None,
    max_chars: int = 26000,
    render_pages: int = 1,
    cache: bool = True,
) -> dict[str, Any]:
    resolved = repo_path(path)
    if resolved is None:
        raise ValueError("candidate path is required")
    if not resolved.exists():
        raise FileNotFoundError(resolved)
    fmt = fmt or infer_format(resolved)
    work_dir = work_dir or ROOT / "evals" / "strategy_report" / "results" / "_parse_cache"
    sample = {
        "curated_id": report_id,
        "format": fmt,
        "curated_path": str(resolved),
        "title": title,
    }
    extracted = extract_document(sample, work_dir=work_dir, max_chars=max_chars, render_pages=render_pages, cache=cache)
    text = extracted.get("text_excerpt") or ""
    if fmt == "pdf":
        text = enrich_pdf_eval_text(resolved, text, max_chars=max_chars)
    html_stats = parse_html_stats(resolved) if fmt == "html" else {}
    headings = extracted.get("headings") or []
    sections = sectionize(text, headings)
    numbers = extract_numbers(text)
    dates = extract_dates(text)
    return {
        "report_id": report_id,
        "path": str(resolved),
        "format": fmt,
        "title": extracted.get("title_hint") or title,
        "text": text,
        "text_length": max(extracted.get("text_length") or 0, len(text)),
        "headings": headings,
        "sections": sections,
        "links": extracted.get("links") or html_stats.get("links") or [],
        "tables_or_figures_hint": extracted.get("tables_or_figures_hint") or [],
        "table_figure_hint_count": len(TABLE_RE.findall(text)) + len(extracted.get("tables_or_figures_hint") or []),
        "source_hint_count": len(SOURCE_RE.findall(text)),
        "disclaimer_hint_count": len(DISCLAIMER_RE.findall(text)),
        "numbers": numbers[:500],
        "dates": dates[:200],
        "page_count": extracted.get("page_count"),
        "parse_method": extracted.get("parse_method"),
        "parse_quality": extracted.get("parse_quality"),
        "render_images": extracted.get("visual_images") or [],
        "html_stats": html_stats,
        "warnings": extracted.get("extraction_warnings") or [],
    }


def infer_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return "html"
    return "pdf"


def enrich_pdf_eval_text(path: Path, base_text: str, max_chars: int) -> str:
    """Add late-page text so end disclaimers and appendices are visible to eval checks."""
    try:
        with fitz.open(path) as doc:
            page_count = doc.page_count
            wanted = sorted(set(list(range(min(page_count, 18))) + list(range(max(0, page_count - 6), page_count))))
            parts = [doc.load_page(index).get_text("text") for index in wanted]
    except Exception:
        return base_text
    richer = "\n\n".join(part for part in parts if part.strip())
    if len(richer) <= max_chars:
        return richer
    head = richer[: int(max_chars * 0.72)]
    tail = richer[-int(max_chars * 0.2) :]
    return f"{head}\n\n[... middle omitted for eval token control ...]\n\n{tail}"


def parse_html_stats(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    links = [{"text": a.get_text(" ", strip=True)[:120], "href": (a.get("href") or "")[:400]} for a in soup.find_all("a", href=True)]
    return {
        "h1_h4_count": len(soup.find_all(["h1", "h2", "h3", "h4"])),
        "table_count": len(soup.find_all("table")),
        "image_count": len(soup.find_all("img")),
        "links": [link for link in links if link["text"] or link["href"]][:50],
    }


def sectionize(text: str, headings: list[str]) -> list[dict[str, str]]:
    normalized_text = text or ""
    sections: list[dict[str, str]] = []
    if not headings:
        chunks = re.split(r"\n\s*\n", normalized_text)
        for index, chunk in enumerate(chunks[:20]):
            if len(chunk.strip()) > 120:
                sections.append({"heading": f"chunk_{index + 1}", "text": chunk.strip()[:2200]})
        return sections
    lower = normalize_text(normalized_text)
    positions: list[tuple[int, str]] = []
    for heading in headings:
        idx = lower.find(normalize_text(heading))
        if idx >= 0:
            positions.append((idx, heading))
    positions = sorted(set(positions))
    for i, (start, heading) in enumerate(positions[:30]):
        end = positions[i + 1][0] if i + 1 < len(positions) else min(len(normalized_text), start + 3000)
        sections.append({"heading": heading, "text": normalized_text[start:end].strip()[:3000]})
    return sections
