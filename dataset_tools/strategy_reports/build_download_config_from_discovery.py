from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import load_json, write_json


def infer_subtype(url: str) -> str:
    lowered = url.lower()
    if "weekly" in lowered:
        return "weekly"
    if "mid-year" in lowered or "midyear" in lowered:
        return "midyear_outlook"
    if "outlook" in lowered or "展望" in url:
        return "annual_or_periodic_outlook"
    if "fixed-income" in lowered or "fixed_income" in lowered or "固收" in url:
        return "fixed_income"
    if "m&a" in lowered or "ma-" in lowered or "并购" in url:
        return "m_and_a"
    if "portfolio" in lowered or "asset" in lowered or "配置" in url:
        return "asset_allocation"
    return "strategy_research"


def add_job(
    jobs: list[dict[str, Any]],
    seen: set[str],
    institution: dict[str, Any],
    url: str,
    source_url: str | None,
    source_bucket: str,
) -> None:
    clean = url.strip()
    if not clean or clean in seen:
        return
    seen.add(clean)
    jobs.append(
        {
            "institution": institution["institution"],
            "business_type": institution.get("business_type"),
            "country_or_region": institution.get("country_or_region"),
            "kind": "direct_pdf",
            "url": clean,
            "subtype_hint": infer_subtype(clean),
            "source_bucket": source_bucket,
            "source_url": source_url,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build download_reports.py config from discovery reports.")
    parser.add_argument("--discovery", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-bucket", action="append", default=[])
    args = parser.parse_args()

    jobs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, discovery_path in enumerate(args.discovery):
        bucket = args.source_bucket[index] if index < len(args.source_bucket) else discovery_path.stem
        report = load_json(discovery_path)
        for institution in report.get("institutions", []):
            for url in institution.get("pdf_samples", []):
                add_job(jobs, seen, institution, url, None, bucket)
            for page in institution.get("page_results", []):
                source_url = page.get("url")
                for item in page.get("pdf_links", []):
                    add_job(jobs, seen, institution, item.get("url", ""), source_url, bucket)
                for item in page.get("child_pdf_links", []):
                    add_job(jobs, seen, institution, item.get("url", ""), item.get("from_page") or source_url, bucket)

    output = {
        "notes": "Generated from source discovery reports. Feed this file to download_reports.py.",
        "sources": jobs,
    }
    write_json(args.out, output)
    print(f"jobs={len(jobs)} out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
