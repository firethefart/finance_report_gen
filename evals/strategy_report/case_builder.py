from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from eval_utils import ROOT, read_jsonl, write_json


def build_case(meta: dict[str, Any]) -> dict[str, Any]:
    source_pdf = meta.get("source_pdf") or {}
    institution = meta.get("institution") or {}
    candidate_query = meta.get("candidate_query") or {}
    return {
        "case_id": meta["case_id"],
        "query": candidate_query.get("query") or "",
        "query_language": candidate_query.get("language"),
        "query_style": candidate_query.get("query_style"),
        "scope_constraints": candidate_query.get("scope_constraints") or [],
        "expected_report_type": meta.get("expected_report_type") or {},
        "institution": institution,
        "report_title": meta.get("report_title"),
        "report_date": meta.get("report_date"),
        "publication_period": meta.get("publication_period"),
        "strategy_subtype": meta.get("strategy_subtype"),
        "quality_tier": meta.get("quality_tier"),
        "source_document": {
            "file_path": source_pdf.get("file_path"),
            "file_name": source_pdf.get("file_name"),
            "format": infer_format(source_pdf.get("file_name") or source_pdf.get("file_path") or ""),
            "sha256": source_pdf.get("sha256"),
            "page_count": source_pdf.get("page_count"),
            "parse_quality": source_pdf.get("parse_quality"),
        },
        "source_pack": meta.get("source_pack") or [],
        "key_facts": meta.get("key_facts") or [],
        "must_have_sections": meta.get("must_have_sections") or [],
        "prohibited_mistakes": meta.get("prohibited_mistakes") or [],
        "charts_and_tables_to_learn_from": meta.get("charts_and_tables_to_learn_from") or [],
        "evaluation_hooks": meta.get("evaluation_hooks") or {},
        "reference_notes": meta.get("reference_notes") or {},
        "extraction_confidence": meta.get("extraction_confidence") or {},
        "calibration_role": "source_document_as_candidate_until_generation_pipeline_exists",
    }


def infer_format(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".pdf":
        return "pdf"
    return "pdf"


def build_cases(input_path: Path, out_dir: Path, limit: int | None = None) -> list[Path]:
    metas = read_jsonl(input_path)
    written: list[Path] = []
    for meta in metas[:limit]:
        case = build_case(meta)
        out_path = out_dir / f"{case['case_id']}.json"
        write_json(out_path, case)
        written.append(out_path)
    index = {
        "source": str(input_path),
        "count": len(written),
        "cases": [str(path) for path in written],
    }
    write_json(out_dir / "index.json", index)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Build strategy report eval cases from extracted golden metadata.")
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "dataset_build" / "meta_extraction_screened27" / "final_cases_dedup.jsonl",
    )
    parser.add_argument("--out-dir", type=Path, default=ROOT / "evals" / "strategy_report" / "cases")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    written = build_cases(args.input, args.out_dir, args.limit)
    print(f"Wrote {len(written)} cases to {args.out_dir}")


if __name__ == "__main__":
    main()

