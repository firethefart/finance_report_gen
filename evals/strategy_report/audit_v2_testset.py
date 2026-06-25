from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import fitz
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SELECTION = ROOT / "evals" / "strategy_report" / "v2_testset_selection.json"

STRATEGY_TERMS = {
    "en": [
        "outlook",
        "strategy",
        "allocation",
        "portfolio",
        "market",
        "investment",
        "scenario",
        "risk",
    ],
    "zh": ["策略", "配置", "市场", "投资", "展望", "风险", "情景", "观点"],
}
SOURCE_TERMS = ["source", "sources", "来源", "资料来源", "数据来源", "bloomberg", "factset", "wind"]
RISK_TERMS = ["risk", "risks", "uncertainty", "scenario", "风险", "不确定", "情景"]
MOJIBAKE_MARKERS = ["锟", "鈥", "鍥", "鐨", "涓", "�"]
REMOTE_RE = re.compile(r"^(?:https?:)?//", re.IGNORECASE)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def count_terms(text: str, terms: list[str]) -> int:
    lower = text.lower()
    return sum(lower.count(term.lower()) for term in terms)


def mojibake_ratio(text: str) -> float:
    sample = text[:50000]
    if not sample:
        return 0.0
    return sum(sample.count(marker) for marker in MOJIBAKE_MARKERS) / len(sample)


