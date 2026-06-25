# 策略研究报告信源扩充实验报告

生成时间：2026-06-08

本轮目标是先扩充“策略研究”报告的公开爬取池，暂不进入 LLM metadata extraction。方法是基于已调研的头部金融机构官网入口，进一步定位可稳定发现报告的栏目页、专题页、PDF 资产路径，并用脚本逐个验证。

## 产物位置

- 扩展信源配置：`dataset_tools/strategy_reports/sources.expanded.json`
- 信源探测脚本：`dataset_tools/strategy_reports/discover_report_sources.py`
- 机器探测结果：`dataset_build/source_discovery_report.json`

复跑命令：

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/discover_report_sources.py --config dataset_tools/strategy_reports/sources.expanded.json --out dataset_build/source_discovery_report.json --max-child-pages 4 --request-timeout 10
```

## 方法说明

本轮对每家机构使用三类入口：

- 官方研究栏目页：如 insights、research and commentary、global market outlook。
- 策略专题页：如 investment outlook、mid-year outlook、weekly commentary、global market outlook。
- PDF 资产路径：如 `/literature/whitepaper/`、`/content/dam/`、`/cms-assets/`、`/library-content/assets/pdf/`。

脚本会识别两类候选：

- `PDF`：可直接下载或从栏目页发现的研究 PDF。
- `HTML`：策略报告或市场观点网页。部分机构以网页文章为主，这类需要后续转 PDF、转 markdown 或直接抽正文。

为了贴近“策略研究”垂直场景，脚本已加入第一层过滤：

- 保留信号：`outlook`、`market`、`macro`、`strategy`、`investment`、`portfolio`、`fixed income`、`equity`、`alternatives`、`research`、`perspectives`、`vemo`、`eotm` 等。
- 剔除噪声：社交分享链接、登录页、订阅管理页、法律文档、投资者权利声明、现代奴隶制声明、目标市场声明、税务策略、性别薪酬报告等。

注意：表中的“机器发现量”仍是粗估。HTML 页容易包含区域镜像、导航页、产品入口和观点短文，因此我同时给出“建议可采量”，作为更接近真实策略报告样本池的人工校正范围。

## 汇总估算

| 信源 | 成功访问情况 | PDF 候选 | HTML 候选 | 机器发现量 | 建议可采量 | 优先级 |
|---|---:|---:|---:|---:|---:|---|
| J.P. Morgan Private Bank / Wealth Management | 5/8 | 23 | 222 | 245 | 40-80 | 高 |
| BlackRock Investment Institute | 4/6 | 4 | 30 | 34 | 15-25 | 高 |
| Goldman Sachs Asset Management | 8/10 | 4 | 26 | 30 | 18-25 | 高 |
| Fidelity International / Fidelity UK | 4/6 | 2 | 33 | 35 | 12-25 | 中 |
| Vanguard | 4/8 | 12 | 11 | 23 | 15-20 | 中 |
| State Street Global Advisors / State Street Investment Management | 7/9 | 2 | 15 | 17 | 10-15 | 中 |
| Morgan Stanley | 3/7 | 2 | 15 | 17 | 8-15 | 中 |

当前扩展池机器发现合计约 `401` 个 report-like 条目；经人工校正后，建议视为约 `118-205` 个策略研究候选。这个规模已经能支撑下一步从中筛出 `20-50` 个 golden-set 任务。

## 中文券商补充

`generation_test/strategy_research_samples/README.md` 中提到的中文头部券商已经单独摸底，详见 `strategy_report_source_expansion_china_report.md`。本轮覆盖中金公司、中信证券、华泰证券、国泰海通、广发证券、招商证券。

简要结论：

| 中文信源层级 | 覆盖机构 | 机器发现量 | 建议可采量 | 判断 |
|---|---:|---:|---:|---|
| 官方入口 | 6 | 7 | 0-4 | 官网多为研究品牌/业务页，几乎不直接暴露策略 PDF |
| 第三方公开入口 | 6 | 45 | 17-33 | 可发现 PDF 或研报详情页，但需版权、来源、去重和质量核验 |

中文公司不是缺失，而是分发链路不同：英文资管更适合直接抓官方 PDF；中文券商完整策略研报更多经由第三方研报库流转。因此中文样本应作为单独 bucket 纳入 golden set，并额外记录 `source_platform`、`mirror_url`、`copyright_note` 和 `access_stability`。

## 分信源结论

### BlackRock Investment Institute

主要入口：

- https://www.blackrock.com/corporate/insights/blackrock-investment-institute
- https://www.blackrock.com/corporate/insights/blackrock-investment-institute/publications/outlook
- https://www.blackrock.com/corporate/insights/blackrock-investment-institute/publications/investment-perspective
- https://www.blackrock.com/corporate/insights/blackrock-investment-institute/publications/weekly-commentary

样例 PDF：

- https://www.blackrock.com/corporate/literature/whitepaper/bii-global-outlook-in-charts.pdf
- https://www.blackrock.com/corporate/literature/whitepaper/bii-investment-perspectives-us-policy-march-2025.pdf

判断：质量高，栏目结构清晰，BII 的 outlook、weekly commentary、investment perspectives 非常贴近策略报告定义。网页与 PDF 同时存在，适合作为“年度/季度展望”“周度市场评论”“专题策略”三类样本源。

### Goldman Sachs Asset Management

主要入口：

- https://am.gs.com/en-us/institutions/insights
- https://am.gs.com/en-us/institutions/insights/article/investment-outlook
- https://am.gs.com/en-us/institutions/insights/article/investment-outlook/public-markets-2026
- https://am.gs.com/en-us/institutions/insights/article/investment-outlook/portfolio-construction-2026

样例 PDF：

- https://am.gs.com/cms-assets/gsam-app/documents/insights/en/2025/Investment-Outlook-2026.pdf
- https://am.gs.com/cms-assets/gsam-app/documents/insights/en/2026/fixed-income-outlook_2q26.pdf?view=true

判断：质量高，专题拆分很适合构造细分 query，例如宏观背景、公开市场、另类资产、组合构建、主题投资。部分 PDF 是视频 transcript 或短材料，筛选时需按页数和正文密度过滤。

### J.P. Morgan Private Bank / Wealth Management

主要入口：

- https://privatebank.jpmorgan.com/nam/en/insights
- https://privatebank.jpmorgan.com/nam/en/insights/latest-and-featured/outlook-b
- https://privatebank.jpmorgan.com/nam/en/insights/latest-and-featured/mid-year-outlook
- https://privatebank.jpmorgan.com/nam/en/insights/latest-and-featured/eotm/outlook

样例 PDF：

- https://assets.jpmprivatebank.com/content/dam/jpm-pb-aem/global/en/documents/2026-mid-year-outlook/2026-mid-year-outlook.pdf
- https://privatebank.jpmorgan.com/content/dam/jpm-pb-aem/global/en/documents/outlook2026/JPMorganOutlook2026PromiseandPressure.pdf
- https://privatebank.jpmorgan.com/content/dam/jpm-pb-aem/global/en/documents/eotm/smothering-heights.pdf

判断：可采量最大，尤其是 `Eye on the Market`、年度展望、年中展望。机器发现量高达 245，主要因为地区镜像和专题内链非常多；后续必须去重 URL、剔除地区重复版、按 PDF 指纹或标题归并。

### Morgan Stanley

主要入口：

- https://www.morganstanley.com/ideas
- https://www.morganstanley.com/insights/articles/stock-market-outlook-2026
- https://www.morganstanley.com/insights/articles/investment-outlook-midyear-2026
- https://www.morganstanley.com/im/en-us/institutional-investor/insights/all-insights.html

样例 PDF：

- https://www.morganstanley.com/content/dam/msdotcom/en/assets/pdfs/IB_MA-2026-Outlook.pdf
- https://www.morganstanley.com/content/dam/msdotcom/en/assets/pdfs/Navigating_the_Next_Decade-10_Demand_Signals_for_the_Next_10_Years_of_Sustainable_Finance.pdf

判断：策略观点质量高，但公开站点更偏网页文章，部分 institutional investor 页面返回 403 或慢响应。适合作为 M&A outlook、市场展望、可持续金融长期主题的补充信源，不建议作为批量 PDF 主力。

### Vanguard

主要入口：

- https://corporate.vanguard.com/content/corporatesite/us/en/corp/what-we-think/research-and-commentary.html
- https://advisors.vanguard.com/insights/article/2026-economic-and-market-outlook
- https://corporate.vanguard.com/content/corporatesite/us/en/corp/vemo/vemo-return-forecasts.html
- https://corporate.vanguard.com/content/corporatesite/us/en/corp/articles/active-fixed-income-perspectives-q2-2026-dispersion-drives-opportunity.html

样例 PDF：

- https://corporate.vanguard.com/content/dam/corp/research/pdf/isg_vemo_2026.pdf
- https://advisors.vanguard.com/content/dam/fas/pdfs/ISGVEMO.pdf
- https://corporate.vanguard.com/content/dam/corp/articles/pdf/afi_perspectives_q22026_income_in_focus.pdf

判断：PDF 质量稳定，宏观与长期资本市场假设类材料突出，适合做“长期预期/资产配置/固定收益展望”样本。部分页面 404 或区域权限不稳定，但 `/content/dam/corp/research/pdf/` 资产路径很有价值。

### Fidelity International / Fidelity UK

主要入口：

- https://www.fidelityinternational.com/editorial/outlook/
- https://www.fidelityinternational.com/editorial/article/fidelity-international-midyear-outlook-a-global-rewiring-651ac8-en5/
- https://www.fidelity.co.uk/markets-insights/markets/global/investment-outlook/
- https://www.fidelity.co.uk/markets-insights/markets/global/the-four-strategies-for-investing-in-2026

样例 PDF：

- https://www.fidelityinternational.com/static/master/media/pdf/outlook/Fidelity-International-Outlook-2026.pdf
- https://www.fidelity.co.uk/media/pi/pdfs/investment-outlook/investment-outlook-q2-2026.pdf

判断：年度/季度 outlook 适合采样，但 UK 零售站点会混入大量个人理财和基金导购文章。后续应优先 Fidelity International 的 outlook 专题，再少量采 Fidelity UK 的 global investment outlook。

### State Street Global Advisors / State Street Investment Management

主要入口：

- https://www.ssga.com/insights/global-market-outlook
- https://www.ssga.com/insights/gmo-macroeconomic-outlook
- https://www.ssga.com/insights/gmo-equity-outlook
- https://www.ssga.com/insights/gmo-fixed-income-outlook
- https://www.ssga.com/is/en_gb/institutional/insights/gmo-implementation-guide

样例 PDF：

- https://www.ssga.com/library-content/assets/pdf/global/global-market-outlook/2026/global-market-outlook-2026.pdf
- https://www.ssga.com/library-content/assets/pdf/global/global-market-outlook/2026/gmo-implementation-guide-2026.pdf

判断：结构非常规范，Global Market Outlook 系列可以拆成宏观、权益、固收、另类、实施指南等子任务。可采量不算最大，但质量/格式稳定，适合作为 benchmark 风格模板。

## 下一步建议

优先级顺序：

1. 批量下载：先抓 J.P. Morgan、BlackRock、Goldman Sachs、Vanguard、State Street 的 PDF 候选和高质量 HTML。
2. 去重归并：按规范化 URL、标题、PDF hash、报告标题和发布日期去重，尤其是 J.P. Morgan 地区镜像。
3. 二次筛选：用页数、正文长度、策略关键词密度、图表/表格数量、报告类型标签打分。
4. 样本分桶：年度展望、年中/季度展望、周度/月度评论、资产配置、主题策略、行业/并购专题、长期资本市场假设。
5. 再进入 metadata extraction：对 A/B 级候选做 `pdf -> structured meta info json`，不要对粗池直接调 LLM。

## 风险和限制

- 本次估算不是全站 sitemap 抓取，只覆盖 `sources.expanded.json` 中配置的公开入口。
- 有些机构用 JS 渲染和区域跳转，纯 requests 可能漏掉页面；必要时可为少数高价值站点加 Playwright 发现器。
- HTML 候选不能直接等同 PDF 财报，需要后续保存正文、截图或转 PDF。
- 报告下载和使用需要遵守各机构公开网站条款；本项目应保留来源 URL、访问日期和版权/免责声明信息。

---

## 2026-06-10 Update: Chinese Eastmoney Strategy API Expansion

The Chinese source expansion has materially changed after inspecting `chinese_report_source_example.txt.txt`. We now have a dedicated Eastmoney strategy-report API source rather than relying only on broker official pages and third-party HTML detail pages.

Source:

- API: `https://reportapi.eastmoney.com/report/dg`
- Required category: `qType=2`
- Required returned type: `columnType=策略报告`
- Required report type: `reportType=4`
- PDF URL rule: `https://pdf.dfcfw.com/pdf/H3_{infoCode}_1.pdf`
- Dedicated crawler: `dataset_tools/strategy_reports/crawl_eastmoney_strategy_reports.py`
- Source note/config: `dataset_tools/strategy_reports/sources.eastmoney_strategy_api.json`

