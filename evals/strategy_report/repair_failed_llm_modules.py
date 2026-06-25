from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

from claim_numeric_verifier import run_claim_numeric_llm_verifier
from eval_utils import ROOT, read_json, write_json, write_text
from report_parser import parse_candidate_report
from scoring import aggregate_scores, render_markdown
from strategy_reasoning_verifier import run_strategy_reasoning_llm_verifier
from verifier_profiles import load_verifier_profile, profile_get


def needs_claim_repair(result: dict[str, Any]) -> bool:
    claim = ((result.get("module_results") or {}).get("claim_numeric_llm") or {})
    return (claim.get("llm_judgement") or {}).get("ok") is not True


def needs_strategy_repair(result: dict[str, Any]) -> bool:
    strategy = ((result.get("module_results") or {}).get("strategy_reasoning_llm") or {})
    extraction = strategy.get("extraction") or {}
    chains = extraction.get("chains") or []
    return (strategy.get("llm_judgement") or {}).get("ok") is not True or extraction.get("ok") is not True or not chains


def retry_call(label: str, retries: int, delay_seconds: int, fn, success_fn=None):
    success_fn = success_fn or (lambda result: (result.get("llm_judgement") or {}).get("ok") is True)
    last = None
    for attempt in range(1, retries + 1):
        last = fn()
        if success_fn(last):
            return last, {"label": label, "attempts": attempt, "ok": True}
        time.sleep(delay_seconds * attempt)
    return last, {"label": label, "attempts": retries, "ok": False, "error": module_error(label, last or {})}


def module_error(label: str, result: dict[str, Any]) -> str | None:
    if label == "strategy_reasoning":
        extraction = result.get("extraction") or {}
        if extraction.get("ok") is not True:
            return extraction.get("error") or "strategy_extraction_failed"
    return ((result or {}).get("llm_judgement") or {}).get("error")


def strategy_success(result: dict[str, Any]) -> bool:
    extraction = result.get("extraction") or {}
    return (
        extraction.get("ok") is True
        and bool(extraction.get("chains") or [])
        and (result.get("llm_judgement") or {}).get("ok") is True
    )


def repair_case(case_path: Path, out_dir: Path, profile: dict[str, Any], retries: int, delay_seconds: int) -> dict[str, Any]:
    case = read_json(case_path)
    case_id = case["case_id"]
    eval_path = out_dir / f"{case_id}.eval.json"
    if not eval_path.exists():
        return {"case_id": case_id, "status": "missing_eval_json"}
    result = read_json(eval_path)
    repair_claim = needs_claim_repair(result)
    repair_strategy = needs_strategy_repair(result)
    if not repair_claim and not repair_strategy:
        return {
            "case_id": case_id,
            "status": "already_ok",
            "claim_judge_ok": (((result.get("module_results") or {}).get("claim_numeric_llm") or {}).get("llm_judgement") or {}).get("ok"),
            "strategy_judge_ok": (((result.get("module_results") or {}).get("strategy_reasoning_llm") or {}).get("llm_judgement") or {}).get("ok"),
            "strategy_extraction_ok": ((((result.get("module_results") or {}).get("strategy_reasoning_llm") or {}).get("extraction") or {}).get("ok")),
            "strategy_chain_count": len(((((result.get("module_results") or {}).get("strategy_reasoning_llm") or {}).get("extraction") or {}).get("chains") or [])),
            "overall_score": result.get("overall_score"),
        }

    source_doc = case.get("source_document") or {}
    parsed = parse_candidate_report(
        ROOT / source_doc["file_path"],
        report_id=case_id,
        title=case.get("report_title") or "",
        fmt=source_doc.get("format"),
        work_dir=out_dir,
        render_pages=0,
        cache=True,
    )
    module_results = result.get("module_results") or {}
    events = []

    if repair_claim:
        claim_result, event = retry_call(
            "claim_numeric",
            retries,
            delay_seconds,
            lambda: run_claim_numeric_llm_verifier(
                case,
                parsed,
                api_key_file=ROOT / "api_key.txt",
                out_dir=out_dir,
                extract_model=profile_get(profile, "models.claim_extract"),
                judge_model=profile_get(profile, "models.claim_judge"),
                max_claims=int(profile_get(profile, "claim_numeric.max_claims", 18)),
                config=profile_get(profile, "claim_numeric", {}),
                cache=False,
            ),
        )
        module_results["claim_numeric_llm"] = claim_result
        events.append(event)

    if repair_strategy:
        strategy_result, event = retry_call(
            "strategy_reasoning",
            retries,
            delay_seconds,
            lambda: run_strategy_reasoning_llm_verifier(
                case,
                parsed,
                api_key_file=ROOT / "api_key.txt",
                out_dir=out_dir,
                extract_model=profile_get(profile, "models.strategy_extract"),
                judge_model=profile_get(profile, "models.strategy_judge"),
                max_chains=int(profile_get(profile, "strategy_reasoning.max_chains", 10)),
                config=profile_get(profile, "strategy_reasoning", {}),
                cache=False,
            ),
            success_fn=strategy_success,
        )
        module_results["strategy_reasoning_llm"] = strategy_result
        events.append(event)

    updated = aggregate_scores(case, parsed, module_results, llm_result=result.get("llm_judge"), scoring_profile=profile_get(profile, "scoring", {}))
    updated["verifier_profile"] = result.get("verifier_profile") or profile
    write_json(eval_path, updated)
    write_text(out_dir / f"{case_id}.eval.md", render_markdown(updated))
    return {
        "case_id": case_id,
        "status": "repaired",
        "events": events,
        "claim_judge_ok": (((updated.get("module_results") or {}).get("claim_numeric_llm") or {}).get("llm_judgement") or {}).get("ok"),
        "strategy_judge_ok": (((updated.get("module_results") or {}).get("strategy_reasoning_llm") or {}).get("llm_judgement") or {}).get("ok"),
        "strategy_extraction_ok": ((((updated.get("module_results") or {}).get("strategy_reasoning_llm") or {}).get("extraction") or {}).get("ok")),
        "strategy_chain_count": len(((((updated.get("module_results") or {}).get("strategy_reasoning_llm") or {}).get("extraction") or {}).get("chains") or [])),
        "overall_score": updated.get("overall_score"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry failed text LLM modules and recompute eval scores.")
    parser.add_argument("--cases-dir", type=Path, default=ROOT / "evals/strategy_report/cases_merged33")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--profile", default="full_best_effort")
    parser.add_argument("--case", type=Path, help="Optional single case JSON to repair.")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--delay-seconds", type=int, default=8)
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
        row = repair_case(resolved.resolve(), out_dir, profile, retries=args.retries, delay_seconds=args.delay_seconds)
        rows.append(row)
        write_json(out_dir / "llm_repair_progress.json", {"rows": rows})
        print(f"{row['case_id']}: {row['status']} claim={row.get('claim_judge_ok')} strategy={row.get('strategy_judge_ok')} score={row.get('overall_score')}")
    failures = [
        row
        for row in rows
        if row.get("claim_judge_ok") is False
        or row.get("strategy_judge_ok") is False
        or row.get("strategy_extraction_ok") is False
        or row.get("strategy_chain_count") == 0
        or row.get("status") == "missing_eval_json"
    ]
    write_json(out_dir / "llm_repair_summary.json", {"rows": rows, "failure_count": len(failures), "failures": failures})
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
