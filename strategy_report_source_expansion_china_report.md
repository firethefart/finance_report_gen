# 中文券商策略研究信源摸底报告

生成时间：2026-06-08

本轮回应 `generation_test/strategy_research_samples/README.md` 中“中文头部券商入口观察”的问题：此前英文信源池没有覆盖中文公司。现已单独对中金公司、中信证券、华泰证券、国泰海通、广发证券、招商证券做了两层摸底。

## 产物位置

- 中文官方入口配置：`dataset_tools/strategy_reports/sources.china.json`
- 中文第三方样例配置：`dataset_tools/strategy_reports/sources.china.thirdparty.json`
- 官方入口探测结果：`dataset_build/source_discovery_report_china.json`
- 第三方入口探测结果：`dataset_build/source_discovery_report_china_thirdparty.json`

复跑命令：

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/discover_report_sources.py --config dataset_tools/strategy_reports/sources.china.json --out dataset_build/source_discovery_report_china.json --max-child-pages 4 --request-timeout 10
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/discover_report_sources.py --config dataset_tools/strategy_reports/sources.china.thirdparty.json --out dataset_build/source_discovery_report_china_thirdparty.json --max-child-pages 4 --request-timeout 10
```

## 口径说明

中文券商和英文资管机构的公开分发方式明显不同：

- 英文机构常把年度展望、季度展望、市场评论作为公开 PDF 或网页专题发布。
- 中文券商官网通常展示研究品牌、研究服务入口或资讯摘要；完整研报 PDF 更多在 Wind、Choice、东方财富研报库、慧博、萝卜投研、发现报告、上调研报、BigQuant、行业报告库等第三方平台流转。
- 因此中文池必须分成两层：`official` 与 `third_party_mirror`。后者只能用于摸底和少量样例，不应默认作为长期稳定、版权清晰的数据源。

脚本已补充中文关键词：`策略`、`研究`、`研报`、`年度策略`、`中期策略`、`投资策略`、`市场策略`、`宏观策略`、`行业比较`、`资产配置`、`大类资产`、`展望` 等。

## 官方入口探测结果

| 机构 | 测试 URL | 状态概览 | PDF 候选 | HTML 候选 | 机器发现量 | 判断 |
|---|---:|---|---:|---:|---:|---|
| 中金公司研究 | 4 | 1 个 200，3 个 521 | 0 | 0 | 0 | 官网/研究入口可达性弱，完整 PDF 不开放 |
| 中信证券研究 | 4 | 4 个 200 | 0 | 0 | 0 | 页面可达，但 requests 未发现公开 PDF/报告页 |
| 华泰证券研究 | 4 | 2 个 200，2 个 404 | 0 | 3 | 3 | 主要是官网/疑似研究入口，非稳定 PDF 源 |
| 国泰海通证券研究 | 4 | 4 个 SSL 失败 | 0 | 0 | 0 | 旧 TLS/站点兼容问题，需浏览器或特殊 TLS 处理 |
| 广发证券研究 | 4 | 4 个 200 | 0 | 4 | 4 | 研究业务页可达，但未发现 PDF |
| 招商证券研究 | 4 | 3 个 200，1 个 404 | 0 | 0 | 0 | 官网入口可达，未暴露策略报告资产 |

结论：以“官网 requests 直接抓取”为口径，中文券商官方源几乎不能支撑批量 PDF 爬取。建议官方源只作为机构归属、研究品牌和合规来源记录，不作为主要下载池。

## 第三方公开入口探测结果

| 机构 | 测试 URL | PDF 候选 | HTML 候选 | 机器发现量 | 建议可采量 | 备注 |
|---|---:|---:|---:|---:|---:|---|
| 中金公司研究 | 5 | 0 | 5 | 5 | 3-5 | BigQuant 页面可访问，偏 HTML 摘要/转载 |
| 中信证券研究 | 2 | 1 | 4 | 5 | 2-4 | 东方财富 PDF 可作为直连样例；慧博页可发现相关入口 |
| 华泰证券研究 | 3 | 1 | 6 | 7 | 3-6 | 上调研报/慧博/期货研报库均有样例 |
| 国泰海通证券研究 | 5 | 2 | 2 | 4 | 2-4 | 东方财富 PDF 和 BigQuant 页面可用 |
| 广发证券研究 | 3 | 0 | 5 | 5 | 2-4 | 多为网页转存，需进一步确认下载能力 |
| 招商证券研究 | 2 | 0 | 19 | 19 | 5-10 | DCBBS 可发现大量相关研究页，但噪声和跨机构混入较多 |

第三方样例层合计发现 `45` 个 report-like 条目，其中直连 PDF `4` 个、HTML/转载详情页 `41` 个。经人工校正后，保守建议可采量约 `17-33` 个。

## 分机构观察

### 中金公司研究

官方入口：

- https://www.cicc.com/
- https://research.cicc.com/

第三方样例：

- https://bigquant.com/square/paper/40febfb0-32e4-421b-835a-823ae4e6641e
- https://bigquant.com/square/paper/b278120a-5d04-401b-93cb-8206dad8e605

判断：中金研究质量很高，但官网对自动化抓取不友好；BigQuant 等平台能找到转载页面，适合做少量中文风格学习样例，不适合作为主力批量源。

### 中信证券研究

官方入口：

- https://www.citics.com/
- https://research.citics.com/rpt

第三方样例：

- https://www.fhyanbao.com/rpview/1664388
- https://pdf.dfcfw.com/pdf/H3_AP202504221660527858_1.pdf?1745342200000.pdf=

判断：官方研究入口能打开，但没有直接暴露报告列表或 PDF。东方财富 PDF 直连对下载更友好，可作为中文券商 PDF 样例池的一部分，但需要记录转载来源。

### 华泰证券研究

官方入口：

- https://www.htsc.com.cn/
- https://crm.htsc.com.cn/

第三方样例：

- https://www.sdyanbao.com/detail/893924
- https://www.fhyanbao.com/rpview/1642640
- https://yb.1qh.cn/reports/2024-11-13/be15f4dcb12629593621c9e5ea82825e4ba0fba0.pdf

判断：华泰研究内容体系值得学习，但官方直接下载入口有限。第三方样例中有较明确的宏观策略/资产配置报告，适合先收少量样例。

### 国泰海通证券研究

官方入口：

- https://www.gtht.com/
- https://www.gtja.com/
- https://www.htsec.com/

第三方样例：

- https://bigquant.com/square/paper/fcd70f9d-4ea4-44d3-acd1-6bb40b13d16e
- https://pdf.dfcfw.com/pdf/H3_AP202506291699633466_1.pdf
- https://pdf.dfcfw.com/pdf/H3_AP202512291810673339_1.pdf?1767081159000.pdf=

判断：官方站点在当前 requests 环境下报 `unsafe legacy renegotiation disabled`，需要浏览器或 TLS 兼容方案。第三方直连 PDF 有一定可用性。

### 广发证券研究

官方入口：

- https://www.gf.com.cn/
- https://www.gf.com.cn/business/research

第三方样例：

- https://www.sdyanbao.com/detail/840821
- https://www.nxny.com/report/view_5986030.html
- https://max.book118.com/html/2025/0219/7135033063010036.shtm

判断：官网研究业务页可达，但未发现 PDF。第三方页面可作为摸底线索，但网页转存、跨机构相关推荐和下载权限噪声明显，需要严格筛选。

### 招商证券研究

官方入口：

- https://www.cmschina.com/
- https://www.cmschina.com/yf.html
- https://www.newone.com.cn/

第三方样例：

- https://www.dcbbs.com/p-227592.html
- https://www.nxny.com/report/view_5858858.html

判断：第三方入口数量看起来最多，但 DCBBS 这类库会混入大量房地产、宏观、其他机构报告，不能按机构名直接相信。适合作为“发现候选”的入口，不适合无筛选批量下载。

## 对测试集构建的建议

中文策略研究应加入 golden set，但建议采用更保守的构建方式：

1. 第一批只取 `6-10` 份中文策略报告，不要一上来追求 50 份中文样本。
2. 优先选择可直连 PDF 的东方财富、期货研报库等样例；网页转载页只在正文完整、来源清楚时使用。
3. 每个中文样本必须额外记录 `source_platform`、`original_institution`、`mirror_url`、`copyright_note`、`access_stability`。
4. 中文样本分桶建议覆盖：A 股年度/中期策略、宏观策略、行业比较、主题策略、政策策略。
5. 对中文第三方源设置更严格筛选：报告标题必须含机构名或 PDF 首页可验证机构；正文/首页必须能看到发布日期、分析师或研究团队；下载文件需要 hash 去重。

## 总体判断

中文公司不是没有，而是公开分发链路更绕。英文池适合“稳定公开 PDF + 官方网页专题”的自动化批量抓取；中文池更适合“第三方发现 + 小批量人工核验 + 严格来源标注”。若本项目要评估中文策略报告生成能力，建议把中文样本作为单独 bucket 纳入，而不是和英文资管样本混在一个下载口径里。

---

## 2026-06-10 Update: Eastmoney API Replaces Sparse Chinese Discovery Path

此前中文券商源偏少，主要原因是我们只做了官网入口和第三方详情页 discovery，没有使用东方财富研报库的分类 API。根据 `chinese_report_source_example.txt.txt`，已确认东方财富公开接口可按报告类型直接拉取策略报告：

- API: `https://reportapi.eastmoney.com/report/dg`
- 策略研究/策略报告分类：`qType=2`
- 返回字段校验：`columnType=策略报告`
- 报告类型字段：`reportType=4`
- PDF 下载规则：`https://pdf.dfcfw.com/pdf/H3_{infoCode}_1.pdf`

