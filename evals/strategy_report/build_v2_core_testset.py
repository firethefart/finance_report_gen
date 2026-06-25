from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from eval_utils import ROOT


OLD_SELECTION = ROOT / "evals" / "strategy_report" / "v2_testset_selection.json"
FROZEN_HTML = ROOT / "evals" / "strategy_report" / "v2_frozen_html_set.json"
DEFAULT_OUT = ROOT / "evals" / "strategy_report" / "v2_testset_selection.json"

KEEP_PDF_IDS = [
    "v2_en_jpm_energy_2025",
    "v2_en_fidelity_outlook_2026",
    "v2_en_blackrock_chartbook_2026",
    "v2_en_gsam_active_etf",
    "v2_zh_guojin_midyear_2026",
    "v2_zh_boc_macro_midyear_2026",
    "v2_zh_huabao_allocation_202606",
    "v2_zh_dongwu_bse_midyear_2026",
    "v2_zh_aijian_q2_allocation_2026",
    "v2_zh_guoyuan_macro_monthly_202605",
    "v2_zh_wanlian_bayarea_strategy",
    "v2_zh_guosen_resident_funds_chartbook",
    "v2_zh_kaiyuan_smart_mining",
    "v2_zh_huaxin_weekly_20260525",
]
KEEP_GENERATED_IDS = ["v2_zh_generated_baseline", "v2_zh_generated_optimized"]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the balanced V2 core set from selected PDFs and frozen HTML.")
    parser.add_argument("--old-selection", type=Path, default=OLD_SELECTION)
    parser.add_argument("--frozen-html", type=Path, default=FROZEN_HTML)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    old = read_json(args.old_selection)
    by_id = {sample["sample_id"]: sample for sample in old["samples"]}
    pdfs = [by_id[sample_id] for sample_id in KEEP_PDF_IDS]
    generated = [by_id[sample_id] for sample_id in KEEP_GENERATED_IDS]
    html = read_json(args.frozen_html)["samples"]
    payload = {
        "testset_name": "strategy_report_v2_core_26_html_balanced",
        "version": "2026-06-18",
        "scope": "High-quality strategy research reports for candidate-only Verifier V2 optimization.",
        "target_count": 26,
        "hard_requirements": {
            "minimum_total_count": 20,
            "maximum_total_count": 30,
            "minimum_html_count": 10,
            "minimum_high_quality_html_count": 10,
            "minimum_real_institution_html_count": 8,
            "maximum_generated_html_count": 2,
            "maximum_single_html_institution_count": 4,
            "minimum_html_subtype_count": 5
        },
        "selection_principles": [
            "Only strategy research reports are eligible.",
            "At least ten HTML reports must be real, high-quality, fully localized, offline-complete, and visually reviewed.",
            "Synthetic fixtures remain separate and do not count toward report-level sample totals.",
            "The two local generated HTML reports are retained only as historical quality controls.",
            "PDFs are retained for chartbooks, parser robustness, long reports, Chinese broker layouts, and subtype coverage.",
            "All core samples must pass the same automated audit before a baseline run."
        ],
        "samples": [*html, *pdfs, *generated],
        "quarantine_candidates": old.get("quarantine_candidates", []),
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "total": len(payload["samples"]),
        "html": sum(sample["format"] == "html" for sample in payload["samples"]),
        "pdf": sum(sample["format"] == "pdf" for sample in payload["samples"]),
        "en": sum(sample["language"] == "en" for sample in payload["samples"]),
        "zh": sum(sample["language"] == "zh" for sample in payload["samples"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
