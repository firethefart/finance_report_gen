from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from common import read_jsonl, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize strategy report dataset build artifacts.")
    parser.add_argument("--download", type=Path, default=Path("dataset_build/manifests/download_manifest.jsonl"))
    parser.add_argument("--screening", type=Path, default=Path("dataset_build/manifests/screening_manifest.jsonl"))
    parser.add_argument("--cases", type=Path, default=Path("dataset_build/extracted_meta/candidate_cases.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("dataset_build/summary.json"))
    args = parser.parse_args()

    downloads = read_jsonl(args.download)
    screenings = read_jsonl(args.screening)
    cases = read_jsonl(args.cases)

    summary = {
        "download_jobs": len(downloads),
        "download_status": dict(collections.Counter(row.get("status") for row in downloads)),
        "downloaded_real_pdfs": sum(1 for row in downloads if row.get("is_pdf")),
        "screened_reports": len(screenings),
        "quality_tiers": dict(collections.Counter(row.get("quality_tier") for row in screenings)),
        "strategy_subtypes": dict(collections.Counter(row.get("strategy_subtype") for row in screenings)),
        "institutions": dict(collections.Counter(row.get("institution") for row in screenings)),
        "candidate_cases": len(cases),
        "candidate_case_tiers": dict(collections.Counter(row.get("quality_tier") for row in cases)),
        "candidate_case_subtypes": dict(collections.Counter(row.get("strategy_subtype") for row in cases)),
    }
    write_json(args.out, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"summary={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

