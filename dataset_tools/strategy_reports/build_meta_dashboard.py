from __future__ import annotations

import argparse
import json
import os
from html import escape
from pathlib import Path
from typing import Any

from common import read_jsonl


def rel_path(path: str | None, base_dir: Path) -> str:
    if not path:
        return ""
    try:
        return Path(os.path.relpath(Path(path).resolve(), base_dir.resolve())).as_posix()
    except ValueError:
        return Path(path).as_posix().replace("\\", "/")


def load_cases(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return read_jsonl(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected list JSON: {path}")
    return data


def enrich_cases(cases: list[dict[str, Any]], base_dir: Path) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for case in cases:
        item = dict(case)
        source_pdf = item.get("source_pdf") or {}
        source_path = source_pdf.get("file_path") or source_pdf.get("source_path")
        item["_source_href"] = rel_path(source_path, base_dir)
        item["_source_kind"] = "html" if str(source_path).lower().endswith((".html", ".htm")) else "pdf"
        item["_source_exists"] = bool(source_path and Path(source_path).exists())
        enriched.append(item)
    return enriched


def build_html(cases: list[dict[str, Any]], title: str) -> str:
    data_json = json.dumps(cases, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d9dee7;
      --text: #1c2430;
      --muted: #667085;
      --accent: #0f766e;
      --accent-2: #1d4ed8;
      --warn: #b45309;
      --bad: #b91c1c;
      --good: #047857;
      --shadow: 0 10px 30px rgba(31, 41, 55, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, "Microsoft YaHei", sans-serif;
      color: var(--text);
      background: var(--bg);
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(255,255,255,.96);
      border-bottom: 1px solid var(--line);
      box-shadow: 0 1px 8px rgba(31, 41, 55, .04);
    }}
    .topbar {{
      display: grid;
      grid-template-columns: auto auto minmax(260px, 1fr) auto auto auto;
      gap: 10px;
      align-items: center;
      padding: 10px 14px;
    }}
    button, select, input {{
      height: 36px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      border-radius: 6px;
      padding: 0 10px;
      font: inherit;
    }}
    button {{
      cursor: pointer;
      font-weight: 700;
    }}
    button:hover {{ border-color: var(--accent); color: var(--accent); }}
    button:disabled {{ opacity: .45; cursor: not-allowed; }}
    select {{ min-width: 260px; }}
    .counter {{
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(420px, 43vw) minmax(480px, 1fr);
      gap: 12px;
      height: calc(100vh - 57px);
      padding: 12px;
    }}
    .pane {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      box-shadow: var(--shadow);
      min-height: 0;
    }}
    .meta-pane {{
      overflow: auto;
      padding: 16px;
    }}
    .viewer-pane {{
      display: grid;
      grid-template-rows: auto 1fr;
    }}
    .viewer-head {{
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: space-between;
      padding: 9px 12px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }}
    .viewer-head a {{
      color: var(--accent-2);
      text-decoration: none;
      font-weight: 700;
      font-size: 13px;
    }}
    iframe {{
      width: 100%;
      height: 100%;
      border: 0;
      background: #fff;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 22px;
      line-height: 1.25;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 18px 0 8px;
      font-size: 15px;
      color: #111827;
      border-bottom: 1px solid var(--line);
      padding-bottom: 6px;
    }}
    .subtitle {{
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 12px;
    }}
    .chips {{
      display: flex;
      gap: 7px;
      flex-wrap: wrap;
      margin: 8px 0 14px;
    }}
    .chip {{
      border: 1px solid var(--line);
      background: #f8fafc;
      border-radius: 999px;
      padding: 5px 9px;
      font-size: 12px;
      color: #344054;
      max-width: 100%;
      overflow-wrap: anywhere;
    }}
    .chip.good {{ color: var(--good); border-color: #a7f3d0; background: #ecfdf5; }}
    .chip.warn {{ color: var(--warn); border-color: #fed7aa; background: #fff7ed; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }}
    .field {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      background: #fcfcfd;
      min-width: 0;
    }}
    .label {{
      display: block;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      margin-bottom: 4px;
    }}
    .value {{
      font-size: 13px;
      overflow-wrap: anywhere;
      line-height: 1.45;
    }}
    .query {{
      border-left: 4px solid var(--accent);
      background: #f0fdfa;
      padding: 10px 12px;
      border-radius: 6px;
      line-height: 1.55;
      font-size: 14px;
    }}
    ul {{
      padding-left: 18px;
      margin: 8px 0;
    }}
    li {{
      margin: 7px 0;
      line-height: 1.5;
      overflow-wrap: anywhere;
    }}
    .fact {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px;
      margin: 8px 0;
      background: #fff;
    }}
    .fact b {{ color: #101828; }}
    .fact small {{
      display: block;
      color: var(--muted);
      margin-top: 5px;
      line-height: 1.45;
    }}
    details {{
      border: 1px solid var(--line);
      border-radius: 6px;
      margin: 8px 0;
      background: #fff;
    }}
    summary {{
      cursor: pointer;
      padding: 9px 10px;
      font-weight: 700;
    }}
    pre {{
      margin: 0;
      padding: 10px;
      background: #0f172a;
      color: #dbeafe;
      overflow: auto;
      font-size: 12px;
      line-height: 1.45;
      max-height: 360px;
    }}
    .empty-viewer {{
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100%;
      color: var(--muted);
      padding: 20px;
      text-align: center;
    }}
    @media (max-width: 980px) {{
      .topbar {{ grid-template-columns: auto auto 1fr; }}
      .layout {{
        height: auto;
        grid-template-columns: 1fr;
      }}
      .viewer-pane {{ height: 78vh; }}
      .grid {{ grid-template-columns: 1fr; }}
      select {{ min-width: 0; width: 100%; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <button id="prevBtn" title="上一个样本">上一条</button>
      <button id="nextBtn" title="下一个样本">下一条</button>
      <select id="sampleSelect" aria-label="选择样本"></select>
      <input id="searchInput" placeholder="搜索标题/机构/类型" />
      <span class="counter" id="counter"></span>
      <button id="copyBtn" title="复制当前样本 JSON">复制 JSON</button>
    </div>
  </header>
  <main class="layout">
    <section class="pane meta-pane" id="metaPane"></section>
    <section class="pane viewer-pane">
      <div class="viewer-head">
        <span id="viewerTitle">原财报</span>
        <a id="openLink" href="#" target="_blank" rel="noreferrer">新窗口打开</a>
      </div>
      <div id="viewerBody"></div>
    </section>
  </main>
  <script id="casesData" type="application/json">{data_json}</script>
  <script>
    const cases = JSON.parse(document.getElementById('casesData').textContent);
    let filtered = cases.map((item, index) => index);
    let currentPos = 0;

    const $ = (id) => document.getElementById(id);
    const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    const arr = (value) => Array.isArray(value) ? value : (value ? [value] : []);

    function field(label, value) {{
      return `<div class="field"><span class="label">${{esc(label)}}</span><div class="value">${{esc(value || '—')}}</div></div>`;
    }}

    function chips(items, extraClass = '') {{
      return `<div class="chips">${{arr(items).map(item => `<span class="chip ${{extraClass}}">${{esc(item)}}</span>`).join('')}}</div>`;
    }}

    function list(items, render) {{
      const safe = arr(items);
      if (!safe.length) return '<p class="subtitle">暂无</p>';
      return `<ul>${{safe.map(item => `<li>${{render ? render(item) : esc(item)}}</li>`).join('')}}</ul>`;
    }}

    function renderCase(index) {{
      const item = cases[index];
      const source = item.source_pdf || {{}};
      const institution = item.institution || {{}};
      const query = item.candidate_query || {{}};
      const expected = item.expected_report_type || {{}};
      const confidence = item.extraction_confidence || {{}};
      const qualityClass = item.quality_tier === 'A' ? 'good' : item.quality_tier === 'B' ? 'warn' : '';

      $('metaPane').innerHTML = `
        <h1>${{esc(item.report_title || item.case_id)}}</h1>
        <div class="subtitle">${{esc(item.case_id)}} · ${{esc(institution.name)}} · ${{esc(item.strategy_subtype)}}</div>
        <div class="chips">
          <span class="chip ${{qualityClass}}">质量 ${{esc(item.quality_tier || '—')}}</span>
          <span class="chip">语言 ${{esc(query.language || '—')}}</span>
          <span class="chip">格式 ${{esc(expected.output_format || '—')}}</span>
          <span class="chip">解析 ${{esc(source.parse_quality || '—')}}</span>
        </div>

        <h2>任务 Query</h2>
        <div class="query">${{esc(query.query || '')}}</div>
        ${{chips(query.scope_constraints || [])}}

        <h2>基础信息</h2>
        <div class="grid">
          ${{field('机构', institution.name)}}
          ${{field('业务类型', institution.business_type)}}
          ${{field('地区', institution.country_or_region)}}
          ${{field('官网', institution.official_url)}}
          ${{field('报告日期', item.report_date)}}
          ${{field('时期', item.publication_period)}}
          ${{field('预期报告类型', expected.type)}}
          ${{field('目标读者', expected.target_reader)}}
        </div>

        <h2>分类与质量</h2>
        <div class="grid">
          ${{field('主类型', item.strategy_subtype)}}
          ${{field('深度', expected.depth)}}
          ${{field('时间范围', expected.expected_time_horizon)}}
          ${{field('页数/文件', `${{source.page_count || '—'}} 页 · ${{source.file_name || '—'}}`)}}
        </div>
        ${{chips(item.secondary_tags || [])}}
        <p>${{esc(item.classification_rationale || '')}}</p>
        <p>${{esc(item.quality_rationale || '')}}</p>

        <h2>Key Facts</h2>
        ${{arr(item.key_facts).map(fact => `
          <div class="fact">
            <b>${{esc(fact.fact_id || '')}}</b> ${{esc(fact.claim || fact.fact || '')}}
            <small>置信度：${{esc(fact.confidence ?? '—')}} · 类型：${{esc(fact.fact_type || '—')}}</small>
            <small>核验提示：${{esc(fact.verification_hint || '')}}</small>
          </div>
        `).join('') || '<p class="subtitle">暂无</p>'}}

        <h2>Must-Have Sections</h2>
        ${{list(item.must_have_sections, section => `<b>${{esc(section.section_name || section)}}</b><br><span class="subtitle">${{esc(section.evaluation_focus || section.purpose || '')}}</span>`)}}

        <h2>Prohibited Mistakes</h2>
        ${{list(item.prohibited_mistakes, mistake => `<b>${{esc(mistake.severity || '')}}</b> · ${{esc(mistake.mistake || mistake)}}<br><span class="subtitle">${{esc(mistake.why_it_matters || '')}}</span>`)}}

        <h2>Source Pack</h2>
        ${{list(item.source_pack, source => `<b>${{esc(source.name || '')}}</b><br><span class="subtitle">${{esc(source.type || '')}} · ${{esc(source.url_or_path || source.source_path || '')}}</span>`)}}

        <h2>图表与版式参考</h2>
        ${{list(item.charts_and_tables_to_learn_from, chart => `<b>${{esc(chart.title_or_description || chart.chart_name || chart.description || '')}}</b><br><span class="subtitle">${{esc(chart.expected_eval_use || chart.type || '')}}</span>`)}}

        <h2>置信度</h2>
        <div class="grid">
          ${{field('overall', confidence.overall)}}
          ${{field('classification', confidence.classification)}}
          ${{field('key_facts', confidence.key_facts)}}
          ${{field('source_pack', confidence.source_pack)}}
          ${{field('query', confidence.query)}}
        </div>

        <details>
          <summary>完整 JSON</summary>
          <pre>${{esc(JSON.stringify(item, null, 2))}}</pre>
        </details>
      `;

      const href = item._source_href || '';
      $('viewerTitle').textContent = `${{item._source_kind === 'html' ? '原网页' : '原 PDF'}}：${{source.file_name || ''}}`;
      $('openLink').href = href || '#';
      if (!href || !item._source_exists) {{
        $('viewerBody').innerHTML = '<div class="empty-viewer">未找到可嵌入的原财报文件。</div>';
      }} else {{
        $('viewerBody').innerHTML = `<iframe src="${{esc(href)}}" title="source report"></iframe>`;
      }}

      const pos = filtered.indexOf(index);
      $('counter').textContent = `${{pos + 1}} / ${{filtered.length}} · 全部 ${{cases.length}}`;
      $('prevBtn').disabled = filtered.length <= 1;
      $('nextBtn').disabled = filtered.length <= 1;
      $('sampleSelect').value = String(index);
    }}

    function rebuildSelect() {{
      const select = $('sampleSelect');
      select.innerHTML = filtered.map(index => {{
        const item = cases[index];
        const label = `${{item.case_id}} · ${{item.institution?.name || ''}} · ${{item.report_title || ''}}`;
        return `<option value="${{index}}">${{esc(label)}}</option>`;
      }}).join('');
      currentPos = Math.min(currentPos, Math.max(0, filtered.length - 1));
      if (filtered.length) renderCase(filtered[currentPos]);
      else $('metaPane').innerHTML = '<p class="subtitle">没有匹配样本</p>';
    }}

    $('prevBtn').addEventListener('click', () => {{
      currentPos = (currentPos - 1 + filtered.length) % filtered.length;
      renderCase(filtered[currentPos]);
    }});
    $('nextBtn').addEventListener('click', () => {{
      currentPos = (currentPos + 1) % filtered.length;
      renderCase(filtered[currentPos]);
    }});
    $('sampleSelect').addEventListener('change', (event) => {{
      const index = Number(event.target.value);
      currentPos = filtered.indexOf(index);
      renderCase(index);
    }});
    $('searchInput').addEventListener('input', (event) => {{
      const q = event.target.value.trim().toLowerCase();
      filtered = cases.map((_, index) => index).filter(index => {{
        const item = cases[index];
        const blob = [
          item.case_id,
          item.report_title,
          item.strategy_subtype,
          item.quality_tier,
          item.institution?.name,
          item.candidate_query?.query,
        ].join(' ').toLowerCase();
        return !q || blob.includes(q);
      }});
      currentPos = 0;
      rebuildSelect();
    }});
    $('copyBtn').addEventListener('click', async () => {{
      const item = cases[filtered[currentPos]];
      await navigator.clipboard.writeText(JSON.stringify(item, null, 2));
      $('copyBtn').textContent = '已复制';
      setTimeout(() => $('copyBtn').textContent = '复制 JSON', 1100);
    }});

    rebuildSelect();
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an HTML dashboard for extracted strategy-report metadata.")
    parser.add_argument("--cases", default="dataset_build/meta_extraction_smoke6_combined.jsonl")
    parser.add_argument("--out", default="dataset_build/meta_extraction_dashboard.html")
    parser.add_argument("--title", default="Strategy Report Meta Extraction Review")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_path = Path(args.out)
    base_dir = out_path.parent
    cases = enrich_cases(load_cases(Path(args.cases)), base_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_html(cases, args.title), encoding="utf-8")
    print(f"Wrote {out_path} with {len(cases)} cases")


if __name__ == "__main__":
    main()
