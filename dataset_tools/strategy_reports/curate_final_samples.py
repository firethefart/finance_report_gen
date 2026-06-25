from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from common import read_jsonl, sha256_file, slugify, utc_now_iso, write_json


OFFICIAL_HOST_HINTS = {
    "BlackRock Investment Institute": ("blackrock.com",),
    "Goldman Sachs Asset Management": ("gs.com",),
    "J.P. Morgan Private Bank / Wealth Management": ("jpmorgan.com", "jpmprivatebank.com"),
    "Morgan Stanley": ("morganstanley.com",),
    "Vanguard": ("vanguard.com",),
    "Fidelity International / Fidelity UK": ("fidelityinternational.com", "fidelity.co.uk"),
    "State Street Global Advisors / State Street Investment Management": ("ssga.com",),
}

REPORT_TERMS = (
    "outlook",
    "strategy",
    "market",
    "macro",
    "portfolio",
    "asset allocation",
    "investment",
    "equity",
    "fixed income",
    "credit",
    "alternatives",
    "weekly commentary",
    "eye on the market",
    "展望",
    "策略",
    "研报",
    "研究",
    "配置",
    "宏观",
    "市场",
    "行业",
    "投资",
)

NOISE_TERMS = (
    "sign in",
    "login",
    "events",
    "webcast",
    "investment stewardship",
    "interactive charts",
    "about us",
    "meet the",
    "products",
    "mutual funds",
    "开户",
    "otc",
    "柜台市场",
)

SUBTYPE_NORMALIZATION = {
    "annual_or_periodic_outlook": "annual_outlook",
    "annual_outlook": "annual_outlook",
    "midyear_outlook": "midyear_outlook",
    "quarterly_outlook": "quarterly_outlook",
    "weekly_commentary": "weekly_commentary",
    "weekly": "weekly_commentary",
    "asset_allocation": "asset_allocation",
    "macro_strategy": "macro_strategy",
    "equity_strategy": "equity_strategy",
    "fixed_income": "fixed_income",
    "strategy_research": "thematic_strategy",
    "thematic_strategy": "thematic_strategy",
    "ma_capital_markets_strategy": "ma_capital_markets_strategy",
    "m_and_a": "ma_capital_markets_strategy",
}

INSTITUTION_NAME_FIXES = {
    "涓噾鍏徃鐮旂┒ / CICC Research - third party mirrors": "中金公司研究 / CICC Research - third party mirrors",
    "涓俊璇佸埜鐮旂┒ / CITIC Securities Research - third party mirrors": "中信证券研究 / CITIC Securities Research - third party mirrors",
    "鍗庢嘲璇佸埜鐮旂┒ / Huatai Securities Research - third party mirrors": "华泰证券研究 / Huatai Securities Research - third party mirrors",
    "鍥芥嘲娴烽€氳瘉鍒哥爺绌?/ Guotai Haitong Research - third party mirrors": "国泰海通证券研究 / Guotai Haitong Research - third party mirrors",
    "骞垮彂璇佸埜鐮旂┒ / GF Securities Research - third party mirrors": "广发证券研究 / GF Securities Research - third party mirrors",
    "鎷涘晢璇佸埜鐮旂┒ / CMS China Research - third party mirrors": "招商证券研究 / CMS China Research - third party mirrors",
}

THIRD_PARTY_ALIASES = {
    "中金公司研究 / CICC Research - third party mirrors": ("中金", "CICC"),
    "中信证券研究 / CITIC Securities Research - third party mirrors": ("中信证券", "CITIC"),
    "华泰证券研究 / Huatai Securities Research - third party mirrors": ("华泰", "华泰证券", "Huatai"),
    "国泰海通证券研究 / Guotai Haitong Research - third party mirrors": ("国泰海通", "国泰君安", "海通证券", "Guotai", "Haitong"),
    "广发证券研究 / GF Securities Research - third party mirrors": ("广发", "广发证券", "GF Securities"),
    "招商证券研究 / CMS China Research - third party mirrors": ("招商证券", "招商", "CMS China"),
}


def normalize_subtype(value: str | None) -> str:
    return SUBTYPE_NORMALIZATION.get(value or "", value or "thematic_strategy")


def clean_institution_name(value: str | None) -> str | None:
    if value is None:
        return None
    return INSTITUTION_NAME_FIXES.get(value, value)


def text_score(text: str, url: str) -> int:
    haystack = f"{text} {url}".lower()
    return sum(1 for term in REPORT_TERMS if term.lower() in haystack)


