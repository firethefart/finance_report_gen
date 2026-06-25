from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from common import USER_AGENT, load_json, write_json

NOISE_DOMAINS = (
    "facebook.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "podcasts.apple.com",
    "my.accessportals.com",
)

NOISE_URL_PARTS = (
    "sign-on",
    "login",
    "share?",
    "sharer",
    "manage_your_subscriptions",
    "investor-rights",
    "modern-slavery",
    "target-market-statement",
    "value-assessment-statement",
    "key_features",
    "tax-strategy",
    "gender-pay",
    "legal/",
    "javascript:",
    "otc.",
    "/otc/",
    "landingpage",
    "aistudio",
    "/alpha",
    "doclist",
)

REPORT_PDF_SIGNALS = (
    "outlook",
    "market",
    "macro",
    "strategy",
    "investment",
    "portfolio",
    "fixed-income",
    "equity",
    "alternatives",
    "research",
    "perspectives",
    "vemo",
    "eotm",
    "whitepaper",
    "策略",
    "研究",
    "研报",
    "报告",
    "年度策略",
    "中期策略",
    "投资策略",
    "市场策略",
    "宏观策略",
    "行业比较",
    "资产配置",
    "大类资产",
    "展望",
)


def fetch(session: requests.Session, url: str, timeout: int) -> tuple[int | None, str, str | None]:
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=True)
        ctype = resp.headers.get("content-type", "").lower()
        if "text/html" in ctype:
            return resp.status_code, ctype, resp.text
        snippet = resp.content[:500].decode("utf-8", errors="ignore").lower()
        return resp.status_code, ctype, resp.text if "<html" in snippet else None
    except Exception as exc:  # noqa: BLE001
        return None, "", repr(exc)


def is_pdf_url(url: str) -> bool:
    parsed = urlparse(url)
    return ".pdf" in parsed.path.lower() or ".pdf" in parsed.query.lower()


def is_noise_url(url: str) -> bool:
    lowered = url.lower()
    host = urlparse(url).netloc.lower()
    return any(domain in host for domain in NOISE_DOMAINS) or any(part in lowered for part in NOISE_URL_PARTS)


def pdf_matches_report_scope(text: str, href: str, keywords: list[str]) -> bool:
    haystack = f"{text} {href}".lower()
    if is_noise_url(href):
        return False
    signals = tuple(keyword.lower().replace(" ", "-") for keyword in keywords) + REPORT_PDF_SIGNALS
    normalized = haystack.replace("_", "-").replace("%20", "-").replace(" ", "-")
    return any(signal in normalized for signal in signals)


