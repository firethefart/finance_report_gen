from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from common import read_jsonl, write_json
from document_extractors import extract_document


HARD_INVALID_IDS: dict[str, str] = {
    "strategy_sample_010": "Vanguard perspectives listing page, not a standalone strategy report.",
    "strategy_sample_025": "Vanguard interactive forecast/model page, useful as source data but not a formal strategy report.",
    "strategy_sample_027": "Morgan Stanley podcast transcript page, not a strategy report.",
    "strategy_sample_028": "Vanguard interview/article page; contains site boilerplate and lacks standalone report structure.",
    "strategy_sample_029": "J.P. Morgan insights listing page, not a standalone report.",
    "strategy_sample_030": "J.P. Morgan Eye on the Market hub/contact page, not a specific report.",
    "strategy_sample_031": "Vanguard short portfolio article, not a formal strategy report.",
    "strategy_sample_035": "Morgan Stanley podcast index page, not a standalone report.",
    "strategy_sample_036": "Morgan Stanley podcast transcript page, not a strategy report.",
    "strategy_sample_037": "Morgan Stanley podcast transcript page, not a formal midyear strategy report.",
    "strategy_sample_038": "Vanguard interview/article page; lacks standalone fixed-income report structure.",
}


COLLECTION_SIGNALS = [
    "perspectives and commentary",
    "latest & featured",
    "featured episode",
    "latest episodes",
    "find an office",
    "contact us to discuss",
    "search | find an office",
]

NON_REPORT_SIGNALS = [
    "podcast",
    "transcript",
    "interview",
    "connect with us",
    "all investing is subject to risk",
]

REPORT_STRUCTURE_SIGNALS = [
    "key takeaways",
    "outlook",
    "market outlook",
    "investment outlook",
    "macro",
    "asset allocation",
    "portfolio construction",
    "scenario",
    "forecast",
    "risk",
    "disclaimer",
]


