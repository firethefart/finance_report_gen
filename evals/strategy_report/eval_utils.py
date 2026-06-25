from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            items.append(json.loads(line))
    return items


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def repo_path(path: str | Path | None) -> Path | None:
    if not path:
        return None
    p = Path(path)
    if p.is_absolute():
        return p
    return ROOT / p


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.lower()
    return re.sub(r"\s+", " ", text).strip()


def token_set(text: str) -> set[str]:
    normalized = normalize_text(text)
    return {
        token
        for token in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9][a-z0-9_\-./%]*", normalized)
        if len(token) > 1 and token not in STOPWORDS
    }


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "are",
    "not",
    "report",
    "section",
    "strategy",
    "outlook",
    "research",
    "market",
}


def token_overlap(expected: str, observed: str) -> float:
    expected_tokens = token_set(expected)
    if not expected_tokens:
        return 0.0
    observed_tokens = token_set(observed)
    return len(expected_tokens & observed_tokens) / len(expected_tokens)


def contains_fuzzy(needle: str, haystack: str, threshold: float = 0.42) -> bool:
    n = normalize_text(needle)
    h = normalize_text(haystack)
    return bool(n and (n in h or token_overlap(n, h) >= threshold))


NUMBER_RE = re.compile(
    r"(?<![\w.])(?:[$€£¥]\s*)?[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"(?:\s*(?:[-–—]\s*)?(?:%|pct|bps|bp|x|times|倍|个百分点|个基点|万亿|亿元|亿美元|"
    r"trillion|billion|million|thousand|bn|mn|trn|years?|months?|quarters?|"
    r"€|£|\$|¥|元|亿|万))?(?![\w.])",
    re.IGNORECASE,
)
DATE_RE = re.compile(
    r"\b(?:20\d{2}|19\d{2})(?:[-/.年](?:0?[1-9]|1[0-2]))?(?:[-/.月](?:0?[1-9]|[12]\d|3[01]))?日?\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+20\d{2}\b",
    re.IGNORECASE,
)


def extract_numbers(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for match in NUMBER_RE.finditer(text or ""):
        value = re.sub(r"\s+", "", match.group(0))
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def canonical_number(value: str) -> str:
    return re.sub(r"[,，\s%％]", "", normalize_text(value))


def extract_dates(text: str) -> list[str]:
    return [m.group(0) for m in DATE_RE.finditer(text or "")]


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def mean(values: list[float], default: float = 0.0) -> float:
    cleaned = [v for v in values if not math.isnan(v)]
    return sum(cleaned) / len(cleaned) if cleaned else default


def issue(
    issue_type: str,
    severity: str,
    location: str,
    description: str,
    suggested_skill_patch: str = "",
    evidence: str = "",
) -> dict[str, str]:
    return {
        "issue_type": issue_type,
        "severity": severity,
        "location": location,
        "description": description,
        "evidence": evidence,
        "suggested_skill_patch": suggested_skill_patch,
    }


def weighted_score(dimension_scores: dict[str, float], weights: dict[str, int]) -> float:
    total = 0.0
    for key, weight in weights.items():
        total += clamp(dimension_scores.get(key, 0.0)) * weight
    return round(total, 2)


def grade_for_score(score: float, redline_issues: list[dict[str, Any]]) -> str:
    if redline_issues:
        return "Reject"
    if score >= 90:
        return "Gold"
    if score >= 80:
        return "Silver"
    if score >= 70:
        return "Bronze"
    return "Reject"