def audit_pdf(path: Path, sample: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    text_parts: list[str] = []
    page_profiles: list[dict[str, Any]] = []
    image_count = 0
    try:
        with fitz.open(path) as doc:
            page_count = doc.page_count
            for index, page in enumerate(doc):
                text_parts.append(page.get_text("text"))
                rect = page.rect
                page_profiles.append(
                    {
                        "page": index + 1,
                        "width": round(rect.width, 2),
                        "height": round(rect.height, 2),
                        "orientation": "landscape" if rect.width > rect.height * 1.05 else "portrait",
                    }
                )
                image_count += len(page.get_images(full=True))
                if index in {0, max(0, page_count // 2), max(0, page_count - 1)}:
                    pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
                    if pix.width < 100 or pix.height < 100:
                        warnings.append(f"render_too_small_page_{index + 1}")
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "admitted": False,
            "errors": [f"pdf_open_or_render_failed: {exc!r}"],
            "warnings": warnings,
        }

    raw_text = "\n".join(text_parts)
    normalized = normalize_text(raw_text)
    language = sample["language"]
    strategy_hits = count_terms(normalized, STRATEGY_TERMS[language])
    source_hits = count_terms(normalized, SOURCE_TERMS)
    risk_hits = count_terms(normalized, RISK_TERMS)
    landscape_pages = sum(row["orientation"] == "landscape" for row in page_profiles)
    landscape_ratio = landscape_pages / max(1, len(page_profiles))
    errors: list[str] = []
    if page_count < 2:
        errors.append("pdf_too_short_or_invalid")
    if len(normalized) < 2500:
        errors.append("insufficient_text_layer")
    if mojibake_ratio(normalized) > 0.01:
        errors.append("probable_mojibake")
    if strategy_hits < 3:
        errors.append("weak_strategy_report_signals")
    if source_hits == 0:
        warnings.append("no_source_signal_detected")
    if risk_hits == 0:
        warnings.append("no_risk_signal_detected")
    if image_count == 0:
        warnings.append("no_embedded_images_detected")
    return {
        "ok": not errors,
        "admitted": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "page_count": page_count,
            "text_length": len(normalized),
            "image_count": image_count,
            "strategy_signal_count": strategy_hits,
            "source_signal_count": source_hits,
            "risk_signal_count": risk_hits,
            "mojibake_ratio": round(mojibake_ratio(normalized), 6),
            "landscape_page_ratio": round(landscape_ratio, 3),
        },
        "text_probe": {
            "head": normalized[:500],
            "tail": normalized[-500:],
        },
    }


def audit_html(path: Path, sample: dict[str, Any]) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "html.parser")
    for node in soup(["script", "style", "noscript"]):
        node.decompose()
    text = normalize_text(soup.get_text(" "))
    resources: list[str] = []
    for tag, attr in [("img", "src"), ("script", "src"), ("link", "href"), ("source", "src")]:
        for node in BeautifulSoup(raw, "html.parser").find_all(tag):
            value = str(node.get(attr) or "").strip()
            if value:
                resources.append(value)
    remote = [value for value in resources if REMOTE_RE.match(value)]
    missing: list[str] = []
    for value in resources:
        if REMOTE_RE.match(value) or value.startswith(("data:", "#", "javascript:")):
            continue
        candidate = (path.parent / value.split("?", 1)[0].split("#", 1)[0]).resolve()
        if not candidate.exists():
            missing.append(value)
    language = sample["language"]
    strategy_hits = count_terms(text, STRATEGY_TERMS[language])
    errors: list[str] = []
    warnings: list[str] = []
    if len(text) < 2500:
        errors.append("html_text_too_short")
    if strategy_hits < 3:
        errors.append("weak_strategy_report_signals")
    if missing:
        errors.append("missing_local_resources")
    if remote:
        errors.append("remote_resources_present")
    if mojibake_ratio(text) > 0.01:
        errors.append("probable_mojibake")
    if not resources:
        warnings.append("html_has_no_external_or_embedded_resource_refs")
    resource_manifest_audit = None
    if sample.get("resource_manifest"):
        manifest_path = (ROOT / sample["resource_manifest"]).resolve()
        manifest_errors: list[str] = []
        if not manifest_path.exists():
            manifest_errors.append("resource_manifest_missing")
            resource_manifest = {}
        else:
            resource_manifest = read_json(manifest_path)
            for item in resource_manifest.get("resources") or []:
                if item.get("status") != "downloaded":
                    if item.get("critical", True):
                        manifest_errors.append(f"critical_resource_failed:{item.get('original_url')}")
                    continue
                local_path = item.get("local_path")
                if not local_path:
                    manifest_errors.append(f"resource_local_path_missing:{item.get('original_url')}")
                    continue
                resource_path = path.parent / local_path
                if not resource_path.exists():
                    manifest_errors.append(f"resource_file_missing:{local_path}")
                    continue
                if sha256_file(resource_path) != item.get("sha256"):
                    manifest_errors.append(f"resource_hash_mismatch:{local_path}")
        if manifest_errors:
            errors.extend(manifest_errors)
        resource_manifest_audit = {
            "path": str(manifest_path),
            "errors": manifest_errors,
            "resource_count": resource_manifest.get("resource_count", 0),
            "downloaded_count": resource_manifest.get("downloaded_count", 0),
            "failed_count": resource_manifest.get("failed_count", 0),
            "critical_failed_count": resource_manifest.get("critical_failed_count", 0),
        }
    if sample.get("source_class") == "official_localized":
        if sample.get("content_review") != "passed":
            errors.append("content_review_not_passed")
        if sample.get("visual_review") != "passed":
            errors.append("visual_review_not_passed")
    return {
        "ok": not errors,
        "admitted": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "text_length": len(text),
            "heading_count": len(soup.find_all(["h1", "h2", "h3", "h4"])),
            "table_count": len(soup.find_all("table")),
            "svg_count": len(soup.find_all("svg")),
            "canvas_count": len(soup.find_all("canvas")),
            "resource_count": len(resources),
            "remote_resource_count": len(remote),
            "missing_resource_count": len(missing),
            "strategy_signal_count": strategy_hits,
            "source_signal_count": count_terms(text, SOURCE_TERMS),
            "risk_signal_count": count_terms(text, RISK_TERMS),
            "mojibake_ratio": round(mojibake_ratio(text), 6),
        },
        "resource_probe": {
            "remote": remote[:20],
            "missing": missing[:20],
        },
        "resource_manifest_audit": resource_manifest_audit,
        "text_probe": {
            "head": text[:500],
            "tail": text[-500:],
        },
    }


