from __future__ import annotations

import argparse
import base64
import html
import json
import time
from pathlib import Path
from typing import Any

from eval_utils import ROOT, read_json, write_json, write_text
from html_runtime_adapter_v2 import adapt_html_runtime_v2


def repo_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def data_uri(path: str | Path | None) -> str:
    if not path:
        return ""
    p = repo_path(path)
    if not p.exists() or not p.is_file():
        return ""
    suffix = p.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg" if suffix in {".jpg", ".jpeg"} else "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def run_test_set(manifest_path: Path, out_dir: Path, max_visuals: int) -> dict[str, Any]:
    manifest_path = repo_path(manifest_path)
    out_dir = repo_path(out_dir)
    manifest = read_json(manifest_path)
    rows: list[dict[str, Any]] = []
    started = time.time()
    for sample in manifest.get("samples", []):
        sample_id = sample["id"]
        sample_out = out_dir / "samples" / sample_id
        row: dict[str, Any] = {
            "id": sample_id,
            "group": sample.get("group"),
            "path": sample.get("path"),
            "expected": sample.get("expected"),
            "out_dir": str(sample_out),
            "ok": False,
        }
        sample_started = time.time()
        try:
            result = adapt_html_runtime_v2(
                html_path=repo_path(sample["path"]),
                out_dir=sample_out,
                report_id=sample_id,
                max_visuals=max_visuals,
            )
            adapter_manifest = result["manifest"]
            visual_objects = result["visual_objects"].get("visual_objects") or []
            skipped_visuals = result["visual_objects"].get("skipped_visuals") or []
            row.update(
                {
                    "ok": True,
                    "elapsed_seconds": round(time.time() - sample_started, 2),
                    "adapter_manifest": adapter_manifest,
                    "visual_objects": visual_objects[:12],
                    "skipped_visuals": skipped_visuals[:12],
                    "full_page_image": str(sample_out / "screenshots" / f"{sample_id}_full_page.png"),
                }
            )
        except Exception as exc:
            row.update({"elapsed_seconds": round(time.time() - sample_started, 2), "error": repr(exc)})
        rows.append(row)
    summary = {
        "test_set": manifest,
        "out_dir": str(out_dir),
        "sample_count": len(rows),
        "ok_count": len([row for row in rows if row["ok"]]),
        "elapsed_seconds": round(time.time() - started, 2),
        "rows": rows,
    }
    write_json(out_dir / "run_summary.json", summary)
    write_text(out_dir / "index.html", build_dashboard(summary))
    return summary


