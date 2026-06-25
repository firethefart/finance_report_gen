from __future__ import annotations

import hashlib
import base64
import re
from io import BytesIO
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, unquote

import fitz
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

from eval_utils import ROOT, extract_dates, extract_numbers, normalize_text, repo_path, write_json


CHART_SIGNAL_RE = re.compile(
    r"\b(figure|fig\.|exhibit|chart|table)\s*\d*|"
    r"(source|sources|note|notes):|"
    r"(图表|图\s*\d+|表\s*\d+|资料来源|数据来源|来源|注[:：])",
    re.IGNORECASE,
)
UNIT_RE = re.compile(r"(%|bps|bp|percent|percentage|usd|eur|rmb|cny|\$|\bbn\b|\bmn\b|\btrn\b|\btimes\b|单位|亿元|亿美元|万亿|百分点|个基点)", re.IGNORECASE)
TITLE_STOP_RE = re.compile(r"^(source|sources|note|notes|资料来源|数据来源|来源|注)[:：]?", re.IGNORECASE)


@dataclass
class ChartCandidate:
    chart_id: str
    report_id: str
    source_format: str
    source_path: str
    page: int | None
    bbox: list[float] | None
    detection_method: str
    chart_kind_hint: str
    page_chart_id: str | None = None
    page_image_path: str | None = None
    page_bbox: list[float] | None = None
    page_text: str = ""
    page_text_blocks: list[dict[str, Any]] = field(default_factory=list)
    object_index: int = 1
    object_count_on_page: int = 1
    object_role: str = "page_body_visual"
    title: str = ""
    caption: str = ""
    nearby_text: str = ""
    source_note: str = ""
    unit_hint: str = ""
    image_path: str | None = None
    html_snippet: str | None = None
    numbers: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    expected_match: str | None = None
    warnings: list[str] = field(default_factory=list)
    crop_quality: dict[str, Any] = field(default_factory=dict)
    page_type: str = ""
    page_action: str = ""
    page_signals: list[str] = field(default_factory=list)
    candidate_tier: str = ""
    candidate_score: float = 0.0
    candidate_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_chart_candidates(
    report_path: str | Path,
    report_id: str,
    fmt: str,
    out_dir: Path,
    expected_charts: list[dict[str, Any]] | None = None,
    max_pages: int = 40,
    max_charts: int = 16,
    dpi: int = 150,
    cache: bool = True,
) -> dict[str, Any]:
    out_path = out_dir / "chart_inventory" / f"{report_id}.charts.json"
    if cache and out_path.exists():
        import json

        return json.loads(out_path.read_text(encoding="utf-8"))
    path = repo_path(report_path)
    if path is None or not path.exists():
        raise FileNotFoundError(report_path)
    chart_dir = out_dir / "chart_inventory" / report_id
    chart_dir.mkdir(parents=True, exist_ok=True)
    if fmt == "html":
        candidates = extract_html_charts(path, report_id, chart_dir, max_charts=max_charts)
        audit = {"skipped_pages": [], "rejected_candidates": [], "truncated_candidates": []}
    else:
        candidates = extract_pdf_charts(path, report_id, chart_dir, expected_charts or [], max_pages=max_pages, max_charts=max_charts, dpi=dpi)
        audit = getattr(extract_pdf_charts, "last_audit", {"skipped_pages": [], "rejected_candidates": [], "truncated_candidates": []})
    data = {
        "report_id": report_id,
        "source_path": str(path),
        "source_format": fmt,
        "chart_count": len(candidates),
        "charts": [candidate.to_dict() for candidate in candidates],
        "audit": audit,
    }
    write_json(out_path, data)
    return data


def extract_pdf_charts(
    path: Path,
    report_id: str,
    chart_dir: Path,
    expected_charts: list[dict[str, Any]],
    max_pages: int,
    max_charts: int,
    dpi: int,
) -> list[ChartCandidate]:
    candidates: list[ChartCandidate] = []
    audit = {"skipped_pages": [], "rejected_candidates": [], "truncated_candidates": []}
    seen: set[str] = set()
    with fitz.open(path) as doc:
        page_indices = pick_pdf_pages(doc, expected_charts, max_pages=max_pages)
        for page_index in page_indices:
            page = doc.load_page(page_index)
            blocks = text_blocks(page)
            page_text = "\n".join(block["text"] for block in blocks)
            visual_stats = page_visual_stats(page)
            page_profile = classify_pdf_page(page_text, visual_stats, expected_charts, page_index)
            if page_profile["action"] == "skip":
                audit["skipped_pages"].append(page_profile)
                continue
            bboxes = detect_visual_bboxes(page, blocks, page_profile=page_profile)
            object_count = len(bboxes)
            for object_index, item in enumerate(bboxes, start=1):
                bbox = item["bbox"]
                method = item["method"]
                key = stable_key(page_index, bbox, method)
                if key in seen:
                    continue
                seen.add(key)
                candidate = build_pdf_candidate(
                    page,
                    blocks,
                    path,
                    report_id,
                    chart_dir,
                    page_index,
                    bbox,
                    method,
                    dpi,
                    object_index=object_index,
                    object_count=object_count,
                    page_profile=page_profile,
                    candidate_profile=item,
                )
                match_expected_chart(candidate, expected_charts)
                if not is_valid_visual_candidate(candidate):
                    audit["rejected_candidates"].append(candidate.to_dict())
                    continue
                candidates.append(candidate)
    ranked = sorted(candidates, key=lambda item: (-item.candidate_score, item.page or 0, item.object_index))
    kept = ranked[:max_charts]
    audit["truncated_candidates"].extend(item.to_dict() for item in ranked[max_charts:])
    setattr(extract_pdf_charts, "last_audit", audit)
    return kept


def pick_pdf_pages(doc: fitz.Document, expected_charts: list[dict[str, Any]], max_pages: int) -> list[int]:
    # Recall-first extraction: inspect every page inside the configured budget.
    # Page classification later skips only high-confidence non-body pages.
    return list(range(min(doc.page_count, max_pages)))


def text_blocks(page: fitz.Page) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for raw in page.get_text("blocks"):
        if len(raw) < 5:
            continue
        text = clean_text(str(raw[4]))
        if not text:
            continue
        blocks.append({"bbox": [float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])], "text": text})
    return blocks


