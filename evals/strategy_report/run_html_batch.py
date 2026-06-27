from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from run_eval_v2 import run_one_v2  # noqa: E402
from verifier_config import apply_model_config_to_profile  # noqa: E402
from verifier_profiles import load_verifier_profile, profile_get  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run candidate-only verifier over local HTML samples.")
    parser.add_argument("--manifest", type=Path, required=True, help="CSV or JSONL with path/sample_id/title/institution columns.")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--verifier-profile", default="html_skill_iteration")
    parser.add_argument("--api-key-file", type=Path, default=ROOT / "api_key.txt")
    parser.add_argument("--sample-id", action="append", default=[])
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--no-extract-charts", action="store_true")
    parser.add_argument("--include-non-html", action="store_true", help="Run rows that do not look like .html/.htm. Defaults to HTML-only.")
    args = parser.parse_args()

    rows = read_manifest(args.manifest)
    if args.sample_id:
        wanted = set(args.sample_id)
        rows = [row for row in rows if row["sample_id"] in wanted]
    if not args.include_non_html:
        rows = [row for row in rows if is_html_row(row)]
    if args.max_samples is not None:
        rows = rows[: args.max_samples]
    profile = apply_model_config_to_profile(load_verifier_profile(args.verifier_profile))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    completed: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    batch_started = time.time()
    for index, row in enumerate(rows, start=1):
        sample_id = row["sample_id"]
        sample_dir = args.out_dir / sample_id
        result_path = sample_dir / f"{sample_id}.v2.eval.json"
        print(f"[{index}/{len(rows)}] {sample_id} {row['path']}", flush=True)
        if args.resume and result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            completed.append(summary_row(row, result, resumed=True))
            continue
        try:
            sample_started = time.time()
            result = run_one_v2(
                candidate_report=ROOT / row["path"],
                out_dir=sample_dir,
                report_id=sample_id,
                report_title=row.get("title", ""),
                report_institution=row.get("institution", ""),
                verifier_profile=profile,
                api_key_file=args.api_key_file,
                enable_chart_vl_judge=bool(profile_get(profile, "modules.enable_chart_vl_judge", False)),
                enable_claim_numeric_llm=bool(profile_get(profile, "modules.enable_claim_numeric_llm", False)),
                enable_strategy_reasoning_llm=bool(profile_get(profile, "modules.enable_strategy_reasoning_llm", False)),
                enable_compliance_llm=bool(profile_get(profile, "modules.enable_compliance_llm", False)),
                extract_charts=not args.no_extract_charts,
                cache=not args.no_cache,
            )
            completed.append(summary_row(row, result, resumed=False, wall_seconds=round(time.time() - sample_started, 2)))
        except Exception as exc:  # noqa: BLE001
            failure = {"sample_id": sample_id, "path": row["path"], "error": repr(exc)}
            failures.append(failure)
            print(f"FAILED {sample_id}: {exc!r}", flush=True)
    vlm_totals = summarize_batch_vlm(completed)
    summary = {
        "manifest": str(args.manifest),
        "profile_name": profile.get("profile_name"),
        "requested_count": len(rows),
        "completed_count": len(completed),
        "failure_count": len(failures),
        "wall_seconds": round(time.time() - batch_started, 2),
        "vlm_timing": vlm_totals,
        "results": completed,
        "failures": failures,
    }
    write_json(args.out_dir / "summary.json", summary)
    write_summary_csv(args.out_dir / "summary.csv", completed)
    print(json.dumps({k: summary[k] for k in ["requested_count", "completed_count", "failure_count"]}, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


def read_manifest(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    normalized: list[dict[str, str]] = []
    for index, row in enumerate(rows, start=1):
        sample_path = row.get("path") or row.get("candidate_path") or row.get("html_path") or row.get("file_path")
        if not sample_path:
            raise ValueError(f"Manifest row {index} has no path/candidate_path/html_path/file_path")
        sample_id = row.get("sample_id") or row.get("id") or safe_id(Path(sample_path).stem)
        normalized.append(
            {
                "sample_id": safe_id(sample_id),
                "path": sample_path.replace("\\", "/"),
                "title": row.get("title") or "",
                "institution": row.get("institution") or "",
                "format": row.get("format") or row.get("input_format") or "",
            }
        )
    return normalized


def safe_id(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9_\-]+", "_", value).strip("_")[:90] or "html_sample"


def is_html_row(row: dict[str, str]) -> bool:
    fmt = (row.get("format") or "").lower()
    if fmt in {"html", "htm", "local_html"}:
        return True
    suffix = Path(row["path"]).suffix.lower()
    return suffix in {".html", ".htm"}


def summary_row(row: dict[str, str], result: dict[str, Any], resumed: bool, wall_seconds: float | None = None) -> dict[str, Any]:
    adapter = result.get("adapter_manifest") or {}
    browser_status = adapter.get("browser_status") or {}
    confidence = result.get("evaluation_confidence") or {}
    module_results = result.get("module_results") or {}
    structure_metrics = ((module_results.get("structure") or {}).get("metrics") or {})
    visual_metrics = ((module_results.get("visual_qa") or {}).get("metrics") or {})
    vlm_timing = result.get("vlm_timing") or {}
    return {
        "sample_id": row["sample_id"],
        "path": row["path"],
        "overall_score": result.get("overall_score"),
        "quality_score": result.get("quality_score", result.get("overall_score")),
        "evaluation_confidence": confidence.get("score"),
        "grade": result.get("grade"),
        "gate_passed": (result.get("gate") or {}).get("passed"),
        "gate_failures": (result.get("gate") or {}).get("failures") or [],
        "dimension_score_normalized": result.get("dimension_score_normalized") or {},
        "html_parse_status": confidence.get("html_parse_status") or structure_metrics.get("html_parse_status"),
        "parse_quality": structure_metrics.get("parse_quality"),
        "report_likeness": confidence.get("report_likeness") if confidence.get("report_likeness") is not None else structure_metrics.get("report_likeness"),
        "analysis_text_length": confidence.get("analysis_text_length"),
        "browser_status": browser_status.get("status"),
        "adapter_warnings": adapter.get("warnings") or [],
        "visual_score": (module_results.get("visual_qa") or {}).get("score"),
        "visual_coverage_status": visual_metrics.get("visual_coverage_status"),
        "visual_object_count": visual_metrics.get("visual_object_count"),
        "chart_count": visual_metrics.get("chart_count"),
        "scorable_chart_count": visual_metrics.get("scorable_chart_count"),
        "visual_filter_drop_count": visual_metrics.get("visual_filter_drop_count"),
        "vlm_call_count": vlm_timing.get("vlm_call_count", 0),
        "vlm_elapsed_sum_seconds": vlm_timing.get("vlm_elapsed_sum_seconds", 0),
        "vlm_elapsed_avg_seconds": vlm_timing.get("vlm_elapsed_avg_seconds", 0),
        "vlm_elapsed_max_seconds": vlm_timing.get("vlm_elapsed_max_seconds", 0),
        "vlm_full_checklist_count": vlm_timing.get("vlm_full_checklist_count", 0),
        "vlm_gate_only_count": vlm_timing.get("vlm_gate_only_count", 0),
        "vlm_cache_hit_count": vlm_timing.get("cache_hit_count", 0),
        "vlm_cache_miss_count": vlm_timing.get("cache_miss_count", 0),
        "vlm_call_error_count": vlm_timing.get("call_error_count", 0),
        "vlm_budget_skipped_count": vlm_timing.get("budget_skipped_count", 0),
        "vlm_client_error": vlm_timing.get("client_error", ""),
        "vlm_wall_seconds": vlm_timing.get("vlm_wall_seconds", 0),
        "wall_seconds": wall_seconds,
        "top_issue": top_issue(result),
        "resumed": resumed,
    }


def summarize_batch_vlm(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "vlm_call_count": sum(int(row.get("vlm_call_count") or 0) for row in rows),
        "vlm_elapsed_sum_seconds": round(sum(float(row.get("vlm_elapsed_sum_seconds") or 0) for row in rows), 2),
        "vlm_elapsed_max_seconds": max([float(row.get("vlm_elapsed_max_seconds") or 0) for row in rows] or [0]),
        "vlm_full_checklist_count": sum(int(row.get("vlm_full_checklist_count") or 0) for row in rows),
        "vlm_gate_only_count": sum(int(row.get("vlm_gate_only_count") or 0) for row in rows),
        "vlm_cache_hit_count": sum(int(row.get("vlm_cache_hit_count") or 0) for row in rows),
        "vlm_cache_miss_count": sum(int(row.get("vlm_cache_miss_count") or 0) for row in rows),
        "vlm_call_error_count": sum(int(row.get("vlm_call_error_count") or 0) for row in rows),
        "vlm_budget_skipped_count": sum(int(row.get("vlm_budget_skipped_count") or 0) for row in rows),
    }


def top_issue(result: dict[str, Any]) -> str:
    issues = result.get("issues") or []
    if not issues:
        return ""
    first = issues[0]
    return f"{first.get('module')}:{first.get('issue_type')}:{first.get('location')}"


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "sample_id",
        "path",
        "overall_score",
        "quality_score",
        "evaluation_confidence",
        "grade",
        "gate_passed",
        "gate_failures",
        "html_parse_status",
        "parse_quality",
        "report_likeness",
        "analysis_text_length",
        "browser_status",
        "adapter_warnings",
        "visual_score",
        "visual_coverage_status",
        "visual_object_count",
        "chart_count",
        "scorable_chart_count",
        "visual_filter_drop_count",
        "vlm_call_count",
        "vlm_elapsed_sum_seconds",
        "vlm_elapsed_avg_seconds",
        "vlm_elapsed_max_seconds",
        "vlm_full_checklist_count",
        "vlm_gate_only_count",
        "vlm_cache_hit_count",
        "vlm_cache_miss_count",
        "vlm_call_error_count",
        "vlm_budget_skipped_count",
        "vlm_client_error",
        "vlm_wall_seconds",
        "wall_seconds",
        "top_issue",
        "resumed",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: (
                        ";".join(row.get(field) or [])
                        if field in {"gate_failures", "adapter_warnings"}
                        else row.get(field)
                    )
                    for field in fields
                }
            )


if __name__ == "__main__":
    raise SystemExit(main())
