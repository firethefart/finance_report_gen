from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import urlopen

from bs4 import BeautifulSoup

from eval_utils import ROOT, extract_dates, extract_numbers, write_json
from html_adapter import build_resource_audit, find_chrome, normalize_html


VISUAL_SELECTOR = ",".join(
    [
        "figure",
        "table",
        "img",
        "svg",
        "canvas",
        "[role='img']",
        "[data-chart]",
        ".chart",
        ".figure",
        ".exhibit",
        ".plot",
        ".plotly",
        ".echarts",
        ".highcharts-container",
        ".kpi",
        ".metric",
        ".metric-card",
        ".data-card",
    ]
)


def short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:10]


class CDPClient:
    def __init__(self, ws_url: str):
        parsed = urlparse(ws_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = int(parsed.port or 80)
        self.path = parsed.path + (("?" + parsed.query) if parsed.query else "")
        self.sock: socket.socket | None = None
        self.next_id = 1

    def __enter__(self) -> "CDPClient":
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        if self.sock:
            self.sock.close()

    def connect(self) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        sock = socket.create_connection((self.host, self.port), timeout=10)
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = sock.recv(4096)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"CDP websocket handshake failed: {response[:200]!r}")
        self.sock = sock

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 30.0) -> dict[str, Any]:
        msg_id = self.next_id
        self.next_id += 1
        self._send_json({"id": msg_id, "method": method, "params": params or {}})
        deadline = time.time() + timeout
        while time.time() < deadline:
            message = self._recv_json(timeout=max(0.1, deadline - time.time()))
            if message.get("id") == msg_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method} failed: {message['error']}")
                return message.get("result") or {}
        raise TimeoutError(f"CDP call timed out: {method}")

    def _send_json(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        # Client-to-server websocket frames must be masked.
        header = bytearray([0x81])
        length = len(data)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(data))
        assert self.sock is not None
        self.sock.sendall(bytes(header) + mask + masked)

    def _recv_exact(self, n: int, timeout: float) -> bytes:
        assert self.sock is not None
        self.sock.settimeout(timeout)
        chunks = []
        remaining = n
        while remaining > 0:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise ConnectionError("CDP websocket closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _recv_json(self, timeout: float) -> dict[str, Any]:
        first = self._recv_exact(2, timeout)
        opcode = first[0] & 0x0F
        masked = bool(first[1] & 0x80)
        length = first[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2, timeout))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8, timeout))[0]
        mask = self._recv_exact(4, timeout) if masked else b""
        payload = self._recv_exact(length, timeout) if length else b""
        if masked:
            payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        if opcode == 0x8:
            raise ConnectionError("CDP websocket close frame")
        if opcode not in {0x1, 0x2}:
            return {}
        return json.loads(payload.decode("utf-8"))


def request_json(url: str) -> Any:
    with urlopen(url, timeout=10) as handle:
        return json.loads(handle.read().decode("utf-8"))


def launch_chrome(chrome: Path, html_path: Path, width: int, height: int) -> tuple[subprocess.Popen, str, Path]:
    user_data_dir = Path(tempfile.mkdtemp(prefix="strategy_html_runtime_"))
    cmd = [
        str(chrome),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--allow-file-access-from-files",
        "--disable-features=Translate,OptimizationHints",
        "--remote-debugging-port=0",
        f"--user-data-dir={user_data_dir}",
        f"--window-size={width},{height}",
        "about:blank",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    port_file = user_data_dir / "DevToolsActivePort"
    deadline = time.time() + 15
    while time.time() < deadline and not port_file.exists():
        if proc.poll() is not None:
            raise RuntimeError(f"Chrome exited early: {proc.returncode}")
        time.sleep(0.1)
    if not port_file.exists():
        proc.terminate()
        raise TimeoutError("Chrome DevToolsActivePort was not created")
    port = port_file.read_text(encoding="utf-8").splitlines()[0].strip()
    targets = request_json(f"http://127.0.0.1:{port}/json/list")
    page_targets = [target for target in targets if target.get("type") == "page" and target.get("webSocketDebuggerUrl")]
    if not page_targets:
        proc.terminate()
        raise RuntimeError("Chrome did not expose a page target")
    target = page_targets[0]
    return proc, target["webSocketDebuggerUrl"], user_data_dir


def eval_js(cdp: CDPClient, expression: str, await_promise: bool = True, timeout: float = 30.0) -> Any:
    result = cdp.call(
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": await_promise,
            "returnByValue": True,
            "timeout": int(timeout * 1000),
        },
        timeout=timeout + 5,
    )
    remote = result.get("result") or {}
    if "value" in remote:
        return remote["value"]
    if remote.get("type") == "undefined":
        return None
    return remote