def build_pdf_candidate(
    page: fitz.Page,
    blocks: list[dict[str, Any]],
    path: Path,
    report_id: str,
    chart_dir: Path,
    page_index: int,
    bbox: list[float],
    method: str,
    dpi: int,
    object_index: int = 1,
    object_count: int = 1,
    page_profile: dict[str, Any] | None = None,
    candidate_profile: dict[str, Any] | None = None,
) -> ChartCandidate:
    page_profile = page_profile or {}
    candidate_profile = candidate_profile or {}
    context = nearby_text_for_bbox(blocks, bbox)
    full_page_text = "\n".join(block["text"] for block in sorted(blocks, key=lambda item: (item["bbox"][1], item["bbox"][0])))
    title = infer_title(context)
    source_note = infer_source_note(context)
    unit_hint = infer_unit_hint(context)
    page_chart_id = f"{report_id}_page_{page_index + 1:03d}"
    image_name = f"{report_id}_p{page_index + 1:03d}_{method}_{short_hash(str(bbox))}.jpg"
    image_path = chart_dir / image_name
    render_pdf_bbox(page, bbox, image_path, dpi=dpi)
    full_page_bbox = [0.0, 0.0, float(page.rect.width), float(page.rect.height)]
    page_image_name = f"{report_id}_p{page_index + 1:03d}_full_page_{short_hash(str(full_page_bbox))}.jpg"
    page_image_path = chart_dir / page_image_name
    render_pdf_bbox(page, full_page_bbox, page_image_path, dpi=min(dpi, 120))
    page_blocks = page_text_blocks(blocks, full_page_bbox)
    crop_quality = crop_quality_metrics(bbox, full_page_bbox)
    return ChartCandidate(
        chart_id=f"{report_id}_chart_{page_index + 1:03d}_{short_hash(method + str(bbox))}",
        report_id=report_id,
        source_format="pdf",
        source_path=str(path),
        page=page_index + 1,
        bbox=[round(x, 2) for x in bbox],
        detection_method=method,
        chart_kind_hint=infer_chart_kind(context),
        page_chart_id=page_chart_id,
        page_image_path=str(page_image_path),
        page_bbox=[round(x, 2) for x in full_page_bbox],
        page_text=full_page_text[:12000],
        page_text_blocks=page_blocks,
        object_index=object_index,
        object_count_on_page=object_count,
        object_role="visual_object",
        title=title,
        caption=title,
        nearby_text=context[:4000],
        source_note=source_note,
        unit_hint=unit_hint,
        image_path=str(image_path),
        numbers=extract_numbers(context)[:80],
        dates=extract_dates(context)[:30],
        warnings=list(candidate_profile.get("warnings") or []),
        crop_quality=crop_quality,
        page_type=str(page_profile.get("page_type") or ""),
        page_action=str(page_profile.get("action") or ""),
        page_signals=list(page_profile.get("signals") or []),
        candidate_tier=str(candidate_profile.get("tier") or ""),
        candidate_score=float(candidate_profile.get("score") or 0.0),
        candidate_signals=list(candidate_profile.get("signals") or []),
    )


