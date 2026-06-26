from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any

from common import write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Build localize_strategy_html.py manifest from discovered HTML candidates.")
    parser.add_argument("--candidates", type=Path, required=True, help="JSONL from discover_html_strategy_pages.py.")
    parser.add_argument("--out", type=Path, default=Path("evals/strategy_report/html_localization_candidates.generated.json"))
    parser.add_argument("--per-language", type=int, default=15, help="Target count for zh and en each. Use 0 to disable quota.")
    parser.add_argument("--language", action="append", choices=["en", "zh"], default=[], help="Restrict to selected language(s).")
    parser.add_argument("--min-score", type=int, default=4)
    parser.add_argument("--max-per-institution", type=int, default=5)
    parser.add_argument("--capture-mode", choices=["archive", "live"], default="archive")
    parser.add_argument("--enabled", action="store_true", help="Mark generated samples enabled. Default is disabled for review.")
    args = parser.parse_args()

    rows = read_jsonl(args.candidates)
    allowed_languages = set(args.language or ["en", "zh"])
    rows = [
        row
        for row in rows
        if row.get("language_hint") in allowed_languages and int(row.get("score") or 0) >= args.min_score
    ]
    rows = sorted(rows, key=lambda item: (int(item.get("score") or 0), item.get("text_length_hint") or 0), reverse=True)
    selected = select_balanced(rows, args.per_language, args.max_per_institution)
    samples = uniquify_sample_ids([to_localizer_sample(row, args.capture_mode, args.enabled) for row in selected])
    manifest = {
        "notes": [
            "Generated from HTML discovery candidates.",
            "Review samples before enabling large localization runs.",
            "The default selection enforces a near 1:1 zh/en balance when both languages are available.",
        ],
        "source_candidates": str(args.candidates),
        "selection": {
            "per_language": args.per_language,
            "languages": sorted(allowed_languages),
            "min_score": args.min_score,
            "max_per_institution": args.max_per_institution,
            "capture_mode": args.capture_mode,
            "enabled": args.enabled,
        },
        "language_counts": dict(collections.Counter(sample["language"] for sample in samples)),
        "samples": samples,
    }
    write_json(args.out, manifest)
    print(json.dumps({"samples": len(samples), "language_counts": manifest["language_counts"], "out": str(args.out)}, ensure_ascii=False, indent=2))
    return 0 if samples else 1


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8-sig") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def select_balanced(rows: list[dict[str, Any]], per_language: int, max_per_institution: int) -> list[dict[str, Any]]:
    if per_language <= 0:
        return limit_per_institution(rows, max_per_institution)
    selected: list[dict[str, Any]] = []
    for language in ["zh", "en"]:
        selected.extend(limit_per_institution([row for row in rows if row.get("language_hint") == language], max_per_institution)[:per_language])
    return sorted(selected, key=lambda item: (item.get("language_hint") or "", -(int(item.get("score") or 0)), item.get("sample_id") or ""))


def limit_per_institution(rows: list[dict[str, Any]], max_per_institution: int) -> list[dict[str, Any]]:
    counts: dict[str, int] = collections.defaultdict(int)
    selected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for row in rows:
        institution = row.get("institution") or "unknown"
        if row["url"] in seen_urls:
            continue
        if max_per_institution > 0 and counts[institution] >= max_per_institution:
            continue
        counts[institution] += 1
        seen_urls.add(row["url"])
        selected.append(row)
    return selected


def to_localizer_sample(row: dict[str, Any], capture_mode: str, enabled: bool) -> dict[str, Any]:
    return {
        "sample_id": row["sample_id"],
        "url": row["url"],
        "institution": row.get("institution") or "",
        "language": row.get("language_hint") or "",
        "subtype": row.get("subtype_hint") or "strategy_research",
        "source_class": "official_candidate",
        "capture_mode": capture_mode,
        "enabled": enabled,
        "discovery": {
            "seed_url": row.get("seed_url"),
            "score": row.get("score"),
            "score_reasons": row.get("score_reasons") or [],
            "title_hint": row.get("title_hint") or "",
            "link_text": row.get("link_text") or "",
            "text_length_hint": row.get("text_length_hint"),
        },
    }


def uniquify_sample_ids(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, int] = {}
    for sample in samples:
        base = sample["sample_id"]
        count = seen.get(base, 0)
        seen[base] = count + 1
        if count:
            suffix = f"_{count + 1}"
            sample["sample_id"] = f"{base[: 90 - len(suffix)]}{suffix}"
    return samples


if __name__ == "__main__":
    raise SystemExit(main())