def noise_score(text: str, url: str) -> int:
    haystack = f"{text} {url}".lower()
    return sum(1 for term in NOISE_TERMS if term.lower() in haystack)


def extract_html_text(path: Path) -> tuple[str, str]:
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else path.stem
    heads = " ".join(h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2"], limit=8))
    text = " ".join(soup.get_text(" ", strip=True).split())
    return re.sub(r"\s+", " ", f"{title} {heads}").strip(), text


def verify_source(institution: str, business_type: str | None, url: str, text: str) -> tuple[str, list[str]]:
    host = urlparse(url).netloc.lower()
    institution = clean_institution_name(institution) or institution
    notes: list[str] = []
    if business_type and "third_party" in business_type:
        notes.append("third-party mirror; requires source and copyright verification")
        aliases = THIRD_PARTY_ALIASES.get(institution, ())
        if any(alias.lower() in text.lower() for alias in aliases):
            return "third_party_mirror_name_match", notes
        return "third_party_mirror_unverified", notes
    hints = OFFICIAL_HOST_HINTS.get(institution, ())
    if hints and any(hint in host for hint in hints):
        return "official_domain_verified", notes
    if not hints:
        notes.append("no host hint configured")
    return "official_domain_uncertain", notes


def pdf_candidates(screening_path: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in read_jsonl(screening_path):
        if row.get("quality_tier") not in {"A", "B"}:
            continue
        path = Path(row["file_path"])
        if not path.exists():
            continue
        subtype = normalize_subtype(row.get("strategy_subtype"))
        tier_bonus = 40 if row["quality_tier"] == "A" else 25
        page_bonus = min(int(row.get("page_count") or 0), 40)
        source_status, notes = verify_source(
            row.get("institution") or "",
            row.get("business_type"),
            row.get("pdf_url") or "",
            f"{row.get('guessed_title') or ''} {row.get('file_name') or ''}",
        )
        candidates.append(
            {
                "format": "pdf",
                "source_path": str(path),
                "source_url": row.get("pdf_url"),
                "institution": clean_institution_name(row.get("institution")),
                "business_type": row.get("business_type"),
                "country_or_region": row.get("country_or_region"),
                "title": row.get("guessed_title") or path.stem,
                "subtype": subtype,
                "quality_tier": row.get("quality_tier"),
                "source_verification": source_status,
                "verification_notes": notes,
                "score": tier_bonus + page_bonus + (15 if source_status == "official_domain_verified" else 0),
                "page_count": row.get("page_count"),
                "sha256": row.get("sha256"),
            }
        )
    return candidates


def html_candidates(html_manifest_path: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in read_jsonl(html_manifest_path):
        if row.get("status") != "archived" or not row.get("file_path"):
            continue
        path = Path(row["file_path"])
        if not path.exists():
            continue
        heading, text = extract_html_text(path)
        url = row.get("url") or ""
        report_signal = text_score(f"{heading} {text[:4000]}", url)
        noise = noise_score(f"{heading} {text[:2000]}", url)
        text_len = len(text)
        source_status, notes = verify_source(
            row.get("institution") or "",
            row.get("business_type"),
            url,
            f"{heading} {text[:2000]}",
        )
        if report_signal < 2:
            continue
        if text_len < 1800:
            continue
        if noise >= 2 and report_signal < 5:
            continue
        subtype = normalize_subtype(row.get("subtype_hint"))
        source_bonus = 15 if source_status == "official_domain_verified" else 4 if "third_party" in source_status else 0
        candidates.append(
            {
                "format": "html",
                "source_path": str(path),
                "source_url": url,
                "institution": clean_institution_name(row.get("institution")),
                "business_type": row.get("business_type"),
                "country_or_region": row.get("country_or_region"),
                "title": heading[:180] or path.stem,
                "subtype": subtype,
                "quality_tier": "HTML-A" if report_signal >= 5 and text_len >= 5000 else "HTML-B",
                "source_verification": source_status,
                "verification_notes": notes,
                "score": min(text_len // 800, 35) + report_signal * 5 - noise * 8 + source_bonus,
                "text_length": text_len,
                "report_signal_count": report_signal,
                "noise_signal_count": noise,
                "sha256": row.get("sha256") or sha256_file(path),
            }
        )
    return candidates


def select_balanced(
    candidates: list[dict[str, Any]],
    target: int,
    max_per_institution: int,
    max_per_subtype: int,
    include_unverified_third_party: bool,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    inst_counts: collections.Counter[str] = collections.Counter()
    subtype_counts: collections.Counter[str] = collections.Counter()
    seen_sha: set[str] = set()
    for item in sorted(candidates, key=lambda row: row["score"], reverse=True):
        institution = item.get("institution") or "unknown"
        subtype = item.get("subtype") or "thematic_strategy"
        sha = item.get("sha256")
        if item.get("source_verification") == "third_party_mirror_unverified" and not include_unverified_third_party:
            continue
        if sha and sha in seen_sha:
            continue
        if inst_counts[institution] >= max_per_institution:
            continue
        if subtype_counts[subtype] >= max_per_subtype:
            continue
        selected.append(item)
        inst_counts[institution] += 1
        subtype_counts[subtype] += 1
        if sha:
            seen_sha.add(sha)
        if len(selected) >= target:
            break
    return selected


def copy_selected(selected: list[dict[str, Any]], out_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(selected, start=1):
        source = Path(item["source_path"])
        subtype = item["subtype"]
        institution = slugify(item.get("institution") or "unknown", max_len=64)
        title = slugify(item.get("title") or source.stem, max_len=80)
        ext = source.suffix.lower() or (".html" if item["format"] == "html" else ".pdf")
        target_dir = out_dir / subtype / item["format"]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{idx:03d}-{institution}-{title}{ext}"
        shutil.copy2(source, target)
        copied = {**item, "curated_id": f"strategy_sample_{idx:03d}", "curated_path": str(target)}
        rows.append(copied)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_readme(path: Path, rows: list[dict[str, Any]]) -> None:
    subtype_counts = collections.Counter(row["subtype"] for row in rows)
    format_counts = collections.Counter(row["format"] for row in rows)
    source_counts = collections.Counter(row["source_verification"] for row in rows)
    lines = [
        "# Curated Strategy Research Samples",
        "",
        f"Generated at: {utc_now_iso()}",
        "",
        f"Total samples: {len(rows)}",
        "",
        "## Format Counts",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(format_counts.items()))
    lines.extend(["", "## Subtype Counts", ""])
    lines.extend(f"- {key}: {value}" for key, value in sorted(subtype_counts.items()))
    lines.extend(["", "## Source Verification Counts", ""])
    lines.extend(f"- {key}: {value}" for key, value in sorted(source_counts.items()))
    lines.extend(["", "## Notes", ""])
    lines.append("- Samples are selected from PDF screening A/B records and archived HTML pages.")
    lines.append("- Chinese third-party mirrors require human source and copyright verification before golden-set promotion.")
    lines.append("- Files are stored by subtype first, then format.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Curate final high-quality strategy report samples.")
    parser.add_argument("--screening", type=Path, default=Path("dataset_build/manifests/screening_manifest.jsonl"))
    parser.add_argument("--html-manifest", type=Path, default=Path("dataset_build/manifests/html_archive_manifest.jsonl"))
    parser.add_argument("--out-dir", type=Path, default=Path("dataset_build/curated_strategy_samples"))
    parser.add_argument("--target", type=int, default=45)
    parser.add_argument("--max-per-institution", type=int, default=8)
    parser.add_argument("--max-per-subtype", type=int, default=12)
    parser.add_argument("--include-unverified-third-party", action="store_true")
    args = parser.parse_args()

    candidates = pdf_candidates(args.screening) + html_candidates(args.html_manifest)
    selected = select_balanced(
        candidates,
        args.target,
        args.max_per_institution,
        args.max_per_subtype,
        args.include_unverified_third_party,
    )
    copied = copy_selected(selected, args.out_dir)
    write_jsonl(args.out_dir / "metadata.jsonl", copied)
    summary = {
        "generated_at": utc_now_iso(),
        "candidate_count": len(candidates),
        "selected_count": len(copied),
        "format_counts": dict(collections.Counter(row["format"] for row in copied)),
        "subtype_counts": dict(collections.Counter(row["subtype"] for row in copied)),
        "source_verification_counts": dict(collections.Counter(row["source_verification"] for row in copied)),
        "institution_counts": dict(collections.Counter(row["institution"] for row in copied)),
    }
    write_json(args.out_dir / "summary.json", summary)
    write_readme(args.out_dir / "README.md", copied)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"out={args.out_dir}")
    return 0 if copied else 1


if __name__ == "__main__":
    raise SystemExit(main())