def page_text_blocks(blocks: list[dict[str, Any]], page_bbox: list[float]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    x0, y0, x1, y1 = page_bbox
    for index, block in enumerate(sorted(blocks, key=lambda item: (item["bbox"][1], item["bbox"][0])), start=1):
        bx0, by0, bx1, by1 = block["bbox"]
        if bx1 < x0 or bx0 > x1 or by1 < y0 or by0 > y1:
            continue
        text = clean_text(block["text"])
        if not text:
            continue
        out.append(
            {
                "span_id": f"t{len(out) + 1:03d}",
                "bbox": [round(v, 2) for v in block["bbox"]],
                "text": text[:1200],
            }
        )
    return out[:80]


def extract_html_charts(path: Path, report_id: str, chart_dir: Path, max_charts: int) -> list[ChartCandidate]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    candidates: list[ChartCandidate] = []
    base_url = html_base_url(soup)
    page_text = clean_text(soup.get_text(" ", strip=True))
    raw_nodes: list[Any] = []
    for selector in ["figure", "table", "img", "svg", "canvas"]:
        raw_nodes.extend(soup.find_all(selector))

    nodes: list[Any] = []
    seen_nodes: set[int] = set()
    for node in raw_nodes:
        node_id = id(node)
        if node_id in seen_nodes:
            continue
        seen_nodes.add(node_id)
        src = str(node.get("src") or node.get("data-src") or node.get("data-original") or "") if hasattr(node, "get") else ""
        context = html_node_context(node)
        if is_valid_html_visual_node(node, src, context):
            nodes.append(node)

    for index, node in enumerate(nodes[:max_charts]):
        context = html_node_context(node)
        snippet = str(node)[:5000]
        kind = node.name if node.name else "html_visual"
        src = str(node.get("src") or node.get("data-src") or node.get("data-original") or "") if hasattr(node, "get") else ""
        warnings: list[str] = []
        image_path = None
        render_source = "none"
        if kind == "img" and src:
            image_path, render_source, image_warnings = save_html_image_asset(src, path, base_url, chart_dir, report_id, index + 1)
            warnings.extend(image_warnings)
        elif kind == "figure":
            img = node.find("img") if hasattr(node, "find") else None
            img_src = str(img.get("src") or img.get("data-src") or img.get("data-original") or "") if img else ""
            if img_src:
                image_path, render_source, image_warnings = save_html_image_asset(img_src, path, base_url, chart_dir, report_id, index + 1)
                warnings.extend(image_warnings)
        elif kind == "table":
            image_path = render_html_table(node, chart_dir, report_id, index + 1)
            render_source = "table_preview" if image_path else "none"
            if not image_path:
                warnings.append("html_table_render_failed")
        elif kind == "svg":
            image_path = render_html_text_preview(node, chart_dir, report_id, index + 1, title="Inline SVG chart")
            render_source = "svg_text_preview" if image_path else "none"
            warnings.append("html_svg_text_preview_only")
        elif kind == "canvas":
            image_path = render_html_text_preview(node, chart_dir, report_id, index + 1, title="Canvas chart")
            render_source = "canvas_text_preview" if image_path else "none"
            warnings.append("html_canvas_preview_only")

        candidate = ChartCandidate(
            chart_id=f"{report_id}_html_chart_{index + 1:03d}",
            report_id=report_id,
            source_format="html",
            source_path=str(path),
            page=1,
            bbox=None,
            detection_method=f"html_{kind}",
            chart_kind_hint=kind,
            page_chart_id=f"{report_id}_html_page_001",
            page_image_path=image_path,
            page_bbox=None,
            page_text=page_text[:12000],
            page_text_blocks=html_text_blocks(context, page_text),
            object_index=index + 1,
            object_count_on_page=min(len(nodes), max_charts),
            object_role="html_visual_object",
            title=infer_title(context),
            caption=infer_title(context),
            nearby_text=context[:4000],
            source_note=infer_source_note(context),
            unit_hint=infer_unit_hint(context),
            image_path=image_path,
            html_snippet=snippet,
            numbers=extract_numbers(context)[:80],
            dates=extract_dates(context)[:30],
            warnings=warnings,
            crop_quality={
                "html_rendered": bool(image_path),
                "render_source": render_source,
                "base_url": base_url,
                "asset_src": src or None,
                "context_chars": len(context),
            },
        )
        candidates.append(candidate)
    return candidates


def html_base_url(soup: BeautifulSoup) -> str | None:
    for selector, attr in [
        ("link[rel='canonical']", "href"),
        ("meta[property='og:url']", "content"),
        ("meta[name='twitter:url']", "content"),
    ]:
        node = soup.select_one(selector)
        value = node.get(attr) if node else None
        if value and str(value).startswith(("http://", "https://")):
            return str(value)
    base = soup.find("base")
    if base and base.get("href"):
        value = str(base.get("href"))
        if value.startswith(("http://", "https://")):
            return value
    return None


def html_node_context(node: Any) -> str:
    texts: list[str] = []
    if hasattr(node, "get"):
        for attr in ["alt", "title", "aria-label"]:
            value = node.get(attr)
            if value:
                texts.append(str(value))
    if hasattr(node, "get_text"):
        texts.append(node.get_text(" ", strip=True))
    parent = getattr(node, "parent", None)
    if parent and hasattr(parent, "get_text"):
        texts.append(parent.get_text(" ", strip=True))
    return clean_text(" ".join(texts))


def is_valid_html_visual_node(node: Any, src: str, context: str) -> bool:
    kind = (getattr(node, "name", "") or "").lower()
    blob = normalize_text(" ".join([src or "", context or "", str(node.get("class") or "") if hasattr(node, "get") else ""]))
    decorative_terms = [
        "logo",
        "favicon",
        "icon",
        "headshot",
        "portrait",
        "profile",
        "author",
        "contact",
        "connect with us",
        "copyright",
        "social",
        "linkedin",
        "twitter",
        "facebook",
        "youtube",
        "instagram",
        "hero",
        "thumbnail",
        "banner",
        "people",
    ]
    if any(term in blob for term in decorative_terms):
        return False
    if kind in {"table", "svg", "canvas"}:
        return html_visual_signal_score(blob, context) >= 2
    if kind == "figure":
        return html_visual_signal_score(blob, context) >= 2 or bool(node.find(["table", "svg", "canvas", "img"]))
    if kind == "img":
        if not src:
            return False
        return html_visual_signal_score(blob, context) >= 2
    return False


def html_visual_signal_score(blob: str, context: str) -> int:
    signals = [
        "chart",
        "graph",
        "figure",
        "exhibit",
        "table",
        "source",
        "note:",
        "data",
        "aum",
        "allocation",
        "yield",
        "inflation",
        "growth",
        "return",
        "bps",
        "percent",
        "%",
        "图",
        "表",
        "资料来源",
        "数据来源",
    ]
    score = sum(1 for term in signals if term in blob)
    if len(extract_numbers(context)) >= 3:
        score += 2
    elif extract_numbers(context):
        score += 1
    return score


def save_html_image_asset(
    src: str,
    html_path: Path,
    base_url: str | None,
    chart_dir: Path,
    report_id: str,
    index: int,
) -> tuple[str | None, str, list[str]]:
    warnings: list[str] = []
    try:
        image = load_html_image(src, html_path, base_url)
        if image is None:
            warnings.append("html_image_load_failed")
            return None, "none", warnings
        width, height = image.size
        if width < 160 or height < 90:
            warnings.append(f"html_image_too_small:{width}x{height}")
        image = image.convert("RGB")
        image.thumbnail((1800, 1800))
        out = chart_dir / f"{report_id}_html_img_{index:03d}_{short_hash(src)}.jpg"
        image.save(out, format="JPEG", quality=86, optimize=True)
        return str(out), "image_asset", warnings
    except Exception as exc:
        warnings.append(f"html_image_error:{type(exc).__name__}")
        return None, "none", warnings


def load_html_image(src: str, html_path: Path, base_url: str | None) -> Image.Image | None:
    src = src.strip()
    if src.startswith("data:image/"):
        header, payload = src.split(",", 1)
        data = base64.b64decode(payload)
        return Image.open(BytesIO(data))

    parsed = urlparse(src)
    if parsed.scheme in {"http", "https"}:
        return fetch_remote_image(src)

    local_candidates: list[Path] = []
    if src.startswith("/"):
        local_candidates.append(html_path.parent / unquote(src.lstrip("/")))
        local_candidates.append(ROOT / unquote(src.lstrip("/")))
    else:
        local_candidates.append(html_path.parent / unquote(src))
    for candidate in local_candidates:
        if candidate.exists() and candidate.is_file():
            return Image.open(candidate)

    if base_url:
        return fetch_remote_image(urljoin(base_url, src))
    return None


def fetch_remote_image(url: str) -> Image.Image | None:
    response = requests.get(
        url,
        timeout=25,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; StrategyReportVerifier/0.1)",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        },
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "svg" in content_type or url.lower().endswith(".svg"):
        return None
    return Image.open(BytesIO(response.content))


def render_html_table(node: Any, chart_dir: Path, report_id: str, index: int) -> str | None:
    rows: list[list[str]] = []
    for tr in node.find_all("tr")[:28]:
        cells = [clean_text(cell.get_text(" ", strip=True))[:80] for cell in tr.find_all(["th", "td"])[:8]]
        if cells:
            rows.append(cells)
    if not rows:
        text = clean_text(node.get_text(" ", strip=True))
        if not text:
            return None
        rows = [[part[:80] for part in text.split(" ")[:6]]]
    col_count = max(len(row) for row in rows)
    cell_w = 190
    cell_h = 46
    pad = 20
    width = min(1800, max(500, col_count * cell_w + pad * 2))
    height = min(1800, max(220, len(rows) * cell_h + pad * 2))
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = preview_font(15)
    for r, row in enumerate(rows):
        y0 = pad + r * cell_h
        for c in range(col_count):
            x0 = pad + c * cell_w
            x1 = min(width - pad, x0 + cell_w)
            y1 = min(height - pad, y0 + cell_h)
            fill = "#f3f6fa" if r == 0 else "white"
            draw.rectangle([x0, y0, x1, y1], outline="#9aa4b2", fill=fill)
            value = row[c] if c < len(row) else ""
            draw.text((x0 + 6, y0 + 6), wrap_text(value, 28, 2), fill="#172033", font=font)
    out = chart_dir / f"{report_id}_html_table_{index:03d}.jpg"
    image.save(out, format="JPEG", quality=86, optimize=True)
    return str(out)


def render_html_text_preview(node: Any, chart_dir: Path, report_id: str, index: int, title: str) -> str | None:
    text = clean_text(node.get_text(" ", strip=True) if hasattr(node, "get_text") else "")
    if not text:
        return None
    image = Image.new("RGB", (1000, 520), "white")
    draw = ImageDraw.Draw(image)
    font = preview_font(16)
    draw.rectangle([0, 0, 999, 519], outline="#9aa4b2")
    draw.text((24, 24), title, fill="#172033", font=font)
    draw.text((24, 64), wrap_text(text[:1200], 110, 14), fill="#172033", font=font)
    out = chart_dir / f"{report_id}_html_preview_{index:03d}.jpg"
    image.save(out, format="JPEG", quality=86, optimize=True)
    return str(out)


def preview_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\arialuni.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def html_text_blocks(context: str, page_text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if context:
        blocks.append({"span_id": "t001", "bbox": None, "text": context[:1200]})
    if page_text and page_text != context:
        blocks.append({"span_id": "t002", "bbox": None, "text": page_text[:1200]})
    return blocks[:2]


def wrap_text(text: str, width: int, max_lines: int) -> str:
    if re.search(r"[\u4e00-\u9fff]", text or ""):
        cjk_width = max(6, int(width * 0.48))
        lines = [text[i : i + cjk_width] for i in range(0, len(text), cjk_width)]
        return "\n".join(lines[:max_lines])
    lines: list[str] = []
    current = ""
    for word in text.split():
        probe = f"{current} {word}".strip()
        if len(probe) <= width:
            current = probe
        else:
            if current:
                lines.append(current)
            current = word
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    return "\n".join(lines)


def render_pdf_bbox(page: fitz.Page, bbox: list[float], image_path: Path, dpi: int) -> None:
    clip = fitz.Rect(*bbox)
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), clip=clip, alpha=False)
    pix.save(image_path)
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        image.thumbnail((1800, 1800))
        image.save(image_path, format="JPEG", quality=84, optimize=True)


