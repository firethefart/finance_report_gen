from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

import requests

from common import USER_AGENT, append_jsonl, is_pdf_file, sha256_file, slugify, utc_now_iso, write_json


LIST_API = "https://reportapi.eastmoney.com/report/dg"
PDF_URL_TEMPLATE = "https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf"
SOURCE_NAME = "东方财富研报 API / Eastmoney reportapi"
SOURCE_PLATFORM = "Eastmoney"

STRATEGY_QTYPE = 2
STRATEGY_COLUMN_TYPE = "策略报告"

NOISE_TITLE_RE = re.compile(r"(早报|晨报|日报|快报|新闻|鑫新闻|收盘|开盘|午评|晚报|早知道|日刊)")
POSITIVE_TITLE_RE = re.compile(
    r"(策略|配置|展望|周报|月报|季报|年度|中期|专题|主题|市场|A股|港股|北交所|资产|宏观|行业|复盘|跟踪|观察|风格|轮动|观点|投资)"
)


def fetch_page(session: requests.Session, page_no: int, page_size: int, begin_time: str, end_time: str) -> dict[str, Any]:
    params = {
        "qType": STRATEGY_QTYPE,
        "pageNo": page_no,
        "pageSize": page_size,
        "beginTime": begin_time,
        "endTime": end_time,
    }
    response = session.get(LIST_API, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def is_strategy_item(item: dict[str, Any], strict_title_filter: bool) -> bool:
    if item.get("columnType") != STRATEGY_COLUMN_TYPE:
        return False
    if str(item.get("reportType")) != "4":
        return False
    if not item.get("infoCode"):
        return False
    title = str(item.get("title") or "")
    if strict_title_filter:
        if NOISE_TITLE_RE.search(title):
            return False
        if not POSITIVE_TITLE_RE.search(title):
            return False
    return True


def pdf_url_for(item: dict[str, Any]) -> str:
    return PDF_URL_TEMPLATE.format(info_code=item["infoCode"])


def short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:10]


def output_path_for(item: dict[str, Any], out_dir: Path) -> Path:
    org = slugify(str(item.get("orgSName") or item.get("orgName") or "unknown"), max_len=48)
    date = str(item.get("publishDate") or "")[:10].replace("-", "")
    title = str(item.get("title") or "strategy-report")
    stem = f"{date}-{item.get('infoCode')}-{short_hash(title)}"
    return out_dir / "raw_pdfs" / "strategy_research" / "eastmoney-strategy-reports" / org / f"{stem}.pdf"


