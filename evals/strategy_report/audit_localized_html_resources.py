from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from eval_utils import ROOT


DEFAULT_ROOT = ROOT / "dataset_build" / "v2_localized_html"
DEFAULT_OUT = ROOT / "evals" / "strategy_report" / "results" / "localized_html_resource_audit.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resource_refs(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    refs: list[str] = []
    for tag, attr in [
        ("img", "src"),
        ("source", "src"),
        ("script", "src"),
        ("link", "href"),
        ("video", "poster"),
        ("object", "data"),
    ]:
        for node in soup.find_all(tag):
            value = str(node.get(attr) or "").strip()
            if value:
                refs.append(value)
    for node in soup.find_all(style=True):
        refs.extend(re.findall(r"url\([\"']?([^\"')]+)", str(node.get("style") or ""), re.I))
    for node in soup.find_all("style"):
        refs.extend(re.findall(r"url\([\"']?([^\"')]+)", node.get_text(), re.I))
    return refs


def audit_sample(sample_dir: Path) -> dict[str, Any]:
    html_path = sample_dir / "index.html"
    manifest_path = sample_dir / "resource_manifest.json"
    errors: list[str] = []
    if not html_path.exists():
        return {"sample_id": sample_dir.name, "admitted": False, "errors": ["missing_index_html"]}
    if not manifest_path.exists():
        return {"sample_id": sample_dir.name, "admitted": False, "errors": ["missing_resource_manifest"]}

    manifest = read_json(manifest_path)
    downloaded = [item for item in manifest["resources"] if item["status"] == "downloaded"]
    failed = [item for item in manifest["resources"] if item["status"] == "failed"]
    critical_failed = [item for item in failed if item.get("critical", True)]
    for item in downloaded:
        local_path = item.get("local_path")
        if not local_path:
            errors.append(f"downloaded_without_local_path:{item['original_url']}")
            continue
        path = sample_dir / local_path
        if not path.exists():
            errors.append(f"missing_local_file:{local_path}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item.get("sha256"):
            errors.append(f"hash_mismatch:{local_path}")
        if path.stat().st_size != item.get("bytes"):
            errors.append(f"size_mismatch:{local_path}")

    refs = resource_refs(html_path.read_text(encoding="utf-8", errors="replace"))
    remote_refs = sorted(
        {
            ref
            for ref in refs
            if ref.startswith(("http://", "https://", "//"))
        }
    )
    missing_html_refs = []
    for ref in refs:
        if ref.startswith(("data:", "#", "javascript:", "mailto:", "tel:", "http://", "https://", "//")):
            continue
        path = sample_dir / ref.split("?", 1)[0].split("#", 1)[0]
        if not path.exists():
            missing_html_refs.append(ref)
    if remote_refs:
        errors.append(f"remote_resource_refs:{len(remote_refs)}")
    if missing_html_refs:
        errors.append(f"missing_html_resource_refs:{len(set(missing_html_refs))}")
    if critical_failed:
        errors.append(f"critical_failed_manifest_resources:{len(critical_failed)}")

    return {
        "sample_id": sample_dir.name,
        "admitted": not errors,
        "resource_count": manifest["resource_count"],
        "downloaded_count": len(downloaded),
        "failed_count": len(failed),
        "critical_failed_count": len(critical_failed),
        "total_bytes": manifest["total_bytes"],
        "remote_resource_refs": remote_refs,
        "missing_html_resource_refs": sorted(set(missing_html_refs)),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit localized HTML resource manifests, hashes, and offline references.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--sample-id", action="append", default=[])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    sample_dirs = [path for path in args.root.iterdir() if path.is_dir()]
    if args.sample_id:
        requested = set(args.sample_id)
        sample_dirs = [path for path in sample_dirs if path.name in requested]
    rows = [audit_sample(path) for path in sorted(sample_dirs)]
    payload = {
        "root": str(args.root),
        "sample_count": len(rows),
        "admitted_count": sum(row["admitted"] for row in rows),
        "failed_count": sum(not row["admitted"] for row in rows),
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ["sample_count", "admitted_count", "failed_count"]}, indent=2))
    return 0 if payload["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
