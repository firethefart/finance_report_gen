# 策略研究样例 Meta Info Extraction 框架

生成时间：2026-06-09

目标：从 `dataset_build/curated_strategy_samples_verified/` 中 38 条高质量样例提取结构化 benchmark metadata，用于后续构造 20-50 个 golden-set case。输出应符合 `strategy-report-metadata-extraction/references/metadata-schema.md`，核心字段包括 `query`、`expected_report_type`、`source_pack`、`key_facts`、`must_have_sections`、`prohibited_mistakes`、`reference_notes`。

## 1. 模型分工

根据当前模型定位：

| 模型 | 用途 | 适合环节 |
|---|---|---|
| `deepseek/deepseek-v4-flash` | token 消耗量大的场景 | 长文初读、章节抽取、候选事实初筛、HTML 正文压缩、批量低成本分类 |
| `deepseek/deepseek-v4-pro` | 推理和精度要求高的场景 | 最终 metadata 生成、事实/预测边界判断、must-have sections、prohibited mistakes、query 设计、QA 修复 |
| `qwen/qwen3-vl-235b-a22b-instruct` | 视觉能力 | PDF 页面截图、图表/表格识别、版式风格、图表学习点、扫描型/图片型 PDF 补充理解 |

原则：Flash 做“候选提取和压缩”，Pro 做“决策与最终结构化”，VL 只在视觉信息真正有价值或文本解析不足时调用。

## 2. 输入资产

主输入：

- `dataset_build/curated_strategy_samples_verified/metadata.jsonl`
- `dataset_build/curated_strategy_samples_verified/<subtype>/<format>/*`

辅助输入：

- `strategy-report-metadata-extraction/SKILL.md`
- `strategy-report-metadata-extraction/references/metadata-schema.md`
- `dataset_build/curated_strategy_samples_verified/summary.json`
- `dataset_build/curated_strategy_samples_verified/final_curation_report.md`

样本格式：

- PDF：15 个，优先用 `pypdf` 抽文本；必要时截图给 VL。
- HTML：23 个，优先用 `BeautifulSoup` 提取正文；必要时保留原始 HTML 结构和标题层级。

## 3. 输出目录

建议新增：

```text
dataset_build/meta_extraction/
  intermediate/
    text_chunks/
    visual_notes/
    flash_pass/
    pro_pass/
  final_cases.jsonl
  final_cases_pretty/
  extraction_manifest.jsonl
  extraction_summary.json
  qa_issues.jsonl
```

输出分层：

- `intermediate/text_chunks/`：PDF/HTML 文本块和章节结构。
- `intermediate/visual_notes/`：VL 对图表、封面、版式、表格截图的观察。
- `intermediate/flash_pass/`：Flash 初筛出的 facts、sections、source hints。
- `intermediate/pro_pass/`：Pro 生成的完整 JSON 草案。
- `final_cases.jsonl`：最终可进入人工 QA 的结构化 metadata。
- `qa_issues.jsonl`：schema 错误、低置信字段、来源不足、视觉失败等问题。

## 4. Python 包与用途

当前已有依赖：

| 包 | 用途 |
|---|---|
| `requests` | OpenRouter API 调用、必要时下载/复核 URL |
| `beautifulsoup4` | HTML 正文、标题、链接、表格提取 |
| `pypdf` | PDF 页数、文本、metadata 抽取 |
| `tqdm` | 批处理进度条 |

建议新增依赖：

| 包 | 用途 | 必要性 |
|---|---|---|
| `pydantic` | 定义 metadata schema，做字段校验和类型约束 | 高 |
| `jsonschema` | 轻量 schema 校验，可选替代/补充 pydantic | 中 |
| `pillow` | 读取截图尺寸、压缩图片、必要时裁剪图表区域 | 中 |
| `python-dateutil` | 规范化报告日期和 publication period | 中 |

可选依赖：

