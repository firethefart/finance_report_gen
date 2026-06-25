from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import requests

from common import utc_now_iso, write_json


def prompt_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def read_api_key(path: Path) -> str:
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError(f"Empty API key file: {path}")
    return key


def extract_json_object(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        return json.loads(cleaned[start : end + 1])
    raise json.JSONDecodeError("No JSON object found", cleaned, 0)


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout: int = 120,
        log_dir: Path | None = None,
        retries: int | None = None,
        backoff_seconds: float | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.log_dir = log_dir
        self.retries = retries if retries is not None else int(os.getenv("OPENROUTER_RETRIES", "3"))
        self.backoff_seconds = backoff_seconds if backoff_seconds is not None else float(os.getenv("OPENROUTER_BACKOFF_SECONDS", "3"))
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost/strategy-report-dataset",
                "X-Title": "Strategy Report Metadata Extraction",
            }
        )

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float = 0,
        response_format: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format
        started = time.time()
        result: dict[str, Any] = {
            "model": model,
            "requested_at": utc_now_iso(),
            "prompt_hash": prompt_hash(payload),
            "metadata": metadata or {},
            "ok": False,
            "http_status": None,
            "elapsed_seconds": None,
            "content": None,
            "json": None,
            "usage": None,
            "error": None,
            "attempts": [],
        }
        max_attempts = max(1, self.retries)
        for attempt in range(1, max_attempts + 1):
            attempt_started = time.time()
            try:
                resp = self.session.post(f"{self.base_url}/chat/completions", json=payload, timeout=self.timeout)
                result["http_status"] = resp.status_code
                body = resp.json()
                attempt_row = {
                    "attempt": attempt,
                    "http_status": resp.status_code,
                    "elapsed_seconds": round(time.time() - attempt_started, 2),
                    "retryable": is_retryable_status(resp.status_code),
                    "error": None if resp.ok else json.dumps(body, ensure_ascii=False)[:1000],
                }
                result["attempts"].append(attempt_row)
                if not resp.ok:
                    result["error"] = json.dumps(body, ensure_ascii=False)[:2000]
                    if is_retryable_status(resp.status_code) and attempt < max_attempts:
                        sleep_before_retry(self.backoff_seconds, attempt)
                        continue
                    break
                choice = (body.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                content = message.get("content")
                result["ok"] = True
                result["content"] = content
                result["usage"] = body.get("usage")
                result["error"] = None
                if isinstance(content, str) and content.strip():
                    try:
                        result["json"] = extract_json_object(content)
                    except Exception as exc:  # noqa: BLE001
                        result["error"] = f"json_parse_error: {exc!r}"
                break
            except Exception as exc:  # noqa: BLE001
                error = repr(exc)
                result["attempts"].append(
                    {
                        "attempt": attempt,
                        "http_status": None,
                        "elapsed_seconds": round(time.time() - attempt_started, 2),
                        "retryable": True,
                        "error": error[:1000],
                    }
                )
                result["error"] = error
                if attempt < max_attempts:
                    sleep_before_retry(self.backoff_seconds, attempt)
                    continue
                break
        result["elapsed_seconds"] = round(time.time() - started, 2)
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            write_json(self.log_dir / f"{result['requested_at'].replace(':', '-')}-{model.replace('/', '__')}-{result['prompt_hash']}.json", result)
        return result


def is_retryable_status(status: int | None) -> bool:
    return status in {408, 409, 425, 429, 500, 502, 503, 504}


def sleep_before_retry(base_seconds: float, attempt: int) -> None:
    time.sleep(max(0.0, base_seconds) * attempt)
