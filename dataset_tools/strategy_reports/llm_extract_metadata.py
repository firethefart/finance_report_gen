from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from common import append_jsonl, read_jsonl, utc_now_iso, write_json
from document_extractors import extract_document, image_to_data_url
from llm_clients import OpenRouterClient, estimate_tokens, extract_json_object, read_api_key
from metadata_models import validate_case


FLASH_MODEL = "deepseek/deepseek-v4-flash"
PRO_MODEL = "deepseek/deepseek-v4-pro"
VL_MODEL = "qwen/qwen3-vl-235b-a22b-instruct"
SMOKE_SAMPLE_IDS = [
    "strategy_sample_001",
    "strategy_sample_002",
    "strategy_sample_003",
    "strategy_sample_024",
    "strategy_sample_028",
    "strategy_sample_032",
]


FLASH_SYSTEM = """You are a careful financial research metadata assistant.
Extract only report-level evidence useful for building a benchmark from strategy research reports.
Return compact valid JSON. Do not invent facts that are not supported by the supplied excerpts."""


PRO_SYSTEM = """You are building golden-set metadata for a strategy research report benchmark.
Return one strict JSON object following the requested schema. Prefer conservative, auditable facts.
Generate user-like candidate queries that would naturally ask for this report type, not queries that quote the title."""


VL_SYSTEM = """You inspect report screenshots for layout, charts, tables, and professional style signals.
Return compact valid JSON with only observations visible in the screenshot."""