def build_dashboard(summary: dict[str, Any]) -> str:
    rows = summary["rows"]
    cards = []
    for row in rows:
        manifest = row.get("adapter_manifest") or {}
        visual_objects = row.get("visual_objects") or []
        skipped = row.get("skipped_visuals") or []
        full_page = data_uri(row.get("full_page_image"))
        visual_cards = []
        for visual in visual_objects:
            visual_cards.append(
                f"""
                <div class="visual">
                  <img src="{data_uri(visual.get('target_image_path'))}" alt="target visual" />
                  <div class="meta">
                    <b>{html.escape(str(visual.get('visual_id')))}</b>
                    <span>{html.escape(str(visual.get('tag')))}</span>
                    <span>{html.escape(str(visual.get('section_heading') or '无标题上下文'))}</span>
                  </div>
                </div>
                """
            )
        skipped_rows = "".join(
            f"<li><b>{html.escape(str(item.get('reason')))}</b> {html.escape(str((item.get('render_status') or {}).get('src') or '')[:180])}</li>"
            for item in skipped[:8]
        )
        warnings = ", ".join(manifest.get("warnings") or [])
        cards.append(
            f"""
            <section class="sample">
              <header>
                <div>
                  <h2>{html.escape(row['id'])}</h2>
                  <p>{html.escape(str(row.get('group') or ''))} · {html.escape(str(row.get('expected') or ''))}</p>
                  <code>{html.escape(str(row.get('path') or ''))}</code>
                </div>
                <span class="status {'ok' if row.get('ok') else 'bad'}">{'OK' if row.get('ok') else 'FAIL'}</span>
              </header>
              <div class="stats">
                <span>耗时 {row.get('elapsed_seconds', 0)}s</span>
                <span>文本 {manifest.get('text_length', 0)}</span>
                <span>标题 {manifest.get('heading_count', 0)}</span>
                <span>视觉 {manifest.get('visual_count', 0)}</span>
                <span>跳过 {manifest.get('skipped_visual_count', 0)}</span>
                <span>缺失资源 {(manifest.get('resource_audit') or {}).get('failed_static_resource_count', 0)}</span>
              </div>
              <p class="warnings">{html.escape(warnings or '无 warning')}</p>
              {f'<p class="error">{html.escape(str(row.get("error")))}</p>' if row.get('error') else ''}
              <div class="grid">
                <div>
                  <h3>完整页面截图</h3>
                  {'<img class="full" src="' + full_page + '" alt="full page" />' if full_page else '<div class="empty">无完整截图</div>'}
                </div>
                <div>
                  <h3>目标视觉截图</h3>
                  <div class="visuals">{''.join(visual_cards) if visual_cards else '<div class="empty">无目标视觉对象</div>'}</div>
                  <h3>跳过对象</h3>
                  <ul class="skipped">{skipped_rows or '<li>无</li>'}</ul>
                </div>
              </div>
            </section>
            """
        )
    payload = json.dumps(summary, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>HTML Runtime Adapter V2 回归看板</title>
  <style>
    body {{ margin: 0; font-family: Arial, "Microsoft YaHei", sans-serif; background: #f5f7fa; color: #182235; }}
    main {{ max-width: 1500px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 26px; }}
    .summary {{ margin-bottom: 18px; color: #4a5668; }}
    .sample {{ background: #fff; border: 1px solid #dce2ea; border-radius: 8px; padding: 18px; margin: 18px 0; }}
    header {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; border-bottom: 1px solid #e6ebf2; padding-bottom: 12px; }}
    h2 {{ margin: 0 0 6px; font-size: 20px; }}
    h3 {{ font-size: 15px; margin: 14px 0 8px; }}
    p {{ margin: 4px 0; }}
    code {{ display: block; margin-top: 6px; color: #52606f; overflow-wrap: anywhere; }}
    .status {{ padding: 5px 10px; border-radius: 999px; font-weight: 700; }}
    .status.ok {{ background: #e8f6ef; color: #13734b; }}
    .status.bad {{ background: #fdecec; color: #a43131; }}
    .stats {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }}
    .stats span {{ background: #eef2f7; padding: 5px 8px; border-radius: 5px; }}
    .warnings {{ color: #8a5b10; overflow-wrap: anywhere; }}
    .error {{ color: #a43131; }}
    .grid {{ display: grid; grid-template-columns: minmax(420px, 0.9fr) minmax(480px, 1.1fr); gap: 18px; align-items: start; }}
    img.full {{ width: 100%; max-height: 760px; object-fit: contain; border: 1px solid #dce2ea; background: #fff; }}
    .visuals {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }}
    .visual {{ border: 1px solid #dce2ea; border-radius: 6px; overflow: hidden; background: #fbfcfe; }}
    .visual img {{ width: 100%; max-height: 260px; object-fit: contain; display: block; background: #fff; }}
    .meta {{ display: grid; gap: 3px; padding: 8px; font-size: 12px; color: #4a5668; }}
    .empty {{ border: 1px dashed #c9d1dc; color: #66758a; padding: 24px; text-align: center; border-radius: 6px; }}
    .skipped {{ max-height: 160px; overflow: auto; padding-left: 20px; color: #5b6675; }}
    script[type="application/json"] {{ display: none; }}
  </style>
</head>
<body>
  <main>
    <h1>HTML Runtime Adapter V2 回归看板</h1>
    <p class="summary">样本 {summary['ok_count']}/{summary['sample_count']} 成功，耗时 {summary['elapsed_seconds']} 秒。重点检查：正文是否保留、外部资源是否被记录、目标视觉截图是否完整、长图是否不被固定页切断。</p>
    {''.join(cards)}
  </main>
  <script id="run-summary" type="application/json">{html.escape(payload)}</script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Run HTML Runtime Adapter V2 regression samples.")
    parser.add_argument("--manifest", type=Path, default=Path("evals/strategy_report/html_runtime_test_set.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("evals/strategy_report/results/html_runtime_v2_regression"))
    parser.add_argument("--max-visuals", type=int, default=40)
    args = parser.parse_args()
    summary = run_test_set(args.manifest, args.out_dir, args.max_visuals)
    print(json.dumps({k: summary[k] for k in ["out_dir", "sample_count", "ok_count", "elapsed_seconds"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