def detect_visual_bboxes(page: fitz.Page, blocks: list[dict[str, Any]], page_profile: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    page_rect = fitz.Rect(page.rect)
    width = float(page_rect.width)
    height = float(page_rect.height)
    body = fitz.Rect(width * 0.02, height * 0.06, width * 0.98, height * 0.92)
    min_area = width * height * 0.003
    max_area = width * height * 0.70
    rects: list[fitz.Rect] = []

    for drawing in page.get_drawings():
        raw = drawing.get("rect")
        if not raw:
            continue
        rect = fitz.Rect(raw) & body
        if usable_visual_rect(rect, min_area=min_area, max_area=max_area):
            rects.append(rect)

    for info in page.get_image_info(xrefs=True):
        bbox = info.get("bbox")
        if not bbox:
            continue
        rect = fitz.Rect(bbox) & body
        if usable_visual_rect(rect, min_area=min_area, max_area=max_area):
            rects.append(rect)

    clusters = prune_visual_clusters(cluster_rects(rects, page_rect), page_rect)
    clusters = merge_horizontal_bar_groups(clusters, page_rect)
    cells = visual_cells(clusters, page_rect)
    raw_candidates: list[dict[str, Any]] = []
    for index, cluster in enumerate(clusters):
        bbox = expand_visual_bbox(cluster, blocks, page_rect, cells[index])
        raw_candidates.append({"bbox": bbox, "method": "visual_object", "source_rect": [round(v, 2) for v in [cluster.x0, cluster.y0, cluster.x1, cluster.y1]]})
    raw_candidates.extend(anchor_bboxes_from_chart_titles(page, blocks))
    profile = page_profile or {}
    if should_use_content_fallback(profile, raw_candidates):
        raw_candidates.append({"bbox": content_bbox_from_blocks(page, blocks), "method": "page_body_fallback", "source_rect": None})
    candidates = prune_visual_candidate_items(raw_candidates, page_rect)
    return rank_visual_candidate_items(candidates, page, blocks, profile)


def page_visual_stats(page: fitz.Page) -> dict[str, Any]:
    page_rect = fitz.Rect(page.rect)
    page_area = max(1.0, float(page_rect.get_area()))
    drawing_rects = [fitz.Rect(item.get("rect")) for item in page.get_drawings() if item.get("rect")]
    image_rects = [fitz.Rect(info.get("bbox")) for info in page.get_image_info(xrefs=True) if info.get("bbox")]
    usable = [
        rect
        for rect in drawing_rects + image_rects
        if not rect.is_empty and 0.001 <= float(rect.get_area()) / page_area <= 0.75
    ]
    max_ratio = max([float(rect.get_area()) / page_area for rect in usable], default=0.0)
    return {
        "drawing_count": len(drawing_rects),
        "image_count": len(image_rects),
        "usable_visual_rect_count": len(usable),
        "max_visual_area_ratio": round(max_ratio, 3),
    }


def classify_pdf_page(text: str, visual_stats: dict[str, Any], expected_charts: list[dict[str, Any]], page_index: int) -> dict[str, Any]:
    low = normalize_text(text)
    numbers = extract_numbers(text)
    signals: list[str] = []
    expected_blob = " ".join(str(item.get("title_or_description") or "") for item in expected_charts)
    expected_tokens = tokenish(expected_blob)
    expected_overlap = len(expected_tokens & tokenish(text)) if expected_tokens else 0
    if expected_overlap >= 3:
        signals.append("expected_chart_overlap")
    toc_signal = bool(re.search(r"\btable of contents\b|\bcontents\b|目录|目錄|图表目录|圖表目錄|list of figures|list of tables", text, re.IGNORECASE))
    if toc_signal:
        signals.append("toc_terms")
    disclaimer_signal = bool(re.search(r"important information|disclosures?|免责声明|风险提示|法律声明|copyright|all rights reserved", text, re.IGNORECASE))
    if disclaimer_signal:
        signals.append("disclaimer_or_contact_terms")
    chart_signal = bool(re.search(r"figures in focus|figure|fig\.|exhibit|chart|table|图表|圖表|图\s*\d+|圖\s*\d+|表\s*\d+", text, re.IGNORECASE))
    if chart_signal:
        signals.append("chart_terms")
    source_signal = bool(re.search(r"\bsource[s]?:|资料来源|資料來源|数据来源|數據來源|来源", text, re.IGNORECASE))
    if source_signal:
        signals.append("source_terms")
    unit_signal = bool(UNIT_RE.search(text))
    if unit_signal:
        signals.append("unit_terms")
    if len(numbers) >= 8:
        signals.append("number_dense")
    if visual_stats.get("usable_visual_rect_count", 0) >= 4 or visual_stats.get("max_visual_area_ratio", 0) >= 0.08:
        signals.append("visual_density")

    page_type = "unknown_keep_for_recall"
    action = "keep"
    confidence = 0.45
    if expected_overlap >= 3:
        page_type = "expected_match_page"
        confidence = 0.9
    elif chart_signal and (source_signal or unit_signal or len(numbers) >= 4 or "visual_density" in signals):
        page_type = "analytical_visual_page"
        confidence = 0.78
    elif toc_signal and not visual_stats.get("usable_visual_rect_count") and len(numbers) <= 18 and not expected_overlap:
        page_type = "toc_or_figure_list"
        action = "skip"
        confidence = 0.88
    elif disclaimer_signal and not chart_signal and visual_stats.get("max_visual_area_ratio", 0) < 0.04 and len(numbers) < 8 and page_index > 2:
        page_type = "disclaimer_or_contact"
        action = "skip"
        confidence = 0.86
    elif "visual_density" in signals or len(numbers) >= 10:
        page_type = "mixed_text_visual_page"
        confidence = 0.65
    return {
        "page": page_index + 1,
        "page_type": page_type,
        "action": action,
        "confidence": round(confidence, 3),
        "signals": signals,
        "visual_stats": visual_stats,
        "number_count": len(numbers),
    }


def should_use_content_fallback(page_profile: dict[str, Any], raw_candidates: list[dict[str, Any]]) -> bool:
    if raw_candidates:
        return False
    signals = set(page_profile.get("signals") or [])
    if "expected_chart_overlap" in signals:
        return True
    if "chart_terms" in signals and ("source_terms" in signals or "unit_terms" in signals or "number_dense" in signals):
        return True
    if page_profile.get("page_type") in {"mixed_text_visual_page", "unknown_keep_for_recall"} and "visual_density" in signals:
        return True
    return False


def anchor_bboxes_from_chart_titles(page: fitz.Page, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    page_rect = fitz.Rect(page.rect)
    width = float(page_rect.width)
    height = float(page_rect.height)
    title_blocks: list[tuple[int, fitz.Rect, str]] = []
    for index, block in enumerate(blocks):
        text = clean_text(block["text"])
        if is_chart_title_text(text):
            title_blocks.append((index, fitz.Rect(block["bbox"]), text))
    anchors: list[dict[str, Any]] = []
    for position, (_, rect, text) in enumerate(title_blocks):
        next_y = height * 0.94
        for _, next_rect, _ in title_blocks[position + 1 :]:
            if next_rect.y0 > rect.y0 + 24:
                next_y = min(next_y, next_rect.y0 - 8)
                break
        y1 = min(next_y, rect.y1 + height * 0.42)
        bbox = [
            round(width * 0.025, 2),
            round(max(height * 0.035, rect.y0 - 12), 2),
            round(width * 0.975, 2),
            round(max(rect.y1 + 90, y1), 2),
        ]
        anchors.append(
            {
                "bbox": bbox,
                "method": "title_anchor_region",
                "source_rect": [round(v, 2) for v in [rect.x0, rect.y0, rect.x1, rect.y1]],
                "anchor_text": text[:180],
            }
        )
    return anchors


def is_chart_title_text(text: str) -> bool:
    if not text:
        return False
    clean = clean_text(text)
    if len(clean) > 240:
        return False
    if re.search(r"\b(figure|fig\.|exhibit|chart|table)\s*[\dA-ZIVX.-]*", clean, re.IGNORECASE):
        return True
    return bool(re.search(r"(图表|圖表|图|圖|表)\s*[\d一二三四五六七八九十百]+", clean))


def prune_visual_candidate_items(items: list[dict[str, Any]], page_rect: fitz.Rect) -> list[dict[str, Any]]:
    page_area = max(1.0, float(page_rect.get_area()))
    normalized: list[dict[str, Any]] = []
    for item in items:
        try:
            rect = fitz.Rect(item.get("bbox")) & page_rect
        except Exception:
            continue
        if rect.is_empty:
            continue
        area_ratio = float(rect.get_area()) / page_area
        max_area = 0.86 if item.get("method") == "page_body_fallback" else 0.74
        if area_ratio < 0.006 or area_ratio > max_area:
            item = {**item, "warnings": list(item.get("warnings") or []) + [f"area_ratio_outlier:{area_ratio:.3f}"]}
            if area_ratio < 0.003 or area_ratio > 0.92:
                continue
        if rect.width < 54 or rect.height < 35:
            continue
        item = dict(item)
        item["bbox"] = [round(v, 2) for v in [rect.x0, rect.y0, rect.x1, rect.y1]]
        item["area_ratio"] = round(area_ratio, 3)
        normalized.append(item)

    kept: list[dict[str, Any]] = []
    for item in sorted(normalized, key=lambda row: (method_priority(row.get("method")), -(row.get("area_ratio") or 0.0))):
        rect = fitz.Rect(item["bbox"])
        duplicate = False
        for existing in kept:
            other = fitz.Rect(existing["bbox"])
            if rect_overlap_ratio(rect, other) > 0.90:
                duplicate = True
                break
        if not duplicate:
            kept.append(item)
    return sorted(kept, key=lambda row: (row["bbox"][1], row["bbox"][0]))[:14]


def method_priority(method: str | None) -> int:
    return {"visual_object": 0, "title_anchor_region": 1, "page_body_fallback": 2}.get(method or "", 3)


def rank_visual_candidate_items(
    candidates: list[dict[str, Any]],
    page: fitz.Page,
    blocks: list[dict[str, Any]],
    page_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    expected_page = "expected_chart_overlap" in set(page_profile.get("signals") or [])
    ranked: list[dict[str, Any]] = []
    for item in candidates:
        bbox = item["bbox"]
        context = nearby_text_for_bbox(blocks, bbox)
        numbers = extract_numbers(context)
        signals: list[str] = []
        score = 0.0
        method = item.get("method")
        if method == "visual_object":
            score += 0.38
            signals.append("drawn_or_image_object")
        elif method == "title_anchor_region":
            score += 0.30
            signals.append("title_anchor")
        elif method == "page_body_fallback":
            score += 0.16
            signals.append("body_fallback")
        if CHART_SIGNAL_RE.search(context):
            score += 0.20
            signals.append("chart_terms_nearby")
        if re.search(r"\bsource[s]?:|资料来源|数据来源|來源|来源", context, re.IGNORECASE):
            score += 0.14
            signals.append("source_terms_nearby")
        if UNIT_RE.search(context):
            score += 0.10
            signals.append("unit_terms_nearby")
        if len(numbers) >= 8:
            score += 0.14
            signals.append("number_dense_nearby")
        elif len(numbers) >= 3:
            score += 0.08
            signals.append("numbers_nearby")
        if expected_page:
            score += 0.18
            signals.append("expected_chart_page")
        rect = fitz.Rect(bbox)
        page_area = max(1.0, float(page.rect.get_area()))
        area_ratio = float(rect.get_area()) / page_area
        aspect = rect.width / max(1.0, rect.height)
        if 0.03 <= area_ratio <= 0.58 and 0.35 <= aspect <= 5.8:
            score += 0.10
            signals.append("sane_crop_geometry")
        if "toc_terms" in set(page_profile.get("signals") or []):
            score -= 0.12
            signals.append("toc_page_penalty")
        if page_profile.get("page_type") == "disclaimer_or_contact":
            score -= 0.20
            signals.append("disclaimer_page_penalty")
        warnings = list(item.get("warnings") or [])
        if score < 0.42:
            warnings.append("low_confidence_kept_for_recall")
        tier = "tier_1_high_confidence" if score >= 0.75 else "tier_2_possible_visual" if score >= 0.45 else "tier_3_low_confidence_fallback"
        ranked.append(
            {
                **item,
                "score": round(max(0.0, score), 3),
                "tier": tier,
                "signals": signals,
                "warnings": warnings,
            }
        )
    ranked = sorted(ranked, key=lambda row: (-row.get("score", 0.0), row["bbox"][1], row["bbox"][0]))
    return suppress_redundant_visual_candidates(ranked)


def suppress_redundant_visual_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(candidates) <= 1:
        return candidates
    near_deduped: list[dict[str, Any]] = []
    for item in sorted(candidates, key=lambda row: candidate_keep_rank(row)):
        rect = fitz.Rect(item["bbox"])
        duplicate = False
        for kept in near_deduped:
            kept_rect = fitz.Rect(kept["bbox"])
            overlap = rect_overlap_ratio(rect, kept_rect)
            containment = max(rect_contains_ratio(rect, kept_rect), rect_contains_ratio(kept_rect, rect))
            if overlap >= 0.82 or containment >= 0.92:
                duplicate = True
                break
        if not duplicate:
            near_deduped.append(item)

    suppress_ids: set[int] = set()
    for index, item in enumerate(near_deduped):
        container = fitz.Rect(item["bbox"])
        container_area = max(1.0, float(container.get_area()))
        children: list[fitz.Rect] = []
        for other_index, other in enumerate(near_deduped):
            if other_index == index:
                continue
            child = fitz.Rect(other["bbox"])
            child_area = max(1.0, float(child.get_area()))
            if child_area >= container_area * 0.82:
                continue
            if rect_contains_ratio(container, child) >= 0.72:
                children.append(child)
        if len(children) < 2:
            continue
        union = fitz.Rect(children[0])
        for child in children[1:]:
            union |= child
        union_ratio = float(union.get_area()) / container_area
        horizontally_split = distinct_centers(children, axis="x", gap=container.width * 0.18)
        vertically_split = distinct_centers(children, axis="y", gap=container.height * 0.18)
        if union_ratio >= 0.42 and (horizontally_split or vertically_split):
            suppress_ids.add(index)

    kept = [item for index, item in enumerate(near_deduped) if index not in suppress_ids]
    return sorted(kept, key=lambda row: (-row.get("score", 0.0), row["bbox"][1], row["bbox"][0]))


def candidate_keep_rank(item: dict[str, Any]) -> tuple[float, int, float, float, float]:
    rect = fitz.Rect(item["bbox"])
    area = float(rect.get_area())
    score = float(item.get("score") or 0.0)
    method = item.get("method") or ""
    method_rank = 0 if method == "visual_object" else 1 if method == "title_anchor_region" else 2
    broad_penalty = 0.12 if item.get("method") == "page_body_fallback" else 0.0
    return (-(score - broad_penalty), method_rank, area, rect.y0, rect.x0)


def rect_contains_ratio(container: fitz.Rect, child: fitz.Rect) -> float:
    inter = container & child
    if inter.is_empty:
        return 0.0
    return float(inter.get_area()) / max(1.0, float(child.get_area()))


def distinct_centers(rects: list[fitz.Rect], axis: str, gap: float) -> bool:
    centers = sorted(((rect.x0 + rect.x1) / 2 if axis == "x" else (rect.y0 + rect.y1) / 2) for rect in rects)
    return any((b - a) >= gap for a, b in zip(centers, centers[1:]))


def usable_visual_rect(rect: fitz.Rect, min_area: float, max_area: float) -> bool:
    if rect.is_empty or rect.is_infinite:
        return False
    width = float(rect.width)
    height = float(rect.height)
    area = float(rect.get_area())
    if width < 14 or height < 10:
        return False
    if area < min_area or area > max_area:
        return False
    aspect = width / max(1.0, height)
    return 0.08 <= aspect <= 12.0


def cluster_rects(rects: list[fitz.Rect], page_rect: fitz.Rect) -> list[fitz.Rect]:
    clusters: list[fitz.Rect] = []
    for rect in sorted(rects, key=lambda r: (r.y0, r.x0, -r.get_area())):
        placed = False
        probe = expand_rect(rect, page_rect, side=12, up=10, down=12)
        for index, cluster in enumerate(clusters):
            if probe.intersects(cluster) or close_rects(rect, cluster):
                clusters[index] = cluster | rect
                placed = True
                break
        if not placed:
            clusters.append(fitz.Rect(rect))

    changed = True
    while changed:
        changed = False
        merged: list[fitz.Rect] = []
        for rect in clusters:
            for index, existing in enumerate(merged):
                if expand_rect(rect, page_rect, side=14, up=12, down=16).intersects(existing) or close_rects(rect, existing):
                    merged[index] = existing | rect
                    changed = True
                    break
            else:
                merged.append(rect)
        clusters = merged
    return clusters


def close_rects(a: fitz.Rect, b: fitz.Rect) -> bool:
    x_overlap = min(a.x1, b.x1) - max(a.x0, b.x0)
    y_overlap = min(a.y1, b.y1) - max(a.y0, b.y0)
    x_gap = max(0.0, max(a.x0, b.x0) - min(a.x1, b.x1))
    y_gap = max(0.0, max(a.y0, b.y0) - min(a.y1, b.y1))
    same_column = x_overlap > min(a.width, b.width) * 0.18 and y_gap < 42
    same_row = y_overlap > min(a.height, b.height) * 0.18 and x_gap < 42
    return same_column or same_row


def prune_visual_clusters(clusters: list[fitz.Rect], page_rect: fitz.Rect) -> list[fitz.Rect]:
    page_area = float(page_rect.get_area())
    filtered: list[fitz.Rect] = []
    for rect in sorted(clusters, key=lambda r: r.get_area(), reverse=True):
        area = float(rect.get_area())
        if area < page_area * 0.010 or area > page_area * 0.68:
            continue
        if rect.width < 70 or rect.height < 35:
            continue
        if any(rect_overlap_ratio(rect, kept) > 0.82 for kept in filtered):
            continue
        filtered.append(rect)
    return sorted(filtered, key=lambda r: (r.y0, r.x0))[:8]


def visual_cells(clusters: list[fitz.Rect], page_rect: fitz.Rect) -> list[fitz.Rect]:
    cells: list[fitz.Rect] = []
    for index, rect in enumerate(clusters):
        left = 0.0
        right = float(page_rect.width)
        top = 0.0
        bottom = float(page_rect.height)
        for other_index, other in enumerate(clusters):
            if index == other_index:
                continue
            vertical_overlap = min(rect.y1, other.y1) - max(rect.y0, other.y0)
            horizontal_overlap = min(rect.x1, other.x1) - max(rect.x0, other.x0)
            if vertical_overlap > min(rect.height, other.height) * 0.12:
                if other.x1 <= rect.x0:
                    left = max(left, (other.x1 + rect.x0) / 2)
                elif other.x0 >= rect.x1:
                    right = min(right, (rect.x1 + other.x0) / 2)
            if horizontal_overlap > min(rect.width, other.width) * 0.12:
                if other.y1 <= rect.y0:
                    top = max(top, (other.y1 + rect.y0) / 2)
                elif other.y0 >= rect.y1:
                    bottom = min(bottom, (rect.y1 + other.y0) / 2)
        cells.append(fitz.Rect(left, top, right, bottom))
    return cells


def merge_horizontal_bar_groups(clusters: list[fitz.Rect], page_rect: fitz.Rect) -> list[fitz.Rect]:
    if len(clusters) < 3:
        return clusters
    page_width = float(page_rect.width)
    used: set[int] = set()
    merged: list[fitz.Rect] = []
    for index, rect in enumerate(clusters):
        if index in used:
            continue
        group = [index]
        for other_index, other in enumerate(clusters):
            if other_index == index or other_index in used:
                continue
            vertical_overlap = min(rect.y1, other.y1) - max(rect.y0, other.y0)
            overlap_ratio = vertical_overlap / max(1.0, min(rect.height, other.height))
            baseline_delta = abs(rect.y1 - other.y1)
            center_delta = abs((rect.y0 + rect.y1) / 2 - (other.y0 + other.y1) / 2)
            narrow_pair = rect.width < page_width * 0.34 and other.width < page_width * 0.34
            if narrow_pair and overlap_ratio > 0.35 and (baseline_delta < 34 or center_delta < 72):
                group.append(other_index)
        if len(group) >= 3:
            union = fitz.Rect(clusters[group[0]])
            for item in group[1:]:
                union |= clusters[item]
            used.update(group)
            merged.append(union)
        else:
            used.add(index)
            merged.append(rect)
    return sorted(merged, key=lambda r: (r.y0, r.x0))


def expand_visual_bbox(rect: fitz.Rect, blocks: list[dict[str, Any]], page_rect: fitz.Rect, cell: fitz.Rect | None = None) -> list[float]:
    allowed = cell or page_rect
    expanded = expand_rect(rect, page_rect, side=16, up=40, down=42) & allowed
    for block in blocks:
        block_rect = fitz.Rect(block["bbox"]) & allowed
        text = clean_text(block["text"])
        if not text or block_rect.is_empty:
            continue
        horizontal_overlap = min(expanded.x1, block_rect.x1) - max(expanded.x0, block_rect.x0)
        near_title = block_rect.y1 >= expanded.y0 - 52 and block_rect.y0 <= expanded.y0 + 12
        near_source = block_rect.y0 <= expanded.y1 + 40 and block_rect.y1 >= expanded.y1 - 8
        inside_or_axis = block_rect.y0 <= expanded.y1 + 10 and block_rect.y1 >= expanded.y0 - 10
        compact = len(text) <= 220 or bool(UNIT_RE.search(text)) or bool(CHART_SIGNAL_RE.search(text))
        mostly_aligned = horizontal_overlap > min(expanded.width, block_rect.width) * 0.12
        if mostly_aligned and compact and (near_title or near_source or inside_or_axis):
            expanded |= block_rect
            expanded &= allowed
    expanded = expand_rect(expanded, page_rect, side=8, up=6, down=8) & allowed
    return [
        round(max(0.0, expanded.x0), 2),
        round(max(0.0, expanded.y0), 2),
        round(min(float(page_rect.width), expanded.x1), 2),
        round(min(float(page_rect.height), expanded.y1), 2),
    ]


def prune_visual_bboxes(bboxes: list[list[float]], page_rect: fitz.Rect) -> list[list[float]]:
    page_area = float(page_rect.get_area())
    rects = [fitz.Rect(bbox) for bbox in bboxes]
    filtered: list[fitz.Rect] = []
    for rect in sorted(rects, key=lambda r: r.get_area(), reverse=True):
        area = float(rect.get_area())
        if area < page_area * 0.018 or area > page_area * 0.72:
            continue
        if rect.width < 80 or rect.height < 45:
            continue
        if any(rect_overlap_ratio(rect, kept) > 0.82 for kept in filtered):
            continue
        filtered.append(rect)
    filtered = sorted(filtered, key=lambda r: (r.y0, r.x0))
    return [[round(v, 2) for v in [r.x0, r.y0, r.x1, r.y1]] for r in filtered[:8]]


def content_bbox_from_blocks(page: fitz.Page, blocks: list[dict[str, Any]]) -> list[float]:
    page_rect = fitz.Rect(page.rect)
    width = float(page_rect.width)
    height = float(page_rect.height)
    body = fitz.Rect(width * 0.03, height * 0.04, width * 0.97, height * 0.92)
    rect: fitz.Rect | None = None
    for block in blocks:
        block_rect = fitz.Rect(block["bbox"]) & body
        text = clean_text(block["text"])
        if block_rect.is_empty or not text or is_running_footer(text):
            continue
        if len(text) <= 3 and block_rect.y0 < height * 0.08:
            continue
        rect = block_rect if rect is None else rect | block_rect
    if rect is None:
        return page_body_bbox(page, blocks)
    rect = expand_rect(rect, page_rect, side=8, up=8, down=8)
    return [round(v, 2) for v in [rect.x0, rect.y0, rect.x1, rect.y1]]


def crop_quality_metrics(bbox: list[float], page_bbox: list[float]) -> dict[str, Any]:
    crop = fitz.Rect(bbox)
    page = fitz.Rect(page_bbox)
    page_area = max(1.0, float(page.get_area()))
    area_ratio = float(crop.get_area()) / page_area
    width_ratio = float(crop.width) / max(1.0, float(page.width))
    height_ratio = float(crop.height) / max(1.0, float(page.height))
    flags: list[str] = []
    if area_ratio > 0.72 or (width_ratio > 0.90 and height_ratio > 0.82):
        flags.append("large_crop")
    if area_ratio < 0.025:
        flags.append("tiny_crop")
    aspect = float(crop.width) / max(1.0, float(crop.height))
    if aspect < 0.20 or aspect > 8.0:
        flags.append("extreme_aspect")
    return {
        "area_ratio": round(area_ratio, 3),
        "width_ratio": round(width_ratio, 3),
        "height_ratio": round(height_ratio, 3),
        "aspect_ratio": round(aspect, 3),
        "flags": flags,
    }


def is_valid_visual_candidate(candidate: ChartCandidate) -> bool:
    text = "\n".join([candidate.title, candidate.nearby_text, candidate.source_note, candidate.unit_hint])
    title_text = "\n".join([candidate.title, candidate.caption, candidate.source_note])
    low = normalize_text(text)
    title_low = normalize_text(title_text)
    numbers = candidate.numbers or []
    if candidate.expected_match:
        return True
    if candidate.candidate_score >= 0.35:
        return True
    if candidate.candidate_tier in {"tier_1_high_confidence", "tier_2_possible_visual"}:
        return True
    if "drawn_or_image_object" in set(candidate.candidate_signals or []) and len(numbers) >= 2:
        return True
    if candidate.source_note and (candidate.unit_hint or len(numbers) >= 4):
        return True
    chart_terms = [" chart", " figure", " fig.", " exhibit", " table"]
    chinese_terms = ["资料来源", "数据来源", "来源", "图表"]
    source_terms = ["source:", "sources:"]
    if (any(term in f" {title_low}" for term in chart_terms) or any(term in low for term in source_terms) or any(term in title_text for term in chinese_terms) or re.search(r"图\s*\d+|表\s*\d+", title_text)) and len(numbers) >= 3:
        return True
    if candidate.unit_hint and len(numbers) >= 12:
        return True
    if len(numbers) >= 18:
        return True
    candidate.warnings.append("low_confidence_candidate_kept_for_visual_gate")
    return True


def rect_overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    return float(inter.get_area()) / max(1.0, min(float(a.get_area()), float(b.get_area())))


def expand_rect(rect: fitz.Rect, page_rect: fitz.Rect, side: float, up: float, down: float) -> fitz.Rect:
    return fitz.Rect(
        max(0.0, rect.x0 - side),
        max(0.0, rect.y0 - up),
        min(float(page_rect.width), rect.x1 + side),
        min(float(page_rect.height), rect.y1 + down),
    )


def nearby_text_for_bbox(blocks: list[dict[str, Any]], bbox: list[float]) -> str:
    x0, y0, x1, y1 = bbox
    relevant = []
    for block in blocks:
        bx0, by0, bx1, by1 = block["bbox"]
        horizontal_overlap = min(x1, bx1) - max(x0, bx0)
        close_vertical = by1 >= y0 - 130 and by0 <= y1 + 170
        if horizontal_overlap > -80 and close_vertical:
            relevant.append((by0, block["text"]))
    return "\n".join(text for _, text in sorted(relevant))


def expand_bbox(bbox: list[float], page_rect: fitz.Rect, up: float, down: float, side: float) -> list[float]:
    x0, y0, x1, y1 = bbox
    return [
        max(0.0, x0 - side),
        max(0.0, y0 - up),
        min(float(page_rect.width), x1 + side),
        min(float(page_rect.height), y1 + down),
    ]


def page_body_bbox(page: fitz.Page, blocks: list[dict[str, Any]]) -> list[float]:
    width = float(page.rect.width)
    height = float(page.rect.height)
    margin_x = width * 0.01
    return [margin_x, height * 0.035, width - margin_x, height * 0.93]


def is_running_footer(text: str) -> bool:
    clean = clean_text(text)
    if len(clean) > 120:
        return False
    return bool(re.search(r"goldman sachs asset management\s+\d+$|^\d+$|important information|disclosures", clean, re.IGNORECASE))


def bbox_area(bbox: list[float]) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def infer_title(text: str) -> str:
    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
    for line in lines:
        if TITLE_STOP_RE.search(line):
            continue
        if CHART_SIGNAL_RE.search(line) or 8 <= len(line) <= 160:
            return line[:180]
    return lines[0][:180] if lines else ""


def infer_source_note(text: str) -> str:
    for line in text.splitlines():
        clean = clean_text(line)
        if re.search(r"\b(source|sources)\b|资料来源|数据来源|来源", clean, re.IGNORECASE):
            return clean[:260]
    return ""


def infer_unit_hint(text: str) -> str:
    matches = UNIT_RE.findall(text or "")
    seen: list[str] = []
    for match in matches:
        value = match if isinstance(match, str) else match[0]
        if value and value not in seen:
            seen.append(value)
    return ", ".join(seen[:8])


def infer_chart_kind(text: str) -> str:
    low = normalize_text(text)
    if any(token in low for token in ["line", "trend", "time series", "走势", "时间"]):
        return "line_or_time_series"
    if any(token in low for token in ["bar", "rank", "排名", "占比"]):
        return "bar_or_comparison"
    if any(token in low for token in ["table", "表"]):
        return "table"
    if any(token in low for token in ["scatter", "matrix", "heatmap"]):
        return "matrix_or_scatter"
    return "unknown"


def likely_chart_page(text: str) -> bool:
    return len(extract_numbers(text)) >= 20 and bool(re.search(r"%|bps|source|资料来源|图|表", text, re.IGNORECASE))


def is_analytical_chart_page(text: str) -> bool:
    low = normalize_text(text)
    numbers = extract_numbers(text)
    source_signal = bool(re.search(r"\bsource[s]?:|资料来源|数据来源|来源", text, re.IGNORECASE))
    chart_signal = bool(re.search(r"figures in focus|figure|exhibit|chart|table|图表|图\s*\d+|表\s*\d+", text, re.IGNORECASE))
    unit_signal = bool(UNIT_RE.search(text))
    if source_signal and (unit_signal or len(numbers) >= 4):
        return True
    if chart_signal and unit_signal and len(numbers) >= 3:
        return True
    if "table of contents" in low or "key themes for" in low:
        return False
    return False


def is_chart_like_context(text: str) -> bool:
    if CHART_SIGNAL_RE.search(text):
        return True
    numbers = extract_numbers(text)
    return len(numbers) >= 4 and bool(UNIT_RE.search(text))


def match_expected_chart(candidate: ChartCandidate, expected: list[dict[str, Any]]) -> None:
    blob = normalize_text(" ".join([candidate.title, candidate.nearby_text]))
    best = ""
    best_score = 0
    for item in expected:
        desc = str(item.get("title_or_description") or "")
        tokens = tokenish(desc)
        if not tokens:
            continue
        overlap = len(tokens & tokenish(blob))
        ratio = overlap / max(1, len(tokens))
        score = overlap if ratio >= 0.45 and overlap >= 3 else 0
        if score > best_score:
            best_score = score
            best = desc
    if best_score >= 2:
        candidate.expected_match = best


def tokenish(text: str) -> set[str]:
    stop = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "amid",
        "focus",
        "chart",
        "table",
        "figure",
        "figures",
        "events",
        "source",
        "sources",
        "investment",
        "market",
        "markets",
    }
    return {token for token in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{3,}", normalize_text(text or "")) if token not in stop}


def stable_key(page_index: int, bbox: list[float], text: str) -> str:
    rounded = ",".join(str(round(v / 12) * 12) for v in bbox)
    return f"{page_index}:{rounded}:{short_hash(text)}"


def short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:8]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