| 包 | 用途 | 备注 |
|---|---|---|
| `pymupdf` / `fitz` | PDF 页面渲染截图、图表区域截图 | 比 Chrome 更适合 PDF 页面截图 |
| `playwright` | HTML 页面截图、动态页面渲染 | 仅在静态 HTML 不够时使用 |
| `selectolax` | 更快的 HTML 抽取 | 可后续优化 |

## 5. 分阶段流程

### Stage 0: Manifest 读取与任务建模

输入 `metadata.jsonl`，生成内部任务对象：

```json
{
  "sample_id": "strategy_sample_001",
  "format": "pdf|html",
  "subtype": "annual_outlook",
  "institution": "...",
  "source_url": "...",
  "local_path": "...",
  "source_verification": "official_domain_verified",
  "score": 95
}
```

使用包：

- `json`
- `pathlib`
- `pydantic` 或 dataclass

LLM：不需要。

### Stage 1: 文本与结构抽取

PDF：

- 用 `pypdf.PdfReader` 抽取前 8-15 页文本，另抽目录、封面、免责声明附近文本。
- 记录 `page_count`、`parse_quality`、`pdf_metadata.title`、`file_size_bytes`、`sha256`。
- 若文本长度太短或图表密集，标记 `needs_visual_pass=true`。

HTML：

- 用 `BeautifulSoup` 去掉 script/style/nav/footer。
- 提取 `title`、`h1/h2/h3`、正文、表格、链接。
- 记录 `text_length`、heading 数量、source links。

使用包：

- `pypdf`
- `bs4`
- `hashlib`
- `re`

LLM：不需要。

### Stage 2: Flash 大吞吐初读

对每个样本构造压缩输入：

- title / institution / subtype / source URL
- headings
- 前 8-12k tokens 文本
- 表格文本摘要
- 已知 curation metadata

调用 `deepseek/deepseek-v4-flash`，输出“候选材料”，不是最终 JSON：

```json
{
  "report_title_candidates": [],
  "date_candidates": [],
  "authors_or_team_candidates": [],
  "subtype_check": {},
  "core_thesis_candidates": [],
  "key_fact_candidates": [],
  "source_pack_candidates": [],
  "must_have_section_candidates": [],
  "risk_and_prohibited_mistake_candidates": [],
  "visual_pass_recommendation": {
    "needed": true,
    "why": "charts appear central / parse text lacks chart values"
  }
}
```

Flash 适用原因：

- 38 个样本总 token 量较大。
- 这一步容忍候选噪声，重点是召回。
- 可并行/断点续跑。

### Stage 3: VL 视觉补充

触发条件：

- PDF `parse_quality=fair/poor/failed`。
- 报告中图表/表格是核心证据。
- HTML 或 PDF 的标题、封面、图表无法从文本中可靠抽取。
- 样本被选为 high-value golden candidate，值得更细看图表风格。

输入：

- PDF：用 Chrome/PyMuPDF 渲染封面、目录页、2-4 个图表页。
- HTML：用 Chrome headless 截首屏或关键 section。

调用 `qwen/qwen3-vl-235b-a22b-instruct`，输出：

```json
{
  "visual_summary": "...",
  "detected_report_title": "...",
  "detected_chart_or_table_candidates": [
    {
      "title_or_description": "...",
      "type": "line|bar|table|scenario_table|matrix|other",
      "visible_axis_or_units": "...",
      "why_relevant": "..."
    }
  ],
  "layout_style_notes": [],
  "visual_confidence": 0.0
}
```

VL 不用于长文总结，只用于视觉线索、图表/表格、版式和 OCR 式补充。

### Stage 4: Pro 最终 Metadata 生成

将以下材料合并给 `deepseek/deepseek-v4-pro`：

- 原始 sample metadata。
- Stage 1 文本结构。
- Stage 2 Flash 候选结果。
- Stage 3 VL 视觉补充。
- schema guide 和 extraction skill 的压缩版规则。

