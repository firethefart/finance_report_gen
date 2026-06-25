from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from eval_utils import ROOT
from html_adapter import find_chrome
from html_runtime_adapter_v2 import CDPClient, eval_js, launch_chrome


DEFAULT_MANIFEST = ROOT / "evals" / "strategy_report" / "html_localization_candidates.json"
DEFAULT_OUT = ROOT / "dataset_build" / "v2_localized_html"
ARCHIVE_MANIFEST = ROOT / "dataset_build" / "manifests" / "html_archive_manifest.jsonl"
STYLE_PROPERTIES = [
    "display", "position", "box-sizing", "width", "max-width", "min-width",
    "height", "max-height", "min-height", "margin", "padding", "border",
    "border-radius", "background", "background-color", "background-image",
    "color", "font-family", "font-size", "font-weight", "font-style",
    "line-height", "letter-spacing", "text-align", "text-decoration",
    "text-transform", "white-space", "vertical-align", "overflow",
    "overflow-x", "overflow-y", "object-fit", "object-position", "opacity",
    "visibility", "grid-template-columns", "grid-template-rows", "grid-gap",
    "gap", "align-items", "justify-content", "flex", "flex-direction",
    "flex-wrap", "list-style", "list-style-type", "table-layout",
    "border-collapse", "break-inside", "page-break-inside"
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


class ResourceStore:
    def __init__(self, sample_dir: Path, session: requests.Session):
        self.sample_dir = sample_dir
        self.assets_dir = sample_dir / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.session = session
        self.cache: dict[str, str] = {}
        self.records: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _extension(url: str, content_type: str) -> str:
        extension = Path(urlparse(url).path).suffix.lower()
        if extension and len(extension) <= 8:
            return extension
        return mimetypes.guess_extension(content_type) or ".bin"

    @staticmethod
    def _failure_classification(absolute: str, role: str) -> tuple[bool, str]:
        extension = Path(urlparse(absolute).path).suffix.lower()
        if role == "css_dependency" and extension in {".eot", ".ttf", ".otf", ".woff", ".woff2", ".svg"}:
            return False, "optional_font_or_icon_variant"
        return True, "required_resource"

    def _save(self, absolute: str, content: bytes, content_type: str, role: str) -> str:
        digest = hashlib.sha256(content).hexdigest()
        filename = f"{digest[:20]}{self._extension(absolute, content_type)}"
        path = self.assets_dir / filename
        if not path.exists():
            path.write_bytes(content)
        local_ref = f"assets/{filename}"
        self.cache[absolute] = local_ref
        self.records[absolute] = {
            "original_url": absolute,
            "local_path": local_ref,
            "status": "downloaded",
            "mime": content_type,
            "sha256": digest,
            "bytes": len(content),
            "role": role,
            "error": None,
        }
        return local_ref

    def fetch(self, value: str, base_url: str, role: str) -> str:
        value = clean_text(value).strip("\"'")
        if not value or value.startswith(("#", "javascript:", "mailto:", "tel:")):
            return value
        if value.startswith("data:"):
            return value
        absolute = urljoin(base_url, value)
        if absolute in self.cache:
            return self.cache[absolute]
        parsed = urlparse(absolute)
        if parsed.scheme == "file":
            source = Path(unquote(parsed.path.lstrip("/")))
            if source.exists():
                content_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
                return self._save(absolute, source.read_bytes(), content_type, role)
        try:
            response = self.session.get(absolute, timeout=30, allow_redirects=True)
            response.raise_for_status()
            if len(response.content) > 20 * 1024 * 1024:
                raise ValueError("asset_too_large")
            content_type = (response.headers.get("content-type") or "").split(";", 1)[0].strip()
            if not content_type or content_type == "application/octet-stream":
                content_type = mimetypes.guess_type(urlparse(absolute).path)[0] or "application/octet-stream"
            return self._save(absolute, response.content, content_type, role)
        except Exception as exc:  # noqa: BLE001
            critical, failure_class = self._failure_classification(absolute, role)
            self.cache[absolute] = ""
            self.records[absolute] = {
                "original_url": absolute,
                "local_path": None,
                "status": "failed",
                "mime": None,
                "sha256": None,
                "bytes": 0,
                "role": role,
                "error": repr(exc),
                "critical": critical,
                "failure_class": failure_class,
            }
            return ""

    def record_inline_text(self, absolute: str, content: str, content_type: str, role: str) -> str:
        return self._save(absolute, content.encode("utf-8"), content_type, role)

    def manifest(self) -> dict[str, Any]:
        records = sorted(self.records.values(), key=lambda item: item["original_url"])
        return {
            "resource_count": len(records),
            "downloaded_count": sum(item["status"] == "downloaded" for item in records),
            "failed_count": sum(item["status"] == "failed" for item in records),
            "critical_failed_count": sum(
                item["status"] == "failed" and item.get("critical", True)
                for item in records
            ),
            "total_bytes": sum(item["bytes"] for item in records),
            "resources": records,
        }


def snapshot_script(options: dict[str, Any] | None = None) -> str:
    props = json.dumps(STYLE_PROPERTIES)
    snapshot_options = json.dumps(options or {})
    return f"""
(async () => {{
  const options = {snapshot_options};
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const clean = value => String(value || '').replace(/\\s+/g, ' ').trim();
  for (let y = 0; y < document.body.scrollHeight; y += Math.max(500, innerHeight * 0.7)) {{
    scrollTo(0, y);
    await sleep(120);
  }}
  scrollTo(0, 0);
  await sleep(1200);

  const selectors = [
    'article', 'main', '[role="main"]', '.main-wrapper',
    '.cmp-experiencefragment[class*="gmo-" i]',
    '.article-content', '.article-body', '.content-body', '.insight-content',
    '.cmp-container', '#main-content'
  ];
  const candidates = [];
  if (options.root_selector) {{
    const forced = document.querySelector(options.root_selector);
    if (forced) {{
      const textLength = clean(forced.innerText).length;
      const rect = forced.getBoundingClientRect();
      if (textLength >= 1200 && rect.width >= 400) {{
        candidates.push({{node: forced, selector: options.root_selector, textLength, forced: true}});
      }}
    }}
  }}
  for (const selector of selectors) {{
    for (const node of document.querySelectorAll(selector)) {{
      const textLength = clean(node.innerText).length;
      const rect = node.getBoundingClientRect();
      if (textLength >= 1200 && rect.width >= 400) candidates.push({{node, selector, textLength}});
    }}
  }}
  candidates.sort((a, b) => (Number(Boolean(b.forced)) - Number(Boolean(a.forced))) || b.textLength - a.textLength);
  const root = candidates.length ? candidates[0].node : document.body;
  const chosenSelector = candidates.length ? candidates[0].selector : 'body';

  const removeSelectors = [
    'script','noscript','iframe','nav','header','footer','form',
    'input[type="hidden"]','.article-list-enhanced','.sharing',
    '.video','.audio-player',
    '[class*="cookie" i]','[id*="cookie" i]','[class*="consent" i]',
    '[id*="consent" i]','[class*="modal" i]','[class*="popup" i]',
    '[class*="overlay" i]','[class*="share" i]','[class*="social" i]',
    '[class*="newsletter" i]','[class*="subscribe" i]'
  ];
  const clone = root.cloneNode(true);
  // Preserve identical tree order while computed styles are copied. Removing
  // nodes before this pass shifts the clone indexes and applies styles to the
  // wrong elements, producing spectacularly broken offline layouts.
  const originals = [root, ...root.querySelectorAll('*')];
  const clones = [clone, ...clone.querySelectorAll('*')];
  const properties = {props};
  const assets = [];
  let removedVisualShells = 0;
  for (let i = 0; i < Math.min(originals.length, clones.length); i++) {{
    const source = originals[i];
    const target = clones[i];
    if (!(source instanceof Element) || !(target instanceof Element)) continue;
    const style = getComputedStyle(source);
    const values = [];
    for (const prop of properties) {{
      const value = style.getPropertyValue(prop);
      const preserveHiddenDisplay = prop === 'display' && value === 'none';
      if (value && (preserveHiddenDisplay || (value !== 'none' && value !== 'normal' && value !== 'auto'))) {{
        values.push(prop + ':' + value);
      }}
    }}
    target.setAttribute('style', values.join(';'));
    if (options.flow_layout && ['DIV','SECTION','ARTICLE','MAIN','ASIDE'].includes(source.tagName)) {{
      target.style.position = 'static';
      target.style.top = 'auto';
      target.style.right = 'auto';
      target.style.bottom = 'auto';
      target.style.left = 'auto';
      target.style.height = 'auto';
      target.style.minHeight = '0';
      target.style.maxHeight = 'none';
      target.style.transform = 'none';
      target.style.overflow = 'visible';
    }}
    if (options.flow_layout && ['SPAN','P','H1','H2','H3','H4','ADDRESS'].includes(source.tagName)
    ) {{
      target.style.height = 'auto';
      target.style.minHeight = '0';
      target.style.maxHeight = 'none';
      if (['fixed','absolute','sticky'].includes(style.position)) {{
        target.style.position = 'static';
        target.style.top = 'auto';
        target.style.right = 'auto';
        target.style.bottom = 'auto';
        target.style.left = 'auto';
        target.style.transform = 'none';
      }}
    }}
    target.removeAttribute('srcset');
    target.removeAttribute('loading');
    if (source.tagName === 'SVG') {{
      const rect = source.getBoundingClientRect();
      const style = getComputedStyle(source);
      if (style.display === 'none' || style.visibility === 'hidden' || rect.width < 80 || rect.height < 40) {{
        target.setAttribute('data-localize-remove', 'small-or-hidden-svg');
        removedVisualShells += 1;
      }}
    }}
    if (source.tagName === 'IMG') {{
      const src = source.currentSrc || source.src || source.getAttribute('src') || '';
      if (src) {{
        target.setAttribute('src', src);
        assets.push(src);
      }}
    }}
    if (source.tagName === 'CANVAS') {{
      try {{
        const img = document.createElement('img');
        img.src = source.toDataURL('image/png');
        img.alt = source.getAttribute('aria-label') || source.getAttribute('title') || 'Rendered chart';
        img.setAttribute('style', target.getAttribute('style') || '');
        target.replaceWith(img);
      }} catch (error) {{}}
    }}
    const bg = style.backgroundImage || '';
    for (const match of bg.matchAll(/url\\(["']?([^"')]+)["']?\\)/g)) assets.push(match[1]);
  }}
  for (const selector of removeSelectors) {{
    for (const node of clone.querySelectorAll(selector)) node.remove();
  }}
  for (const prefix of (options.remove_text_prefixes || [])) {{
    const normalized = String(prefix).toLowerCase();
    for (const node of [...clone.querySelectorAll('h1,h2,h3,h4,p')]) {{
      if (clean(node.innerText).toLowerCase().startsWith(normalized)) {{
        const container = node.closest('.homesectioncontainer,section,aside') || node;
        container.remove();
      }}
    }}
  }}
  for (const node of clone.querySelectorAll('[data-localize-remove]')) node.remove();
  for (let pass = 0; pass < 3; pass++) {{
    for (const node of [...clone.querySelectorAll('div,section,aside')]) {{
      if (!clean(node.innerText) && !node.querySelector('img,svg,canvas,table,figure')) node.remove();
    }}
  }}
  clone.style.marginTop = '0';
  clone.style.top = 'auto';
  if (['fixed', 'absolute', 'sticky'].includes(clone.style.position)) clone.style.position = 'relative';
  const text = clean(root.innerText);
  return {{
    title: document.title || '',
    final_url: location.href,
    chosen_selector: chosenSelector,
    text_length: text.length,
    heading_count: root.querySelectorAll('h1,h2,h3,h4').length,
    image_count: root.querySelectorAll('img').length,
    svg_count: root.querySelectorAll('svg').length,
    canvas_count: root.querySelectorAll('canvas').length,
    removed_visual_shell_count: removedVisualShells,
    assets: [...new Set(assets)].slice(0, 500),
    html: clone.outerHTML
  }};
}})()
"""


def launch_for_url(chrome: Path, width: int = 1440, height: int = 1100) -> tuple[subprocess.Popen, str, Path]:
    return launch_chrome(chrome, Path("about_blank.html"), width, height)


def archive_path_for_url(url: str) -> Path | None:
    if not ARCHIVE_MANIFEST.exists():
        return None
    for line in ARCHIVE_MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("url") == url and row.get("status") == "archived" and row.get("file_path"):
            path = ROOT / row["file_path"]
            if path.exists():
                return path
    return None


def localize_css(css: str, base_url: str, store: ResourceStore, *, from_asset_file: bool = False) -> str:
    url_pattern = re.compile(r"url\([\"']?([^\"')]+)[\"']?\)", re.IGNORECASE)

    def replace(match: re.Match[str]) -> str:
        localized = store.fetch(match.group(1), base_url, "css_dependency")
        if from_asset_file and localized.startswith("assets/"):
            localized = localized.removeprefix("assets/")
        return f"url('{localized}')" if localized else "none"

    return url_pattern.sub(replace, css)


def hydrate_archived_html(source_html: str, base_url: str, store: ResourceStore) -> tuple[str, dict[str, Any]]:
    soup = BeautifulSoup(source_html, "html.parser")
    before = len(store.records)

    for script in soup.find_all("script"):
        script.decompose()
    for link in list(soup.find_all("link", href=True)):
        rel = " ".join(str(item).lower() for item in (link.get("rel") or []))
        if "stylesheet" not in rel:
            link.decompose()
            continue
        href = str(link.get("href") or "")
        absolute = urljoin(base_url, href)
        try:
            response = store.session.get(absolute, timeout=30, allow_redirects=True)
            response.raise_for_status()
            css = localize_css(response.text, absolute, store, from_asset_file=True)
            local_ref = store.record_inline_text(absolute, css, "text/css", "stylesheet")
            link["href"] = local_ref
            link["rel"] = ["stylesheet"]
        except Exception as exc:  # noqa: BLE001
            store.records[absolute] = {
                "original_url": absolute,
                "local_path": None,
                "status": "failed",
                "mime": "text/css",
                "sha256": None,
                "bytes": 0,
                "role": "stylesheet",
                "error": repr(exc),
                "critical": True,
                "failure_class": "required_resource",
            }
            link.decompose()
    for style in soup.find_all("style"):
        style.string = localize_css(style.get_text(), base_url, store)
    for tag, attr in [("img", "src"), ("source", "src"), ("video", "poster")]:
        for node in soup.find_all(tag):
            value = str(node.get(attr) or "")
            localized = store.fetch(value, base_url, f"{tag}_{attr}")
            if localized:
                node[attr] = localized
            elif tag in {"img", "source"}:
                node.decompose()
                continue
            node.attrs.pop("srcset", None)
    url_pattern = re.compile(r"url\([\"']?([^\"')]+)[\"']?\)", re.IGNORECASE)
    for node in soup.find_all(style=True):
        style = str(node.get("style") or "")

        def replace_inline(match: re.Match[str]) -> str:
            localized = store.fetch(match.group(1), base_url, "inline_style")
            return f"url('{localized}')" if localized else "none"

        node["style"] = url_pattern.sub(replace_inline, style)
    base = soup.find("base")
    if base:
        base.decompose()
    new_records = list(store.records.values())[before:]
    return str(soup), {
        "downloaded_asset_count": sum(item["status"] == "downloaded" for item in new_records),
        "failed_assets": [
            {"url": item["original_url"], "error": item["error"]}
            for item in new_records
            if item["status"] == "failed"
        ],
    }


def localize_snapshot_assets(html: str, base_url: str, store: ResourceStore) -> tuple[str, dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    before = len(store.records)

    for image in soup.find_all("img"):
        src = str(image.get("src") or "")
        localized = store.fetch(src, base_url, "snapshot_image")
        if localized:
            image["src"] = localized
        else:
            image.decompose()
            continue
        image.attrs.pop("srcset", None)
    for node in soup.find_all(["video", "audio", "iframe", "object", "embed"]):
        replacement = soup.new_tag("div")
        replacement["class"] = ["localized-interactive-placeholder"]
        label = clean_text(str(node.get("aria-label") or node.get("title") or "Interactive media omitted"))
        replacement.string = label
        node.replace_with(replacement)
    url_pattern = re.compile(r"url\([\"']?([^\"')]+)[\"']?\)", re.IGNORECASE)
    for node in soup.find_all(style=True):
        style = str(node.get("style") or "")

        def replace(match: re.Match[str]) -> str:
            localized = store.fetch(match.group(1), base_url, "snapshot_style")
            return f"url('{localized}')" if localized else "none"

        node["style"] = url_pattern.sub(replace, style)
    new_records = list(store.records.values())[before:]
    return str(soup), {
        "downloaded_asset_count": sum(item["status"] == "downloaded" for item in new_records),
        "failed_assets": [
            {"url": item["original_url"], "error": item["error"]}
            for item in new_records
            if item["status"] == "failed"
        ],
    }


def build_document(snapshot: dict[str, Any], localized_body: str, source_url: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="source-url" content="{source_url}" />
  <title>{snapshot.get('title') or 'Localized strategy report'}</title>
  <style>
    html, body {{ margin: 0; padding: 0; background: #fff; }}
    body {{ max-width: 1600px; margin: 0 auto; font-family: Arial, sans-serif; }}
    img, svg, canvas, table {{ max-width: 100%; }}
    .localized-interactive-placeholder {{
      border: 1px solid #bbb; background: #f6f6f6; color: #555;
      padding: 12px; margin: 12px 0; font: 14px/1.4 Arial, sans-serif;
    }}
  </style>
</head>
<body>
{localized_body}
</body>
</html>"""


def localize_one(sample: dict[str, Any], out_root: Path, chrome: Path) -> dict[str, Any]:
    sample_dir = out_root / sample["sample_id"]
    sample_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = sample_dir / "assets"
    if assets_dir.exists():
        shutil.rmtree(assets_dir)
    started = time.time()
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 strategy-report-verifier-localizer/1.0"})
    store = ResourceStore(sample_dir, session)
    capture_mode = sample.get("capture_mode", "archive")
    archive_path = archive_path_for_url(sample["url"])
    hydrated_path = sample_dir / "_hydrated_source.html"
    if capture_mode == "live":
        hydration_audit = {"downloaded_asset_count": 0, "failed_assets": []}
        navigation_url = sample["url"]
    else:
        if archive_path is None:
            raise FileNotFoundError(f"No archived HTML found for {sample['url']}")
        hydrated_html, hydration_audit = hydrate_archived_html(
            archive_path.read_text(encoding="utf-8", errors="replace"),
            sample["url"],
            store,
        )
        hydrated_path.write_text(hydrated_html, encoding="utf-8")
        navigation_url = hydrated_path.resolve().as_uri()

    proc = None
    user_data_dir = None
    try:
        proc, ws_url, user_data_dir = launch_for_url(chrome)
        with CDPClient(ws_url) as cdp:
            cdp.call("Page.enable")
            cdp.call("Runtime.enable")
            cdp.call("Network.enable")
            cdp.call("Page.navigate", {"url": navigation_url}, timeout=45)
            deadline = time.time() + (90 if capture_mode == "live" else 45)
            while time.time() < deadline:
                state = eval_js(cdp, "document.readyState", timeout=5)
                text_len = eval_js(cdp, "(document.body && document.body.innerText || '').length", timeout=5) or 0
                if state == "complete" and text_len >= 1200:
                    break
                time.sleep(0.5)
            snapshot = eval_js(cdp, snapshot_script(sample.get("snapshot_options")), timeout=120)
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        if user_data_dir is not None:
            shutil.rmtree(user_data_dir, ignore_errors=True)

    if snapshot.get("text_length", 0) < 2500:
        raise ValueError(f"localized_article_text_too_short: {snapshot.get('text_length')}")
    if str(snapshot.get("final_url") or "").startswith("chrome-error:"):
        raise ValueError("chrome_error_page")
    localized_body, asset_audit = localize_snapshot_assets(snapshot["html"], snapshot["final_url"], store)
    output_html = sample_dir / "index.html"
    output_html.write_text(build_document(snapshot, localized_body, sample["url"]), encoding="utf-8")
    resource_manifest = store.manifest()
    write_json(sample_dir / "resource_manifest.json", resource_manifest)
    metadata = {
        **sample,
        "localized_path": str(output_html.relative_to(ROOT)),
        "localized_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(time.time() - started, 2),
        "snapshot": {key: value for key, value in snapshot.items() if key not in {"html", "assets"}},
        "capture_mode": capture_mode,
        "archive_source_path": str(archive_path.relative_to(ROOT)) if archive_path else None,
        "hydration_audit": hydration_audit,
        "asset_audit": asset_audit,
        "resource_manifest_path": str((sample_dir / "resource_manifest.json").relative_to(ROOT)),
        "resource_summary": {
            key: resource_manifest[key]
            for key in [
                "resource_count", "downloaded_count", "failed_count",
                "critical_failed_count", "total_bytes",
            ]
        },
        "status": "localized"
        if resource_manifest["failed_count"] == 0
        else (
            "localized_with_noncritical_failures"
            if resource_manifest["critical_failed_count"] == 0
            else "localized_with_failed_assets"
        ),
    }
    write_json(sample_dir / "metadata.json", metadata)
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Create self-contained browser-rendered snapshots of strategy-report HTML pages.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sample-id", action="append", default=[])
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--chrome-path", default=None)
    args = parser.parse_args()

    manifest = read_json(args.manifest)
    samples = manifest["samples"]
    if args.sample_id:
        requested = set(args.sample_id)
        samples = [sample for sample in samples if sample["sample_id"] in requested]
    else:
        samples = [sample for sample in samples if sample.get("enabled", True)]
    if args.max_samples is not None:
        samples = samples[: args.max_samples]
    chrome = find_chrome(args.chrome_path)
    if chrome is None:
        raise FileNotFoundError("Chrome or Edge executable was not found.")

    rows = []
    failures = []
    for index, sample in enumerate(samples, start=1):
        print(f"[{index}/{len(samples)}] {sample['sample_id']} {sample['url']}", flush=True)
        try:
            rows.append(localize_one(sample, args.out_dir, chrome))
        except Exception as exc:  # noqa: BLE001
            failure = {**sample, "status": "failed", "error": repr(exc)}
            failures.append(failure)
            print(f"FAILED: {exc!r}", flush=True)
    summary = {
        "manifest": str(args.manifest),
        "out_dir": str(args.out_dir),
        "requested_count": len(samples),
        "localized_count": len(rows),
        "failure_count": len(failures),
        "rows": rows,
        "failures": failures,
    }
    write_json(args.out_dir / "localization_summary.json", summary)
    print(json.dumps({key: summary[key] for key in ["requested_count", "localized_count", "failure_count"]}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
