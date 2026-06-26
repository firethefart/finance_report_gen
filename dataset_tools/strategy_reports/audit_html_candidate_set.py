from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from common import sha256_file, write_json
from html_article_quality import assess_html_report_quality


ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "evals" / "strategy_report"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit localized HTML candidates and build admitted verifier manifest.")
    parser.add_argument("--localized-dir", type=Path, default=Path("dataset_build/html_candidates_localized"))
    parser.add_argument("--localization-summary", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=Path("dataset_build/html_candidate_audit"))
    parser.add_argument("--min-text-length", type=int, default=2200)
    parser.add_argument("--min-article-quality", type=float, default=45.0)
    parser.add_argument("--max-critical-failed-resources", type=int, default=0)
    parser.add_argument("--max-remote-refs", type=int, default=0)
    parser.add_argument("--per-language", type=int, default=15, help="Admitted manifest quota for zh and en each. Use 0 to keep all admitted.")
    parser.add_argument("--runtime", action="store_true", help="Run html_runtime_adapter_v2 for each admitted static candidate.")
    parser.add_argument("--chrome", default=None)
    args = parser.parse_args()

    sample_dirs = discover_sample_dirs(args.localized_dir, args.localization_summary)
    audits = [audit_one(sample_dir, args) for sample_dir in sample_dirs]
    admitted = [row for row in audits if row["admitted"]]
    admitted_selected = select_balanced(admitted, args.per_language)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "html_candidate_audit.json", {"rows": audits})
    write_csv(args.out_dir / "html_candidate_audit.csv", audits)
    write_verifier_manifest(args.out_dir / "html_production_manifest.csv", admitted_selected)
    write_json(
        args.out_dir / "summary.json",
        {
            "localized_dir": str(args.localized_dir),
            "candidate_count": len(audits),
            "admitted_count": len(admitted),
            "selected_count": len(admitted_selected),
            "language_counts_all": dict(collections.Counter(row["language"] for row in audits)),
            "language_counts_admitted": dict(collections.Counter(row["language"] for row in admitted)),
            "language_counts_selected": dict(collections.Counter(row["language"] for row in admitted_selected)),
            "common_errors": dict(collections.Counter(error for row in audits for error in row["errors"])),
            "manifest": str(args.out_dir / "html_production_manifest.csv"),
        },
    )
    print(
        json.dumps(
            {
                "candidate_count": len(audits),
                "admitted_count": len(admitted),
                "selected_count": len(admitted_selected),
                "language_counts_selected": dict(collections.Counter(row["language"] for row in admitted_selected)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if admitted_selected else 1


def discover_sample_dirs(localized_dir: Path, summary_path: Path | None) -> list[Path]:
    dirs: list[Path] = []
    if summary_path and summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        for row in summary.get("rows") or []:
            localized_path = row.get("localized_path")
            if localized_path:
                dirs.append((ROOT / localized_path).parent)
    if not dirs and localized_dir.exists():
        dirs = [path for path in localized_dir.iterdir() if path.is_dir() and (path / "index.html").exists()]
    return sorted(set(path.resolve() for path in dirs))


def audit_one(sample_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    index_path = sample_dir / "index.html"
    metadata_path = sample_dir / "metadata.json"
    resource_manifest_path = sample_dir / "resource_manifest.json"
    errors: list[str] = []
    warnings: list[str] = []
    metadata = read_json(metadata_path) if metadata_path.exists() else {}
    resource_manifest = read_json(resource_manifest_path) if resource_manifest_path.exists() else {}
    if not index_path.exists():
        errors.append("missing_index_html")
        html = ""
    else:
        html = index_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    text = clean_text(soup.get_text(" ", strip=True))
    language = metadata.get("language") or detect_language(text)
    article_quality = assess_html_report_quality(html, source_url=metadata.get("url") or "", min_text_length=args.min_text_length)
    remote_refs = collect_remote_refs(soup)
    missing_local_refs = collect_missing_local_refs(soup, sample_dir)
    critical_failed = int(resource_manifest.get("critical_failed_count") or 0)
    failed_count = int(resource_manifest.get("failed_count") or 0)
    visual_count_static = len(soup.find_all(["img", "svg", "canvas", "table", "figure"]))
    if len(text) < args.min_text_length:
        errors.append("text_too_short")
    if not article_quality.article_like:
        errors.extend(article_quality.reject_reasons)
    if article_quality.quality_score < args.min_article_quality:
        errors.append("article_quality_below_threshold")
    if critical_failed > args.max_critical_failed_resources:
        errors.append("critical_resource_failures")
    elif failed_count:
        warnings.append("noncritical_resource_failures")
    if len(remote_refs) > args.max_remote_refs:
        errors.append("remote_resource_refs")
    if missing_local_refs:
        errors.append("missing_local_resource_refs")
    if not visual_count_static:
        warnings.append("no_static_visual_candidates")
    runtime_audit: dict[str, Any] = {}
    if args.runtime and not errors:
        runtime_audit = run_runtime_audit(index_path, args.chrome)
        if not runtime_audit.get("adapter_ok"):
            errors.append("runtime_adapter_failed")
        if runtime_audit.get("warnings"):
            warnings.extend(f"runtime:{item}" for item in runtime_audit["warnings"])
    return {
        "sample_id": sample_dir.name,
        "path": relative_to_root(index_path),
        "metadata_path": relative_to_root(metadata_path) if metadata_path.exists() else "",
        "resource_manifest_path": relative_to_root(resource_manifest_path) if resource_manifest_path.exists() else "",
        "source_url": metadata.get("url") or metadata.get("source_url") or "",
        "institution": metadata.get("institution") or "",
        "title": ((metadata.get("snapshot") or {}).get("title") or metadata.get("title") or ""),
        "language": language,
        "subtype": metadata.get("subtype") or "",
        "source_class": metadata.get("source_class") or "",
        "text_length": len(text),
        "article_text_length": article_quality.text_length,
        "article_quality_score": article_quality.quality_score,
        "article_quality": article_quality.to_dict(),
        "visual_count_static": visual_count_static,
        "resource_count": int(resource_manifest.get("resource_count") or 0),
        "failed_resource_count": failed_count,
        "critical_failed_resource_count": critical_failed,
        "remote_ref_count": len(remote_refs),
        "missing_local_ref_count": len(missing_local_refs),
        "sha256": sha256_file(index_path) if index_path.exists() else "",
        "admitted": not errors,
        "errors": errors,
        "warnings": sorted(set(warnings)),
        "runtime_audit": runtime_audit,
    }


def run_runtime_audit(index_path: Path, chrome: str | None) -> dict[str, Any]:
    from html_runtime_adapter_v2 import adapt_html_runtime_v2

    out_dir = index_path.parent / "_runtime_audit"
    try:
        adapter = adapt_html_runtime_v2(index_path, out_dir, index_path.parent.name, max_visuals=12, chrome_path=chrome)
        manifest = adapter.get("manifest") or {}
        return {
            "adapter_ok": bool(adapter.get("report_text", {}).get("text")),
            "text_length": adapter.get("report_text", {}).get("text_length"),
            "visual_count": len(adapter.get("visual_objects", {}).get("visual_objects") or []),
            "warnings": manifest.get("warnings") or [],
        }
    except Exception as exc:  # noqa: BLE001
        return {"adapter_ok": False, "error": repr(exc), "warnings": []}


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def detect_language(text: str) -> str:
    zh_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    ascii_letters = len(re.findall(r"[A-Za-z]", text))
    if zh_chars >= 20 and zh_chars >= ascii_letters * 0.08:
        return "zh"
    return "en"


def collect_remote_refs(soup: BeautifulSoup) -> list[str]:
    refs: list[str] = []
    for tag, attr in [("img", "src"), ("script", "src"), ("link", "href"), ("source", "src"), ("video", "poster")]:
        for node in soup.find_all(tag):
            value = str(node.get(attr) or "")
            if value.startswith(("http://", "https://", "//")):
                refs.append(value)
    return refs


def collect_missing_local_refs(soup: BeautifulSoup, sample_dir: Path) -> list[str]:
    missing: list[str] = []
    for tag, attr in [("img", "src"), ("script", "src"), ("link", "href"), ("source", "src"), ("video", "poster")]:
        for node in soup.find_all(tag):
            value = str(node.get(attr) or "")
            if not value or value.startswith(("#", "data:", "http://", "https://", "//", "mailto:", "tel:")):
                continue
            if not (sample_dir / value).exists():
                missing.append(value)
    return sorted(set(missing))


def select_balanced(rows: list[dict[str, Any]], per_language: int) -> list[dict[str, Any]]:
    rows = sorted(rows, key=lambda item: (-int(item.get("text_length") or 0), item.get("sample_id") or ""))
    if per_language <= 0:
        return rows
    selected: list[dict[str, Any]] = []
    for language in ["zh", "en"]:
        selected.extend([row for row in rows if row["language"] == language][:per_language])
    return sorted(selected, key=lambda item: (item["language"], item["sample_id"]))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "sample_id",
        "path",
        "source_url",
        "institution",
        "title",
        "language",
        "subtype",
        "text_length",
        "article_text_length",
        "article_quality_score",
        "visual_count_static",
        "failed_resource_count",
        "critical_failed_resource_count",
        "remote_ref_count",
        "missing_local_ref_count",
        "admitted",
        "errors",
        "warnings",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_cell(row.get(field)) for field in fields})


def write_verifier_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "sample_id",
        "path",
        "candidate_path",
        "title",
        "institution",
        "language",
        "format",
        "subtype",
        "source_class",
        "source_url",
        "resource_manifest",
        "quality_tier",
        "recommended_runner",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "sample_id": row["sample_id"],
                    "path": row["path"],
                    "candidate_path": row["path"],
                    "title": row.get("title") or "",
                    "institution": row.get("institution") or "",
                    "language": row.get("language") or "",
                    "format": "html",
                    "subtype": row.get("subtype") or "",
                    "source_class": row.get("source_class") or "official_candidate_localized",
                    "source_url": row.get("source_url") or "",
                    "resource_manifest": row.get("resource_manifest_path") or "",
                    "quality_tier": "candidate",
                    "recommended_runner": "evals/strategy_report/run_html_batch.py",
                }
            )


def format_cell(value: Any) -> str:
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "" if value is None else str(value)


def relative_to_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


if __name__ == "__main__":
    raise SystemExit(main())
