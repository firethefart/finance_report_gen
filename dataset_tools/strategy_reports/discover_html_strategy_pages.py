from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from common import USER_AGENT, slugify, utc_now_iso, write_json
from html_article_quality import assess_html_report_quality


HTML_SIGNALS_EN = (
    "outlook",
    "strategy",
    "strategies",
    "market",
    "markets",
    "macro",
    "investment",
    "portfolio",
    "asset allocation",
    "equity",
    "fixed income",
    "credit",
    "alternatives",
    "research",
    "insights",
    "perspectives",
    "weekly",
    "mid-year",
    "midyear",
)
HTML_SIGNALS_ZH = (
    "策略",
    "研究",
    "研报",
    "报告",
    "展望",
    "宏观",
    "市场",
    "投资",
    "资产配置",
    "权益",
    "股票",
    "固收",
    "债券",
    "行业",
    "主题",
    "周报",
    "月报",
    "中期",
    "年度",
)
NEGATIVE_SIGNALS = (
    "login",
    "sign-in",
    "signin",
    "register",
    "subscribe",
    "privacy",
    "cookie",
    "terms",
    "careers",
    "contact",
    "press-release",
    "podcast",
    "video",
    "webcast",
    "fund",
    "etf/",
    "prospectus",
    "literature",
    "pdf",
    "download",
)
NOISE_DOMAINS = (
    "facebook.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
    "podcasts.apple.com",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover report-like HTML strategy pages from configured source URLs.")
    parser.add_argument("--config", type=Path, action="append", required=True, help="Source config JSON with a top-level sources array.")
    parser.add_argument("--out-dir", type=Path, default=Path("dataset_build/html_discovery"))
    parser.add_argument("--max-links-per-seed", type=int, default=80)
    parser.add_argument("--max-candidates-per-source", type=int, default=20)
    parser.add_argument("--request-timeout", type=int, default=15)
    parser.add_argument("--min-score", type=int, default=4)
    parser.add_argument("--min-article-quality", type=float, default=45.0)
    parser.add_argument("--no-validate-candidates", action="store_true", help="Do not fetch candidate links; useful only for diagnostics.")
    parser.add_argument("--include-rejected", action="store_true", help="Include rejected/non-article pages in the main candidates JSONL.")
    parser.add_argument("--include-cross-domain", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    candidates_path = args.out_dir / "html_strategy_candidates.jsonl"
    rejected_path = args.out_dir / "html_strategy_rejected.jsonl"
    summary_path = args.out_dir / "html_strategy_discovery_summary.json"
    if args.reset:
        candidates_path.unlink(missing_ok=True)
        rejected_path.unlink(missing_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    all_candidates: list[dict[str, Any]] = []
    rejected_candidates: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    source_counts: dict[str, int] = collections.defaultdict(int)
    seen_urls: set[str] = set()
    for config_path in args.config:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        for source in config.get("sources", []):
            institution = source.get("institution") or "unknown"
            keywords = source.get("keywords") or []
            per_source: list[dict[str, Any]] = []
            for seed_url in source.get("urls", []):
                if looks_like_pdf(seed_url):
                    continue
                try:
                    page = fetch_html(session, seed_url, args.request_timeout)
                except Exception as exc:  # noqa: BLE001
                    failures.append({"seed_url": seed_url, "institution": institution, "error": repr(exc)})
                    continue
                seed_candidate = candidate_from_html(
                    page,
                    seed_url,
                    seed_url,
                    institution,
                    source,
                    keywords,
                )
                if seed_candidate["score"] >= args.min_score:
                    route_candidate(seed_candidate, per_source, rejected_candidates, args)
                for link in extract_links(page["html"], seed_url, args.max_links_per_seed):
                    if link["url"] in seen_urls or looks_like_pdf(link["url"]) or is_noise_url(link["url"]):
                        continue
                    if not args.include_cross_domain and not same_registered_host(seed_url, link["url"]):
                        continue
                    link_candidate = candidate_from_link(link, seed_url, institution, source, keywords)
                    if link_candidate["score"] >= args.min_score:
                        if args.no_validate_candidates:
                            route_candidate(link_candidate, per_source, rejected_candidates, args)
                        else:
                            try:
                                linked_page = fetch_html(session, link["url"], args.request_timeout)
                                validated = candidate_from_html(
                                    linked_page,
                                    link["url"],
                                    seed_url,
                                    institution,
                                    source,
                                    keywords,
                                    link_text=link.get("text") or "",
                                )
                                route_candidate(validated, per_source, rejected_candidates, args)
                            except Exception as exc:  # noqa: BLE001
                                rejected_candidates.append(
                                    {
                                        **link_candidate,
                                        "candidate_status": "fetch_failed",
                                        "article_like": False,
                                        "reject_reasons": [f"candidate_fetch_failed:{exc!r}"],
                                    }
                                )
                        seen_urls.add(link["url"])
            per_source = sorted(
                dedupe_by_url(per_source),
                key=lambda item: (item["score"], item.get("text_length_hint") or 0),
                reverse=True,
            )[: args.max_candidates_per_source]
            source_counts[institution] += len(per_source)
            all_candidates.extend(per_source)

    all_candidates = sorted(dedupe_by_url(all_candidates), key=lambda item: (item["score"], item["url"]))
    with candidates_path.open("w", encoding="utf-8") as handle:
        for row in all_candidates:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with rejected_path.open("w", encoding="utf-8") as handle:
        for row in sorted(dedupe_by_url(rejected_candidates), key=lambda item: (item.get("url") or "")):
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "created_at": utc_now_iso(),
        "configs": [str(path) for path in args.config],
        "candidate_count": len(all_candidates),
        "rejected_count": len(rejected_candidates),
        "failure_count": len(failures),
        "language_counts": dict(collections.Counter(row["language_hint"] for row in all_candidates)),
        "institution_counts": dict(source_counts),
        "candidates_path": str(candidates_path),
        "rejected_path": str(rejected_path),
        "common_reject_reasons": dict(
            collections.Counter(reason for row in rejected_candidates for reason in row.get("reject_reasons", []))
        ),
        "failures": failures[:100],
        "notes": [
            "Candidates passed article-like discovery gates but are not admitted samples until localization and audit pass.",
            "The language hint is heuristic and should be reviewed for borderline mixed-language pages.",
            "Use the admitted manifest builder to enforce a near 1:1 Chinese/English balance.",
        ],
    }
    write_json(summary_path, summary)
    print(json.dumps({k: summary[k] for k in ["candidate_count", "failure_count", "language_counts"]}, ensure_ascii=False, indent=2))
    print(f"candidates={candidates_path}")
    return 0 if all_candidates else 1


def fetch_html(session: requests.Session, url: str, timeout: int) -> dict[str, Any]:
    response = session.get(url, timeout=timeout, allow_redirects=True)
    ctype = response.headers.get("content-type", "")
    response.raise_for_status()
    text = response.text
    if "text/html" not in ctype.lower() and "<html" not in text[:1000].lower():
        raise ValueError(f"not_html:{ctype}")
    return {"url": response.url, "status": response.status_code, "content_type": ctype, "html": text}


def extract_links(html: str, base_url: str, limit: int) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, str(anchor.get("href") or "").strip()).split("#", 1)[0]
        if not href.startswith(("http://", "https://")) or href in seen:
            continue
        seen.add(href)
        text = clean_text(anchor.get_text(" ", strip=True))
        title = clean_text(str(anchor.get("title") or ""))
        aria = clean_text(str(anchor.get("aria-label") or ""))
        links.append({"url": href, "text": text, "title": title, "aria_label": aria})
        if len(links) >= limit:
            break
    return links


def candidate_from_html(
    page: dict[str, Any],
    url: str,
    seed_url: str,
    institution: str,
    source: dict[str, Any],
    keywords: list[str],
    link_text: str = "",
) -> dict[str, Any]:
    soup = BeautifulSoup(page["html"], "html.parser")
    title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    headings = clean_text(" ".join(node.get_text(" ", strip=True) for node in soup.find_all(["h1", "h2"], limit=6)))
    text = clean_text(soup.get_text(" ", strip=True))
    haystack = f"{title} {headings} {url} {text[:1800]}"
    score, reasons = score_candidate(haystack, url, keywords)
    quality = assess_html_report_quality(page["html"], source_url=url)
    return {
        "sample_id": build_sample_id(institution, title or url),
        "url": url,
        "seed_url": seed_url,
        "institution": institution,
        "business_type": source.get("business_type") or "",
        "country_or_region": source.get("country_or_region") or "",
        "title_hint": title,
        "link_text": link_text,
        "language_hint": quality.language,
        "subtype_hint": infer_subtype(haystack),
        "score": score,
        "score_reasons": reasons,
        "text_length_hint": quality.text_length or len(text),
        "article_like": quality.article_like,
        "candidate_status": "article_like" if quality.article_like else "rejected",
        "article_quality_score": quality.quality_score,
        "article_quality": quality.to_dict(),
        "reject_reasons": quality.reject_reasons,
        "discovered_at": utc_now_iso(),
    }


def candidate_from_link(
    link: dict[str, str],
    seed_url: str,
    institution: str,
    source: dict[str, Any],
    keywords: list[str],
) -> dict[str, Any]:
    haystack = f"{link.get('text','')} {link.get('title','')} {link.get('aria_label','')} {link['url']}"
    score, reasons = score_candidate(haystack, link["url"], keywords)
    return {
        "sample_id": build_sample_id(institution, link.get("text") or link["url"]),
        "url": link["url"],
        "seed_url": seed_url,
        "institution": institution,
        "business_type": source.get("business_type") or "",
        "country_or_region": source.get("country_or_region") or "",
        "title_hint": link.get("title") or link.get("text") or "",
        "link_text": link.get("text") or "",
        "language_hint": detect_language(haystack),
        "subtype_hint": infer_subtype(haystack),
        "score": score,
        "score_reasons": reasons,
        "text_length_hint": None,
        "discovered_at": utc_now_iso(),
    }


def score_candidate(haystack: str, url: str, keywords: list[str]) -> tuple[int, list[str]]:
    lowered = haystack.lower()
    normalized = lowered.replace("_", " ").replace("-", " ").replace("%20", " ")
    reasons: list[str] = []
    score = 0
    for keyword in keywords:
        if keyword and keyword.lower() in normalized:
            score += 2
            reasons.append(f"keyword:{keyword}")
    for signal in HTML_SIGNALS_EN:
        if signal in normalized:
            score += 1
            reasons.append(f"en_signal:{signal}")
    for signal in HTML_SIGNALS_ZH:
        if signal in haystack:
            score += 2
            reasons.append(f"zh_signal:{signal}")
    for signal in NEGATIVE_SIGNALS:
        if signal in lowered:
            score -= 2
            reasons.append(f"negative:{signal}")
    if re.search(r"/(article|insights|research|outlook|strategy|market|markets|perspectives)/", url.lower()):
        score += 2
        reasons.append("report_like_url_path")
    return score, sorted(set(reasons))


def route_candidate(
    candidate: dict[str, Any],
    accepted: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    args: argparse.Namespace,
) -> None:
    quality_score = float(candidate.get("article_quality_score") or 0.0)
    is_article = bool(candidate.get("article_like")) and quality_score >= args.min_article_quality
    if is_article:
        accepted.append(candidate)
        return
    candidate = {
        **candidate,
        "candidate_status": candidate.get("candidate_status") or "rejected",
        "article_like": False,
    }
    rejected.append(candidate)
    if args.include_rejected:
        accepted.append(candidate)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def detect_language(text: str) -> str:
    zh_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    ascii_letters = len(re.findall(r"[A-Za-z]", text))
    if zh_chars >= 20 and zh_chars >= ascii_letters * 0.08:
        return "zh"
    return "en"


def infer_subtype(text: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ["fixed income", "credit"]) or any(term in text for term in ["固收", "债券"]):
        return "fixed_income_strategy"
    if any(term in lowered for term in ["equity", "stock"]) or any(term in text for term in ["权益", "股票"]):
        return "equity_strategy"
    if any(term in lowered for term in ["macro", "economic"]) or "宏观" in text:
        return "macro_strategy"
    if any(term in lowered for term in ["portfolio", "asset allocation"]) or "资产配置" in text:
        return "asset_allocation_strategy"
    if any(term in lowered for term in ["alternatives", "private market"]):
        return "alternatives_strategy"
    return "strategy_research"


def build_sample_id(institution: str, title_or_url: str) -> str:
    return slugify(f"html_{institution}_{title_or_url}", max_len=90)


def looks_like_pdf(url: str) -> bool:
    lowered = url.lower()
    return ".pdf" in urlparse(lowered).path or ".pdf" in urlparse(lowered).query


def is_noise_url(url: str) -> bool:
    parsed = urlparse(url)
    lowered = url.lower()
    return any(domain in parsed.netloc.lower() for domain in NOISE_DOMAINS) or any(signal in lowered for signal in NEGATIVE_SIGNALS[:8])


def same_registered_host(a: str, b: str) -> bool:
    def key(url: str) -> str:
        host = urlparse(url).netloc.lower().split(":")[0]
        parts = [part for part in host.split(".") if part and part != "www"]
        return ".".join(parts[-2:]) if len(parts) >= 2 else host

    return key(a) == key(b)


def dedupe_by_url(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        previous = best.get(row["url"])
        if previous is None or row["score"] > previous["score"]:
            best[row["url"]] = row
    return list(best.values())


if __name__ == "__main__":
    raise SystemExit(main())