def audit_sample(row: dict[str, Any], work_dir: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "curated_id": row.get("curated_id"),
        "format": row.get("format"),
        "title": row.get("title"),
        "institution": row.get("institution"),
        "subtype": row.get("subtype"),
        "decision": "keep",
        "reason": "passes report-content screen",
        "flags": [],
        "metrics": {},
    }
    curated_id = row.get("curated_id") or ""
    hard_reason = HARD_INVALID_IDS.get(curated_id)
    if curated_id in HARD_INVALID_IDS:
        result["decision"] = "reject"
        result["reason"] = hard_reason
    if row.get("format") == "pdf":
        result["metrics"] = {
            "page_count": row.get("page_count"),
            "quality_tier": row.get("quality_tier"),
            "source_verification": row.get("source_verification"),
        }
        if (row.get("page_count") or 0) < 8:
            result["decision"] = "reject"
            result["reason"] = "PDF is too short to function as a formal strategy report."
            result["flags"].append("short_pdf")
        return result

    doc = extract_document(row, work_dir=work_dir, max_chars=16000, render_pages=0, cache=False)
    raw_html = Path(row["curated_path"]).read_text(encoding="utf-8", errors="ignore").lower()
    text = f"{doc.get('title_hint','')} {' '.join(doc.get('headings') or [])} {doc.get('text_excerpt','')}".lower()
    collection_hits = [signal for signal in COLLECTION_SIGNALS if signal in text]
    non_report_hits = [signal for signal in NON_REPORT_SIGNALS if signal in text]
    structure_hits = [signal for signal in REPORT_STRUCTURE_SIGNALS if signal in text]
    headings = doc.get("headings") or []
    result["metrics"] = {
        "text_length": doc.get("text_length"),
        "heading_count": len(headings),
        "collection_hits": collection_hits,
        "non_report_hits": non_report_hits,
        "structure_signal_count": len(structure_hits),
        "parse_quality": doc.get("parse_quality"),
    }
    if hard_reason:
        return result
    if collection_hits and len(structure_hits) < 4:
        result["decision"] = "reject"
        result["reason"] = f"HTML appears to be a hub/listing page: {', '.join(collection_hits[:3])}."
        result["flags"].append("collection_or_hub_page")
    is_actual_podcast = (
        'content_mediatype" content="msdotcom:content-types/format-or-media-type--do-not-use-/podcast' in raw_html
        or "/insights/podcasts/thoughts-on-the-market/" in (row.get("source_url") or "").lower()
        or "transcript | thoughts on the market" in text
        or "thoughts on the market | up next | more insights" in text
    )
    if "transcript" in non_report_hits or is_actual_podcast:
        if row.get("institution", "").startswith("Morgan Stanley") and is_actual_podcast:
            result["decision"] = "reject"
            result["reason"] = "HTML appears to be a podcast/transcript page rather than a strategy report."
            result["flags"].append("podcast_or_transcript")
    if doc.get("text_length", 0) < 9000 and len(structure_hits) < 5:
        result["decision"] = "reject"
        result["reason"] = "HTML content is too thin and lacks enough strategy-report structure."
        result["flags"].append("thin_html")
    return result


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_report(path: Path, audits: list[dict[str, Any]], valid_rows: list[dict[str, Any]]) -> None:
    rejected = [item for item in audits if item["decision"] == "reject"]
    kept = [item for item in audits if item["decision"] == "keep"]
    lines = [
        "# Golden Sample Screening Report",
        "",
        f"- Input samples: {len(audits)}",
        f"- Kept samples: {len(kept)}",
        f"- Rejected samples: {len(rejected)}",
        "",
        "## Rejected Samples",
        "",
    ]
    for item in rejected:
        metrics = item.get("metrics") or {}
        lines.append(
            f"- `{item['curated_id']}` | {item.get('institution')} | {item.get('subtype')} | {item.get('title')}\n"
            f"  - Reason: {item.get('reason')}\n"
            f"  - Metrics: {json.dumps(metrics, ensure_ascii=False)}"
        )
    lines += [
        "",
        "## Kept Distribution",
        "",
    ]
    subtype_counts = Counter(row.get("subtype", "unknown") for row in valid_rows)
    format_counts = Counter(row.get("format", "unknown") for row in valid_rows)
    institution_counts = Counter(row.get("institution", "unknown") for row in valid_rows)
    lines.append(f"- Formats: {dict(format_counts)}")
    lines.append(f"- Subtypes: {dict(subtype_counts)}")
    lines.append(f"- Institutions: {dict(institution_counts)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen curated golden strategy samples for non-report HTML pages.")
    parser.add_argument("--metadata", default="dataset_build/curated_strategy_samples_verified/metadata.jsonl")
    parser.add_argument("--out-dir", default="dataset_build/curated_strategy_samples_screened")
    parser.add_argument("--work-dir", default="dataset_build/golden_screening_tmp")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_jsonl(Path(args.metadata))
    out_dir = Path(args.out_dir)
    work_dir = Path(args.work_dir)
    audits = [audit_sample(row, work_dir=work_dir) for row in rows]
    rejected_ids = {item["curated_id"] for item in audits if item["decision"] == "reject"}
    valid_rows = [row for row in rows if row.get("curated_id") not in rejected_ids]
    rejected_rows = [row for row in rows if row.get("curated_id") in rejected_ids]

    write_jsonl(out_dir / "metadata.jsonl", valid_rows)
    write_jsonl(out_dir / "rejected_metadata.jsonl", rejected_rows)
    write_json(out_dir / "audit.json", audits)
    write_json(
        out_dir / "summary.json",
        {
            "input_count": len(rows),
            "kept_count": len(valid_rows),
            "rejected_count": len(rejected_rows),
            "rejected_ids": sorted(rejected_ids),
            "format_counts": dict(Counter(row.get("format", "unknown") for row in valid_rows)),
            "subtype_counts": dict(Counter(row.get("subtype", "unknown") for row in valid_rows)),
            "institution_counts": dict(Counter(row.get("institution", "unknown") for row in valid_rows)),
        },
    )
    write_report(out_dir / "screening_report.md", audits, valid_rows)
    print(f"Kept {len(valid_rows)} / {len(rows)} samples")
    print(f"Rejected: {', '.join(sorted(rejected_ids))}")
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
