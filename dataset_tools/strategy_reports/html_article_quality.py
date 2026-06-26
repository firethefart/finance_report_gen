from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from bs4 import BeautifulSoup, Tag


REPORT_TERMS_EN = (
    "outlook",
    "strategy",
    "market",
    "markets",
    "macro",
    "economic",
    "investment",
    "portfolio",
    "asset allocation",
    "equity",
    "fixed income",
    "credit",
    "alternatives",
    "risk",
    "scenario",
    "earnings",
    "inflation",
    "rates",
)
REPORT_TERMS_ZH = (
    "策略",
    "市场",
    "宏观",
    "投资",
    "配置",
    "资产",
    "权益",
    "股票",
    "固收",
    "债券",
    "行业",
    "主题",
    "风险",
    "情景",
    "展望",
    "经济",
)
GENERIC_TITLES = {
    "insights",
    "research",
    "publications",
    "markets & insights",
    "markets and insights",
    "investment insights",
    "perspectives",
    "ideas",
    "the markets",
    "global market outlook",
}
LANDING_TERMS = (
    "view all",
    "latest insights",
    "related insights",
    "subscribe",
    "newsletter",
    "webcast",
    "podcast",
    "video library",
    "events",
    "fund center",
    "product",
    "prospectus",
)
HARD_REJECT_URL_TERMS = (
    "podcast",
    "video",
    "webcast",
    "/people/",
    "/person/",
    "/about-us/",
    "investment-professionals",
    "professionals/",
    "events",
)
CONTAINER_SELECTORS = (
    "article",
    "main",
    "[role='main']",
    ".article",
    ".article-body",
    ".article-content",
    ".content",
    ".content-body",
    ".insight-content",
    ".research-content",
    ".report",
    ".report-body",
    "#main-content",
)


@dataclass
class ArticleQuality:
    article_like: bool
    quality_score: float
    language: str
    title: str
    chosen_selector: str
    text_length: int
    zh_char_count: int
    paragraph_count: int
    long_paragraph_count: int
    heading_count: int
    link_count: int
    link_text_ratio: float
    list_item_count: int
    visual_count: int
    report_signal_count: int
    landing_signal_count: int
    reject_reasons: list[str]
    warnings: list[str]
    text_preview: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_html_report_quality(html: str, *, source_url: str = "", min_text_length: int | None = None) -> ArticleQuality:
    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup.find_all(["script", "style", "noscript", "template"]):
        node.decompose()
    title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    language = detect_language(soup.get_text(" ", strip=True))
    candidate = choose_article_container(soup)
    node = candidate["node"]
    text = clean_text(node.get_text(" ", strip=True)) if node else ""
    paragraphs = [clean_text(p.get_text(" ", strip=True)) for p in node.find_all(["p", "li"]) if clean_text(p.get_text(" ", strip=True))] if node else []
    long_threshold = 35 if language == "zh" else 80
    long_paragraphs = [p for p in paragraphs if len(p) >= long_threshold]
    link_text = " ".join(a.get_text(" ", strip=True) for a in node.find_all("a")) if node else ""
    link_count = len(node.find_all("a")) if node else 0
    heading_count = len(node.find_all(["h1", "h2", "h3"])) if node else 0
    list_item_count = len(node.find_all("li")) if node else 0
    visual_count = len(node.find_all(["img", "svg", "canvas", "table", "figure"])) if node else 0
    link_text_ratio = round(len(clean_text(link_text)) / max(1, len(text)), 3)
    zh_char_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    report_signal_count = count_report_signals(f"{title} {source_url} {text}", language)
    landing_signal_count = count_landing_signals(f"{title} {source_url} {text[:3000]}")
    reject_reasons: list[str] = []
    warnings: list[str] = []
    effective_min = min_text_length or (1800 if language == "zh" else 3000)
    if not node:
        reject_reasons.append("article_container_missing")
    if len(text) < effective_min:
        reject_reasons.append("text_too_short")
    if language == "zh" and zh_char_count < 900:
        reject_reasons.append("zh_text_too_short")
    if len(long_paragraphs) < (5 if language == "zh" else 6):
        reject_reasons.append("paragraph_count_too_low")
    if link_text_ratio > 0.28:
        reject_reasons.append("link_density_too_high")
    if link_count > max(80, len(long_paragraphs) * 8) and link_text_ratio > 0.18:
        reject_reasons.append("navigation_heavy_page")
    if is_generic_title(title) and len(text) < 6500:
        reject_reasons.append("generic_landing_title")
    if landing_signal_count >= 4 and len(long_paragraphs) < 10:
        reject_reasons.append("landing_or_index_page")
    if report_signal_count < 3:
        reject_reasons.append("weak_strategy_report_signals")
    if any(term in f"{source_url} {title}".lower() for term in HARD_REJECT_URL_TERMS):
        reject_reasons.append("non_report_page_type")
    if len(text) > 350000:
        reject_reasons.append("page_text_implausibly_large")
    if visual_count == 0:
        warnings.append("no_visual_candidates")
    if heading_count < 2:
        warnings.append("few_headings")
    quality_score = compute_quality_score(
        text_length=len(text),
        long_paragraph_count=len(long_paragraphs),
        link_text_ratio=link_text_ratio,
        report_signal_count=report_signal_count,
        landing_signal_count=landing_signal_count,
        visual_count=visual_count,
    )
    return ArticleQuality(
        article_like=not reject_reasons,
        quality_score=quality_score,
        language=language,
        title=title,
        chosen_selector=str(candidate["selector"]),
        text_length=len(text),
        zh_char_count=zh_char_count,
        paragraph_count=len(paragraphs),
        long_paragraph_count=len(long_paragraphs),
        heading_count=heading_count,
        link_count=link_count,
        link_text_ratio=link_text_ratio,
        list_item_count=list_item_count,
        visual_count=visual_count,
        report_signal_count=report_signal_count,
        landing_signal_count=landing_signal_count,
        reject_reasons=sorted(set(reject_reasons)),
        warnings=sorted(set(warnings)),
        text_preview=text[:1200],
    )


