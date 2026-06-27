from __future__ import annotations

import argparse
from pathlib import Path

from case_builder import build_cases
from chart_extractor import extract_chart_candidates
from chart_judges import DEFAULT_VL_MODEL, run_chart_vl_judges
from chart_qa import chart_qa_v2_check
from checks import run_rule_checks
from claim_numeric_verifier import DEFAULT_CLAIM_EXTRACT_MODEL, DEFAULT_CLAIM_JUDGE_MODEL, run_claim_numeric_llm_verifier
from eval_utils import ROOT, read_json, write_json, write_text
from feedback import write_feedback_artifacts
from llm_judges import DEFAULT_MODEL, run_llm_judge
from report_parser import parse_candidate_report
from run_eval_v2 import (
    adapt_html_runtime_v2,
    chart_inventory_from_html_adapter,
    merge_chart_vl_judges,
    parsed_from_html_adapter,
    promote_vlm_visual_gate_fallbacks,
    summarize_vlm_timing,
)
from scoring import aggregate_scores, render_markdown
from strategy_reasoning_verifier import DEFAULT_STRATEGY_EXTRACT_MODEL, DEFAULT_STRATEGY_JUDGE_MODEL, run_strategy_reasoning_llm_verifier
from verifier_config import apply_model_config_to_profile
from verifier_profiles import load_verifier_profile, profile_get


