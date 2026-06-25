from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from eval_utils import ROOT


DEFAULT_CANDIDATES = ROOT / "evals" / "strategy_report" / "html_localization_candidates.json"
DEFAULT_LOCALIZED_ROOT = ROOT / "dataset_build" / "v2_localized_html"
DEFAULT_OUT = ROOT / "evals" / "strategy_report" / "localized_html_runtime_test_set.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Runtime Adapter manifest from enabled localized HTML candidates.")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--localized-root", type=Path, default=DEFAULT_LOCALIZED_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sample-id", action="append", default=[])
    args = parser.parse_args()

    requested = set(args.sample_id)
    rows = []
    missing = []
    for sample in read_json(args.candidates)["samples"]:
        if not sample.get("enabled", True):
            continue
        if requested and sample["sample_id"] not in requested:
            continue
        path = args.localized_root / sample["sample_id"] / "index.html"
        if not path.exists():
            missing.append(sample["sample_id"])
            continue
        rows.append(
            {
                "id": sample["sample_id"],
                "group": "localized_real_institution",
                "path": str(path.relative_to(ROOT)),
                "expected": (
                    f"{sample['institution']} {sample['subtype']} HTML; "
                    "offline-complete text and meaningful visuals."
                ),
                "institution": sample["institution"],
                "language": sample["language"],
                "subtype": sample["subtype"],
                "archetype": sample["archetype"],
            }
        )
    payload = {
        "name": "v2_localized_real_html_candidates",
        "purpose": "Runtime and visual review set for localized real-institution strategy reports.",
        "samples": rows,
        "missing_enabled_candidates": missing,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"sample_count": len(rows), "missing_count": len(missing), "missing": missing}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
