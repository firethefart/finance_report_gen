# 策略报告测试集构建计划

目标：先构建 20-50 个高质量策略报告 golden-set case，为后续自动化评测、人类评审和 skill iteration 提供稳定基准。

## 1. 两阶段路线

### Phase 1: 收集与筛选真实策略报告

从头部金融机构公开来源收集 100-200 份策略研究 PDF，覆盖不同机构、地区、资产类别、主题和报告形态。然后按质量和类型筛选出候选样本。

### Phase 2: PDF -> Meta JSON 提取

使用 `strategy-report-metadata-extraction` skill，将候选 PDF 转换为结构化 metadata JSON：

- query
- expected report type
- source pack
- key facts
- must-have sections
- prohibited mistakes
- reference reports or human notes
- quality tier
- extraction confidence

## 2. Phase 1 报告来源池

优先机构：

| 机构 | 报告类型 | 获取方式 |
| --- | --- | --- |
| BlackRock Investment Institute | weekly commentary, global outlook, thematic strategy | 官方 insights / literature PDF |
| Goldman Sachs Asset Management | annual outlook, quarterly outlook, fixed income outlook | 官方 insights PDF |
| J.P. Morgan Private Bank / Wealth Management | annual outlook, midyear outlook, Eye on the Market | 官方 PDF |
| Morgan Stanley | capital markets, M&A outlook, thematic research | 官方 insights PDF |
| Vanguard | economic and market outlook, long-term outlook | 官方 research PDF |
| Fidelity International | annual outlook, quarterly outlook, sector/theme outlook | 官方 outlook PDF |
| State Street Global Advisors | global market outlook, implementation guide | 官方 insights PDF |
| UBS / Citi / BofA / Schwab / Invesco 等 | outlook and market strategy | 视公开下载稳定性补充 |
| 中文头部券商 | 年度策略、A 股策略、行业比较、主题策略 | 官方公开页优先，第三方研报库需标注权限和稳定性 |

## 3. 目标分桶

最终 20-50 个 golden-set case 建议覆盖：

| 分桶 | 目标数量 | 说明 |
| --- | ---: | --- |
| annual / midyear outlook | 5-8 | 学习完整年度策略结构 |
| quarterly / monthly outlook | 3-5 | 学习中篇市场展望 |
| weekly commentary | 3-5 | 学习短篇高密度观点 |
| thematic strategy | 4-8 | AI、新能源、并购、地缘、通胀等 |
| sector strategy | 3-6 | 行业格局、产业链、盈利周期 |
| asset allocation / cross-asset | 3-6 | 股票、债券、现金、另类资产配置 |
| macro / rates / credit strategy | 2-5 | 利率、信用、汇率、通胀 |
| capital markets / M&A strategy | 2-4 | 并购、IPO、资本市场活动 |
| implementation guide | 2-4 | 观点如何落到组合或工具 |

## 4. 初筛质量标准

抓取 100-200 份后，先给每份 PDF 打 `A/B/C/Reject`。

### A 级

- 明确策略 thesis。
- 有专业结构和执行摘要。
- 证据、图表、来源较完整。
- 有情景、风险或反证意识。
- 版式和图表值得学习。
- 适合进入 20-50 golden set。

### B 级

- 专业可用，但某些方面偏弱。
- 可作为补充样本或自动化训练样本。

### C 级

- 太短、太营销、证据弱、图表少、结构普通。
- 暂不进入 golden set，但可用于负样本或边界样本。

### Reject

- 非策略研究。
- 无法解析。
- 链接不稳定或疑似登录页。
- 版权/权限明显不适合作为样本。

## 5. 爬取与存档建议

建议目录：

```text
dataset_build/
  raw_pdfs/
    blackrock/
    goldman_sachs_am/
    jpmorgan/
    vanguard/
    fidelity/
    state_street/
    morgan_stanley/
  manifests/
    download_manifest.jsonl
    screening_manifest.jsonl
  extracted_meta/
    candidate_cases.jsonl
  golden_cases/
    case_0001.json
```

每份下载记录至少保存：

- institution
- title
- URL
- download date
- file path
- file size
- HTTP status
- PDF header check
- SHA256
- guessed subtype
- parse status

## 6. Phase 2 提取工序

对每份 A/B 候选 PDF 使用：

[strategy-report-metadata-extraction/SKILL.md](strategy-report-metadata-extraction/SKILL.md)

输出一个结构化 JSON。提取完成后进行三类 QA：

1. JSON schema QA：字段是否完整、JSON 是否有效。
2. Evidence QA：key facts 是否有来源、forecast 是否被标注。
3. Benchmark QA：candidate_query 是否自然、must-have sections 是否可评估、prohibited mistakes 是否具体。

## 7. 第一批推荐样本策略

为了快速形成可用 golden set，第一批建议先选 20 个：

- 8 个英文头部机构年度/中期/季度展望。
- 4 个 weekly commentary。
- 4 个 thematic strategy。
- 2 个 capital markets / M&A strategy。
- 2 个中文策略报告或中文市场主题报告。

这样能先覆盖结构完整报告、短报告、主题报告和中文场景，再逐步扩到 50 个。

## 8. 关键风险

- PDF 解析失败：需要 OCR 或人工降级。
- 官方链接变化：必须保存 PDF 本地副本和下载 manifest。
- 报告版权：只用于内部评测构建，不在输出中长篇复制原文。
- 同质化：年度展望容易重复，需要控制同机构同类型数量。
- query 反推过拟合：candidate query 不能泄露报告完整答案。
- meta 提取漂移：需要用固定 schema 和人工抽检反复打磨。