def run_one(
    case_path: Path,
    candidate_report: Path | None,
    out_dir: Path,
    enable_llm_judge: bool,
    api_key_file: Path,
    model: str,
    render_pages: int,
    cache: bool,
    extract_charts: bool,
    chart_max_pages: int,
    chart_max_charts: int,
    enable_chart_vl_judge: bool,
    chart_vl_model: str,
    chart_vl_max_charts: int,
    enable_claim_numeric_llm: bool,
    claim_extract_model: str,
    claim_judge_model: str,
    enable_strategy_reasoning_llm: bool,
    strategy_extract_model: str,
    strategy_judge_model: str,
    verifier_profile: dict | None = None,
) -> dict:
    case = read_json(case_path)
    source_doc = case.get("source_document") or {}
    candidate = candidate_report or ROOT / source_doc["file_path"]
    candidate_fmt = source_doc.get("format") if candidate_report is None else None
    is_html = (candidate_fmt or "").lower() in {"html", "htm"} or candidate.suffix.lower() in {".html", ".htm"}
    adapter_manifest: dict = {}
    if is_html:
        adapter_result = adapt_html_runtime_v2(
            html_path=candidate,
            out_dir=out_dir / "html_adapter" / case["case_id"],
            report_id=case["case_id"],
            max_visuals=int(profile_get(verifier_profile or {}, "html_adapter.max_visuals", 80)),
            viewport_width=int(profile_get(verifier_profile or {}, "html_adapter.viewport_width", 1440)),
            viewport_height=int(profile_get(verifier_profile or {}, "html_adapter.viewport_height", 1100)),
            context_height=int(profile_get(verifier_profile or {}, "html_adapter.context_height", 1200)),
        )
        adapter_manifest = adapter_result["manifest"]
        parsed = parsed_from_html_adapter(
            report_id=case["case_id"],
            source_path=candidate,
            adapter_result=adapter_result,
            fallback_title=case.get("report_title") or "",
            institution=(case.get("institution") or {}).get("name") or "",
        )
    else:
        parsed = parse_candidate_report(
            candidate,
            report_id=case["case_id"],
            title=case.get("report_title") or "",
            fmt=candidate_fmt,
            work_dir=out_dir,
            render_pages=render_pages,
            cache=cache,
        )
    if extract_charts and is_html:
        parsed["chart_inventory"] = chart_inventory_from_html_adapter(case["case_id"], adapter_result)
    elif extract_charts:
        chart_inventory = extract_chart_candidates(
            candidate,
            report_id=case["case_id"],
            fmt=candidate_fmt or parsed["format"],
            out_dir=out_dir,
            expected_charts=case.get("charts_and_tables_to_learn_from") or [],
            max_pages=chart_max_pages,
            max_charts=chart_max_charts,
            cache=cache,
        )
        parsed["chart_inventory"] = chart_inventory
    rule_results = run_rule_checks(case, parsed)
    chart_vl_judges = None
    if enable_chart_vl_judge and parsed.get("chart_inventory"):
        chart_vl_judges = run_chart_vl_judges(
            parsed["chart_inventory"].get("charts") or [],
            parsed,
            api_key_file=api_key_file,
            out_dir=out_dir,
            model=chart_vl_model,
            max_charts=chart_vl_max_charts,
            max_tokens=int(profile_get(verifier_profile or {}, "chart.vl_max_tokens", 4200)),
            repair_max_tokens=int(profile_get(verifier_profile or {}, "chart.vl_repair_max_tokens", 2600)),
            selection_strategy=profile_get(verifier_profile or {}, "chart.vl_selection_strategy", "first_n"),
            gate_all=bool(profile_get(verifier_profile or {}, "chart.vl_gate_all", False)),
            gate_max_charts=int(profile_get(verifier_profile or {}, "chart.vl_gate_max_charts", 16)),
            gate_max_tokens=int(profile_get(verifier_profile or {}, "chart.vl_gate_max_tokens", 900)),
            max_total_calls=profile_get(verifier_profile or {}, "chart.vlm_budget.max_total_calls", None),
            max_elapsed_seconds=profile_get(verifier_profile or {}, "chart.vlm_budget.max_elapsed_seconds", None),
        )
        if (
            not (parsed["chart_inventory"].get("charts") or [])
            and parsed["chart_inventory"].get("visual_gate_fallback_candidates")
            and bool(profile_get(verifier_profile or {}, "chart.vl_zero_chart_fallback_enabled", True))
        ):
            fallback_judges = run_chart_vl_judges(
                parsed["chart_inventory"].get("visual_gate_fallback_candidates") or [],
                parsed,
                api_key_file=api_key_file,
                out_dir=out_dir / "visual_gate_fallback",
                model=chart_vl_model,
                max_charts=0,
                max_tokens=int(profile_get(verifier_profile or {}, "chart.vl_max_tokens", 4200)),
                repair_max_tokens=int(profile_get(verifier_profile or {}, "chart.vl_repair_max_tokens", 2600)),
                selection_strategy=profile_get(verifier_profile or {}, "chart.vl_selection_strategy", "first_n"),
                gate_all=True,
                gate_max_charts=int(profile_get(verifier_profile or {}, "chart.vl_zero_chart_fallback_max_visuals", 2)),
                gate_max_tokens=int(profile_get(verifier_profile or {}, "chart.vl_gate_max_tokens", 900)),
                max_total_calls=profile_get(verifier_profile or {}, "chart.vlm_budget.max_fallback_calls", None),
                max_elapsed_seconds=profile_get(verifier_profile or {}, "chart.vlm_budget.max_fallback_elapsed_seconds", None),
            )
            chart_vl_judges = merge_chart_vl_judges(chart_vl_judges, fallback_judges, audit_key="zero_chart_fallback")
            promote_vlm_visual_gate_fallbacks(parsed["chart_inventory"], fallback_judges)
        rule_results["chart_qa"] = chart_qa_v2_check(case, parsed, parsed.get("chart_inventory"), chart_vl_judges)
    if enable_claim_numeric_llm:
        rule_results["claim_numeric_llm"] = run_claim_numeric_llm_verifier(
            case,
            parsed,
            api_key_file=api_key_file,
            out_dir=out_dir,
            extract_model=claim_extract_model,
            judge_model=claim_judge_model,
            max_claims=int(profile_get(verifier_profile or {}, "claim_numeric.max_claims", 18)),
            config=profile_get(verifier_profile or {}, "claim_numeric", {}),
            cache=cache,
        )
    if enable_strategy_reasoning_llm:
        rule_results["strategy_reasoning_llm"] = run_strategy_reasoning_llm_verifier(
            case,
            parsed,
            api_key_file=api_key_file,
            out_dir=out_dir,
            extract_model=strategy_extract_model,
            judge_model=strategy_judge_model,
            max_chains=int(profile_get(verifier_profile or {}, "strategy_reasoning.max_chains", 10)),
            config=profile_get(verifier_profile or {}, "strategy_reasoning", {}),
            cache=cache,
        )
    llm_result = None
    if enable_llm_judge:
        llm_result = run_llm_judge(case, parsed, api_key_file=api_key_file, out_dir=out_dir, model=model)
    result = aggregate_scores(case, parsed, rule_results, llm_result=llm_result, scoring_profile=profile_get(verifier_profile or {}, "scoring", {}))
    if adapter_manifest:
        result["adapter_manifest"] = adapter_manifest
        result["html_parse_status"] = parsed.get("html_parse_status")
        result["parse_quality"] = parsed.get("parse_quality")
        result["report_likeness"] = parsed.get("report_likeness")
        result["html_parse_diagnostics"] = parsed.get("html_parse_diagnostics") or {}
    if chart_vl_judges:
        result["vlm_timing"] = summarize_vlm_timing(chart_vl_judges)
    if verifier_profile:
        result["verifier_profile"] = verifier_profile
    result["feedback"] = write_feedback_artifacts(result, out_dir, flavor="v1_reference", stem=case["case_id"])
    write_json(out_dir / f"{case['case_id']}.eval.json", result)
    write_text(out_dir / f"{case['case_id']}.eval.md", render_markdown(result))
    return result


