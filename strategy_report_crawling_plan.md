# 策略研究报告 100-150 份爬取计划

生成时间：2026-06-08

目标：基于现有中外信源摸底结果，爬取 `100-150` 份顶端质量的“策略研究”类报告候选，并完成本地分类储存、基础元信息保存和后续筛选入口建设。

## 1. 当前信源基础

现有三类 discovery 结果：

| 信源池 | 文件 | PDF 候选 | HTML 候选 | 机器发现量 | 定位 |
|---|---|---:|---:|---:|---|
| 全球官方公开源 | `dataset_build/source_discovery_report.json` | 49 | 352 | 401 | 主力来源，质量和版权边界最好 |
| 中文券商官方源 | `dataset_build/source_discovery_report_china.json` | 0 | 7 | 7 | 仅作官方归属和研究品牌记录 |
| 中文第三方公开源 | `dataset_build/source_discovery_report_china_thirdparty.json` | 4 | 41 | 45 | 中文样本补充，必须严格标注转载来源 |

结论：纯 PDF 候选约 `53` 份，无法独立达到 `100-150`。本轮爬取必须采用 `PDF + HTML 报告页归档` 的混合策略，再通过筛选脚本选出顶端质量样本。

## 2. 爬取目标配额

建议先构建 `130-160` 个原始候选，经过筛选后保留 `100-150` 个高质量候选。

| 来源 | 原始候选目标 | 预期高质量保留 | 说明 |
|---|---:|---:|---|
| 全球官方 PDF | 45-50 | 35-45 | 优先抓完，质量最高 |
| 全球官方 HTML 报告页 | 70-90 | 45-65 | J.P. Morgan、BlackRock、GSAM、Fidelity 等网页报告 |
| 中文第三方 PDF | 4-8 | 3-5 | 东方财富、期货研报库等直连 PDF 优先 |
| 中文第三方 HTML/转载页 | 20-30 | 10-20 | 只保留来源、标题、机构可核验者 |
| 中文官方 HTML | 0-7 | 0-3 | 主要用于记录入口，不强求纳入训练样本 |

最终 golden-set 构建时不需要全部使用，目标是从这些候选中提取 `20-50` 个高质量任务。

## 3. 报告类型分桶

本地储存和筛选均按 `subtype_hint` 分桶：

| 分桶 | 目标数量 | 典型来源 |
|---|---:|---|
| `annual_or_periodic_outlook` | 35-45 | BlackRock、GSAM、JPM、Vanguard、Fidelity、SSGA |
| `midyear_outlook` | 8-12 | JPM、Fidelity、中文券商中期策略 |
| `weekly` / `monthly_commentary` | 10-20 | BlackRock weekly、JPM Eye on the Market |
| `asset_allocation` | 15-25 | GSAM portfolio construction、Vanguard、SSGA implementation |
| `macro_strategy` | 10-20 | JPM、CICC/华泰/中信第三方样例 |
| `equity_strategy` | 8-15 | 中文 A 股策略、Morgan Stanley、SSGA equity outlook |
| `fixed_income` | 8-12 | GSAM fixed income、Vanguard fixed income、SSGA fixed income |
| `thematic_strategy` | 10-20 | AI、并购、可持续金融、新能源、政策主题 |
| `m_and_a` | 2-5 | Morgan Stanley IB/M&A outlook、中文并购主题 |

## 4. 本地目录规范

推荐输出根目录仍使用 `dataset_build/`，但按格式和类型进一步组织：

```text
dataset_build/
  raw_pdfs/
    annual_or_periodic_outlook/
      blackrock-investment-institute/
        ...
    asset_allocation/
      goldman-sachs-asset-management/
        ...
  raw_html/
    annual_or_periodic_outlook/
      j-p-morgan-private-bank-wealth-management/
        ...
    macro_strategy/
      cicc-research-third-party-mirrors/
        ...
  manifests/
    download_manifest.jsonl
    html_archive_manifest.jsonl
    screening_manifest.jsonl
  extracted_meta/
    candidate_cases.jsonl
```

