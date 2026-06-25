from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from chart_extractor import extract_html_charts
from eval_utils import ROOT, extract_dates, extract_numbers, write_json


DEFAULT_HIDE_SELECTORS = [
    "[class*='cookie' i]",
    "[id*='cookie' i]",
    "[class*='consent' i]",
    "[id*='consent' i]",
    "[class*='newsletter' i]",
    "[id*='newsletter' i]",
    "[class*='subscribe' i]",
    "[id*='subscribe' i]",
    "[class*='modal' i]",
    "[class*='popup' i]",
    "[class*='overlay' i]",
    "[class*='share' i]",
    "[class*='social' i]",
    "[class*='ad-' i]",
    "[id*='ad-' i]",
]


def find_chrome(explicit_path: str | None = None) -> Path | None:
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    candidates.extend(
        [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def read_html(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:10]


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def build_resource_audit(soup: BeautifulSoup, html_path: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for tag_name, attr in [("img", "src"), ("script", "src"), ("link", "href"), ("source", "src")]:
        for node in soup.find_all(tag_name):
            value = node.get(attr)
            if not value:
                continue
            rows.append(classify_resource(str(value), html_path, tag_name, attr))
    failed = [row for row in rows if row["status"] not in {"inline", "local_exists", "remote"}]
    remote = [row for row in rows if row["status"] == "remote"]
    return {
        "resource_count": len(rows),
        "remote_resource_count": len(remote),
        "failed_static_resource_count": len(failed),
        "resources": rows[:500],
    }


def classify_resource(value: str, html_path: Path, tag: str, attr: str) -> dict[str, Any]:
    value = value.strip()
    parsed = urlparse(value)
    status = "unknown"
    resolved = ""
    if value.startswith("data:"):
        status = "inline"
        resolved = "data-uri"
    elif parsed.scheme in {"http", "https"}:
        status = "remote"
        resolved = value
    elif parsed.scheme:
        status = f"unsupported_scheme:{parsed.scheme}"
        resolved = value
    else:
        candidates = []
        if value.startswith("/"):
            candidates.append(ROOT / unquote(value.lstrip("/")))
            candidates.append(html_path.parent / unquote(value.lstrip("/")))
        else:
            candidates.append(html_path.parent / unquote(value))
        hit = next((candidate for candidate in candidates if candidate.exists()), None)
        status = "local_exists" if hit else "local_missing"
        resolved = str(hit or candidates[0])
    return {"tag": tag, "attr": attr, "value": value[:800], "status": status, "resolved": resolved}


def normalize_html(raw_html: str, source_path: Path, out_dir: Path) -> tuple[str, dict[str, Any]]:
    soup = BeautifulSoup(raw_html, "html.parser")
    removed = []
    for selector in DEFAULT_HIDE_SELECTORS:
        for node in soup.select(selector):
            text = clean_text(node.get_text(" ", strip=True))
            if should_hide_overlay_node(node, text):
                removed.append({"selector": selector, "tag": node.name, "text": text[:160]})
                node.decompose()
    if soup.head is None:
        head = soup.new_tag("head")
        if soup.html:
            soup.html.insert(0, head)
        else:
            soup.insert(0, head)
    base = soup.find("base")
    if base is None:
        base = soup.new_tag("base", href=source_path.parent.resolve().as_uri() + "/")
        soup.head.insert(0, base)
    style = soup.new_tag("style")
    style.string = "\n".join(
        [
            "html { scroll-behavior: auto !important; }",
            "body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }",
            ".strategy-html-adapter-hidden { display: none !important; }",
            "@media print {",
            "  figure, table, img, svg, canvas, section, article, .card, .panel, .chart, .figure, .exhibit { break-inside: avoid; page-break-inside: avoid; }",
            "  h1, h2, h3, h4 { break-after: avoid; page-break-after: avoid; }",
            "}",
        ]
    )
    soup.head.append(style)
    normalized = str(soup)
    (out_dir / "normalized.html").write_text(normalized, encoding="utf-8")
    return normalized, {"removed_overlay_like_nodes": removed[:100], "removed_count": len(removed)}


def should_hide_overlay_node(node: Any, text: str) -> bool:
    attrs = getattr(node, "attrs", None) or {}
    tag_name = str(getattr(node, "name", "") or "").lower()
    if tag_name in {"html", "body", "main", "article"}:
        return False
    low = " ".join(
        [
            str(attrs.get("class") or ""),
            str(attrs.get("id") or ""),
            text,
        ]
    ).lower()
    overlay_terms = [
        "cookie",
        "consent",
        "privacy",
        "newsletter",
        "subscribe",
        "sign up",
        "share",
        "follow us",
        "connect with us",
        "advertisement",
        "广告",
        "订阅",
        "隐私",
        "同意",
    ]
    weak_overlay_terms = [
        "share",
        "follow us",
        "connect with us",
        "social",
    ]
    strong_overlay_terms = [term for term in overlay_terms if term not in weak_overlay_terms]
    if any(term in low for term in strong_overlay_terms):
        return len(text) < 1500
    if any(term in low for term in weak_overlay_terms):
        return len(text) < 360
    return len(text) < 80


def extract_text_payload(soup: BeautifulSoup) -> dict[str, Any]:
    for node in soup(["script", "style", "noscript"]):
        node.decompose()
    title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    headings = [clean_text(h.get_text(" ", strip=True)) for h in soup.find_all(["h1", "h2", "h3", "h4"]) if clean_text(h.get_text(" ", strip=True))]
    text = clean_text(soup.get_text(" ", strip=True))
    return {
        "title": title,
        "headings": headings[:80],
        "text": text[:80000],
        "text_length": len(text),
        "numbers": extract_numbers(text)[:800],
        "dates": extract_dates(text)[:300],
    }


def capture_screenshot(chrome: Path | None, html_path: Path, out_path: Path, width: int, height: int, timeout: int) -> dict[str, Any]:
    if chrome is None:
        return {"ok": False, "reason": "chrome_not_found", "screenshot_path": None}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(chrome),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--hide-scrollbars",
        "--allow-file-access-from-files",
        "--disable-features=Translate,OptimizationHints",
        f"--window-size={width},{height}",
        f"--screenshot={out_path.resolve()}",
        html_path.resolve().as_uri(),
    ]
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    return {
        "ok": proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0,
        "returncode": proc.returncode,
        "elapsed_seconds": round(time.time() - started, 2),
        "screenshot_path": str(out_path),
        "screenshot_size_bytes": out_path.stat().st_size if out_path.exists() else 0,
        "stdout_tail": (proc.stdout or "")[-500:],
        "stderr_tail": (proc.stderr or "")[-500:],
    }


def render_pdf(chrome: Path | None, html_path: Path, out_path: Path, timeout: int) -> dict[str, Any]:
    if chrome is None:
        return {"ok": False, "reason": "chrome_not_found", "pdf_path": None}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(chrome),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--allow-file-access-from-files",
        "--disable-features=Translate,OptimizationHints",
        "--no-pdf-header-footer",
        f"--print-to-pdf={out_path.resolve()}",
        html_path.resolve().as_uri(),
    ]
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    return {
        "ok": proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0,
        "returncode": proc.returncode,
        "elapsed_seconds": round(time.time() - started, 2),
        "pdf_path": str(out_path),
        "pdf_size_bytes": out_path.stat().st_size if out_path.exists() else 0,
        "stdout_tail": (proc.stdout or "")[-500:],
        "stderr_tail": (proc.stderr or "")[-500:],
    }


def copy_or_download_remote_image(src: str, html_path: Path, base_url: str | None, out_dir: Path) -> str | None:
    parsed = urlparse(src)
    try:
        if src.startswith("data:"):
            return None
        if parsed.scheme in {"http", "https"}:
            response = requests.get(src, timeout=20, headers={"User-Agent": "Mozilla/5.0 StrategyReportVerifier HTMLAdapter"})
            response.raise_for_status()
            suffix = Path(parsed.path).suffix or ".bin"
            out = out_dir / f"remote_{short_hash(src)}{suffix}"
            out.write_bytes(response.content)
            return str(out)
        candidates = []
        if src.startswith("/"):
            candidates.append(ROOT / unquote(src.lstrip("/")))
            candidates.append(html_path.parent / unquote(src.lstrip("/")))
        else:
            candidates.append(html_path.parent / unquote(src))
        hit = next((candidate for candidate in candidates if candidate.exists() and candidate.is_file()), None)
        if hit:
            out = out_dir / f"local_{short_hash(str(hit))}{hit.suffix}"
            shutil.copy2(hit, out)
            return str(out)
        if base_url:
            return copy_or_download_remote_image(urljoin(base_url, src), html_path, None, out_dir)
    except Exception:
        return None
    return None


def adapt_html_report(
    html_path: Path,
    out_dir: Path,
    report_id: str | None = None,
    max_charts: int = 24,
    screenshot_width: int = 1440,
    screenshot_height: int = 2200,
    chrome_path: str | None = None,
) -> dict[str, Any]:
    html_path = html_path.resolve()
    report_id = report_id or html_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_html = read_html(html_path)
    raw_soup = BeautifulSoup(raw_html, "html.parser")
    resource_audit = build_resource_audit(raw_soup, html_path)
    normalized_html, cleanup_audit = normalize_html(raw_html, html_path, out_dir)
    normalized_path = out_dir / "normalized.html"
    normalized_soup = BeautifulSoup(normalized_html, "html.parser")
    text_payload = extract_text_payload(BeautifulSoup(normalized_html, "html.parser"))
    write_json(out_dir / "report_text.json", text_payload)

    chrome = find_chrome(chrome_path)
    screenshot = capture_screenshot(
        chrome=chrome,
        html_path=normalized_path,
        out_path=out_dir / "screenshots" / f"{report_id}_page_001.png",
        width=screenshot_width,
        height=screenshot_height,
        timeout=45,
    )
    rendered_pdf = render_pdf(
        chrome=chrome,
        html_path=normalized_path,
        out_path=out_dir / "rendered.pdf",
        timeout=60,
    )
    chart_dir = out_dir / "chart_inventory" / report_id
    chart_dir.mkdir(parents=True, exist_ok=True)
    candidates = extract_html_charts(normalized_path, report_id, chart_dir, max_charts=max_charts)
    full_page_image = screenshot.get("screenshot_path") if screenshot.get("ok") else None
    candidate_dicts = []
    for candidate in candidates:
        item = candidate.to_dict()
        if full_page_image:
            item["page_image_path"] = full_page_image
        candidate_dicts.append(item)
    chart_inventory = {
        "report_id": report_id,
        "source_path": str(html_path),
        "normalized_path": str(normalized_path),
        "source_format": "html",
        "chart_count": len(candidate_dicts),
        "charts": candidate_dicts,
        "audit": {
            "resource_audit": resource_audit,
            "cleanup_audit": cleanup_audit,
            "screenshot": screenshot,
            "rendered_pdf": rendered_pdf,
        },
    }
    write_json(out_dir / "chart_candidates.json", chart_inventory)
    manifest = {
        "adapter_version": "html_adapter_v0.1",
        "report_id": report_id,
        "source_path": str(html_path),
        "normalized_html": str(normalized_path),
        "text_json": str(out_dir / "report_text.json"),
        "chart_candidates_json": str(out_dir / "chart_candidates.json"),
        "screenshot": screenshot,
        "rendered_pdf": rendered_pdf,
        "resource_audit": {
            "resource_count": resource_audit["resource_count"],
            "remote_resource_count": resource_audit["remote_resource_count"],
            "failed_static_resource_count": resource_audit["failed_static_resource_count"],
        },
        "cleanup_audit": cleanup_audit,
        "text_length": text_payload["text_length"],
        "heading_count": len(text_payload["headings"]),
        "chart_candidate_count": len(candidate_dicts),
        "pagination_strategy": {
            "mode": "chrome_print_to_pdf",
            "risk": "HTML has no native report pages; Chrome pagination may still split very tall visuals despite break-inside CSS.",
            "mitigation": "normalized.html injects print CSS to avoid breaking common visual containers; future browser-backed virtual pages should use DOM bboxes.",
        },
        "warnings": adapter_warnings(resource_audit, screenshot, rendered_pdf, len(candidate_dicts), text_payload["text_length"]),
    }
    write_json(out_dir / "render_manifest.json", manifest)
    return {"manifest": manifest, "text": text_payload, "chart_inventory": chart_inventory}


def adapter_warnings(resource_audit: dict[str, Any], screenshot: dict[str, Any], rendered_pdf: dict[str, Any], chart_count: int, text_length: int) -> list[str]:
    warnings = []
    if resource_audit.get("failed_static_resource_count", 0) > 0:
        warnings.append("html_static_resource_missing")
    if resource_audit.get("remote_resource_count", 0) > 0:
        warnings.append("html_has_external_resources")
    if not screenshot.get("ok"):
        warnings.append("html_screenshot_failed")
    if not rendered_pdf.get("ok"):
        warnings.append("html_pdf_render_failed")
    if chart_count == 0:
        warnings.append("html_no_chart_candidates")
    if text_length < 2000:
        warnings.append("html_text_too_short_for_strategy_report")
    return warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze/adapt an HTML strategy report into verifier-friendly artifacts.")
    parser.add_argument("--html", type=Path, required=True, help="Local HTML file to adapt.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output adapter package directory.")
    parser.add_argument("--report-id", default=None)
    parser.add_argument("--max-charts", type=int, default=24)
    parser.add_argument("--screenshot-width", type=int, default=1440)
    parser.add_argument("--screenshot-height", type=int, default=2200)
    parser.add_argument("--chrome-path", default=None)
    args = parser.parse_args()
    result = adapt_html_report(
        html_path=args.html,
        out_dir=args.out_dir,
        report_id=args.report_id,
        max_charts=args.max_charts,
        screenshot_width=args.screenshot_width,
        screenshot_height=args.screenshot_height,
        chrome_path=args.chrome_path,
    )
    print(json.dumps(result["manifest"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