def capture_png(cdp: CDPClient, out_path: Path, clip: dict[str, float] | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"format": "png", "captureBeyondViewport": True, "fromSurface": True}
    if clip:
        params["clip"] = {
            "x": max(0, float(clip["x"])),
            "y": max(0, float(clip["y"])),
            "width": max(1, float(clip["width"])),
            "height": max(1, float(clip["height"])),
            "scale": 1,
        }
    result = cdp.call("Page.captureScreenshot", params, timeout=45)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = base64.b64decode(result["data"])
    out_path.write_bytes(data)
    return {"path": str(out_path), "bytes": len(data), "ok": bool(data)}


def runtime_extract_script(selector: str, max_visuals: int) -> str:
    return f"""
(async () => {{
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  window.scrollTo(0, 0);
  await sleep(250);
  const step = Math.max(500, Math.floor(window.innerHeight * 0.75));
  for (let y = 0; y < document.body.scrollHeight; y += step) {{
    window.scrollTo(0, y);
    await sleep(80);
  }}
  window.scrollTo(0, 0);
  await sleep(250);

  const clean = s => String(s || '').replace(/\\s+/g, ' ').trim();
  const headingFor = el => {{
    let node = el;
    for (let depth = 0; node && depth < 8; depth++, node = node.parentElement) {{
      let prev = node.previousElementSibling;
      for (let hops = 0; prev && hops < 8; hops++, prev = prev.previousElementSibling) {{
        if (/^H[1-4]$/.test(prev.tagName)) return clean(prev.innerText);
      }}
    }}
    return '';
  }};
  const textAround = el => {{
    const parts = [];
    if (el.getAttribute) {{
      for (const attr of ['alt','title','aria-label']) {{
        const value = el.getAttribute(attr);
        if (value) parts.push(value);
      }}
    }}
    parts.push(el.innerText || el.textContent || '');
    let parent = el.parentElement;
    for (let i = 0; parent && i < 2; i++, parent = parent.parentElement) {{
      parts.push(parent.innerText || parent.textContent || '');
    }}
    return clean(parts.join(' ')).slice(0, 5000);
  }};
  const isVisible = el => {{
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
    return rect.width >= 80 && rect.height >= 40;
  }};
  const candidates = Array.from(document.querySelectorAll({json.dumps(selector)}));
  const seen = new Set();
  const visuals = [];
  const skipped = [];
  for (const el of candidates) {{
    if (!isVisible(el)) continue;
    const tag = el.tagName.toLowerCase();
    const renderStatus = (() => {{
      if (tag !== 'img') return {{status: 'not_img'}};
      const naturalWidth = Number(el.naturalWidth || 0);
      const naturalHeight = Number(el.naturalHeight || 0);
      const complete = Boolean(el.complete);
      const src = el.currentSrc || el.src || el.getAttribute('src') || '';
      const ok = complete && naturalWidth >= 20 && naturalHeight >= 20;
      return {{status: ok ? 'rendered' : 'broken_or_unloaded', complete, naturalWidth, naturalHeight, src}};
    }})();
    if (renderStatus.status === 'broken_or_unloaded') {{
      const rect = el.getBoundingClientRect();
      skipped.push({{
        tag,
        reason: 'broken_or_unloaded_img',
        render_status: renderStatus,
        bbox: {{x: rect.left + scrollX, y: rect.top + scrollY, width: rect.width, height: rect.height}},
        nearby_text: textAround(el).slice(0, 500),
      }});
      continue;
    }}
    const rect = el.getBoundingClientRect();
    const key = [Math.round(rect.left + scrollX), Math.round(rect.top + scrollY), Math.round(rect.width), Math.round(rect.height), el.tagName].join(':');
    if (seen.has(key)) continue;
    seen.add(key);
    const id = 'visual_' + String(visuals.length + 1).padStart(3, '0');
    el.setAttribute('data-verifier-visual-id', id);
    const pageX = rect.left + scrollX;
    const pageY = rect.top + scrollY;
    visuals.push({{
      visual_id: id,
      tag,
      class_name: String(el.className || ''),
      role: el.getAttribute('role') || '',
      render_status: renderStatus,
      bbox: {{x: pageX, y: pageY, width: rect.width, height: rect.height}},
      viewport_bbox: {{x: rect.left, y: rect.top, width: rect.width, height: rect.height}},
      center_y: pageY + rect.height / 2,
      oversized_visual: rect.height > window.innerHeight * 0.92 || rect.width > window.innerWidth * 0.98,
      nearby_text: textAround(el),
      section_heading: headingFor(el),
      numbers: (textAround(el).match(/[-+]?\\d[\\d,.]*(?:%|bp|bps|倍|亿元|万|亿)?/g) || []).slice(0, 80),
    }});
    if (visuals.length >= {int(max_visuals)}) break;
  }}
  const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4')).map((h, i) => ({{
    id: 'h' + String(i + 1).padStart(3, '0'),
    level: h.tagName.toLowerCase(),
    text: clean(h.innerText),
    y: h.getBoundingClientRect().top + scrollY
  }})).filter(h => h.text);
  const links = Array.from(document.querySelectorAll('a[href]')).map(a => ({{
    text: clean(a.innerText).slice(0, 160),
    href: a.href
  }})).filter(a => a.text || a.href).slice(0, 200);
  const bodyText = clean(document.body.innerText || document.body.textContent || '');
  return {{
    url: location.href,
    title: document.title || '',
    viewport: {{width: window.innerWidth, height: window.innerHeight}},
    document_size: {{width: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth), height: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)}},
    text: bodyText,
    text_length: bodyText.length,
    headings,
    links,
    visual_objects: visuals,
    skipped_visuals: skipped,
  }};
}})()
"""