def ensure_cases(cases_dir: Path, input_path: Path, limit: int | None = None) -> None:
    if (cases_dir / "index.json").exists() and list(cases_dir.glob("*.json")):
        return
    build_cases(input_path, cases_dir, limit=limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run automated strategy-report evaluation.")
    parser.add_argument("--case", type=Path, default=None)
    parser.add_argument("--cases-dir", type=Path, default=ROOT / "evals" / "strategy_report" / "cases")
    parser.add_argument(
        "--cases-input",
        type=Path,
        default=ROOT / "dataset_build" / "meta_extraction_screened27" / "final_cases_dedup.jsonl",
    )
    parser.add_argument("--candidate-report", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "evals" / "strategy_report" / "results" / "smoke")
    parser.add_argument("--max-cases", type=int, default=1)
    parser.add_argument("--enable-llm-judge", action="store_true")
    parser.add_argument("--api-key-file", type=Path, default=ROOT / "api_key.txt")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--render-pages", type=int, default=1)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--no-extract-charts", action="store_true")
    parser.add_argument("--chart-max-pages", type=int, default=40)
    parser.add_argument("--chart-max-charts", type=int, default=16)
    parser.add_argument("--enable-chart-vl-judge", action="store_true")
    parser.add_argument("--chart-vl-model", default=DEFAULT_VL_MODEL)
    parser.add_argument("--chart-vl-max-charts", type=int, default=3)
    parser.add_argument("--enable-claim-numeric-llm", action="store_true")
    parser.add_argument("--claim-extract-model", default=DEFAULT_CLAIM_EXTRACT_MODEL)
    parser.add_argument("--claim-judge-model", default=DEFAULT_CLAIM_JUDGE_MODEL)
    parser.add_argument("--enable-strategy-reasoning-llm", action="store_true")
    parser.add_argument("--strategy-extract-model", default=DEFAULT_STRATEGY_EXTRACT_MODEL)
    parser.add_argument("--strategy-judge-model", default=DEFAULT_STRATEGY_JUDGE_MODEL)
    parser.add_argument("--verifier-profile", default=None, help="Profile name under evals/strategy_report/profiles or path to a profile JSON.")
    args = parser.parse_args()

    profile = apply_model_config_to_profile(load_verifier_profile(args.verifier_profile))
    args.render_pages = args.render_pages if args.render_pages != parser.get_default("render_pages") else int(profile_get(profile, "execution.render_pages", args.render_pages))
    profile_extract_charts = bool(profile_get(profile, "execution.extract_charts", not args.no_extract_charts))
    profile_cache = bool(profile_get(profile, "execution.cache", not args.no_cache))
    args.chart_max_pages = args.chart_max_pages if args.chart_max_pages != parser.get_default("chart_max_pages") else int(profile_get(profile, "chart.max_pages", args.chart_max_pages))
    args.chart_max_charts = args.chart_max_charts if args.chart_max_charts != parser.get_default("chart_max_charts") else int(profile_get(profile, "chart.max_charts", args.chart_max_charts))
    args.chart_vl_max_charts = args.chart_vl_max_charts if args.chart_vl_max_charts != parser.get_default("chart_vl_max_charts") else int(profile_get(profile, "chart.vl_max_charts", args.chart_vl_max_charts))
    args.model = args.model if args.model != parser.get_default("model") else profile_get(profile, "models.consolidated_llm", args.model)
    args.chart_vl_model = args.chart_vl_model if args.chart_vl_model != parser.get_default("chart_vl_model") else profile_get(profile, "models.chart_vl", args.chart_vl_model)
    args.claim_extract_model = args.claim_extract_model if args.claim_extract_model != parser.get_default("claim_extract_model") else profile_get(profile, "models.claim_extract", args.claim_extract_model)
    args.claim_judge_model = args.claim_judge_model if args.claim_judge_model != parser.get_default("claim_judge_model") else profile_get(profile, "models.claim_judge", args.claim_judge_model)
    args.strategy_extract_model = args.strategy_extract_model if args.strategy_extract_model != parser.get_default("strategy_extract_model") else profile_get(profile, "models.strategy_extract", args.strategy_extract_model)
    args.strategy_judge_model = args.strategy_judge_model if args.strategy_judge_model != parser.get_default("strategy_judge_model") else profile_get(profile, "models.strategy_judge", args.strategy_judge_model)

    enable_llm_judge = args.enable_llm_judge or bool(profile_get(profile, "modules.enable_consolidated_llm_judge", False))
    enable_chart_vl_judge = args.enable_chart_vl_judge or bool(profile_get(profile, "modules.enable_chart_vl_judge", False))
    enable_claim_numeric_llm = args.enable_claim_numeric_llm or bool(profile_get(profile, "modules.enable_claim_numeric_llm", False))
    enable_strategy_reasoning_llm = args.enable_strategy_reasoning_llm or bool(profile_get(profile, "modules.enable_strategy_reasoning_llm", False))

    ensure_cases(args.cases_dir, args.cases_input)
    if args.case:
        case_paths = [args.case]
    else:
        case_paths = [p for p in sorted(args.cases_dir.glob("*.json")) if p.name != "index.json"][: args.max_cases]
    results = []
    for case_path in case_paths:
        result = run_one(
            case_path=case_path,
            candidate_report=args.candidate_report,
            out_dir=args.out_dir,
            enable_llm_judge=enable_llm_judge,
            api_key_file=args.api_key_file,
            model=args.model,
            render_pages=args.render_pages,
            cache=(not args.no_cache) and profile_cache,
            extract_charts=(not args.no_extract_charts) and profile_extract_charts,
            chart_max_pages=args.chart_max_pages,
            chart_max_charts=args.chart_max_charts,
            enable_chart_vl_judge=enable_chart_vl_judge,
            chart_vl_model=args.chart_vl_model,
            chart_vl_max_charts=args.chart_vl_max_charts,
            enable_claim_numeric_llm=enable_claim_numeric_llm,
            claim_extract_model=args.claim_extract_model,
            claim_judge_model=args.claim_judge_model,
            enable_strategy_reasoning_llm=enable_strategy_reasoning_llm,
            strategy_extract_model=args.strategy_extract_model,
            strategy_judge_model=args.strategy_judge_model,
            verifier_profile=profile,
        )
        results.append(result)
        print(f"{result['case_id']}: {result['overall_score']} {result['grade']} gate={result['gate']['passed']}")
    all_results = []
    for result_path in sorted(args.out_dir.glob("*.eval.json")):
        all_results.append(read_json(result_path))
    summary = {
        "count": len(all_results),
        "results": [
            {
                "case_id": r["case_id"],
                "overall_score": r["overall_score"],
                "grade": r["grade"],
                "gate_passed": r["gate"]["passed"],
                "gate_failures": r["gate"]["failures"],
                "chart_count": r.get("module_results", {}).get("chart_qa", {}).get("metrics", {}).get("chart_count"),
                "chart_score": r.get("dimension_scores", {}).get("charts"),
                "html_parse_status": r.get("html_parse_status"),
                "parse_quality": r.get("parse_quality"),
                "report_likeness": r.get("report_likeness"),
                "visual_coverage_status": (r.get("module_results", {}).get("chart_qa", {}).get("metrics", {}) or {}).get("visual_coverage_status"),
                "visual_object_count": (r.get("module_results", {}).get("chart_qa", {}).get("metrics", {}) or {}).get("visual_object_count"),
                "scorable_chart_count": (r.get("module_results", {}).get("chart_qa", {}).get("metrics", {}) or {}).get("scorable_chart_count"),
                "vlm_call_count": (r.get("vlm_timing") or {}).get("vlm_call_count"),
                "vlm_elapsed_sum_seconds": (r.get("vlm_timing") or {}).get("vlm_elapsed_sum_seconds"),
                "vlm_cache_hit_count": (r.get("vlm_timing") or {}).get("cache_hit_count"),
                "vlm_call_error_count": (r.get("vlm_timing") or {}).get("call_error_count"),
                "vlm_budget_skipped_count": (r.get("vlm_timing") or {}).get("budget_skipped_count"),
                "feedback_markdown": (r.get("feedback") or {}).get("feedback_markdown"),
                "feedback_json": (r.get("feedback") or {}).get("feedback_json"),
            }
            for r in all_results
        ],
    }
    write_json(args.out_dir / "summary.json", summary)


if __name__ == "__main__":
    main()