Successful crawl:

| Metric | Value |
| --- | ---: |
| Downloaded strategy PDFs | 150 |
| Failed/non-PDF | 0 |
| Date range observed | 2026-05-21 to 2026-06-10 |
| Output directory | `dataset_build/raw_pdfs/strategy_research/eastmoney-strategy-reports/` |
| Manifest | `dataset_build/manifests/eastmoney_strategy_download_manifest.jsonl` |
| Screening manifest | `dataset_build/manifests/eastmoney_strategy_screening_manifest.jsonl` |

Screening result:

| Tier | Count |
| --- | ---: |
| A | 32 |
| B | 99 |
| C | 19 |
| Reject | 0 |

Impact on source pool:

- Previous Chinese discovery found only a small number of direct PDFs and many fragile HTML/detail pages.
- Eastmoney now provides a large, type-labeled Chinese strategy-report PDF pool.
- This source should be treated as `china_eastmoney_strategy_api`, not mixed into official broker sources.
- Downstream metadata should preserve `source_platform=Eastmoney`, `org_short_name`, `info_code`, `pdf_url`, and `needs_human_source_verification=true`.
- For golden-set construction, select from A/B-tier reports and prefer annual/midyear strategy, asset allocation, A-share strategy, BSE/北交所 strategy, macro strategy, and industry/thematic strategy. Short daily market comments should be deprioritized despite being API-labeled as strategy reports.
