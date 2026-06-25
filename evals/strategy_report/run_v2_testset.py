from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from run_eval_v2 import run_one_v2  # noqa: E402
from verifier_config import apply_model_config_to_profile  # noqa: E402
from verifier_profiles import load_verifier_profile, profile_get  # noqa: E402


DEFAULT_SELECTION = HERE / "v2_testset_selection.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Verifier V2 over the curated strategy-report core test set.")
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "evals" / "strategy_report" / "results" / "v2_core_24_rules")
    parser.add_argument("--verifier-profile", default="v2_html_smoke")
    parser.add_argument("--api-key-file", type=Path, default=ROOT / "api_key.txt")
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--sample-id", action="append", default=[])
    parser.add_argument("--no-extract-charts", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    selection = read_json(args.selection)
    samples = selection["samples"]
    if args.sample_id:
        requested = set(args.sample_id)
        samples = [sample for sample in samples if sample["sample_id"] in requested]
        missing = requested - {sample["sample_id"] for sample in samples}
        if missing:
            raise ValueError(f"Unknown sample ids: {sorted(missing)}")
    if args.max_samples is not None:
        samples = samples[: args.max_samples]

    profile = apply_model_config_to_profile(load_verifier_profile(args.verifier_profile))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index, sample in enumerate(samples, start=1):
        print(f"[{index}/{len(samples)}] {sample['sample_id']} {sample['path']}", flush=True)
        try:
            result = run_one_v2(
                candidate_report=ROOT / sample["path"],
                out_dir=args.out_dir / sample["sample_id"],
                report_id=sample["sample_id"],
                report_title=sample.get("title") or "",
                report_institution=sample.get("institution") or "",
                verifier_profile=profile,
                api_key_file=args.api_key_file,
                enable_chart_vl_judge=bool(profile_get(profile, "modules.enable_chart_vl_judge", False)),
                enable_claim_numeric_llm=bool(profile_get(profile, "modules.enable_claim_numeric_llm", False)),
                enable_strategy_reasoning_llm=bool(profile_get(profile, "modules.enable_strategy_reasoning_llm", False)),
                enable_compliance_llm=bool(profile_get(profile, "modules.enable_compliance_llm", False)),
                extract_charts=not args.no_extract_charts,
                cache=not args.no_cache,
            )
            rows.append(
                {
                    "sample_id": sample["sample_id"],
                    "path": sample["path"],
                    "language": sample["language"],
                    "format": sample["format"],
                    "subtype": sample["subtype"],
                    "archetype": sample["archetype"],
                    "institution": sample["institution"],
                    "overall_score": result["overall_score"],
                    "grade": result["grade"],
                    "gate_passed": result["gate"]["passed"],
                    "gate_failures": result["gate"]["failures"],
                    "dimension_score_normalized": result["dimension_score_normalized"],
                }
            )
        except Exception as exc:  # noqa: BLE001
            failure = {
                "sample_id": sample["sample_id"],
                "path": sample["path"],
                "error": repr(exc),
            }
            failures.append(failure)
            print(f"FAILED {sample['sample_id']}: {exc!r}", flush=True)

    summary = {
        "testset_name": selection["testset_name"],
        "testset_version": selection["version"],
        "profile_name": profile.get("profile_name"),
        "requested_count": len(samples),
        "completed_count": len(rows),
        "failure_count": len(failures),
        "chart_extraction_enabled": not args.no_extract_charts,
        "results": rows,
        "failures": failures,
    }
    write_json(args.out_dir / "summary.json", summary)
    print(json.dumps({key: summary[key] for key in ["requested_count", "completed_count", "failure_count"]}, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