新增文件：

- `dataset_tools/strategy_reports/crawl_eastmoney_strategy_reports.py`
- `dataset_tools/strategy_reports/sources.eastmoney_strategy_api.json`
- `dataset_build/manifests/eastmoney_strategy_download_manifest.jsonl`
- `dataset_build/manifests/eastmoney_strategy_list_items.jsonl`
- `dataset_build/manifests/eastmoney_strategy_screening_manifest.jsonl`
- `dataset_build/manifests/eastmoney_strategy_summary.json`

最新补爬结果：

| 指标 | 数值 |
| --- | ---: |
| 目标 | 只抓取东方财富 `qType=2` 策略报告 |
| 下载 PDF | 150 |
| 失败/非 PDF | 0 |
| 发布日期范围 | 2026-05-21 至 2026-06-10 |
| 初筛 A/B/C | A=32, B=99, C=19 |
| Reject | 0 |

Top contributing institutions in this run:

| 机构简称 | 数量 |
| --- | ---: |
| 东吴证券 | 21 |
| 开源证券 | 20 |
| 国信证券 | 15 |
| 中山证券 | 13 |
| 华源证券 | 10 |
| 国金证券 | 7 |
| 华宝证券 | 6 |
| 中银证券 | 6 |

重要判断：

1. 中文策略报告候选池已经从“少量 PDF + 若干详情页”升级为可稳定批量补爬。
2. 东方财富 API 是当前中文策略报告 PDF 的主力源；官网入口仍主要用于机构归属和来源解释。
3. 该源是第三方镜像，进入 golden set 前必须保留原券商、东方财富平台、PDF URL 和人工来源核验标记。
4. 虽然 API 类型为策略报告，但其中仍混有短篇市场点评/每日类报告；构建 golden set 时应优先挑 A/B 档、页数充足、标题明确的年度/中期/资产配置/宏观/A股/行业主题策略。

推荐复跑命令：

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/crawl_eastmoney_strategy_reports.py `
  --limit 150 `
  --page-size 50 `
  --max-pages 30 `
  --out dataset_build `
  --reset-manifest
```

推荐初筛命令：

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/screen_reports.py `
  --manifest dataset_build/manifests/eastmoney_strategy_download_manifest.jsonl `
  --out dataset_build/manifests/eastmoney_strategy_screening_manifest.jsonl `
  --reset-manifest
```