def choose_article_container(soup: BeautifulSoup) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for selector in CONTAINER_SELECTORS:
        for node in soup.select(selector):
            if not isinstance(node, Tag):
                continue
            metrics = score_node(node)
            if metrics["text_length"] >= 500:
                candidates.append({"node": node, "selector": selector, **metrics})
    body = soup.body
    if body:
        candidates.append({"node": body, "selector": "body", **score_node(body)})
    if not candidates:
        return {"node": None, "selector": "", "score": 0}
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[0]


def score_node(node: Tag) -> dict[str, Any]:
    text = clean_text(node.get_text(" ", strip=True))
    link_text_length = sum(len(clean_text(a.get_text(" ", strip=True))) for a in node.find_all("a"))
    paragraph_count = len([p for p in node.find_all(["p", "li"]) if len(clean_text(p.get_text(" ", strip=True))) >= 40])
    link_ratio = link_text_length / max(1, len(text))
    density_bonus = min(2500, paragraph_count * 80)
    score = len(text) * max(0.15, 1.0 - min(0.85, link_ratio)) + density_bonus
    return {
        "text_length": len(text),
        "link_text_ratio": round(link_ratio, 3),
        "paragraph_count": paragraph_count,
        "score": score,
    }


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def detect_language(text: str) -> str:
    zh_chars = len(re.findall(r"[\u4e00-\u9fff]", text or ""))
    ascii_letters = len(re.findall(r"[A-Za-z]", text or ""))
    if zh_chars >= 20 and zh_chars >= ascii_letters * 0.08:
        return "zh"
    return "en"


def count_report_signals(text: str, language: str) -> int:
    lowered = (text or "").lower()
    terms = REPORT_TERMS_ZH if language == "zh" else REPORT_TERMS_EN
    return sum(1 for term in terms if (term in text if language == "zh" else term in lowered))


def count_landing_signals(text: str) -> int:
    lowered = (text or "").lower()
    return sum(1 for term in LANDING_TERMS if term in lowered)


def is_generic_title(title: str) -> bool:
    normalized = clean_text(title).lower().strip(" -|")
    if normalized in GENERIC_TITLES:
        return True
    return len(normalized) <= 24 and any(term == normalized for term in GENERIC_TITLES)


def compute_quality_score(
    *,
    text_length: int,
    long_paragraph_count: int,
    link_text_ratio: float,
    report_signal_count: int,
    landing_signal_count: int,
    visual_count: int,
) -> float:
    score = 0.0
    score += min(35.0, text_length / 180.0)
    score += min(25.0, long_paragraph_count * 2.2)
    score += min(20.0, report_signal_count * 3.0)
    score += min(10.0, visual_count * 1.5)
    score -= min(25.0, link_text_ratio * 70.0)
    score -= min(20.0, landing_signal_count * 3.0)
    return round(max(0.0, min(100.0, score)), 2)