def build_flash_prompt(sample: dict[str, Any], doc: dict[str, Any]) -> str:
    excerpt = doc["text_excerpt"]
    if has_probable_mojibake(doc):
        excerpt = "[Text layer appears garbled; rely on manifest, headings, and visual/OCR notes if available.]"
    payload = {
        "sample_manifest": compact_manifest(sample),
        "local_extract": {
            "parse_quality": doc["parse_quality"],
            "title_hint": doc["title_hint"],
            "headings": doc["headings"][:30],
            "tables_or_figures_hint": doc.get("tables_or_figures_hint", [])[:12],
            "links": doc.get("links", [])[:12],
            "text_excerpt": excerpt,
        },
    }
    return (
        "Read the manifest and excerpt. Return JSON with keys: "
        "report_identity, subtype_candidates, important_claims, likely_sections, source_pack_candidates, "
        "style_signals, candidate_query_ideas, quality_notes, risks_or_uncertainties. "
        "Keep important_claims to 6-10 items and cite excerpt evidence briefly.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def build_pro_prompt(sample: dict[str, Any], doc: dict[str, Any], flash: dict[str, Any], visual: dict[str, Any] | None) -> str:
    source_language = infer_source_language(sample, doc)
    short_excerpt = doc["text_excerpt"][:6000]
    if has_probable_mojibake(doc):
        short_excerpt = "[Omitted because the PDF text layer is likely mojibake. Use manifest fields and visual notes conservatively.]"
    schema_hint = {
        "case_id": "string",
        "source_pdf": {
            "file_path": "string",
            "file_name": "string",
            "sha256": "string|null",
            "file_size_bytes": 0,
            "page_count": 0,
            "parse_method": "text|ocr|hybrid|manual|unknown",
            "parse_quality": "excellent|good|fair|poor|failed",
        },
        "institution": {
            "name": "string",
            "business_type": "asset_manager|investment_bank|private_bank|brokerage|research_provider|other",
            "country_or_region": "string|null",
            "official_url": "string|null",
        },
        "report_title": "string",
        "report_date": "YYYY-MM-DD|null",
        "publication_period": "string|null",
        "authors_or_team": ["string"],
        "strategy_subtype": "string",
        "secondary_tags": ["string"],
        "classification_rationale": "string",
        "quality_tier": "A|B|C|Reject",
        "quality_rationale": "string",
        "candidate_query": {
            "query": "string",
            "language": "zh|en|mixed",
            "query_style": "retail_user|institutional_client|analyst_request|portfolio_committee|other",
            "scope_constraints": ["string"],
        },
        "expected_report_type": {
            "type": "string",
            "depth": "quick_brief|standard_report|institutional_style",
            "output_format": "webpage|markdown|pdf|pptx|docx|dashboard|unspecified",
            "expected_time_horizon": "string|null",
            "target_reader": "string|null",
        },
        "source_pack": [],
        "key_facts": [],
        "must_have_sections": [],
        "prohibited_mistakes": [],
        "reference_notes": {},
        "charts_and_tables_to_learn_from": [],
        "evaluation_hooks": {},
        "extraction_confidence": {
            "overall": 0.0,
            "classification": 0.0,
            "key_facts": 0.0,
            "source_pack": 0.0,
            "query": 0.0,
        },
        "extraction_notes": "string",
    }
    payload = {
        "schema": schema_hint,
        "rules": [
            "For source_pdf, use the local document metadata even for HTML sources; keep the key name source_pdf for schema compatibility.",
            "Create 4-7 key_facts. Each claim, why_it_matters, and verification_hint must be one concise sentence.",
            "Create 3-5 source_pack items. Use short names and notes; do not include long source descriptions.",
            "Create 5-7 must_have_sections and 4-6 prohibited_mistakes tailored to this subtype.",
            "Keep reference_notes, charts_and_tables_to_learn_from, and evaluation_hooks compact.",
            "Do not add alternate schemas such as candidate_queries, primary_topics, primary_asset_classes, or confidence.",
            f"Candidate query should be reusable for a benchmark. Use language={source_language}; do not mix encodings.",
            "If date or authors are not visible, set null or empty list rather than guessing.",
        ],
        "sample_manifest": compact_manifest(sample),
        "document_metadata": {
            "file_path": doc["source_path"],
            "file_name": doc["file_name"],
            "sha256": doc["sha256"],
            "file_size_bytes": doc["file_size_bytes"],
            "page_count": doc["page_count"],
            "parse_method": doc["parse_method"],
            "parse_quality": doc["parse_quality"],
            "title_hint": doc["title_hint"],
            "headings": doc["headings"][:24],
        },
        "flash_extraction": flash,
        "visual_notes": visual or {},
        "short_excerpt_for_grounding": short_excerpt,
    }
    return "Return only valid JSON.\n\n" + json.dumps(payload, ensure_ascii=False)


def infer_source_language(sample: dict[str, Any], doc: dict[str, Any]) -> str:
    country = (sample.get("country_or_region") or "").upper()
    text = f"{sample.get('title', '')} {doc.get('text_excerpt', '')[:1000]}"
    chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    if country in {"CN", "HK", "TW"} or chinese_chars > 20:
        return "zh"
    return "en"


def has_probable_mojibake(doc: dict[str, Any]) -> bool:
    warnings = doc.get("extraction_warnings") or []
    return any("mojibake" in warning for warning in warnings)


def build_repair_prompt(raw_content: str, validation_errors: list[str]) -> str:
    return (
        "Repair this metadata output into one valid JSON object matching the schema. "
        "Do not add new claims; only fix JSON/schema issues.\n"
        f"Validation errors: {validation_errors}\n"
        f"Raw output:\n{raw_content[:10000]}"
    )


def compact_manifest(sample: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "curated_id",
        "format",
        "source_url",
        "institution",
        "business_type",
        "country_or_region",
        "title",
        "subtype",
        "quality_tier",
        "source_verification",
        "score",
        "page_count",
    ]
    return {key: sample.get(key) for key in keys if key in sample}


def call_flash(client: OpenRouterClient, sample: dict[str, Any], doc: dict[str, Any], out_dir: Path, cache: bool) -> dict[str, Any]:
    out_path = out_dir / "flash_pass" / f"{sample['curated_id']}.json"
    if cache and out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
    prompt = build_flash_prompt(sample, doc)
    result = client.chat(
        FLASH_MODEL,
        [{"role": "system", "content": FLASH_SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=1200,
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"stage": "flash", "sample_id": sample["curated_id"], "input_tokens_est": estimate_tokens(prompt)},
    )
    data = result.get("json") if result.get("ok") else None
    output = {"ok": bool(data), "raw_result": result, "data": data or {}}
    write_json(out_path, output)
    return output


def call_visual(
    client: OpenRouterClient,
    sample: dict[str, Any],
    doc: dict[str, Any],
    out_dir: Path,
    cache: bool,
) -> dict[str, Any] | None:
    images = [Path(p) for p in doc.get("visual_images", [])[:2]]
    if not images:
        return None
    out_path = out_dir / "visual_pass" / f"{sample['curated_id']}.json"
    if cache and out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Inspect this report page screenshot. Return JSON keys: visible_title, layout_style, "
                "chart_or_table_observations, data_density, branding_or_compliance_signals, reusable_style_notes."
            ),
        }
    ]
    for image_path in images:
        content.append({"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}})
    result = client.chat(
        VL_MODEL,
        [{"role": "system", "content": VL_SYSTEM}, {"role": "user", "content": content}],
        max_tokens=600,
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"stage": "visual", "sample_id": sample["curated_id"], "image_count": len(images)},
    )
    data = result.get("json") if result.get("ok") else None
    output = {"ok": bool(data), "raw_result": result, "data": data or {}}
    write_json(out_path, output)
    return output


def call_pro(
    client: OpenRouterClient,
    sample: dict[str, Any],
    doc: dict[str, Any],
    flash: dict[str, Any],
    visual: dict[str, Any] | None,
    out_dir: Path,
    cache: bool,
) -> dict[str, Any]:
    out_path = out_dir / "pro_pass" / f"{sample['curated_id']}.json"
    if cache and out_path.exists():
        return json.loads(out_path.read_text(encoding="utf-8"))
    flash_data = flash.get("data") or {}
    visual_data = (visual or {}).get("data") if visual else None
    prompt = build_pro_prompt(sample, doc, flash_data, visual_data)
    result = client.chat(
        PRO_MODEL,
        [{"role": "system", "content": PRO_SYSTEM}, {"role": "user", "content": prompt}],
        max_tokens=4500,
        temperature=0,
        response_format={"type": "json_object"},
        metadata={"stage": "pro", "sample_id": sample["curated_id"], "input_tokens_est": estimate_tokens(prompt)},
    )
    data = result.get("json") if result.get("ok") else None
    if data is None:
        retry = client.chat(
            PRO_MODEL,
            [{"role": "system", "content": PRO_SYSTEM}, {"role": "user", "content": prompt}],
            max_tokens=5000,
            temperature=0,
            response_format={"type": "json_object"},
            metadata={"stage": "pro_retry", "sample_id": sample["curated_id"], "input_tokens_est": estimate_tokens(prompt)},
        )
        result["retry_result"] = retry
        data = retry.get("json") if retry.get("ok") else None
    valid = False
    normalized: dict[str, Any] = {}
    errors: list[str] = []
    if isinstance(data, dict):
        data["case_id"] = sample["curated_id"]
        valid, normalized, errors = validate_case(data)
    if not valid and result.get("content"):
        repair = client.chat(
            PRO_MODEL,
            [
                {"role": "system", "content": PRO_SYSTEM},
                {"role": "user", "content": build_repair_prompt(result["content"], errors)},
            ],
            max_tokens=4500,
            temperature=0,
            response_format={"type": "json_object"},
            metadata={"stage": "repair", "sample_id": sample["curated_id"]},
        )
        repaired = repair.get("json")
        if isinstance(repaired, dict):
            repaired["case_id"] = sample["curated_id"]
            valid, normalized, errors = validate_case(repaired)
        result["repair_result"] = repair
    output = {"ok": valid, "validation_errors": errors, "raw_result": result, "data": normalized if valid else data or {}}
    write_json(out_path, output)
    return output


def select_samples(rows: list[dict[str, Any]], ids: list[str], limit: int | None) -> list[dict[str, Any]]:
    if ids:
        wanted = set(ids)
        rows = [row for row in rows if row.get("curated_id") in wanted]
        rows.sort(key=lambda row: ids.index(row["curated_id"]) if row.get("curated_id") in wanted else 999)
    if limit:
        rows = rows[:limit]
    return rows


def run(args: argparse.Namespace) -> None:
    metadata_path = Path(args.metadata)
    work_dir = Path(args.work_dir)
    out_path = Path(args.out)
    manifest_path = work_dir / "run_manifest.jsonl"
    samples = read_jsonl(metadata_path)
    sample_ids = SMOKE_SAMPLE_IDS if args.smoke_test else args.sample_ids
    selected = select_samples(samples, sample_ids, args.limit)
    if not selected:
        raise SystemExit("No samples selected.")
    client: OpenRouterClient | None = None
    if not args.local_only:
        api_key = read_api_key(Path(args.api_key_file))
        client = OpenRouterClient(api_key=api_key, base_url=args.base_url, log_dir=work_dir / "llm_logs")
    if args.reset_output and out_path.exists():
        out_path.unlink()
    completed_ids: set[str] = set()
    if args.skip_existing and out_path.exists():
        for row in read_jsonl(out_path):
            case_id = row.get("case_id")
            if case_id:
                completed_ids.add(case_id)
    visual_calls = 0
    for index, sample in enumerate(selected, start=1):
        sample_id = sample["curated_id"]
        if sample_id in completed_ids:
            print(f"[{index}/{len(selected)}] skipping existing {sample_id}")
            continue
        print(f"[{index}/{len(selected)}] extracting {sample_id} {sample.get('title')}")
        doc = extract_document(sample, work_dir=work_dir, max_chars=args.max_chars, render_pages=args.render_pages, cache=not args.no_cache)
        if args.local_only:
            append_jsonl(
                manifest_path,
                [
                    {
                        "case_id": sample_id,
                        "completed_at": utc_now_iso(),
                        "format": sample.get("format"),
                        "local_extract_ok": doc.get("parse_quality") != "failed",
                        "parse_quality": doc.get("parse_quality"),
                        "text_length": doc.get("text_length"),
                        "visual_images": len(doc.get("visual_images", [])),
                    }
                ],
            )
            continue
        assert client is not None
        flash = call_flash(client, sample, doc, work_dir, cache=not args.no_cache)
        visual = None
        use_visual = args.enable_vl and sample.get("format") == "pdf" and visual_calls < args.vl_limit
        if use_visual:
            visual = call_visual(client, sample, doc, work_dir, cache=not args.no_cache)
            visual_calls += 1
        pro = call_pro(client, sample, doc, flash, visual, work_dir, cache=not args.no_cache)
        row = {
            "case_id": sample_id,
            "completed_at": utc_now_iso(),
            "format": sample.get("format"),
            "flash_ok": flash.get("ok"),
            "visual_ok": None if visual is None else visual.get("ok"),
            "pro_ok": pro.get("ok"),
            "validation_errors": pro.get("validation_errors", []),
            "output_path": str(out_path),
        }
        append_jsonl(manifest_path, [row])
        if pro.get("ok"):
            append_jsonl(out_path, [pro["data"]])
        else:
            write_json(work_dir / "failed_cases" / f"{sample_id}.json", {"sample": sample, "doc": doc, "flash": flash, "visual": visual, "pro": pro})
    print(f"Done. Final cases: {out_path}")
    print(f"Run manifest: {manifest_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract benchmark metadata from curated strategy reports with LLM assistance.")
    parser.add_argument("--metadata", default="dataset_build/curated_strategy_samples_verified/metadata.jsonl")
    parser.add_argument("--out", default="dataset_build/meta_extraction/final_cases.jsonl")
    parser.add_argument("--work-dir", default="dataset_build/meta_extraction")
    parser.add_argument("--api-key-file", default="api_key.txt")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--sample-ids", nargs="*", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--enable-vl", action="store_true")
    parser.add_argument("--vl-limit", type=int, default=2)
    parser.add_argument("--max-chars", type=int, default=18000)
    parser.add_argument("--render-pages", type=int, default=2)
    parser.add_argument("--local-only", action="store_true", help="Run document extraction only; do not call LLMs.")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--reset-output", action="store_true")
    parser.add_argument("--skip-existing", action="store_true", help="Skip samples whose case_id already exists in --out.")
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
