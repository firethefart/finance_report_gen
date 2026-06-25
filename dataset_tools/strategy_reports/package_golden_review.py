from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def load_dashboard_cases(dashboard: Path) -> list[dict[str, Any]]:
    html = dashboard.read_text(encoding="utf-8")
    match = re.search(r'<script id="casesData" type="application/json">(.*?)</script>', html, flags=re.S)
    if not match:
        raise ValueError(f"Could not find embedded casesData in {dashboard}")
    return json.loads(match.group(1))


def copy_meta(out_dir: Path, meta_dir: Path) -> None:
    target = out_dir / "meta"
    target.mkdir(parents=True, exist_ok=True)
    for name in ["final_cases_dedup.jsonl", "final_cases_dedup.json", "run_manifest.jsonl"]:
        src = meta_dir / name
        if src.exists():
            shutil.copy2(src, target / name)
    screened_dir = ROOT / "dataset_build" / "curated_strategy_samples_screened"
    for src_name, dst_name in [
        ("screening_report.md", "screening_report.md"),
        ("metadata.jsonl", "screened_source_metadata.jsonl"),
    ]:
        src = screened_dir / src_name
        if src.exists():
            shutil.copy2(src, target / dst_name)


def copy_sources(cases: list[dict[str, Any]], out_dir: Path) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for case in cases:
        href = case.get("_source_href")
        source_path = ((case.get("source_pdf") or {}).get("file_path")) or ""
        if href:
            src = ROOT / "dataset_build" / href
            dst = out_dir / href
        elif source_path:
            src = ROOT / source_path
            rel = source_path.replace("\\", "/")
            if rel.startswith("dataset_build/"):
                rel = rel[len("dataset_build/") :]
            dst = out_dir / rel
        else:
            missing.append({"case_id": case.get("case_id", ""), "reason": "missing_source_path"})
            continue
        if not src.exists():
            missing.append({"case_id": case.get("case_id", ""), "reason": f"not_found: {src}"})
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return missing


def write_manifest(cases: list[dict[str, Any]], out_dir: Path) -> None:
    fields = ["case_id", "institution", "strategy_subtype", "quality_tier", "report_title", "source_href"]
    with (out_dir / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "case_id": case.get("case_id", ""),
                    "institution": (case.get("institution") or {}).get("name", ""),
                    "strategy_subtype": case.get("strategy_subtype", ""),
                    "quality_tier": case.get("quality_tier", ""),
                    "report_title": case.get("report_title", ""),
                    "source_href": case.get("_source_href", ""),
                }
            )


def write_readme(out_dir: Path, case_count: int, missing: list[dict[str, str]]) -> None:
    readme = f"""# Golden Strategy Report Review Package

This folder contains a portable review package for the {case_count} screened golden strategy-report samples.

## How to Open

1. Double-click `start_server.bat`, or start a static server from this folder:

```powershell
python -m http.server 8789
```

2. Open:

```text
http://127.0.0.1:8789/index.html
```

Directly opening `index.html` may show the metadata, but many browsers block local PDF rendering inside the page. The local server path is more reliable.

## Contents

- `index.html`: review dashboard with previous/next navigation, metadata, and source report viewer.
- `manifest.csv`: compact list of case id, institution, subtype, quality tier, title, and local source path.
- `meta/final_cases_dedup.jsonl`: structured golden metadata, one JSON object per sample.
- `meta/final_cases_dedup.json`: structured golden metadata as a JSON array.
- `meta/screening_report.md`: invalid-sample screening notes.
- `curated_strategy_samples_verified/`: copied source PDF/HTML reports used by the dashboard.

## Notes

- The dashboard data is embedded inside `index.html`, so it does not need network access.
- Source files are copied with the same relative paths expected by the dashboard.
- These reports are public research samples collected for internal evaluation research; keep original attribution intact.
"""
    if missing:
        readme += "\n## Missing Sources\n\n"
        for item in missing:
            readme += f"- {item.get('case_id')}: {item.get('reason')}\n"
    (out_dir / "README.md").write_text(readme, encoding="utf-8")
    (out_dir / "start_server.bat").write_text(
        "@echo off\r\n"
        "cd /d %~dp0\r\n"
        "echo Serving golden sample review package at http://127.0.0.1:8789/index.html\r\n"
        "python -m http.server 8789\r\n"
        "pause\r\n",
        encoding="utf-8",
    )


def write_portable_dashboard(src: Path, dst: Path) -> None:
    html = src.read_text(encoding="utf-8")
    html = html.replace("iframe {\n", "iframe, object {\n")
    old = """        $('viewerBody').innerHTML = `<iframe src="${esc(href)}" title="source report"></iframe>`;"""
    new = """        const viewerHref = encodeURI(href);
        if (item._source_kind === 'pdf') {
          $('viewerBody').innerHTML = `<object data="${esc(viewerHref)}" type="application/pdf" title="source report"><iframe src="${esc(viewerHref)}" title="source report"></iframe><div class="empty-viewer">浏览器未能内嵌渲染 PDF，请点击右上角“新窗口打开”。</div></object>`;
        } else {
          $('viewerBody').innerHTML = `<iframe src="${esc(viewerHref)}" title="source report"></iframe>`;
        }"""
    if old not in html:
        raise ValueError("Dashboard template changed; could not patch viewer embed.")
    html = html.replace(old, new)
    dst.write_text(html, encoding="utf-8")


def package_review(dashboard: Path, meta_dir: Path, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_portable_dashboard(dashboard, out_dir / "index.html")
    cases = load_dashboard_cases(dashboard)
    copy_meta(out_dir, meta_dir)
    missing = copy_sources(cases, out_dir)
    write_manifest(cases, out_dir)
    write_readme(out_dir, len(cases), missing)
    source_count = len(list((out_dir / "curated_strategy_samples_verified").rglob("*.*")))
    return {"out_dir": str(out_dir), "case_count": len(cases), "source_file_count": source_count, "missing": missing}


def main() -> None:
    parser = argparse.ArgumentParser(description="Package the 27 golden sample dashboard and source reports for review.")
    parser.add_argument("--dashboard", type=Path, default=ROOT / "dataset_build" / "meta_extraction_dashboard.html")
    parser.add_argument("--meta-dir", type=Path, default=ROOT / "dataset_build" / "meta_extraction_screened27")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "dataset_build" / "golden_samples_review_package")
    args = parser.parse_args()
    result = package_review(args.dashboard, args.meta_dir, args.out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
