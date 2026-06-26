from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a local review dashboard for localized HTML candidate audits.")
    parser.add_argument("--audit-json", type=Path, required=True)
    parser.add_argument("--localization-summary", type=Path, default=None)
    parser.add_argument("--verifier-summary", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--title", default="HTML candidate review")
    args = parser.parse_args()

    data = json.loads(args.audit_json.read_text(encoding="utf-8"))
    rows = merge_localization_failures(data.get("rows") or [], args.localization_summary)
    rows = merge_verifier_summary(rows, args.verifier_summary)
    rows = prepare_rows(rows, args.out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_html(rows, args.title, args.out), encoding="utf-8")
    print(f"dashboard={args.out}")
    return 0


def build_html(rows: list[dict[str, Any]], title: str, out_path: Path) -> str:
    payload = json.dumps(rows, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(title)}</title>
  <style>
    :root {{ --border: #d9dee8; --muted: #657083; --bg: #f6f8fb; --good: #0f7b3f; --bad: #b3261e; }}
    body {{ margin: 0; font: 14px/1.45 system-ui, -apple-system, Segoe UI, Arial, sans-serif; color: #172033; background: var(--bg); }}
    header {{ padding: 18px 22px; background: #fff; border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 2; }}
    h1 {{ margin: 0 0 8px; font-size: 20px; }}
    .summary {{ display: flex; gap: 10px; flex-wrap: wrap; color: var(--muted); }}
    .chip {{ border: 1px solid var(--border); background: #fff; border-radius: 999px; padding: 4px 10px; }}
    main {{ display: grid; grid-template-columns: 420px minmax(600px, 1fr); min-height: calc(100vh - 84px); }}
    aside {{ border-right: 1px solid var(--border); background: #fff; overflow: auto; max-height: calc(100vh - 84px); }}
    .filters {{ display: flex; gap: 8px; padding: 12px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }}
    button {{ border: 1px solid var(--border); background: #fff; border-radius: 8px; padding: 6px 9px; cursor: pointer; }}
    button.active {{ background: #172033; color: white; border-color: #172033; }}
    .item {{ padding: 12px 14px; border-bottom: 1px solid var(--border); cursor: pointer; }}
    .item:hover, .item.active {{ background: #eef4ff; }}
    .item-title {{ font-weight: 650; margin-bottom: 4px; }}
    .meta {{ color: var(--muted); font-size: 12px; }}
    .status {{ font-weight: 700; }}
    .ok {{ color: var(--good); }}
    .bad {{ color: var(--bad); }}
    section {{ display: grid; grid-template-rows: auto 1fr; min-width: 0; }}
    .detail {{ padding: 14px 18px; background: #fff; border-bottom: 1px solid var(--border); }}
    .detail-grid {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 8px; margin-top: 10px; }}
    .field {{ background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 8px; }}
    .field b {{ display: block; font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .03em; }}
    iframe {{ width: 100%; height: 100%; border: 0; background: white; }}
    .empty {{ padding: 24px; color: var(--muted); }}
    code {{ background: #f0f2f6; border-radius: 4px; padding: 1px 4px; }}
  </style>
</head>
<body>
<header>
  <h1>{esc(title)}</h1>
  <div class="summary" id="summary"></div>
</header>
<main>
  <aside>
    <div class="filters">
      <button data-filter="all" class="active">All</button>
      <button data-filter="admitted">Admitted</button>
      <button data-filter="rejected">Rejected</button>
      <button data-filter="en">EN</button>
      <button data-filter="zh">ZH</button>
    </div>
    <div id="list"></div>
  </aside>
  <section>
    <div class="detail" id="detail"><div class="empty">Select a sample.</div></div>
    <iframe id="viewer" title="localized sample preview"></iframe>
  </section>
</main>
<script>
const rows = {payload};
let filter = 'all';
let selected = rows[0] || null;
const list = document.getElementById('list');
const detail = document.getElementById('detail');
const viewer = document.getElementById('viewer');
const summary = document.getElementById('summary');
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function filteredRows() {{
  return rows.filter(row => filter === 'all'
    || (filter === 'admitted' && row.admitted)
    || (filter === 'rejected' && !row.admitted)
    || row.language === filter);
}}
function renderSummary() {{
  const admitted = rows.filter(r => r.admitted).length;
  const en = rows.filter(r => r.language === 'en').length;
  const zh = rows.filter(r => r.language === 'zh').length;
  summary.innerHTML = [
    ['total', rows.length],
    ['admitted', admitted],
    ['rejected', rows.length - admitted],
    ['en', en],
    ['zh', zh],
  ].map(([k, v]) => `<span class="chip">${{k}}: ${{v}}</span>`).join('');
}}
function renderList() {{
  const visible = filteredRows();
  if (!visible.includes(selected)) selected = visible[0] || null;
  list.innerHTML = visible.map(row => `
    <div class="item ${{row === selected ? 'active' : ''}}" data-id="${{esc(row.sample_id)}}">
      <div class="item-title">${{esc(row.title || row.sample_id)}}</div>
      <div class="meta">
        <span class="status ${{row.admitted ? 'ok' : 'bad'}}">${{row.admitted ? 'ADMIT' : 'REJECT'}}</span>
        · ${{esc(row.language)}} · len=${{row.text_length}} · visuals=${{row.visual_count_static}} · score=${{row.overall_score ?? '—'}}
      </div>
      <div class="meta">${{esc(row.institution || '')}}</div>
      <div class="meta">${{esc((row.errors || []).join('; ') || (row.warnings || []).join('; '))}}</div>
    </div>
  `).join('') || '<div class="empty">No rows.</div>';
  for (const node of list.querySelectorAll('.item')) {{
    node.onclick = () => {{
      selected = rows.find(row => row.sample_id === node.dataset.id);
      render();
    }};
  }}
}}
function renderDetail() {{
  if (!selected) {{
    detail.innerHTML = '<div class="empty">No sample selected.</div>';
    viewer.src = 'about:blank';
    return;
  }}
  detail.innerHTML = `
    <div><b>${{esc(selected.sample_id)}}</b></div>
    <div class="meta">${{esc(selected.source_url || '')}}</div>
    <div class="detail-grid">
      ${{field('status', selected.status || (selected.admitted ? 'admitted' : 'rejected'))}}
      ${{field('language', selected.language)}}
      ${{field('text length', selected.text_length)}}
      ${{field('verifier score', selected.overall_score ?? '—')}}
      ${{field('grade', selected.grade ?? '—')}}
      ${{field('gate', selected.gate_passed === undefined ? '—' : selected.gate_passed)}}
      ${{field('visuals', selected.visual_count_static)}}
      ${{field('critical resources', selected.critical_failed_resource_count)}}
      ${{field('remote refs', selected.remote_ref_count)}}
      ${{field('missing refs', selected.missing_local_ref_count)}}
      ${{field('errors', (selected.errors || []).join('; ') || '—')}}
      ${{field('gate failures', (selected.gate_failures || []).join('; ') || '—')}}
    </div>
  `;
  viewer.src = selected.preview_href || 'about:blank';
}}
function field(label, value) {{
  return `<div class="field"><b>${{esc(label)}}</b>${{esc(value)}}</div>`;
}}
function render() {{
  renderSummary();
  renderList();
  renderDetail();
}}
for (const button of document.querySelectorAll('button[data-filter]')) {{
  button.onclick = () => {{
    filter = button.dataset.filter;
    document.querySelectorAll('button[data-filter]').forEach(btn => btn.classList.toggle('active', btn === button));
    render();
  }};
}}
render();
</script>
</body>
</html>
"""


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def prepare_rows(rows: list[dict[str, Any]], out_path: Path) -> list[dict[str, Any]]:
    base = out_path.resolve().parent
    prepared = []
    for row in rows:
        item = dict(row)
        sample_path = Path(str(row.get("path") or ""))
        if not row.get("path"):
            item["preview_href"] = "about:blank"
            prepared.append(item)
            continue
        if not sample_path.is_absolute():
            sample_path = Path.cwd() / sample_path
        try:
            item["preview_href"] = sample_path.resolve().relative_to(base).as_posix()
        except ValueError:
            item["preview_href"] = sample_path.resolve().as_uri()
        prepared.append(item)
    return prepared


def merge_localization_failures(rows: list[dict[str, Any]], summary_path: Path | None) -> list[dict[str, Any]]:
    merged = list(rows)
    seen = {row.get("sample_id") for row in merged}
    if not summary_path or not summary_path.exists():
        return merged
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    for failure in summary.get("failures") or []:
        sample_id = failure.get("sample_id") or failure.get("url") or "localization_failure"
        if sample_id in seen:
            continue
        seen.add(sample_id)
        merged.append(
            {
                "sample_id": sample_id,
                "path": "",
                "source_url": failure.get("url") or "",
                "institution": failure.get("institution") or "",
                "title": ((failure.get("discovery") or {}).get("title_hint") or failure.get("sample_id") or ""),
                "language": failure.get("language") or "",
                "subtype": failure.get("subtype") or "",
                "text_length": 0,
                "visual_count_static": 0,
                "critical_failed_resource_count": "",
                "remote_ref_count": "",
                "missing_local_ref_count": "",
                "admitted": False,
                "status": "localization_failed",
                "errors": [f"localization_failed:{failure.get('error') or ''}"],
                "warnings": [],
            }
        )
    return merged


def merge_verifier_summary(rows: list[dict[str, Any]], summary_path: Path | None) -> list[dict[str, Any]]:
    if not summary_path or not summary_path.exists():
        return rows
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    by_id = {row.get("sample_id"): row for row in summary.get("results") or []}
    merged = []
    for row in rows:
        item = dict(row)
        verifier = by_id.get(row.get("sample_id"))
        if verifier:
            item["overall_score"] = verifier.get("overall_score")
            item["grade"] = verifier.get("grade")
            item["gate_passed"] = verifier.get("gate_passed")
            item["gate_failures"] = verifier.get("gate_failures") or []
        merged.append(item)
    return merged


if __name__ == "__main__":
    raise SystemExit(main())
