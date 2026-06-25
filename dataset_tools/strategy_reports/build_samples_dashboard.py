from __future__ import annotations

import argparse
import json
from collections import Counter
from html import escape
from pathlib import Path
from typing import Any

from common import read_jsonl


SUBTYPE_LABELS = {
    "annual_outlook": "Annual Outlook",
    "asset_allocation": "Asset Allocation",
    "thematic_strategy": "Thematic Strategy",
    "midyear_outlook": "Midyear Outlook",
    "fixed_income": "Fixed Income",
    "equity_strategy": "Equity Strategy",
}


def rel_path(path: str | None, base_dir: Path) -> str:
    if not path:
        return ""
    try:
        return Path(path).resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def pct(value: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{value / total * 100:.1f}%"


def bar_list(counter: Counter[str], total: int, label_map: dict[str, str] | None = None) -> str:
    if not counter:
        return '<p class="empty">No data</p>'
    max_value = max(counter.values())
    parts = []
    for key, value in counter.most_common():
        label = label_map.get(key, key) if label_map else key
        width = value / max_value * 100 if max_value else 0
        parts.append(
            f"""
            <div class="bar-row">
              <div class="bar-meta">
                <span>{escape(label)}</span>
                <strong>{value}</strong>
              </div>
              <div class="bar-track"><div class="bar-fill" style="width:{width:.2f}%"></div></div>
              <div class="bar-note">{pct(value, total)}</div>
            </div>
            """
        )
    return "\n".join(parts)


def compact_list(counter: Counter[str], total: int) -> str:
    return "\n".join(
        f'<span class="chip"><span>{escape(key)}</span><strong>{value}</strong><em>{pct(value, total)}</em></span>'
        for key, value in counter.most_common()
    )


def sample_rows(rows: list[dict[str, Any]], base_dir: Path) -> str:
    out = []
    for row in rows:
        subtype = row.get("subtype") or "unknown"
        title = row.get("title") or row.get("curated_id") or "Untitled"
        local_href = rel_path(row.get("curated_path"), base_dir)
        source_url = row.get("source_url") or ""
        pages_or_len = row.get("page_count") if row.get("format") == "pdf" else row.get("text_length")
        metric_label = "pages" if row.get("format") == "pdf" else "chars"
        out.append(
            f"""
            <tr data-subtype="{escape(subtype)}" data-format="{escape(row.get('format') or '')}" data-source="{escape(row.get('source_verification') or '')}" data-institution="{escape(row.get('institution') or '')}">
              <td class="sample-id">{escape(row.get('curated_id') or '')}</td>
              <td><span class="type-pill subtype-{escape(subtype)}">{escape(SUBTYPE_LABELS.get(subtype, subtype))}</span></td>
              <td><span class="format-pill">{escape((row.get('format') or '').upper())}</span></td>
              <td class="title-cell">
                <a href="{escape(local_href)}" target="_blank" rel="noreferrer">{escape(title)}</a>
                <small>{escape(row.get('curated_path') or '')}</small>
              </td>
              <td>{escape(row.get('institution') or '')}</td>
              <td>{escape(row.get('country_or_region') or '')}</td>
              <td><span class="verify">{escape(row.get('source_verification') or '')}</span></td>
              <td class="num">{escape(str(row.get('score') or ''))}</td>
              <td class="num">{escape(str(pages_or_len or ''))} <small>{metric_label}</small></td>
              <td class="source-link">{f'<a href="{escape(source_url)}" target="_blank" rel="noreferrer">source</a>' if source_url else ''}</td>
            </tr>
            """
        )
    return "\n".join(out)


def option_list(values: list[str], label_map: dict[str, str] | None = None) -> str:
    parts = ['<option value="all">All</option>']
    for value in values:
        label = label_map.get(value, value) if label_map else value
        parts.append(f'<option value="{escape(value)}">{escape(label)}</option>')
    return "\n".join(parts)


def build_html(rows: list[dict[str, Any]], base_dir: Path) -> str:
    total = len(rows)
    subtype_counts = Counter(row.get("subtype") or "unknown" for row in rows)
    format_counts = Counter(row.get("format") or "unknown" for row in rows)
    institution_counts = Counter(row.get("institution") or "unknown" for row in rows)
    source_counts = Counter(row.get("source_verification") or "unknown" for row in rows)
    country_counts = Counter(row.get("country_or_region") or "unknown" for row in rows)
    pdf_count = format_counts.get("pdf", 0)
    html_count = format_counts.get("html", 0)
    verified_count = source_counts.get("official_domain_verified", 0) + source_counts.get("third_party_mirror_name_match", 0)
    avg_score = sum(float(row.get("score") or 0) for row in rows) / total if total else 0
    subtype_options = option_list(sorted(subtype_counts), SUBTYPE_LABELS)
    format_options = option_list(sorted(format_counts))
    source_options = option_list(sorted(source_counts))
    rows_json = json.dumps(rows, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Strategy Research Sample Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #657282;
      --line: #d9dee7;
      --accent: #1b6ca8;
      --accent-2: #2f7d5c;
      --accent-3: #9a5b23;
      --accent-4: #6d5aa8;
      --warn: #a54444;
      --soft: #eef3f7;
      --shadow: 0 10px 28px rgba(25, 35, 50, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, "Segoe UI", Arial, "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--ink);
      letter-spacing: 0;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    header {{
      padding: 24px 32px 18px;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
    }}
    .header-top {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 20px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 26px;
      line-height: 1.2;
      font-weight: 760;
    }}
    .subtitle {{
      margin: 0;
      max-width: 980px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.55;
    }}
    .actions {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .action-btn {{
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      padding: 8px 11px;
      font-size: 13px;
      border-radius: 6px;
      cursor: pointer;
    }}
    main {{ padding: 22px 32px 34px; }}
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(140px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .kpi {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 16px;
      box-shadow: var(--shadow);
    }}
    .kpi span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }}
    .kpi strong {{
      font-size: 25px;
      line-height: 1;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.05fr 1fr;
      gap: 16px;
      margin-bottom: 18px;
    }}
    section.panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      box-shadow: var(--shadow);
      min-width: 0;
    }}
    section.panel h2 {{
      margin: 0 0 14px;
      font-size: 16px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: minmax(160px, 1fr) 2fr 58px;
      gap: 10px;
      align-items: center;
      margin: 10px 0;
    }}
    .bar-meta {{
      display: flex;
      justify-content: space-between;
      gap: 8px;
      font-size: 13px;
      min-width: 0;
    }}
    .bar-meta span {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .bar-track {{
      height: 9px;
      background: var(--soft);
      border-radius: 999px;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      border-radius: 999px;
    }}
    .bar-note {{
      font-size: 12px;
      color: var(--muted);
      text-align: right;
    }}
    .chip-wrap {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .chip {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 9px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fafbfc;
      font-size: 12px;
    }}
    .chip strong {{ font-size: 14px; }}
    .chip em {{ color: var(--muted); font-style: normal; }}
    .filters {{
      display: grid;
      grid-template-columns: 1.4fr repeat(3, minmax(130px, 180px));
      gap: 10px;
      margin-bottom: 12px;
    }}
    input, select {{
      width: 100%;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 6px;
      padding: 9px 10px;
      font-size: 13px;
    }}
    .table-wrap {{
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 1180px;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #f1f4f7;
      z-index: 1;
      color: #354250;
      font-weight: 700;
      font-size: 12px;
    }}
    tr:hover td {{ background: #fafcff; }}
    .sample-id {{
      font-family: "Cascadia Mono", Consolas, monospace;
      color: #465466;
      white-space: nowrap;
    }}
    .title-cell {{
      max-width: 320px;
    }}
    .title-cell small {{
      display: block;
      margin-top: 5px;
      color: var(--muted);
      word-break: break-all;
      line-height: 1.35;
    }}
    .num {{ text-align: right; white-space: nowrap; }}
    .type-pill, .format-pill, .verify {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 12px;
      white-space: nowrap;
      background: #edf2f8;
      color: #23415c;
    }}
    .format-pill {{
      background: #f2eee7;
      color: #704b22;
    }}
    .verify {{
      background: #eaf5ef;
      color: #255b42;
      border-radius: 6px;
    }}
    .subtype-asset_allocation {{ background: #e9f4ef; color: #245d43; }}
    .subtype-thematic_strategy {{ background: #f5eee7; color: #7a4a1f; }}
    .subtype-annual_outlook {{ background: #e8f1f8; color: #24577a; }}
    .subtype-midyear_outlook {{ background: #efedf8; color: #594c91; }}
    .subtype-fixed_income {{ background: #f3edf1; color: #784761; }}
    .subtype-equity_strategy {{ background: #edf3e5; color: #50661d; }}
    .source-link {{ white-space: nowrap; }}
    .footer-note {{
      margin: 14px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }}
    @media (max-width: 980px) {{
      header, main {{ padding-left: 18px; padding-right: 18px; }}
      .header-top {{ display: block; }}
      .actions {{ justify-content: flex-start; margin-top: 14px; }}
      .kpi-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .grid {{ grid-template-columns: 1fr; }}
      .filters {{ grid-template-columns: 1fr 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-top">
      <div>
        <h1>Strategy Research Sample Dashboard</h1>
        <p class="subtitle">展示最终 verified 样本集的 38 条策略研究样例，包含子类别、格式、机构来源、核验状态、标题、本地文件和原始来源。数据来自 <code>metadata.jsonl</code>。</p>
      </div>
      <div class="actions">
        <button class="action-btn" id="resetFilters">Reset Filters</button>
        <button class="action-btn" id="copySummary">Copy Summary</button>
      </div>
    </div>
  </header>
  <main>
    <div class="kpi-grid">
      <div class="kpi"><span>Total Samples</span><strong>{total}</strong></div>
      <div class="kpi"><span>PDF</span><strong>{pdf_count}</strong></div>
      <div class="kpi"><span>HTML</span><strong>{html_count}</strong></div>
      <div class="kpi"><span>Verified Sources</span><strong>{verified_count}</strong></div>
      <div class="kpi"><span>Average Score</span><strong>{avg_score:.1f}</strong></div>
    </div>
    <div class="grid">
      <section class="panel">
        <h2>Subtype Distribution</h2>
        {bar_list(subtype_counts, total, SUBTYPE_LABELS)}
      </section>
      <section class="panel">
        <h2>Institution Distribution</h2>
        {bar_list(institution_counts, total)}
      </section>
      <section class="panel">
        <h2>Format And Source Verification</h2>
        <div class="chip-wrap">{compact_list(format_counts, total)}</div>
        <div style="height:12px"></div>
        <div class="chip-wrap">{compact_list(source_counts, total)}</div>
      </section>
      <section class="panel">
        <h2>Region Distribution</h2>
        <div class="chip-wrap">{compact_list(country_counts, total)}</div>
        <p class="footer-note">中文第三方样例仅保留机构名可核验项；未核验镜像未进入最终 verified 样本集。</p>
      </section>
    </div>
    <section class="panel">
      <h2>Sample Registry</h2>
      <div class="filters">
        <input id="searchBox" type="search" placeholder="Search title, institution, id, URL">
        <select id="subtypeFilter">{subtype_options}</select>
        <select id="formatFilter">{format_options}</select>
        <select id="sourceFilter">{source_options}</select>
      </div>
      <div class="table-wrap">
        <table id="sampleTable">
          <thead>
            <tr>
              <th>ID</th>
              <th>Subtype</th>
              <th>Format</th>
              <th>Title / Local File</th>
              <th>Institution</th>
              <th>Region</th>
              <th>Verification</th>
              <th>Score</th>
              <th>Size</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {sample_rows(rows, base_dir)}
          </tbody>
        </table>
      </div>
      <p class="footer-note"><span id="visibleCount">{total}</span> visible samples. Local file links are relative to this dashboard.</p>
    </section>
  </main>
  <script>
    const rows = {rows_json};
    const searchBox = document.getElementById('searchBox');
    const subtypeFilter = document.getElementById('subtypeFilter');
    const formatFilter = document.getElementById('formatFilter');
    const sourceFilter = document.getElementById('sourceFilter');
    const visibleCount = document.getElementById('visibleCount');
    const tableRows = Array.from(document.querySelectorAll('#sampleTable tbody tr'));

    function applyFilters() {{
      const q = searchBox.value.trim().toLowerCase();
      const subtype = subtypeFilter.value;
      const format = formatFilter.value;
      const source = sourceFilter.value;
      let count = 0;
      tableRows.forEach((tr) => {{
        const text = tr.innerText.toLowerCase();
        const okSearch = !q || text.includes(q);
        const okSubtype = subtype === 'all' || tr.dataset.subtype === subtype;
        const okFormat = format === 'all' || tr.dataset.format === format;
        const okSource = source === 'all' || tr.dataset.source === source;
        const show = okSearch && okSubtype && okFormat && okSource;
        tr.style.display = show ? '' : 'none';
        if (show) count += 1;
      }});
      visibleCount.textContent = count;
    }}

    [searchBox, subtypeFilter, formatFilter, sourceFilter].forEach((el) => el.addEventListener('input', applyFilters));
    document.getElementById('resetFilters').addEventListener('click', () => {{
      searchBox.value = '';
      subtypeFilter.value = 'all';
      formatFilter.value = 'all';
      sourceFilter.value = 'all';
      applyFilters();
    }});
    document.getElementById('copySummary').addEventListener('click', async () => {{
      const summary = `Samples: {total}\\nPDF: {pdf_count}\\nHTML: {html_count}\\nVerified: {verified_count}\\nSubtypes: {dict(subtype_counts)}`;
      await navigator.clipboard.writeText(summary);
    }});
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a static dashboard for curated strategy samples.")
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    rows = read_jsonl(args.metadata)
    base_dir = args.out.parent
    args.out.write_text(build_html(rows, base_dir), encoding="utf-8")
    print(f"dashboard={args.out} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