Pro 生成完整 JSON：

- `case_id`
- `source_pdf` 或 `source_document`
- `institution`
- `report_title`
- `report_date`
- `strategy_subtype`
- `candidate_query`
- `expected_report_type`
- `source_pack`
- `key_facts`
- `must_have_sections`
- `prohibited_mistakes`
- `reference_notes`
- `charts_and_tables_to_learn_from`
- `evaluation_hooks`
- `extraction_confidence`

Pro 适用原因：

- 需要区分事实、预测、假设和观点。
- 需要把报告内容转化为 benchmark case，而不是摘要。
- 需要设计自然 query、红线错误、评估关注点。

### Stage 5: Schema 校验与自动修复

先本地校验：

- JSON parse。
- required fields。
- 枚举字段。
- `key_facts` 数量和 source_ref。
- `candidate_query.query` 非空且语言合理。
- `source_pack` 至少包含 primary document。
- `prohibited_mistakes` 至少 4 条。

若失败：

1. 对小错误用本地 Python 修复，例如 null/default、字段重命名。
2. 对结构性错误调用 `deepseek/deepseek-v4-pro` 做 JSON repair。
3. 对内容不足调用 `deepseek/deepseek-v4-flash` 重新补候选，再交给 Pro。

使用包：

- `pydantic`
- `json`
- `jsonschema` 可选

LLM：

- Pro：结构性修复。
- Flash：补召回。

### Stage 6: 质量评分与 Golden 候选选择

对每条 metadata 计算 extraction score：

| 维度 | 权重 | 说明 |
|---|---:|---|
| schema completeness | 20 | 字段齐全、类型正确 |
| source grounding | 20 | source_pack 和 key_facts 可核验 |
| query usefulness | 15 | query 自然、约束合理、不泄答案 |
| subtype fit | 15 | 报告类型准确 |
| strategy benchmark value | 20 | must-have / prohibited mistakes 有评测价值 |
| visual/reference notes | 10 | 图表和版式学习点有用 |

输出：

- `A`: 可进入 golden-set 人工复核。
- `B`: 可用但需补 key facts 或来源。
- `C`: metadata 太弱，仅存档。
- `Reject`: 非策略、来源不清或解析失败。

LLM：

- Pro 可做最终 rubric judge。
- Flash 可批量生成初步评分解释。

## 6. 推荐调用策略

### 6.1 成本优先默认策略

每个样本：

1. 本地抽取文本。
2. Flash 初读一次。
3. 仅对需要视觉的样本调用 VL。
4. Pro 生成最终 JSON 一次。
5. 本地校验；失败才 Pro repair。

适合 38 条全量跑。

### 6.2 高精度 golden 策略

对最终要进 golden set 的 20-50 条：

1. Flash 初读。
2. VL 至少看封面/首屏，图表密集样本再看 2-3 张图表页。
3. Pro 生成 JSON。
4. Pro 自检一次，要求列出不确定字段和证据缺口。
5. 本地 schema 校验。

### 6.3 中文第三方样本策略

中文第三方样本必须额外：

- Pro 判断 `original_institution` 是否与页面/标题/PDF 首页一致。
- source_pack 标记 `third_party_mirror`。
- `copyright_note` 和 `access_stability` 写入 `extraction_notes` 或扩展字段。
- 若机构归属不确定，不进入 golden，只保留为 archive。

## 7. Prompt 分工草案

### Flash Prompt: Candidate Extraction

角色：研究助理。

目标：从长文本中高召回抽取候选事实、章节、来源和风险。

要求：

- 不输出最终 metadata。
- 不编造缺失日期/作者。
- forecast/assumption 必须标注。
- 输出 JSON。

### VL Prompt: Visual Extraction

角色：视觉研究助理。

目标：识别封面标题、报告类型、图表/表格标题、版式风格和图表证据。

要求：

