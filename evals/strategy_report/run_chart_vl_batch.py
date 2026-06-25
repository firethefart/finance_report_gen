from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from chart_extractor import extract_chart_candidates
from chart_judges import run_chart_vl_judges
from chart_qa import chart_qa_v2_check
from eval_utils import ROOT, read_json, write_json, write_text
from report_parser import parse_candidate_report
from scoring import aggregate_scores, render_markdown
from verifier_profiles import load_verifier_profile, profile_get


def run_chart_case(
    case_path: Path,
    out_dir: Path,
    profile: dict[str, Any],
    max_charts: int,
    force_recompute_score: bool = True,
) -> dict[str, Any]:
    case = read_json(case_path)
    case_id = case["case_id"]
    eval_path = out_dir / f"{case_id}.eval.json"
    if not eval_path.exists():
        return {"case_id": case_id, "status": "missing_eval_json"}
    result = read_json(eval_path)
    source_doc = case.get("source_document") or {}
    candidate = ROOT / source_doc["file_path"]
    parsed = parse_candidate_report(
        candidate,
        report_id=case_id,
        title=case.get("report_title") or "",
        fmt=source_doc.get("format"),
        work_dir=out_dir,
        render_pages=0,
        cache=True,
    )
    inventory = extract_chart_candidates(
        candidate,
        report_id=case_id,
        fmt=source_doc.get("format") or parsed.get("format"),
        out_dir=out_dir,
        expected_charts=case.get("charts_and_tables_to_learn_from") or [],
        max_pages=int(profile_get(profile, "chart.max_pages", 40)),
        max_charts=int(profile_get(profile, "chart.max_charts", 40)),
        cache=True,
    )
    parsed["chart_inventory"] = inventory
    judged = run_chart_vl_judges(
        inventory.get("charts") or [],
        parsed,
        api_key_file=ROOT / "api_key.txt",
        out_dir=out_dir,
        model=profile_get(profile, "models.chart_vl"),
        max_charts=max_charts,
        max_tokens=int(profile_get(profile, "chart.vl_max_tokens", 4200)),
        repair_max_tokens=int(profile_get(profile, "chart.vl_repair_max_tokens", 2600)),
    )
    module_results = result.get("module_results") or {}
    module_results["chart_qa"] = chart_qa_v2_check(case, parsed, inventory, judged)
    if force_recompute_score:
        updated = aggregate_scores(case, parsed, module_results, llm_result=result.get("llm_judge"), scoring_profile=profile_get(profile, "scoring", {}))
        updated["verifier_profile"] = result.get("verifier_profile") or profile
        write_json(eval_path, updated)
        write_text(out_dir / f"{case_id}.eval.md", render_markdown(updated))
        result = updated
    return {
        "case_id": case_id,
        "status": "ok",
        "chart_count": len(inventory.get("charts") or []),
        "vl_judged_count": len(judged),
        "chart_score": module_results["chart_qa"].get("score"),
        "overall_score": result.get("overall_score"),
        "gate_failures": (result.get("gate") or {}).get("failures") or [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or extend Chart VLM judging as a separate resumable batch.")
    parser.add_argument("--cases-dir", type=Path, default=ROOT / "evals/strategy_report/cases_merged33")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--profile", default="full_best_effort")
    parser.add_argument("--max-charts", type=int, default=4)
    parser.add_argument("--case", type=Path)
    args = parser.parse_args()

    out_dir = (ROOT / args.out_dir).resolve() if not args.out_dir.is_absolute() else args.out_dir
    cases_dir = (ROOT / args.cases_dir).resolve() if not args.cases_dir.is_absolute() else args.cases_dir
    profile = load_verifier_profile(args.profile)
    case_paths = [args.case] if args.case else sorted(cases_dir.glob("*.json"))
    rows = []
    for case_path in case_paths:
        if case_path.name == "index.json":
            continue
        resolved = case_path if case_path.is_absolute() else ROOT / case_path
        row = run_chart_case(resolved.resolve(), out_dir, profile, max_charts=args.max_charts)
        rows.append(row)
        write_json(out_dir / "chart_vl_batch_progress.json", {"rows": rows})
        print(f"{row['case_id']}: {row['status']} vl={row.get('vl_judged_count')} score={row.get('chart_score')}")
    failures = [row for row in rows if row.get("status") != "ok"]
    write_json(out_dir / "chart_vl_batch_summary.json", {"rows": rows, "failure_count": len(failures), "failures": failures})
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
