from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from eval_utils import ROOT


DEFAULT_ARCHIVE_MANIFEST = ROOT / "dataset_build" / "manifests" / "html_archive_manifest.jsonl"
DEFAULT_PRIORITY_MANIFEST = ROOT / "evals" / "strategy_report" / "html_localization_candidates.json"
DEFAULT_JSON = ROOT / "evals" / "strategy_report" / "results" / "v2_html_candidate_inventory.json"
DEFAULT_MARKDOWN = ROOT / "evals" / "strategy_report" / "results" / "v2_html_candidate_inventory.md"

RESOURCE_ATTRS = (
    ("img", "src"),
    ("source", "src"),
    ("script", "src"),
    ("link", "href"),
    ("video", "poster"),
    ("object", "data"),
)
STRATEGY_TERMS = (
    "outlook", "strategy", "market", "macro", "portfolio", "allocation",
    "equity", "fixed income", "credit", "rates", "investment", "economic",
    "展望", "策略", "市场", "宏观", "配置", "权益", "固收", "利率", "信用", "投资",
)
LISTING_TERMS = (
    "contact us", "latest insights", "all insights", "events", "podcasts",
    "investment stewardship", "interactive charts", "research library",
    "联系我们", "最新观点", "研究报告列表", "报告列表",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def detect_language(soup: BeautifulSoup, text: str) -> str:
    html_lang = str((soup.html or {}).get("lang") or "").lower()
    if html_lang.startswith("zh"):
        return "zh"
    if html_lang.startswith("en"):
        return "en"
    sample = text[:12000]
    cjk = len(re.findall(r"[\u3400-\u9fff]", sample))
    letters = len(re.findall(r"[A-Za-z]", sample))
    return "zh" if cjk > max(80, letters * 0.2) else "en"


def extract_date(soup: BeautifulSoup) -> str | None:
    keys = (
        ("meta", "property", "article:published_time", "content"),
        ("meta", "name", "date", "content"),
        ("meta", "name", "publish-date", "content"),
        ("meta", "name", "publication_date", "content"),
    )
    for tag, key, value, attr in keys:
        node = soup.find(tag, attrs={key: value})
        if node and node.get(attr):
            return clean_text(str(node.get(attr)))[:40]
    time_node = soup.find("time")
    if time_node:
        return clean_text(str(time_node.get("datetime") or time_node.get_text(" ", strip=True)))[:40] or None
    return None


def resource_audit(soup: BeautifulSoup, html_path: Path) -> dict[str, Any]:
    refs: list[str] = []
    for tag, attr in RESOURCE_ATTRS:
        for node in soup.find_all(tag):
            value = clean_text(str(node.get(attr) or ""))
            if value:
                refs.append(value)
            srcset = clean_text(str(node.get("srcset") or ""))
            if srcset:
                refs.extend(part.strip().split(" ", 1)[0] for part in srcset.split(",") if part.strip())
    for node in soup.find_all(style=True):
        refs.extend(re.findall(r"url\([\"']?([^\"')]+)", str(node.get("style") or ""), re.I))
    for node in soup.find_all("style"):
        refs.extend(re.findall(r"url\([\"']?([^\"')]+)", node.get_text(), re.I))

    remote = 0
    missing = 0
    root_relative = 0
    local = 0
    for ref in refs:
        if ref.startswith(("data:", "#", "javascript:", "mailto:", "tel:")):
            continue
        if ref.startswith(("//", "http://", "https://")):
            remote += 1
            continue
        if ref.startswith("/"):
            root_relative += 1
            missing += 1
            continue
        local += 1
        path = (html_path.parent / ref.split("?", 1)[0].split("#", 1)[0]).resolve()
        if not path.exists():
            missing += 1
    return {
        "resource_count": len(refs),
        "remote_count": remote,
        "root_relative_count": root_relative,
        "local_count": local,
        "missing_count": missing,
    }


def assess(title: str, url: str, text: str, metrics: dict[str, Any], priority: bool) -> tuple[str, list[str], int]:
    haystack = f"{title} {url} {text[:5000]}".lower()
    reasons: list[str] = []
    strategy_hits = sum(term in haystack for term in STRATEGY_TERMS)
    listing_hits = sum(term in haystack for term in LISTING_TERMS)
    text_len = metrics["text_length"]

    if text_len < 1200:
        reasons.append("正文过短")
    if listing_hits >= 2 and text_len < 8000:
        reasons.append("疑似导航、聚合或列表页")
    if strategy_hits < 2:
        reasons.append("策略研究信号不足")

    score = min(text_len // 500, 30)
    score += min(strategy_hits * 4, 24)
    score += min(metrics["heading_count"], 10)
    score += min((metrics["image_count"] + metrics["svg_count"] + metrics["canvas_count"]) * 2, 16)
    score += min(metrics["table_count"] * 2, 8)
    score -= min(metrics["remote_count"], 20)
    score -= min(metrics["missing_count"] * 2, 24)
    if priority:
        score += 30
    if reasons:
        score -= 25

    if "正文过短" in reasons or "疑似导航、聚合或列表页" in reasons:
        status = "exclude_preliminary"
    elif priority or (text_len >= 2500 and strategy_hits >= 3):
        status = "localize_priority"
    else:
        status = "manual_review"
    return status, reasons, score


def inspect_row(row: dict[str, Any], priority_urls: set[str]) -> dict[str, Any]:
    path = ROOT / row["file_path"]
    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "html.parser")
    for node in soup(["script", "style", "noscript"]):
        node.extract()
    text = clean_text(soup.get_text(" ", strip=True))
    title = clean_text((soup.title.get_text(" ", strip=True) if soup.title else "") or "")
    h1 = soup.find("h1")
    if h1 and len(clean_text(h1.get_text(" ", strip=True))) > 10:
        title = clean_text(h1.get_text(" ", strip=True))

    # Reparse because style/script nodes are needed for resource inspection.
    resource_soup = BeautifulSoup(raw, "html.parser")
    resources = resource_audit(resource_soup, path)
    metrics = {
        "text_length": len(text),
        "heading_count": len(resource_soup.find_all(["h1", "h2", "h3", "h4"])),
        "table_count": len(resource_soup.find_all("table")),
        "image_count": len(resource_soup.find_all("img")),
        "svg_count": len(resource_soup.find_all("svg")),
        "canvas_count": len(resource_soup.find_all("canvas")),
        **resources,
    }
    priority = row["url"] in priority_urls
    status, reasons, score = assess(title, row["url"], text, metrics, priority)
    return {
        "candidate_id": hashlib.sha256(row["url"].encode("utf-8")).hexdigest()[:12],
        "source_url": row["url"],
        "local_path": row["file_path"],
        "institution": row.get("institution"),
        "language": detect_language(resource_soup, text),
        "subtype": row.get("subtype_hint"),
        "title": title,
        "published_date": extract_date(resource_soup),
        **metrics,
        "priority_manifest_match": priority,
        "preliminary_status": status,
        "preliminary_reasons": reasons,
        "priority_score": score,
        "manual_content_review": "pending",
    }


def markdown_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# V2 HTML 候选清点",
        "",
        f"生成时间：{payload['generated_at']}",
        "",
        "## 摘要",
        "",
        f"- 归档记录：{summary['archive_rows']}",
        f"- 唯一 URL：{summary['unique_urls']}",
        f"- 优先本地化：{summary['status_counts'].get('localize_priority', 0)}",
        f"- 待人工复核：{summary['status_counts'].get('manual_review', 0)}",
        f"- 初步排除：{summary['status_counts'].get('exclude_preliminary', 0)}",
        "",
        "说明：状态由可复现的启发式初筛产生，`manual_content_review` 仍为 `pending`；",
        "进入核心集前仍须逐份完成人工内容和浏览器视觉审查。",
        "",
        "## 优先候选",
        "",
        "| 分数 | 机构 | 语言 | subtype | 正文 | 图/表 | remote/missing | 标题 |",
        "| ---: | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    candidates = [item for item in payload["candidates"] if item["preliminary_status"] == "localize_priority"]
    for item in candidates[:40]:
        visual_count = item["image_count"] + item["svg_count"] + item["canvas_count"] + item["table_count"]
        title = item["title"].replace("|", "\\|")[:100]
        lines.append(
            f"| {item['priority_score']} | {item['institution']} | {item['language']} | "
            f"{item['subtype']} | {item['text_length']} | {visual_count} | "
            f"{item['remote_count']}/{item['missing_count']} | {title} |"
        )
    lines.extend(["", "## 机构分布", "", "| 机构 | 数量 |", "| --- | ---: |"])
    for institution, count in summary["institution_counts"].items():
        lines.append(f"| {institution} | {count} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a reproducible inventory of archived strategy-report HTML candidates.")
    parser.add_argument("--archive-manifest", type=Path, default=DEFAULT_ARCHIVE_MANIFEST)
    parser.add_argument("--priority-manifest", type=Path, default=DEFAULT_PRIORITY_MANIFEST)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    archive_rows = [row for row in read_jsonl(args.archive_manifest) if row.get("status") == "archived"]
    latest_by_url = {row["url"]: row for row in archive_rows if row.get("url") and row.get("file_path")}
    priority_urls = {
        row["url"]
        for row in read_json(args.priority_manifest).get("samples", [])
        if row.get("enabled", True)
    }
    candidates = []
    failures = []
    for row in latest_by_url.values():
        try:
            candidates.append(inspect_row(row, priority_urls))
        except Exception as exc:  # noqa: BLE001
            failures.append({"url": row.get("url"), "file_path": row.get("file_path"), "error": repr(exc)})
    candidates.sort(key=lambda item: (-item["priority_score"], item["institution"] or "", item["title"]))
    status_counts = Counter(item["preliminary_status"] for item in candidates)
    institution_counts = Counter(item["institution"] or "Unknown" for item in candidates)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "archive_manifest": str(args.archive_manifest),
            "priority_manifest": str(args.priority_manifest),
        },
        "summary": {
            "archive_rows": len(archive_rows),
            "unique_urls": len(latest_by_url),
            "candidate_count": len(candidates),
            "failure_count": len(failures),
            "status_counts": dict(status_counts),
            "institution_counts": dict(institution_counts.most_common()),
            "language_counts": dict(Counter(item["language"] for item in candidates)),
        },
        "candidates": candidates,
        "failures": failures,
    }
    write_json(args.json_out, payload)
    args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_out.write_text(markdown_report(payload), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