def normalize_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def create_browser_work_copy(normalized_html: str) -> tuple[Path, Path]:
    work_dir = Path(tempfile.mkdtemp(prefix="srh_"))
    browser_path = work_dir / "n.html"
    browser_path.write_text(normalized_html, encoding="utf-8")
    return work_dir, browser_path


def adapt_html_runtime_v2(
    html_path: Path,
    out_dir: Path,
    report_id: str | None = None,
    max_visuals: int = 60,
    viewport_width: int = 1440,
    viewport_height: int = 1100,
    context_height: int = 1200,
    chrome_path: str | None = None,
) -> dict[str, Any]:
    html_path = normalize_path(html_path).resolve()
    out_dir = normalize_path(out_dir)
    report_id = report_id or html_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_html = html_path.read_text(encoding="utf-8", errors="ignore")
    raw_soup = BeautifulSoup(raw_html, "html.parser")
    resource_audit = build_resource_audit(raw_soup, html_path)
    normalized_html, cleanup_audit = normalize_html(raw_html, html_path, out_dir)
    normalized_path = out_dir / "normalized.html"
    browser_work_dir, browser_path = create_browser_work_copy(normalized_html)
    browser_url = browser_path.resolve().as_uri()

    chrome = find_chrome(chrome_path)
    if chrome is None:
        shutil.rmtree(browser_work_dir, ignore_errors=True)
        raise FileNotFoundError("Chrome or Edge executable was not found.")
    proc = None
    user_data_dir = None
    navigation_result: dict[str, Any] = {}
    try:
        proc, ws_url, user_data_dir = launch_chrome(chrome, browser_path, viewport_width, viewport_height)
        with CDPClient(ws_url) as cdp:
            cdp.call("Page.enable")
            cdp.call("Runtime.enable")
            navigation_result = cdp.call("Page.navigate", {"url": browser_url}, timeout=10)
            if navigation_result.get("errorText"):
                raise RuntimeError(f"Chrome failed to navigate to browser work copy: {navigation_result['errorText']}")
            deadline = time.time() + 20
            while time.time() < deadline:
                if eval_js(cdp, "document.readyState", timeout=5) == "complete":
                    break
                time.sleep(0.2)
            runtime = eval_js(cdp, runtime_extract_script(VISUAL_SELECTOR, max_visuals), timeout=60)
            runtime_url = str(runtime.get("url") or "")
            if runtime_url.startswith("chrome-error://"):
                raise RuntimeError(f"Chrome opened an error document instead of the HTML report: {runtime_url}")
            doc = runtime["document_size"]
            full_clip = {"x": 0, "y": 0, "width": min(float(doc["width"]), 2400.0), "height": min(float(doc["height"]), 12000.0)}
            full_page = capture_png(cdp, out_dir / "screenshots" / f"{report_id}_full_page.png", full_clip)
            visual_records = []
            for index, visual in enumerate(runtime["visual_objects"], start=1):
                bbox = visual["bbox"]
                pad = 16
                target_clip = {
                    "x": bbox["x"] - pad,
                    "y": bbox["y"] - pad,
                    "width": bbox["width"] + pad * 2,
                    "height": bbox["height"] + pad * 2,
                }
                context_y = max(0, float(visual["center_y"]) - context_height / 2)
                context_clip = {
                    "x": 0,
                    "y": context_y,
                    "width": min(float(doc["width"]), 1800.0),
                    "height": min(float(context_height), float(doc["height"]) - context_y),
                }
                target = capture_png(cdp, out_dir / "visuals" / f"{report_id}_{visual['visual_id']}_target.png", target_clip)
                context = capture_png(cdp, out_dir / "visuals" / f"{report_id}_{visual['visual_id']}_context.png", context_clip)
                visual_records.append(
                    {
                        **visual,
                        "object_index": index,
                        "object_count": len(runtime["visual_objects"]),
                        "target_image_path": target["path"],
                        "context_image_path": context["path"],
                        "full_page_image_path": full_page["path"],
                        "context_clip": context_clip,
                        "target_clip": target_clip,
                    }
                )
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        if user_data_dir is not None:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        shutil.rmtree(browser_work_dir, ignore_errors=True)

    text = runtime.get("text") or ""
    report_text = {
        "title": runtime.get("title") or "",
        "url": runtime.get("url"),
        "text": text[:120000],
        "text_length": len(text),
        "headings": runtime.get("headings") or [],
        "links": runtime.get("links") or [],
        "numbers": extract_numbers(text)[:1000],
        "dates": extract_dates(text)[:400],
        "document_size": runtime.get("document_size") or {},
        "viewport": runtime.get("viewport") or {},
    }
    visual_objects = {
        "report_id": report_id,
        "source_path": str(html_path),
        "normalized_html": str(normalized_path),
        "source_format": "html_runtime",
        "visual_count": len(visual_records),
        "visual_objects": visual_records,
        "skipped_visual_count": len(runtime.get("skipped_visuals") or []),
        "skipped_visuals": runtime.get("skipped_visuals") or [],
    }
    manifest = {
        "adapter_version": "html_runtime_adapter_v2",
        "report_id": report_id,
        "source_path": str(html_path),
        "normalized_html": str(normalized_path),
        "report_text_json": str(out_dir / "report_text.json"),
        "visual_objects_json": str(out_dir / "visual_objects.json"),
        "layout_snapshot_json": str(out_dir / "layout_snapshot.json"),
        "text_length": report_text["text_length"],
        "heading_count": len(report_text["headings"]),
        "visual_count": len(visual_records),
        "skipped_visual_count": len(runtime.get("skipped_visuals") or []),
        "oversized_visual_count": len([item for item in visual_records if item.get("oversized_visual")]),
        "resource_audit": {
            "resource_count": resource_audit["resource_count"],
            "remote_resource_count": resource_audit["remote_resource_count"],
            "failed_static_resource_count": resource_audit["failed_static_resource_count"],
        },
        "cleanup_audit": cleanup_audit,
        "browser_navigation": {
            "mode": "short_temporary_work_copy",
            "formal_normalized_html": str(normalized_path),
            "formal_path_length": len(str(normalized_path.resolve())),
            "browser_url": report_text["url"],
            "browser_path_length": len(str(browser_path.resolve())),
            "navigation_frame_id": navigation_result.get("frameId"),
            "temporary_work_copy_removed": not browser_work_dir.exists(),
        },
        "pagination_strategy": {
            "mode": "dom_visual_object_centered",
            "description": "Visuals are captured by DOM bounding boxes, not by fixed-height page slicing.",
            "context": "Each visual has its own target crop and a surrounding viewport context screenshot.",
        },
        "warnings": runtime_warnings(resource_audit, report_text, visual_records, runtime.get("skipped_visuals") or []),
    }
    write_json(out_dir / "report_text.json", report_text)
    write_json(out_dir / "visual_objects.json", visual_objects)
    write_json(
        out_dir / "layout_snapshot.json",
        {
            "document_size": report_text["document_size"],
            "viewport": report_text["viewport"],
            "headings": report_text["headings"],
            "full_page_image_path": str(out_dir / "screenshots" / f"{report_id}_full_page.png"),
        },
    )
    write_json(out_dir / "adapter_manifest.json", manifest)
    return {"manifest": manifest, "report_text": report_text, "visual_objects": visual_objects}