- 只描述图片中能看见的内容。
- 看不清则标 `uncertain`。
- 不推断图外数据。
- 输出 JSON。

### Pro Prompt: Final Metadata

角色：benchmark case designer。

目标：基于文本候选和视觉 notes 生成符合 schema 的完整 metadata。

要求：

- 输出单个 JSON object。
- candidate_query 应自然且不泄露完整答案。
- key_facts 只保留可核验且评估重要的事实/预测。
- must_have_sections 面向评测，不复制目录。
- prohibited_mistakes 要 case-specific。
- 对不确定字段使用 null 并降低 confidence。

### Pro Prompt: QA Repair

角色：JSON schema repairer + financial benchmark reviewer。

目标：修复 JSON schema 问题并指出低置信字段。

要求：

- 尽量少改内容。
- 不添加无来源事实。
- 输出修复后的 JSON 和 issue list，或只输出 JSON。

## 8. 需要新增/升级的脚本

建议新增：

```text
dataset_tools/strategy_reports/llm_extract_metadata.py
dataset_tools/strategy_reports/llm_clients.py
dataset_tools/strategy_reports/document_extractors.py
dataset_tools/strategy_reports/metadata_models.py
dataset_tools/strategy_reports/render_sample_pages.py
dataset_tools/strategy_reports/validate_metadata.py
```

职责：

- `llm_clients.py`: OpenRouter client、重试、速率限制、响应记录、成本统计。
- `document_extractors.py`: PDF/HTML 文本抽取、chunking、截图路径生成。
- `metadata_models.py`: Pydantic models，对应 schema。
- `llm_extract_metadata.py`: 主流程编排，支持 `--limit`、`--sample-id`、`--stage`、`--resume`。
- `render_sample_pages.py`: PDF/HTML 截图，供 VL 使用。
- `validate_metadata.py`: schema、字段和质量校验。

## 9. 断点续跑与日志

每个样本维护阶段状态：

```json
{
  "sample_id": "strategy_sample_001",
  "stage_text_extract": "done",
  "stage_flash": "done",
  "stage_vl": "skipped|done|failed",
  "stage_pro": "done",
  "stage_validation": "done",
  "final_status": "A|B|C|Reject|needs_review"
}
```

所有 LLM 调用保存：

- model
- prompt hash
- input token estimate
- output token usage
- latency
- status
- error
- response path

不要保存 API key。

## 10. 第一轮实验建议

不要一开始跑 38 条全量。建议：

1. 选 6 条 smoke test：
   - 2 个 PDF annual outlook。
   - 1 个 PDF asset allocation。
   - 1 个 HTML thematic strategy。
   - 1 个 HTML fixed income。
   - 1 个中文第三方 PDF。
2. 跑完整 Flash + VL 条件触发 + Pro + validation。
3. 人工检查输出质量。
4. 调整 prompt 和 schema。
5. 再跑全量 38 条。

推荐 smoke test：

- `strategy_sample_001`: GSAM Investment Outlook 2026。
- `strategy_sample_002`: JPM Mid-Year Outlook。
- `strategy_sample_003`: JPM Eye on the Market。
- `strategy_sample_024`: GSAM Market Brief HTML。
- `strategy_sample_028`: Vanguard fixed income HTML。
- `strategy_sample_032`: 国泰君安期货全球宏观与商品策略。

## 11. 成功标准

第一轮全量 extraction 成功后，应得到：

- `38` 条 metadata JSONL。
- 至少 `25` 条 extraction quality A/B。
- 每条都有自然 query、source pack、key facts、must-have sections、prohibited mistakes。
- 中文第三方样本明确标注镜像来源和核验限制。
- 至少 `10` 条样本包含图表/表格学习点。
- 所有 JSON 能通过 schema 校验。

这时即可进入下一步：人工 QA、golden-set promotion，以及让 agent 使用这些 case 进行策略报告生成评测。
