from __future__ import annotations

import base64
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import fitz
from bs4 import BeautifulSoup
from charset_normalizer import from_bytes
from PIL import Image
from pypdf import PdfReader
from selectolax.parser import HTMLParser

from common import sha256_file, write_json


WHITESPACE_RE = re.compile(r"\s+")
MOJIBAKE_RE = re.compile(r"[锟�鈥€鍥鐨涓浠鏃勾湪缇]")


@dataclass
class ExtractedDocument:
    sample_id: str
    format: str
    source_path: str
    file_name: str
    sha256: str | None
    file_size_bytes: int
    page_count: int
    parse_method: str
    parse_quality: str
    title_hint: str
    headings: list[str] = field(default_factory=list)
    text_excerpt: str = ""
    text_length: int = 0
    tables_or_figures_hint: list[str] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)
    visual_images: list[str] = field(default_factory=list)
    extraction_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clean_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def compact_text(parts: list[str], max_chars: int = 18000) -> str:
    text = "\n\n".join(clean_text(p) for p in parts if clean_text(p))
    if len(text) <= max_chars:
        return text
    head = text[: int(max_chars * 0.72)]
    tail = text[-int(max_chars * 0.18) :]
    return f"{head}\n\n[... middle omitted for token control ...]\n\n{tail}"


def quality_from_text(text: str, warnings: list[str]) -> str:
    if warnings and not text:
        return "failed"
    if looks_mojibake(text):
        warnings.append("probable_mojibake_text_layer")
        return "poor"
    if len(text) > 12000:
        return "excellent"
    if len(text) > 5000:
        return "good"
    if len(text) > 1000:
        return "fair"
    return "poor"


def looks_mojibake(text: str) -> bool:
    if not text:
        return False
    sample = text[:20000]
    score = len(MOJIBAKE_RE.findall(sample)) / max(1, len(sample))
    cjk_count = sum(1 for char in sample if "\u4e00" <= char <= "\u9fff")
    ascii_letters = sum(1 for char in sample if char.isascii() and char.isalpha())
    return score > 0.08 and cjk_count > ascii_letters


def extract_headings_from_text(text: str, max_items: int = 30) -> list[str]:
    headings: list[str] = []
    for raw in text.splitlines():
        line = clean_text(raw)
        if not line or len(line) > 110:
            continue
        word_count = len(line.split())
        has_case_signal = line.isupper() or line.istitle()
        has_strategy_signal = any(
            token in line.lower()
            for token in ["outlook", "strategy", "allocation", "macro", "market", "risk", "theme", "scenario"]
        )
        if word_count <= 12 and (has_case_signal or has_strategy_signal):
            headings.append(line)
        if len(headings) >= max_items:
            break
    return dedupe_keep_order(headings)


def dedupe_keep_order(items: list[str], max_items: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = clean_text(item).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if max_items and len(out) >= max_items:
            break
    return out


def render_pdf_pages(path: Path, out_dir: Path, max_pages: int = 2, dpi: int = 130) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    images: list[str] = []
    with fitz.open(path) as doc:
        for index in range(min(max_pages, doc.page_count)):
            page = doc.load_page(index)
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
            image_path = out_dir / f"page_{index + 1:03d}.jpg"
            pix.save(image_path)
            compress_image(image_path)
            images.append(str(image_path))
    return images


def compress_image(path: Path, max_side: int = 1600, quality: int = 78) -> None:
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((max_side, max_side))
        image.save(path, format="JPEG", quality=quality, optimize=True)


def image_to_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def extract_pdf(sample: dict[str, Any], work_dir: Path, max_chars: int = 18000, render_pages: int = 2) -> ExtractedDocument:
    path = Path(sample["curated_path"])
    warnings: list[str] = []
    page_count = int(sample.get("page_count") or 0)
    text_parts: list[str] = []
    method = "pymupdf"
    try:
        with fitz.open(path) as doc:
            page_count = doc.page_count
            for index, page in enumerate(doc):
                if index >= min(page_count, 12):
                    break
                text_parts.append(page.get_text("text"))
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"pymupdf_text_failed: {exc!r}")
        method = "pypdf"
        try:
            reader = PdfReader(str(path))
            page_count = len(reader.pages)
            for page in reader.pages[:12]:
                text_parts.append(page.extract_text() or "")
        except Exception as pypdf_exc:  # noqa: BLE001
            warnings.append(f"pypdf_text_failed: {pypdf_exc!r}")
    raw_text = "\n\n".join(text_parts)
    text_excerpt = compact_text(text_parts, max_chars=max_chars)
    headings = extract_headings_from_text(raw_text)
    figures = [
        line
        for line in extract_headings_from_text(raw_text, max_items=80)
        if any(token in line.lower() for token in ["figure", "chart", "table", "exhibit"])
    ][:12]
    images: list[str] = []
    if render_pages > 0:
        try:
            images = render_pdf_pages(path, work_dir / "images" / sample["curated_id"], max_pages=render_pages)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"pdf_render_failed: {exc!r}")
    return ExtractedDocument(
        sample_id=sample["curated_id"],
        format="pdf",
        source_path=str(path),
        file_name=path.name,
        sha256=sample.get("sha256") or sha256_file(path),
        file_size_bytes=path.stat().st_size,
        page_count=page_count,
        parse_method=method,
        parse_quality=quality_from_text(raw_text, warnings),
        title_hint=sample.get("title") or "",
        headings=headings,
        text_excerpt=text_excerpt,
        text_length=len(raw_text),
        tables_or_figures_hint=figures,
        visual_images=images,
        extraction_warnings=warnings,
    )