def download_pdf(session: requests.Session, url: str, out_path: Path, overwrite: bool = False) -> dict[str, Any]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and not overwrite:
        return {
            "status": "exists",
            "file_path": str(out_path),
            "http_status": None,
            "file_size_bytes": out_path.stat().st_size,
            "sha256": sha256_file(out_path),
            "is_pdf": is_pdf_file(out_path),
            "error": None,
        }

    tmp = out_path.with_suffix(".pdf.part")
    try:
        with session.get(url, stream=True, timeout=60) as response:
            status_code = response.status_code
            response.raise_for_status()
            with tmp.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        handle.write(chunk)
        size = tmp.stat().st_size
        if size < 10_000:
            tmp.unlink(missing_ok=True)
            return {
                "status": "failed_small",
                "file_path": None,
                "http_status": status_code,
                "file_size_bytes": size,
                "sha256": None,
                "is_pdf": False,
                "error": "file smaller than 10KB",
            }
        if not is_pdf_file(tmp):
            tmp.unlink(missing_ok=True)
            return {
                "status": "failed_not_pdf",
                "file_path": None,
                "http_status": status_code,
                "file_size_bytes": size,
                "sha256": None,
                "is_pdf": False,
                "error": "downloaded payload is not a PDF",
            }
        tmp.replace(out_path)
        return {
            "status": "downloaded",
            "file_path": str(out_path),
            "http_status": status_code,
            "file_size_bytes": out_path.stat().st_size,
            "sha256": sha256_file(out_path),
            "is_pdf": True,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        return {
            "status": "failed",
            "file_path": None,
            "http_status": None,
            "file_size_bytes": 0,
            "sha256": None,
            "is_pdf": False,
            "error": repr(exc),
        }


def crawl(args: argparse.Namespace) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Referer": "https://data.eastmoney.com/report/",
            "Accept": "application/json,text/plain,*/*",
        }
    )
    manifest_path = args.out / "manifests" / "eastmoney_strategy_download_manifest.jsonl"
    list_path = args.out / "manifests" / "eastmoney_strategy_list_items.jsonl"
    if args.reset_manifest:
        manifest_path.unlink(missing_ok=True)
        list_path.unlink(missing_ok=True)

    seen_info_codes: set[str] = set()
    rows: list[dict[str, Any]] = []
    list_rows: list[dict[str, Any]] = []
    page_no = 1
    total_pages = None
    downloaded_ok = 0

    while downloaded_ok < args.limit and page_no <= args.max_pages:
        data = fetch_page(session, page_no, args.page_size, args.begin_time, args.end_time)
        if total_pages is None:
            total_pages = data.get("TotalPage")
        items = data.get("data") or []
        if not items:
            break
        for item in items:
            info_code = str(item.get("infoCode") or "")
            if not info_code or info_code in seen_info_codes:
                continue
            seen_info_codes.add(info_code)
            if not is_strategy_item(item, strict_title_filter=args.strict_title_filter):
                continue
            pdf_url = pdf_url_for(item)
            out_path = output_path_for(item, args.out)
            row = {
                "downloaded_at": utc_now_iso(),
                "source_platform": SOURCE_PLATFORM,
                "source_name": SOURCE_NAME,
                "source_api": LIST_API,
                "source_bucket": "china_eastmoney_strategy_api",
                "institution": item.get("orgName"),
                "org_short_name": item.get("orgSName"),
                "business_type": "broker_research_third_party",
                "country_or_region": "CN",
                "subtype_hint": "strategy_research",
                "eastmoney_qtype": STRATEGY_QTYPE,
                "eastmoney_column_type": item.get("columnType"),
                "eastmoney_report_type": item.get("reportType"),
                "title": item.get("title"),
                "publish_date": item.get("publishDate"),
                "researcher": item.get("researcher"),
                "author": item.get("author"),
                "org_code": item.get("orgCode"),
                "info_code": info_code,
                "eastmoney_id": item.get("id"),
                "pdf_url": pdf_url,
                "mirror_url": pdf_url,
                "detail_url": f"https://data.eastmoney.com/report/zw_macresearch.jshtml?encodeUrl={item.get('encodeUrl')}",
                "copyright_note": "Third-party public Eastmoney mirror; original broker/institution attribution must be preserved.",
                "needs_human_source_verification": True,
            }
            list_rows.append({**row, "raw_item": item})
            result = download_pdf(session, pdf_url, out_path, overwrite=args.overwrite)
            row.update(result)
            rows.append(row)
            if result.get("status") in {"downloaded", "exists"} and result.get("is_pdf"):
                downloaded_ok += 1
            if downloaded_ok >= args.limit:
                break
            if args.sleep:
                time.sleep(args.sleep)
        append_jsonl(manifest_path, rows)
        append_jsonl(list_path, list_rows)
        rows = []
        list_rows = []
        print(f"page={page_no} ok={downloaded_ok} total_pages={total_pages}")
        page_no += 1
        if args.sleep_page:
            time.sleep(args.sleep_page)

    all_rows = []
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                all_rows.append(json.loads(line))
    ok_rows = [row for row in all_rows if row.get("status") in {"downloaded", "exists"} and row.get("is_pdf")]
    failed_rows = [row for row in all_rows if row not in ok_rows]
    summary = {
        "generated_at": utc_now_iso(),
        "source_name": SOURCE_NAME,
        "source_api": LIST_API,
        "qType": STRATEGY_QTYPE,
        "columnType": STRATEGY_COLUMN_TYPE,
        "begin_time": args.begin_time,
        "end_time": args.end_time,
        "strict_title_filter": args.strict_title_filter,
        "requested_limit": args.limit,
        "downloaded_or_existing_pdfs": len(ok_rows),
        "failed_or_non_pdf": len(failed_rows),
        "manifest_path": str(manifest_path),
        "list_items_path": str(list_path),
        "output_root": str(args.out / "raw_pdfs" / "strategy_research" / "eastmoney-strategy-reports"),
        "top_orgs": top_counts(ok_rows, "org_short_name"),
        "date_range_observed": observed_date_range(ok_rows),
    }
    write_json(args.out / "manifests" / "eastmoney_strategy_summary.json", summary)
    return summary


def top_counts(rows: list[dict[str, Any]], key: str, limit: int = 20) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return [{"name": name, "count": count} for name, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]]


def observed_date_range(rows: list[dict[str, Any]]) -> dict[str, str | None]:
    dates = sorted(str(row.get("publish_date") or "")[:10] for row in rows if row.get("publish_date"))
    return {"min": dates[0] if dates else None, "max": dates[-1] if dates else None}


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl Eastmoney strategy-report PDFs using report/dg qType=2.")
    parser.add_argument("--out", type=Path, default=Path("dataset_build"))
    parser.add_argument("--begin-time", default="2025-01-01")
    parser.add_argument("--end-time", default="2026-06-10")
    parser.add_argument("--limit", type=int, default=150)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--sleep", type=float, default=0.05)
    parser.add_argument("--sleep-page", type=float, default=0.2)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--reset-manifest", action="store_true")
    parser.add_argument("--no-strict-title-filter", dest="strict_title_filter", action="store_false")
    parser.set_defaults(strict_title_filter=True)
    args = parser.parse_args()
    summary = crawl(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["downloaded_or_existing_pdfs"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