def runtime_warnings(
    resource_audit: dict[str, Any],
    report_text: dict[str, Any],
    visual_records: list[dict[str, Any]],
    skipped_visuals: list[dict[str, Any]] | None = None,
) -> list[str]:
    warnings = []
    if resource_audit.get("failed_static_resource_count", 0):
        warnings.append("html_static_resource_missing")
    if resource_audit.get("remote_resource_count", 0):
        warnings.append("html_has_external_resources")
    if report_text.get("text_length", 0) < 2000:
        warnings.append("html_text_too_short_for_strategy_report")
    if not visual_records:
        warnings.append("html_no_visual_objects")
    if any(item.get("oversized_visual") for item in visual_records):
        warnings.append("html_has_oversized_visuals")
    if skipped_visuals:
        warnings.append("html_broken_visual_resources")
    return warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Runtime HTML adapter V2: DOM visual screenshots and layout snapshot.")
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--report-id", default=None)
    parser.add_argument("--max-visuals", type=int, default=60)
    parser.add_argument("--viewport-width", type=int, default=1440)
    parser.add_argument("--viewport-height", type=int, default=1100)
    parser.add_argument("--context-height", type=int, default=1200)
    parser.add_argument("--chrome-path", default=None)
    args = parser.parse_args()
    result = adapt_html_runtime_v2(
        html_path=args.html,
        out_dir=args.out_dir,
        report_id=args.report_id,
        max_visuals=args.max_visuals,
        viewport_width=args.viewport_width,
        viewport_height=args.viewport_height,
        context_height=args.context_height,
        chrome_path=args.chrome_path,
    )
    print(json.dumps(result["manifest"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
