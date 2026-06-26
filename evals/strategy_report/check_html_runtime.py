from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from html_adapter import find_chrome
from html_runtime_adapter_v2 import adapt_html_runtime_v2


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight check for local HTML runtime verification.")
    parser.add_argument("--chrome", default=None, help="Optional explicit Chrome/Chromium executable path.")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result: dict[str, Any] = {
        "chrome_found": False,
        "chrome_path": "",
        "headless_launch": False,
        "cdp_available": False,
        "local_file_navigation": False,
        "screenshot_ok": False,
        "adapter_ok": False,
        "errors": [],
    }
    chrome = find_chrome(args.chrome)
    if chrome:
        result["chrome_found"] = True
        result["chrome_path"] = str(chrome)
    else:
        result["errors"].append("Chrome/Chromium executable not found. Install google-chrome-stable/chromium or pass --chrome.")
        emit(result, args.json)
        return 1

    out_dir = args.out_dir or Path(tempfile.mkdtemp(prefix="strategy_html_preflight_out_"))
    html_dir = Path(tempfile.mkdtemp(prefix="strategy_html_preflight_src_"))
    html_path = html_dir / "preflight.html"
    html_path.write_text(
        """<!doctype html><html><head><meta charset='utf-8'><title>Verifier HTML Preflight</title></head>
<body><main><h1>Strategy Outlook Preflight</h1>
<p>We expect market leadership to broaden because earnings growth improves and policy uncertainty declines.</p>
<figure><svg width='420' height='160' role='img'><rect x='20' y='80' width='80' height='60'></rect><rect x='140' y='50' width='80' height='90'></rect></svg>
<figcaption>Figure 1. Earnings breadth improves. Source: internal test.</figcaption></figure>
<p>Risk scenarios include slower growth, higher rates, and policy volatility.</p></main></body></html>""",
        encoding="utf-8",
    )
    try:
        adapter = adapt_html_runtime_v2(
            html_path=html_path,
            out_dir=out_dir,
            report_id="html_runtime_preflight",
            max_visuals=8,
            chrome_path=args.chrome,
        )
        manifest = adapter.get("manifest") or {}
        result["headless_launch"] = True
        result["cdp_available"] = True
        result["local_file_navigation"] = not str((manifest.get("browser_navigation") or {}).get("final_url") or "").startswith("chrome-error://")
        full_page_paths = [
            Path(item.get("full_page_image_path") or "")
            for item in (adapter.get("visual_objects", {}).get("visual_objects") or [])
            if item.get("full_page_image_path")
        ]
        result["screenshot_ok"] = any(path.exists() and path.stat().st_size > 0 for path in full_page_paths)
        result["adapter_ok"] = bool(adapter.get("report_text", {}).get("text")) and bool(adapter.get("visual_objects", {}).get("visual_objects"))
        result["manifest_warnings"] = manifest.get("warnings") or []
        result["text_length"] = adapter.get("report_text", {}).get("text_length")
        result["visual_count"] = len(adapter.get("visual_objects", {}).get("visual_objects") or [])
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(repr(exc))
    finally:
        shutil.rmtree(html_dir, ignore_errors=True)
        if args.out_dir is None:
            shutil.rmtree(out_dir, ignore_errors=True)
    emit(result, args.json)
    return 0 if result["adapter_ok"] else 1


def emit(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    for key, value in result.items():
        if key == "errors":
            continue
        print(f"{key}={value}")
    if result.get("errors"):
        print("errors:")
        for error in result["errors"]:
            print(f"- {error}")


if __name__ == "__main__":
    raise SystemExit(main())