PDF 下载脚本已支持 `--organize-by-subtype`，会按 `raw_pdfs/<subtype>/<institution>/` 落盘。

HTML 归档脚本会按 `raw_html/<subtype>/<institution>/` 保存页面快照，并写入 manifest。

## 5. 基本元信息字段

每条下载/归档记录至少保存：

| 字段 | 说明 |
|---|---|
| `institution` | 机构名 |
| `business_type` | 机构/来源类型，如 asset_manager、private_bank、broker_research_third_party |
| `country_or_region` | 地区 |
| `subtype_hint` | 报告类型初判 |
| `source_bucket` | `global_official`、`china_official`、`china_third_party` |
| `source_url` / `discovered_from` | 发现来源 |
| `pdf_url` / `url` | 实际下载或归档 URL |
| `file_path` | 本地路径 |
| `http_status` | HTTP 状态 |
| `file_size_bytes` | 文件大小 |
| `sha256` | 去重 hash |
| `status` | downloaded、exists、archived、failed 等 |
| `downloaded_at` / `archived_at` | 时间戳 |

中文第三方源需要额外在后续 metadata 阶段补充：

- `source_platform`
- `mirror_url`
- `original_institution`
- `copyright_note`
- `access_stability`
- `needs_human_source_verification`

## 6. 执行命令

### 6.1 生成 PDF 下载清单

已生成：

```text
dataset_tools/strategy_reports/sources.crawl_batch_100_150_pdfs.json
```

复跑命令：

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/build_download_config_from_discovery.py `
  --discovery dataset_build/source_discovery_report.json `
  --discovery dataset_build/source_discovery_report_china_thirdparty.json `
  --source-bucket global_official `
  --source-bucket china_third_party `
  --out dataset_tools/strategy_reports/sources.crawl_batch_100_150_pdfs.json
```

当前生成 `50` 个 PDF job。

### 6.2 下载 PDF

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/download_reports.py `
  --config dataset_tools/strategy_reports/sources.crawl_batch_100_150_pdfs.json `
  --out dataset_build `
  --organize-by-subtype `
  --reset-manifest
```

如需避免覆盖旧结果，去掉 `--reset-manifest`；如需重新下载同名文件，加 `--overwrite`。

### 6.3 归档 HTML 报告页

全球官方 HTML 建议先抓每家前 `12` 个，共约 `80` 个：

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/archive_report_pages.py `
  --discovery dataset_build/source_discovery_report.json `
  --out dataset_build `
  --max-pages-per-institution 12 `
  --limit 84 `
  --reset-manifest
```

中文第三方 HTML 建议先抓 `25-35` 个：

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/archive_report_pages.py `
  --discovery dataset_build/source_discovery_report_china_thirdparty.json `
  --out dataset_build `
  --max-pages-per-institution 8 `
  --limit 35
```

### 6.4 初筛 PDF

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/screen_reports.py `
  --manifest dataset_build/manifests/download_manifest.jsonl `
  --out dataset_build/manifests/screening_manifest.jsonl `
  --reset-manifest
```

筛选目标：

- A 级：结构完整、页数/正文充分、策略类型明确。
- B 级：可用但需要人工确认。
- C/Reject：太短、非策略、合规材料、解析失败或重复。

HTML 初筛暂以 manifest + 人工抽查为主；后续可加 HTML 正文抽取和屏幕截图质量检查。

## 7. 质量控制

爬取完成后按以下顺序做质量控制：

1. 去重：按 `sha256`、规范化 URL、标题、机构、发布日期去重。
2. 类型校正：修正 `subtype_hint`，避免 transcript、合规声明、基金销售材料混入。
3. 解析质量：PDF 用 `pypdf` 检查页数和文本长度；HTML 检查正文密度、标题和来源。
4. 来源稳定性：记录 `official`、`third_party_mirror`、`requires_browser`、`unstable_tls`。
5. 中文样本复核：确认首页/标题能看到机构名、报告日期、研究团队或平台来源。
6. 样本平衡：避免 JPM/招商第三方页占比过高，单机构建议不超过最终候选的 25%。

