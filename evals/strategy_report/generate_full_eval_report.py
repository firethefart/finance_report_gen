from __future__ import annotations

import argparse
import collections
import json
import statistics as st
from pathlib import Path
from typing import Any


def safe_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "mean": None, "median": None, "max": None}
    return {"min": min(values), "mean": round(st.mean(values), 2), "median": round(st.median(values), 2), "max": max(values)}


def collect_eval_rows(out_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(out_dir.glob("*.eval.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        modules = data.get("module_results") or {}
        claim = modules.get("claim_numeric_llm") or {}
        strategy = modules.get("strategy_reasoning_llm") or {}
        extraction = strategy.get("extraction") or {}
        chart = modules.get("chart_qa") or {}
        rows.append(
            {
                "case_id": data.get("case_id"),
                "overall_score": data.get("overall_score"),
                "grade": data.get("grade"),
                "gate_passed": (data.get("gate") or {}).get("passed"),
                "gate_failures": (data.get("gate") or {}).get("failures") or [],
                "claim_judge_ok": (claim.get("llm_judgement") or {}).get("ok"),
                "strategy_extraction_ok": extraction.get("ok"),
                "strategy_judge_ok": (strategy.get("llm_judgement") or {}).get("ok"),
                "strategy_chain_count": len(extraction.get("chains") or []),
                "chart_score": chart.get("score"),
                "vl_judged_chart_count": (chart.get("metrics") or {}).get("vl_judged_chart_count"),
                "dimension_score_normalized": data.get("dimension_score_normalized") or {},
                "score_diagnostics": data.get("score_diagnostics") or {},
            }
        )
    return rows


def collect_token_stats(out_dir: Path) -> dict[str, Any]:
    by_judge: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for path in out_dir.glob("**/*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict) or "usage" not in data or "metadata" not in data:
            continue
        usage = data.get("usage") or {}
        metadata = data.get("metadata") or {}
        judge = metadata.get("judge") or "unknown"
        by_judge[judge].append(
            {
                "prompt": usage.get("prompt_tokens") or 0,
                "completion": usage.get("completion_tokens") or 0,
                "total": usage.get("total_tokens") or 0,
                "attempt_count": len(data.get("attempts") or []),
                "error": data.get("error"),
            }
        )
    summary = {}
    for judge, rows in sorted(by_judge.items()):
        summary[judge] = {
            "call_count": len(rows),
            "prompt_tokens": safe_stats([row["prompt"] for row in rows]),
            "completion_tokens": safe_stats([row["completion"] for row in rows]),
            "total_tokens": safe_stats([row["total"] for row in rows]),
            "retry_attempt_count": sum(max(0, row["attempt_count"] - 1) for row in rows),
            "error_count": sum(1 for row in rows if row.get("error")),
        }
    return summary


def build_report(out_dir: Path) -> dict[str, Any]:
    rows = collect_eval_rows(out_dir)
    scores = [row["overall_score"] for row in rows if isinstance(row.get("overall_score"), (int, float))]
    gate_failures = collections.Counter(failure for row in rows for failure in row.get("gate_failures", []))
    suspicious = []
    for row in rows:
        if row.get("strategy_extraction_ok") is not True or row.get("strategy_judge_ok") is not True or row.get("strategy_chain_count") == 0:
            suspicious.append({"case_id": row["case_id"], "reason": "strategy_module_incomplete", "row": row})
        fact_diag = (row.get("score_diagnostics") or {}).get("facts") or {}
        if fact_diag.get("claim_numeric_llm", 1.0) < 0.6 and fact_diag.get("legacy_fact_rules", 0.0) > 0.85:
            suspicious.append({"case_id": row["case_id"], "reason": "llm_low_legacy_high_fact_disagreement", "row": row})
    return {
        "result_dir": str(out_dir),
        "case_count": len(rows),
        "score_distribution": safe_stats(scores),
        "grade_counts": dict(collections.Counter(row.get("grade") for row in rows)),
        "gate_counts": {
            "passed": sum(1 for row in rows if row.get("gate_passed") is True),
            "failed": sum(1 for row in rows if row.get("gate_passed") is False),
        },
        "gate_failure_counts": dict(gate_failures),
        "module_success": {
            "claim_judge": sum(1 for row in rows if row.get("claim_judge_ok") is True),
            "strategy_extraction": sum(1 for row in rows if row.get("strategy_extraction_ok") is True),
            "strategy_judge": sum(1 for row in rows if row.get("strategy_judge_ok") is True),
        },
        "lowest_scores": sorted([(row["case_id"], row["overall_score"]) for row in rows], key=lambda item: item[1] or -1)[:10],
        "token_stats": collect_token_stats(out_dir),
        "suspicious_cases": suspicious[:30],
        "rows": rows,
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Full Eval Report",
        "",
        f"- Result dir: {report['result_dir']}",
        f"- Cases: {report['case_count']}",
        f"- Score min/mean/median/max: {report['score_distribution']}",
        f"- Grades: {report['grade_counts']}",
        f"- Gate: {report['gate_counts']}",
        f"- Gate failures: {report['gate_failure_counts']}",
        f"- Module success: {report['module_success']}",
        "",
        "## Lowest Scores",
    ]
    for case_id, score in report["lowest_scores"]:
        lines.append(f"- {case_id}: {score}")
    lines.extend(["", "## Token Stats"])
    for judge, stats in report["token_stats"].items():
        lines.append(f"- {judge}: calls={stats['call_count']}, total={stats['total_tokens']}, retries={stats['retry_attempt_count']}, errors={stats['error_count']}")
    lines.extend(["", "## Suspicious Cases"])
    if report["suspicious_cases"]:
        for item in report["suspicious_cases"]:
            lines.append(f"- {item['case_id']}: {item['reason']}")
    else:
        lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a full strategy verifier evaluation report.")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    out_dir = args.out_dir.resolve()
    report = build_report(out_dir)
    (out_dir / "full_eval_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, out_dir / "full_eval_report.md")
    print(json.dumps({k: report[k] for k in ["case_count", "score_distribution", "gate_counts", "module_success"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