def extract_html(sample: dict[str, Any], work_dir: Path, max_chars: int = 18000) -> ExtractedDocument:
    path = Path(sample["curated_path"])
    warnings: list[str] = []
    raw = path.read_bytes()
    match = from_bytes(raw).best()
    html = str(match) if match else raw.decode("utf-8", errors="ignore")
    try:
        parser = HTMLParser(html)
        for node in parser.css("script, style, noscript, svg"):
            node.decompose()
        title_node = parser.css_first("title")
        title_hint = clean_text(title_node.text()) if title_node else sample.get("title", "")
        heading_nodes = parser.css("h1, h2, h3")
        headings = dedupe_keep_order([clean_text(node.text()) for node in heading_nodes], max_items=30)
        text = parser.body.text(separator="\n") if parser.body else parser.text(separator="\n")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"selectolax_failed: {exc!r}")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        title_hint = clean_text(soup.title.get_text(" ")) if soup.title else sample.get("title", "")
        headings = dedupe_keep_order([clean_text(h.get_text(" ")) for h in soup.find_all(["h1", "h2", "h3"])], max_items=30)
        text = soup.get_text("\n")
    links = extract_links_bs4(html)
    text_excerpt = compact_text([text], max_chars=max_chars)
    return ExtractedDocument(
        sample_id=sample["curated_id"],
        format="html",
        source_path=str(path),
        file_name=path.name,
        sha256=sample.get("sha256") or sha256_file(path),
        file_size_bytes=path.stat().st_size,
        page_count=1,
        parse_method="html_dom",
        parse_quality=quality_from_text(text, warnings),
        title_hint=title_hint or sample.get("title", ""),
        headings=headings or extract_headings_from_text(text),
        text_excerpt=text_excerpt,
        text_length=len(text),
        links=links[:20],
        extraction_warnings=warnings,
    )


def extract_links_bs4(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[dict[str, str]] = []
    for link in soup.find_all("a", href=True):
        text = clean_text(link.get_text(" "))
        href = str(link.get("href") or "")
        if text and href:
            links.append({"text": text[:120], "href": href[:400]})
    return links


def extract_document(
    sample: dict[str, Any],
    work_dir: Path,
    max_chars: int = 18000,
    render_pages: int = 2,
    cache: bool = True,
) -> dict[str, Any]:
    out_path = work_dir / "local_extracts" / f"{sample['curated_id']}.json"
    if cache and out_path.exists():
        return write_json_passthrough(out_path)
    if sample.get("format") == "html":
        extracted = extract_html(sample, work_dir=work_dir, max_chars=max_chars)
    else:
        extracted = extract_pdf(sample, work_dir=work_dir, max_chars=max_chars, render_pages=render_pages)
    data = extracted.to_dict()
    write_json(out_path, data)
    return data


def write_json_passthrough(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