def link_matches(text: str, href: str, keywords: list[str]) -> bool:
    if is_noise_url(href):
        return False
    haystack = f"{text} {href}".lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def discover_from_page(
    session: requests.Session,
    url: str,
    keywords: list[str],
    max_child_pages: int,
    request_timeout: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "url": url,
        "status": None,
        "content_type": "",
        "direct_pdf": is_pdf_url(url),
        "source_page_report_like": False,
        "pdf_links": [],
        "strategy_page_links": [],
        "child_pdf_links": [],
        "error": None,
    }
    if is_pdf_url(url):
        return result
    status, ctype, html_or_error = fetch(session, url, request_timeout)
    result["status"] = status
    result["content_type"] = ctype
    if status is None:
        result["error"] = html_or_error
        return result
    if not html_or_error or not isinstance(html_or_error, str):
        return result

    soup = BeautifulSoup(html_or_error, "html.parser")
    page_title = soup.title.get_text(" ", strip=True) if soup.title else ""
    page_heads = " ".join(head.get_text(" ", strip=True) for head in soup.find_all(["h1", "h2"], limit=4))
    page_text_sample = " ".join(soup.get_text(" ", strip=True).split())[:1000]
    result["source_page_report_like"] = link_matches(
        f"{page_title} {page_heads} {page_text_sample}",
        url,
        keywords,
    )
    seen_pages: set[str] = set()
    seen_pdfs: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"].strip()).split("#", 1)[0]
        text = " ".join(a.get_text(" ", strip=True).split())
        if is_pdf_url(href):
            if href not in seen_pdfs and pdf_matches_report_scope(text, href, keywords):
                seen_pdfs.add(href)
                result["pdf_links"].append({"url": href, "text": text})
        elif link_matches(text, href, keywords):
            if href not in seen_pages:
                seen_pages.add(href)
                result["strategy_page_links"].append({"url": href, "text": text})

    child_pdfs: set[str] = set()
    for page in result["strategy_page_links"][:max_child_pages]:
        child_status, _, child_html = fetch(session, page["url"], request_timeout)
        if child_status is None or not child_html or not isinstance(child_html, str):
            continue
        child_soup = BeautifulSoup(child_html, "html.parser")
        for a in child_soup.find_all("a", href=True):
            href = urljoin(page["url"], a["href"].strip()).split("#", 1)[0]
            text = a.get_text(" ", strip=True)
            if is_pdf_url(href) and href not in child_pdfs and pdf_matches_report_scope(text, href, keywords):
                child_pdfs.add(href)
                result["child_pdf_links"].append({"url": href, "from_page": page["url"], "text": text})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Estimate crawlable strategy report source volume.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("dataset_build/source_discovery_report.json"))
    parser.add_argument("--max-child-pages", type=int, default=12)
    parser.add_argument("--request-timeout", type=int, default=12)
    args = parser.parse_args()

    config = load_json(args.config)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    institutions = []
    for source in config["sources"]:
        pages = []
        all_pdfs: set[str] = set()
        all_pages: set[str] = set()
        child_pdfs: set[str] = set()
        for url in source["urls"]:
            page_result = discover_from_page(
                session,
                url,
                source.get("keywords", []),
                args.max_child_pages,
                args.request_timeout,
            )
            pages.append(page_result)
            if page_result["direct_pdf"]:
                all_pdfs.add(url)
            for item in page_result["pdf_links"]:
                all_pdfs.add(item["url"])
            for item in page_result["child_pdf_links"]:
                all_pdfs.add(item["url"])
                child_pdfs.add(item["url"])
            if page_result.get("source_page_report_like"):
                all_pages.add(url)
            for item in page_result["strategy_page_links"]:
                all_pages.add(item["url"])

        status_counts = collections.Counter(str(page["status"]) for page in pages)
        institutions.append(
            {
                "institution": source["institution"],
                "business_type": source.get("business_type"),
                "country_or_region": source.get("country_or_region"),
                "tested_urls": len(source["urls"]),
                "status_counts": dict(status_counts),
                "unique_direct_or_discovered_pdfs": len(all_pdfs),
                "unique_child_pdfs": len(child_pdfs),
                "unique_strategy_html_pages": len(all_pages),
                "estimated_crawlable_strategy_reports": len(all_pdfs) + len(all_pages),
                "pdf_samples": sorted(all_pdfs)[:20],
                "strategy_page_samples": sorted(all_pages)[:20],
                "page_results": pages,
            }
        )
        partial_summary = {
            "config": str(args.config),
            "institutions": institutions,
            "total_unique_report_like_items_estimate": sum(
                item["estimated_crawlable_strategy_reports"] for item in institutions
            ),
            "partial": True,
        }
        write_json(args.out, partial_summary)
        print(f"completed={source['institution']}", flush=True)

    summary = {
        "config": str(args.config),
        "institutions": institutions,
        "total_unique_report_like_items_estimate": sum(item["estimated_crawlable_strategy_reports"] for item in institutions),
        "notes": [
            "Counts are estimates from configured public URLs, not exhaustive site indexes.",
            "HTML report pages are counted separately from PDFs because several institutions publish strategy reports primarily as web articles.",
            "Duplicate regional mirrors and non-English duplicates should be de-duplicated during final dataset selection."
        ],
    }
    write_json(args.out, summary)
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    print(f"out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
