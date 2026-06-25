from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import requests

from common import USER_AGENT, append_jsonl, load_json, sha256_file, slugify, utc_now_iso


def infer_subtype(url: str) -> str:
    lowered = url.lower()
    if "weekly" in lowered:
        return "weekly"
    if "mid-year" in lowered or "midyear" in lowered:
        return "midyear_outlook"
    if "outlook" in lowered or "展望" in url:
        return "annual_or_periodic_outlook"
    if "macro" in lowered or "宏观" in url:
        return "macro_strategy"
    if "equity" in lowered or "a股" in lowered:
        return "equity_strategy"
    if "fixed-income" in lowered or "固收" in url:
        return "fixed_income"
    if "portfolio" in lowered or "配置" in url:
        return "asset_allocation"
    return "strategy_research"


def iter_candidate_pages(report: dict[str, Any], max_pages_per_institution: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for institution in report.get("institutions", []):
        seen: set[str] = set()
        for url in institution.get("strategy_page_samples", []):
            if len(seen) >= max_pages_per_institution:
                break
            if not url.startswith("http") or url in seen:
                continue
            seen.add(url)
            rows.append(
                {
                    "institution": institution["institution"],
                    "business_type": institution.get("business_type"),
                    "country_or_region": institution.get("country_or_region"),
                    "url": url,
                    "subtype_hint": infer_subtype(url),
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive report-like HTML pages from discovery reports.")
    parser.add_argument("--discovery", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, default=Path("dataset_build"))
    parser.add_argument("--max-pages-per-institution", type=int, default=12)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--reset-manifest", action="store_true")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    candidates: list[dict[str, Any]] = []
    for path in args.discovery:
        candidates.extend(iter_candidate_pages(load_json(path), args.max_pages_per_institution))
    if args.limit is not None:
        candidates = candidates[: args.limit]

    manifest_path = args.out / "manifests" / "html_archive_manifest.jsonl"
    if args.reset_manifest:
        manifest_path.unlink(missing_ok=True)

    rows: list[dict[str, Any]] = []
    for item in candidates:
        inst_slug = slugify(item["institution"], max_len=64)
        subtype = item["subtype_hint"]
        file_name = slugify(item["url"], max_len=120) + ".html"
        out_path = args.out / "raw_html" / subtype / inst_slug / file_name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "archived_at": utc_now_iso(),
            "institution": item["institution"],
            "business_type": item.get("business_type"),
            "country_or_region": item.get("country_or_region"),
            "subtype_hint": subtype,
            "url": item["url"],
            "file_path": None,
            "status": "failed",
            "http_status": None,
            "content_type": None,
            "file_size_bytes": 0,
            "sha256": None,
            "error": None,
        }
        try:
            resp = session.get(item["url"], timeout=30, allow_redirects=True)
            row["http_status"] = resp.status_code
            row["content_type"] = resp.headers.get("content-type")
            resp.raise_for_status()
            out_path.write_text(resp.text, encoding="utf-8")
            row["status"] = "archived"
            row["file_path"] = str(out_path)
            row["file_size_bytes"] = out_path.stat().st_size
            row["sha256"] = sha256_file(out_path)
        except Exception as exc:  # noqa: BLE001
            row["error"] = repr(exc)
        rows.append(row)

    append_jsonl(manifest_path, rows)
    ok = sum(1 for row in rows if row["status"] == "archived")
    print(f"jobs={len(rows)} ok={ok} failed={len(rows) - ok}")
    print(f"manifest={manifest_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
