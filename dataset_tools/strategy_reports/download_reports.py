from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from common import (
    USER_AGENT,
    append_jsonl,
    filename_from_url,
    institution_slug,
    is_pdf_file,
    load_json,
    sha256_file,
    utc_now_iso,
)


def discover_pdf_links(session: requests.Session, url: str, same_domain: bool = True) -> list[str]:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    base_host = urlparse(url).netloc
    links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        parsed = urlparse(href)
        if same_domain and parsed.netloc and parsed.netloc != base_host:
            continue
        clean = href.split("#", 1)[0]
        if ".pdf" not in parsed.path.lower() and ".pdf" not in parsed.query.lower():
            continue
        if clean not in seen:
            seen.add(clean)
            links.append(clean)
    return links


def download_pdf(
    session: requests.Session,
    url: str,
    out_path: Path,
    min_bytes: int = 10_000,
) -> dict[str, Any]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".part")
    status = "downloaded"
    error = None
    size = 0
    try:
        with session.get(url, stream=True, timeout=60, allow_redirects=True) as resp:
            http_status = resp.status_code
            resp.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        f.write(chunk)
        size = tmp.stat().st_size
        if size < min_bytes:
            status = "failed_small"
        elif not is_pdf_file(tmp):
            status = "failed_not_pdf"
        if status == "downloaded":
            tmp.replace(out_path)
        else:
            tmp.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001
        http_status = None
        status = "failed"
        error = repr(exc)
        tmp.unlink(missing_ok=True)
    return {
        "url": url,
        "file_path": str(out_path) if status == "downloaded" else None,
        "http_status": http_status,
        "status": status,
        "error": error,
        "file_size_bytes": out_path.stat().st_size if out_path.exists() else size,
        "sha256": sha256_file(out_path) if out_path.exists() else None,
        "is_pdf": is_pdf_file(out_path) if out_path.exists() else False,
    }


def build_download_jobs(config: dict[str, Any], session: requests.Session, max_discovered_per_page: int) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for source in config.get("sources", []):
        kind = source.get("kind", "direct_pdf")
        if kind == "direct_pdf":
            jobs.append({**source, "pdf_url": source["url"], "discovered_from": None})
        elif kind == "landing_page":
            try:
                links = discover_pdf_links(session, source["url"])
            except Exception as exc:  # noqa: BLE001
                jobs.append({**source, "pdf_url": None, "discovery_error": repr(exc), "discovered_from": source["url"]})
                continue
            for link in links[:max_discovered_per_page]:
                jobs.append({**source, "pdf_url": link, "discovered_from": source["url"]})
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description="Download public strategy research PDFs.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("dataset_build"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-discovered-per-page", type=int, default=25)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--reset-manifest", action="store_true")
    parser.add_argument("--organize-by-subtype", action="store_true")
    args = parser.parse_args()

    config = load_json(args.config)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    jobs = build_download_jobs(config, session, args.max_discovered_per_page)
    if args.limit is not None:
        jobs = jobs[: args.limit]

    manifest_path = args.out / "manifests" / "download_manifest.jsonl"
    if args.reset_manifest:
        manifest_path.unlink(missing_ok=True)
    rows: list[dict[str, Any]] = []
    for job in tqdm(jobs, desc="downloading"):
        pdf_url = job.get("pdf_url")
        row = {
            "downloaded_at": utc_now_iso(),
            "institution": job.get("institution"),
            "business_type": job.get("business_type"),
            "country_or_region": job.get("country_or_region"),
            "subtype_hint": job.get("subtype_hint"),
            "source_kind": job.get("kind"),
            "source_url": job.get("url"),
            "discovered_from": job.get("discovered_from"),
            "pdf_url": pdf_url,
        }
        if not pdf_url:
            row.update({"status": "failed_discovery", "error": job.get("discovery_error")})
            rows.append(row)
            continue

        inst_dir = args.out / "raw_pdfs" / institution_slug(job.get("institution", "unknown"))
        if args.organize_by_subtype:
            inst_dir = args.out / "raw_pdfs" / institution_slug(job.get("subtype_hint") or "uncategorized") / institution_slug(job.get("institution", "unknown"))
        out_path = inst_dir / filename_from_url(pdf_url)
        if out_path.exists() and not args.overwrite:
            result = {
                "status": "exists",
                "file_path": str(out_path),
                "file_size_bytes": out_path.stat().st_size,
                "sha256": sha256_file(out_path),
                "is_pdf": is_pdf_file(out_path),
                "http_status": None,
                "error": None,
            }
        else:
            result = download_pdf(session, pdf_url, out_path)
        row.update(result)
        rows.append(row)

    append_jsonl(manifest_path, rows)
    ok = sum(1 for r in rows if r.get("status") in {"downloaded", "exists"} and r.get("is_pdf"))
    failed = len(rows) - ok
    print(f"jobs={len(rows)} ok={ok} failed_or_non_pdf={failed}")
    print(f"manifest={manifest_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