## 8. 推荐执行顺序

1. 先跑 PDF 下载，拿到最稳定的 40-50 个样本。
2. 跑全球官方 HTML 归档，补足到 110-130 个候选。
3. 跑中文第三方 HTML/PDF，补充 15-25 个中文候选。
4. PDF 初筛，预计保留 35-45 个 A/B 级。
5. HTML 人工抽样初筛，预计保留 55-85 个。
6. 汇总形成 `100-150` 个候选池。
7. 再进入 metadata extraction，不在粗池阶段调用 LLM。

## 9. 风险

- 纯 PDF 数量不足，HTML 归档是必要补充。
- 中文第三方源版权和稳定性较弱，必须严格标注，不应与官方源混同。
- 部分英文网页含产品导航和社交链接，虽然已做噪声过滤，仍需二次筛选。
- 部分 PDF 可能是 transcript、营销材料或法规披露，需要筛选脚本和人工复核剔除。
- 大规模下载前建议控制并发和频率，避免对公开站点造成压力。

---

## 2026-06-10 Update: Eastmoney Strategy Report API Source

根据 `chinese_report_source_example.txt.txt` 暴露的信息，本轮新增并验证东方财富研报分类 API。该源有明确报告类型定义，可以只抓取“策略报告/策略研究”类型，解决此前中文源候选过少的问题。

Source details:

- List API: `https://reportapi.eastmoney.com/report/dg`
- Required category parameter: `qType=2`
- Required returned type: `columnType=策略报告`
- Required report type: `reportType=4`
- PDF URL rule: `https://pdf.dfcfw.com/pdf/H3_{infoCode}_1.pdf`
- Dedicated crawler: `dataset_tools/strategy_reports/crawl_eastmoney_strategy_reports.py`
- Source config note: `dataset_tools/strategy_reports/sources.eastmoney_strategy_api.json`

Latest run:

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/crawl_eastmoney_strategy_reports.py `
  --limit 150 `
  --page-size 50 `
  --max-pages 30 `
  --out dataset_build `
  --reset-manifest
```

Result:

| Metric | Value |
| --- | ---: |
| Requested PDFs | 150 |
| Successful PDFs | 150 |
| Failed/non-PDF | 0 |
| Observed publish date range | 2026-05-21 to 2026-06-10 |
| Output root | `dataset_build/raw_pdfs/strategy_research/eastmoney-strategy-reports/` |
| Download manifest | `dataset_build/manifests/eastmoney_strategy_download_manifest.jsonl` |
| API list manifest | `dataset_build/manifests/eastmoney_strategy_list_items.jsonl` |
| Summary JSON | `dataset_build/manifests/eastmoney_strategy_summary.json` |

Screening run:

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/screen_reports.py `
  --manifest dataset_build/manifests/eastmoney_strategy_download_manifest.jsonl `
  --out dataset_build/manifests/eastmoney_strategy_screening_manifest.jsonl `
  --reset-manifest
```

Screening result:

| Quality tier | Count |
| --- | ---: |
| A | 32 |
| B | 99 |
| C | 19 |
| Reject | 0 |

Parse quality was `good=142`, `fair=7`, `poor=1`. Page count ranged from `3` to `66`, with an average of about `14.4` pages.

Recommended next use:

1. Use `eastmoney_strategy_screening_manifest.jsonl` as the main Chinese strategy-report candidate pool.
2. Prefer A/B-tier reports with annual/midyear strategy, asset allocation, A-share strategy, BSE/北交所 strategy, macro strategy, and industry thematic strategy.
3. Deprioritize short daily/overnight market comments even if the API classifies them as strategy reports.
4. Preserve `source_platform=Eastmoney`, `org_short_name`, `info_code`, `pdf_url`, and `needs_human_source_verification=true` in downstream metadata.