def render_pdf_review_contact(path: Path, sample: dict[str, Any], review_dir: Path) -> str:
    review_dir.mkdir(parents=True, exist_ok=True)
    with fitz.open(path) as doc:
        indices = sorted({0, max(0, doc.page_count // 2), max(0, doc.page_count - 1)})
        panels: list[Image.Image] = []
        for index in indices:
            page = doc.load_page(index)
            pix = page.get_pixmap(matrix=fitz.Matrix(0.9, 0.9), alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            image.thumbnail((700, 900))
            canvas = Image.new("RGB", (720, 960), "white")
            canvas.paste(image, ((720 - image.width) // 2, 40))
            draw = ImageDraw.Draw(canvas)
            draw.text((18, 12), f"{sample['sample_id']} — page {index + 1}/{doc.page_count}", fill="black")
            panels.append(canvas)
    contact = Image.new("RGB", (720 * len(panels), 960), "#d9dde3")
    for index, panel in enumerate(panels):
        contact.paste(panel, (720 * index, 0))
    out = review_dir / f"{sample['sample_id']}.jpg"
    contact.save(out, format="JPEG", quality=84, optimize=True)
    return str(out)


def audit_sample(sample: dict[str, Any], review_dir: Path | None = None) -> dict[str, Any]:
    path = (ROOT / sample["path"]).resolve()
    base = {
        **sample,
        "absolute_path": str(path),
        "exists": path.exists(),
    }
    if not path.exists():
        return {**base, "ok": False, "admitted": False, "errors": ["file_missing"], "warnings": []}
    result = audit_pdf(path, sample) if sample["format"] == "pdf" else audit_html(path, sample)
    review_contact = None
    if review_dir is not None and sample["format"] == "pdf" and result.get("ok"):
        try:
            review_contact = render_pdf_review_contact(path, sample, review_dir)
        except Exception as exc:  # noqa: BLE001
            result.setdefault("warnings", []).append(f"review_contact_render_failed: {exc!r}")
    return {
        **base,
        "sha256": sha256_file(path),
        "file_size_bytes": path.stat().st_size,
        "review_contact_sheet": review_contact,
        **result,
    }


def distribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def counts(key: str) -> dict[str, int]:
        return dict(sorted(Counter(str(row.get(key) or "") for row in rows).items()))

    roles = Counter(role for row in rows for role in row.get("test_roles") or [])
    return {
        "language": counts("language"),
        "format": counts("format"),
        "subtype": counts("subtype"),
        "archetype": counts("archetype"),
        "institution": counts("institution"),
        "test_roles": dict(sorted(roles.items())),
    }


def build_review_overview(rows: list[dict[str, Any]], review_dir: Path) -> str | None:
    paths = [Path(row["review_contact_sheet"]) for row in rows if row.get("review_contact_sheet")]
    if not paths:
        return None
    thumb_width = 900
    thumb_height = 400
    cols = 2
    rows_count = (len(paths) + cols - 1) // cols
    overview = Image.new("RGB", (thumb_width * cols, thumb_height * rows_count), "#b8bec7")
    for index, path in enumerate(paths):
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((thumb_width - 10, thumb_height - 10))
            x = (index % cols) * thumb_width + (thumb_width - image.width) // 2
            y = (index // cols) * thumb_height + (thumb_height - image.height) // 2
            overview.paste(image, (x, y))
    out = review_dir / "overview.jpg"
    overview.save(out, format="JPEG", quality=86, optimize=True)
    return str(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the curated Verifier V2 strategy-report test set.")
    parser.add_argument("--selection", type=Path, default=DEFAULT_SELECTION)
    parser.add_argument("--out", type=Path, default=ROOT / "evals" / "strategy_report" / "v2_testset_audit.json")
    parser.add_argument("--review-dir", type=Path, default=None)
    args = parser.parse_args()

    selection = read_json(args.selection)
    rows = [audit_sample(sample, review_dir=args.review_dir) for sample in selection["samples"]]
    hashes = Counter(row.get("sha256") for row in rows if row.get("sha256"))
    for row in rows:
        if row.get("sha256") and hashes[row["sha256"]] > 1:
            row.setdefault("errors", []).append("duplicate_file_hash")
            row["ok"] = False
            row["admitted"] = False

    admitted = [row for row in rows if row.get("admitted")]
    rejected = [row for row in rows if not row.get("admitted")]
    requirements = selection.get("hard_requirements") or {}
    html_rows = [row for row in admitted if row.get("format") == "html"]
    high_quality_html = [
        row for row in html_rows
        if row.get("quality_expectation") == "A" and row.get("source_class") == "official_localized"
    ]
    real_html = [row for row in html_rows if row.get("source_class") == "official_localized"]
    generated_html = [row for row in html_rows if row.get("source_class") == "self_contained_local"]
    html_institutions = Counter(row.get("institution") for row in real_html)
    html_subtypes = {row.get("subtype") for row in real_html}
    hard_gate_errors: list[str] = []
    checks = [
        ("total_below_minimum", len(admitted), requirements.get("minimum_total_count"), lambda a, b: a < b),
        ("total_above_maximum", len(admitted), requirements.get("maximum_total_count"), lambda a, b: a > b),
        ("html_below_minimum", len(html_rows), requirements.get("minimum_html_count"), lambda a, b: a < b),
        (
            "high_quality_html_below_minimum",
            len(high_quality_html),
            requirements.get("minimum_high_quality_html_count"),
            lambda a, b: a < b,
        ),
        (
            "real_institution_html_below_minimum",
            len(real_html),
            requirements.get("minimum_real_institution_html_count"),
            lambda a, b: a < b,
        ),
        (
            "generated_html_above_maximum",
            len(generated_html),
            requirements.get("maximum_generated_html_count"),
            lambda a, b: a > b,
        ),
        (
            "single_html_institution_above_maximum",
            max(html_institutions.values(), default=0),
            requirements.get("maximum_single_html_institution_count"),
            lambda a, b: a > b,
        ),
        (
            "html_subtypes_below_minimum",
            len(html_subtypes),
            requirements.get("minimum_html_subtype_count"),
            lambda a, b: a < b,
        ),
    ]
    for name, actual, threshold, failed in checks:
        if threshold is not None and failed(actual, threshold):
            hard_gate_errors.append(f"{name}: actual={actual} threshold={threshold}")
    review_overview = build_review_overview(rows, args.review_dir) if args.review_dir else None
    payload = {
        "testset_name": selection["testset_name"],
        "version": selection["version"],
        "requested_count": len(rows),
        "admitted_count": len(admitted),
        "rejected_count": len(rejected),
        "all_files_unique": all(count == 1 for count in hashes.values()),
        "hard_gate_errors": hard_gate_errors,
        "hard_gate_metrics": {
            "total_count": len(admitted),
            "html_count": len(html_rows),
            "high_quality_html_count": len(high_quality_html),
            "real_institution_html_count": len(real_html),
            "generated_html_count": len(generated_html),
            "maximum_single_html_institution_count": max(html_institutions.values(), default=0),
            "html_subtype_count": len(html_subtypes),
        },
        "review_overview": review_overview,
        "distribution_all": distribution(rows),
        "distribution_admitted": distribution(admitted),
        "rejected_samples": [
            {
                "sample_id": row["sample_id"],
                "path": row["path"],
                "errors": row.get("errors") or [],
                "warnings": row.get("warnings") or [],
            }
            for row in rejected
        ],
        "samples": rows,
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in [
        "requested_count", "admitted_count", "rejected_count", "all_files_unique",
        "hard_gate_errors", "hard_gate_metrics", "rejected_samples",
    ]}, ensure_ascii=False, indent=2))
    return 0 if not rejected and not hard_gate_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
