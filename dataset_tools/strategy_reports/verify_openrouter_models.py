from __future__ import annotations

import argparse
import base64
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from common import utc_now_iso, write_json


TEXT_MODELS = [
    "deepseek/deepseek-v4-pro",
    "deepseek/deepseek-v4-flash",
]

VISION_MODEL = "qwen/qwen3-vl-235b-a22b-instruct"


def read_api_key(path: Path) -> str:
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError(f"Empty API key file: {path}")
    return key


def find_chrome(explicit_path: str | None) -> Path:
    candidates = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    candidates.extend(
        [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not find Chrome or Edge executable for screenshot capture.")


def capture_report_screenshot(chrome: Path, html_path: Path, out_path: Path) -> dict[str, Any]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_out = out_path.resolve()
    cmd = [
        str(chrome),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--hide-scrollbars",
        "--window-size=1440,1200",
        f"--screenshot={absolute_out}",
        html_path.resolve().as_uri(),
    ]
    started = time.time()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
        check=False,
    )
    return {
        "command_status": proc.returncode,
        "stdout": (proc.stdout or "")[-500:],
        "stderr": (proc.stderr or "")[-500:],
        "screenshot_path": str(absolute_out),
        "screenshot_exists": absolute_out.exists(),
        "screenshot_size_bytes": absolute_out.stat().st_size if absolute_out.exists() else 0,
        "elapsed_seconds": round(time.time() - started, 2),
    }


def post_chat(base_url: str, api_key: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost/strategy-report-dataset",
        "X-Title": "Strategy Report Dataset Model Connectivity Test",
    }
    started = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        elapsed = round(time.time() - started, 2)
        result: dict[str, Any] = {
            "ok": resp.ok,
            "http_status": resp.status_code,
            "elapsed_seconds": elapsed,
        }
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001
            body = {"raw_text": resp.text[:1000]}
        if resp.ok:
            choice = (body.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            result.update(
                {
                    "response_id": body.get("id"),
                    "finish_reason": choice.get("finish_reason"),
                    "content_preview": str(message.get("content", ""))[:800],
                    "usage": body.get("usage"),
                }
            )
        else:
            result["error_preview"] = json.dumps(body, ensure_ascii=False)[:1200]
        return result
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "http_status": None,
            "elapsed_seconds": round(time.time() - started, 2),
            "error_preview": repr(exc),
        }


def text_payload(model: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a concise API connectivity tester. Reply in valid JSON only.",
            },
            {
                "role": "user",
                "content": (
                    "Return JSON with keys status, model_family, task. "
                    "Use status='ok' and task='strategy_report_metadata_extraction_connectivity'."
                ),
            },
        ],
        "temperature": 0,
        "max_tokens": 512,
    }


def vision_payload(model: str, image_path: Path) -> dict[str, Any]:
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    data_url = f"data:image/png;base64,{encoded}"
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "这是一张此前生成的策略研究网页报告截图。"
                            "请用中文回答：截图中最可能展示的报告主题是什么？"
                            "只需一句话，并指出你看到了哪些视觉线索。"
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 180,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify OpenRouter model connectivity.")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--api-key-file", type=Path, default=Path("api_key.txt"))
    parser.add_argument("--report-html", type=Path, default=Path("generation_test/1/index.html"))
    parser.add_argument("--screenshot-out", type=Path, default=Path("dataset_build/openrouter_vision_test/report_screenshot.png"))
    parser.add_argument("--result-out", type=Path, default=Path("dataset_build/openrouter_model_connectivity.json"))
    parser.add_argument("--chrome-path", default=None)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    api_key = read_api_key(args.api_key_file)
    chrome = find_chrome(args.chrome_path)
    screenshot_result = capture_report_screenshot(chrome, args.report_html, args.screenshot_out)

    results: dict[str, Any] = {
        "tested_at": utc_now_iso(),
        "base_url": args.base_url,
        "api_key_file": str(args.api_key_file),
        "report_html": str(args.report_html),
        "screenshot": screenshot_result,
        "models": {},
    }
    for model in TEXT_MODELS:
        results["models"][model] = post_chat(args.base_url, api_key, text_payload(model), args.timeout)

    if screenshot_result["screenshot_exists"]:
        results["models"][VISION_MODEL] = post_chat(
            args.base_url,
            api_key,
            vision_payload(VISION_MODEL, args.screenshot_out),
            args.timeout,
        )
    else:
        results["models"][VISION_MODEL] = {
            "ok": False,
            "error_preview": "Screenshot capture failed; vision test skipped.",
        }

    write_json(args.result_out, results)
    printable = {
        "tested_at": results["tested_at"],
        "screenshot_exists": screenshot_result["screenshot_exists"],
        "screenshot_size_bytes": screenshot_result["screenshot_size_bytes"],
        "models": {
            model: {
                "ok": data.get("ok"),
                "http_status": data.get("http_status"),
                "elapsed_seconds": data.get("elapsed_seconds"),
                "content_preview": data.get("content_preview"),
                "error_preview": data.get("error_preview"),
            }
            for model, data in results["models"].items()
        },
        "result_out": str(args.result_out),
    }
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    return 0 if all(item.get("ok") for item in results["models"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
