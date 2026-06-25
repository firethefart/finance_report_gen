from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from eval_utils import ROOT, write_json


def case_id_from_path(path: Path) -> str:
    return path.stem


def run_case(
    case_path: Path,
    cases_dir: Path,
    out_dir: Path,
    profile: str,
    chart_vl_max_charts: int,
    timeout_seconds: int,
    force: bool,
) -> dict[str, Any]:
    case_id = case_id_from_path(case_path)
    eval_path = out_dir / f"{case_id}.eval.json"
    if eval_path.exists() and not force:
        return summarize_existing(case_id, eval_path, skipped=True)

    cmd = [
        sys.executable,
        str(ROOT / "evals/strategy_report/run_eval.py"),
        "--case",
        str(case_path),
        "--cases-dir",
        str(cases_dir),
        "--out-dir",
        str(out_dir),
        "--verifier-profile",
        profile,
        "--chart-vl-max-charts",
        str(chart_vl_max_charts),
    ]
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "case_id": case_id,
            "status": "timeout",
            "elapsed_seconds": round(time.time() - started, 2),
            "returncode": None,
            "stdout_tail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
            "eval_json_exists": eval_path.exists(),
        }

    row = {
        "case_id": case_id,
        "status": "ok" if proc.returncode == 0 and eval_path.exists() else "failed",
        "elapsed_seconds": round(time.time() - started, 2),
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
        "eval_json_exists": eval_path.exists(),
    }
    if eval_path.exists():
        row.update(summarize_eval(eval_path))
    return row


def summarize_existing(case_id: str, eval_path: Path, skipped: bool = False) -> dict[str, Any]:
    row = {
        "case_id": case_id,
        "status": "skipped_existing" if skipped else "ok",
        "elapsed_seconds": 0.0,
        "returncode": 0,
        "eval_json_exists": True,
    }
    row.update(summarize_eval(eval_path))
    return row


def summarize_eval(eval_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(eval_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"eval_parse_error": repr(exc)}
    modules = data.get("module_results") or {}
    claim = modules.get("claim_numeric_llm") or {}
    strategy = modules.get("strategy_reasoning_llm") or {}
    strategy_extraction = strategy.get("extraction") or {}
    chart = modules.get("chart_qa") or {}
    return {
        "overall_score": data.get("overall_score"),
        "grade": data.get("grade"),
        "gate_passed": (data.get("gate") or {}).get("passed"),
        "gate_failures": (data.get("gate") or {}).get("failures") or [],
        "facts_norm": (data.get("dimension_score_normalized") or {}).get("facts"),
        "strategy_norm": (data.get("dimension_score_normalized") or {}).get("strategy_reasoning"),
        "charts_norm": (data.get("dimension_score_normalized") or {}).get("charts"),
        "claim_numeric_score": claim.get("score"),
        "claim_judge_ok": (claim.get("llm_judgement") or {}).get("ok"),
        "strategy_reasoning_score": strategy.get("score"),
        "strategy_judge_ok": (strategy.get("llm_judgement") or {}).get("ok"),
        "strategy_extraction_ok": strategy_extraction.get("ok"),
        "strategy_chain_count": len((strategy_extraction.get("chains") or [])),
        "strategy_module_complete": (
            strategy_extraction.get("ok") is True
            and bool(strategy_extraction.get("chains") or [])
            and (strategy.get("llm_judgement") or {}).get("ok") is True
        ),
        "chart_score": chart.get("score"),
        "chart_count": len((((modules.get("chart_inventory") or {}) or {}).get("charts") or [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run strategy verifier full batch with resume-friendly per-case subprocesses.")
    parser.add_argument("--cases-dir", type=Path, default=ROOT / "evals/strategy_report/cases_merged33")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--profile", default="full_best_effort")
    parser.add_argument("--chart-vl-max-charts", type=int, default=4)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    out_dir = (ROOT / args.out_dir).resolve() if not args.out_dir.is_absolute() else args.out_dir
    cases_dir = (ROOT / args.cases_dir).resolve() if not args.cases_dir.is_absolute() else args.cases_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = [p.resolve() for p in sorted(cases_dir.glob("*.json")) if p.name != "index.json"]
    write_json(
        out_dir / "batch_config.json",
        {
            "cases_dir": str(cases_dir),
            "case_count": len(cases),
            "profile": args.profile,
            "chart_vl_max_charts": args.chart_vl_max_charts,
            "workers": args.workers,
            "timeout_seconds": args.timeout_seconds,
            "force": args.force,
        },
    )

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [
            executor.submit(
                run_case,
                case,
                cases_dir,
                out_dir,
                args.profile,
                args.chart_vl_max_charts,
                args.timeout_seconds,
                args.force,
            )
            for case in cases
        ]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            write_json(out_dir / "batch_progress.json", {"rows": sorted(rows, key=lambda item: item["case_id"])})
            print(f"{row['case_id']}: {row['status']} score={row.get('overall_score')} elapsed={row.get('elapsed_seconds')}")

    rows = sorted(rows, key=lambda item: item["case_id"])
    failures = [
        row
        for row in rows
        if row.get("status") not in {"ok", "skipped_existing"}
        or row.get("claim_judge_ok") is False
        or row.get("strategy_module_complete") is False
    ]
    summary = {
        "case_count": len(rows),
        "completed_count": len(rows) - len(failures),
        "failure_count": len(failures),
        "failures": failures,
        "rows": rows,
    }
    write_json(out_dir / "batch_summary.json", summary)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
