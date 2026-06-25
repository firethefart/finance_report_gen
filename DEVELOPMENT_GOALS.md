# 项目开发目标与 Agent 交接文档

更新时间：2026-06-19  
当前阶段：`Verifier V2 优化 — rules-only 饱和度与剩余偏差诊断`  
文档性质：持续维护的开发目标、执行计划与轮次摘要。后续每一轮实质开发都必须更新本文档。

命名约定：**Verifier V2 指无需 reference 的 candidate-only verifier 变种，
不是版本号。** 后续工程运行使用 `r1/r2/...`；历史 `_v1` 至 `_v5` 目录只作为
legacy run label 保留，不再写成“Verifier 的版本”。

当前 session 的精确交接、已验证命令和下一步见：
[`evals/strategy_report/SESSION_HANDOFF_20260619_CANDIDATE_ONLY_R8.md`](evals/strategy_report/SESSION_HANDOFF_20260619_CANDIDATE_ONLY_R8.md)。

---

## 0. 给零上下文 Agent 的最短说明

本项目只聚焦一种金融研究产物：**策略研究报告（strategy research report）**。

这里的策略报告包括：

- 年度、中期、季度市场展望；
- 宏观、利率、信用、权益策略；
- 资产配置、跨资产和组合实施；
- 行业格局、产业链和主题策略；
- 周度/月度策略评论；
- 并购、资本市场及其他具有策略含义的专题报告。

它不等于上市公司的年报、季报、盈利公告，也不等于单家公司 earnings
update、普通新闻综述、基金销售页或泛行业文章。正式定义、专业规范和边界见：

- [`generation_test/strategy_research_framework.md`](generation_test/strategy_research_framework.md)
- [`strategy_report_eval_standard.md`](strategy_report_eval_standard.md)

项目最终目标是构建以下闭环：

```text
高质量策略报告数据与测试集
        ↓
自动化 Verifier
        ↓
自动化策略报告生成管线
        ↓
基于失败归因的 Skill Iteration
        ↓
held-out 回归验证与版本门控
```

我们希望通过持续修改可审计、可回滚的 skill 和工具来提升报告生成能力，而不是把主要希望寄托在重新训练底层模型上。相关研究背景见：

- [`01_agent_skill_research_report.md`](01_agent_skill_research_report.md)
- [`02_skill_iteration_finance_report.md`](02_skill_iteration_finance_report.md)

---

## 1. 当前总体路线

开发顺序已经确定：

1. **将 Verifier V2 优化到接近当前工程能力上限。**
2. **搭建自动化策略报告生成管线。**
3. **启动正式 Skill Iteration。**
4. **在 Verifier 经过充分工程优化后进行昂贵的人类对齐实验。**

人类对齐非常重要，但不是当前下一步。专家标注成本很高；在 V2 仍存在明显、
可由工程开发解决的问题时，不应提前消耗对齐预算。

同样，当前阶段不以自动生成大量测试报告为前提。自动化生成管线属于下一阶段。
V2 优化期间的样本优先来自：

- 仓库中已经积累的高质量 PDF；
- 已调研的官方/高质量 HTML 策略报告源；
- 对真实 HTML 引用资源进行完整本地化后的离线快照；
- 现有两份本地生成 HTML 只能作为历史对照，不能代表理想 HTML 质量。

---

## 2. Verifier V1 与 V2

### 2.1 V1

V1 是 reference-aware evaluator：

- 输入包括 golden case metadata 和 candidate report；
- 使用 key facts、must-have sections、expected themes 等参考信息；
- 适合 benchmark、校准和同一任务下的版本比较。

主要入口和文档：

- [`evals/strategy_report/run_eval.py`](evals/strategy_report/run_eval.py)
- [`evals/strategy_report/VERIFIER_PIPELINE_OVERVIEW.md`](evals/strategy_report/VERIFIER_PIPELINE_OVERVIEW.md)
- [`strategy_report_golden_set_status.md`](strategy_report_golden_set_status.md)

### 2.2 V2

V2 是 candidate-only verifier：

- 只输入待测 PDF/HTML；
- 不依赖 golden answer 或参考报告；
- 判断报告本身是否专业、可信、完整、可交付；
- 是未来自动化生成管线和 Skill Iteration 的主要质量反馈器。

主要入口：

- [`evals/strategy_report/run_eval_v2.py`](evals/strategy_report/run_eval_v2.py)
- [`evals/strategy_report/v2_checks.py`](evals/strategy_report/v2_checks.py)
- [`evals/strategy_report/v2_llm_verifiers.py`](evals/strategy_report/v2_llm_verifiers.py)
- [`evals/strategy_report/scoring_v2.py`](evals/strategy_report/scoring_v2.py)
- [`evals/strategy_report/profiles/v2_full_smoke.json`](evals/strategy_report/profiles/v2_full_smoke.json)

V2 当前包括：

- PDF/HTML 解析和交付检查；
- 结构、来源可追溯性、数字/claim 纪律；
- 策略推理、情景风险、合规；
- 图表抽取、VLM visual gate 和 checklist；
- candidate-only Claim/Numeric LLM；
- candidate-only Strategy Reasoning LLM；
- 合规规则候选的 LLM 上下文确认；
- 报告 archetype 区分；
- JSON/Markdown 输出及 review dashboard。

---

## 3. 方法必须泛化，但任务范围是策略报告

样本发现、筛选和评测 rubric 可以针对策略报告，因为这就是产品范围。

但是 Verifier 的底层方法不能依赖：

- 某一家机构；
- 某一个样本；
- 固定章节标题；
- 固定报告模板；
- 为提高少数测试分数而添加的样本专用关键词；
- “如果文件名等于 X 就走 Y 逻辑”一类 hard code。

应通过以下方式适配策略报告内部差异：

- 可配置 profile；
- 语义判断；
- 报告 archetype；
- 中英文通用概念和本土表达支持；
- 可审计的规则/LLM/VLM 融合；
- 明确的 uncertainty 与 failure mode。

垂直聚焦不等于样本过拟合。

---

## 4. 当前测试集状态

第一版 V2 核心集已经建立，共 24 份：

- 12 英文、12 中文；
- 22 PDF、2 HTML；
- 24/24 通过文件完整性和基础 V2 兼容性；
- 24/24 能执行 deterministic V2 和图表抽取。

相关文件：

- [`evals/strategy_report/v2_testset_selection.json`](evals/strategy_report/v2_testset_selection.json)
- [`evals/strategy_report/V2_CORE_TESTSET_README.md`](evals/strategy_report/V2_CORE_TESTSET_README.md)
- [`evals/strategy_report/v2_testset_audit.json`](evals/strategy_report/v2_testset_audit.json)
- [`evals/strategy_report/audit_v2_testset.py`](evals/strategy_report/audit_v2_testset.py)
- [`evals/strategy_report/run_v2_testset.py`](evals/strategy_report/run_v2_testset.py)
- [`evals/strategy_report/results/v2_core_24_rules_v1/summary.json`](evals/strategy_report/results/v2_core_24_rules_v1/summary.json)

### 4.1 当前测试集的重大缺陷

用户已明确指出：**HTML 是 V2 的重点测试对象，但当前正式核心集只有 2 份
HTML，而且这两份本地历史生成报告质量不够高。当前测试集因此不能视为满意或
完成。**

新的硬要求：

1. 正式核心测试集中必须补充到**至少 10 份高质量 HTML 策略报告**。
2. 可以裁撤部分 PDF，以维持总规模约 `20–30` 份并提高 HTML 占比。
3. 现有两份生成 HTML 可以保留为历史质量对照，但不能被当成“高质量 HTML”
   配额的主要组成。
4. synthetic fixture 不计入报告级样本数量。
5. 资源缺失、正文不完整、图表不可见的爬取页面不能因为“文本还能抽取”而进入
   高质量核心集。

旧文件
[`evals/strategy_report/V2_HTML_TEST_EXPANSION_PLAN.md`](evals/strategy_report/V2_HTML_TEST_EXPANSION_PLAN.md)
包含“优先自动生成大量 HTML”的早期建议。该建议与当前阶段决策不一致：

- 自动化生成管线尚未搭建；
- 当前应优先使用真实高质量 HTML，并进行资源本地化；
- 不得为了快速凑样本而手工制造一批无法代表真实输入分布的 HTML。

以后若引用该旧计划，只能使用其中的 inventory、资源审计和 adapter edge-case
信息，不能直接沿用其执行顺序。

---

## 5. HTML 样本准入标准

高质量 HTML 样本必须同时通过内容和技术门槛。

### 5.1 内容门槛

- 确实属于策略研究；
- 来源机构和发布时间可核验；
- 有明确 thesis 或策略问题；
- 有证据、传导机制和投资研究含义；
- 有风险、情景或判断边界；
- 图表或表格对论证有实际作用；
- 不是导航页、聚合页、空壳专题页、transcript 列表或营销页；
- 不因页面来自头部机构就自动判为高质量。

### 5.2 技术门槛

- HTML 正文完整；
- CSS、图片、SVG、字体和必要脚本已本地化；
- 离线运行不依赖远程网络；
- 无关键资源缺失；
- 动态图表在浏览器 runtime 中真实渲染；
- lazy loading 内容能被触发；
- `srcset`、CSS background、SVG sprite、canvas 等资源得到正确处理；
- cookie、modal、share shell 清理不能误删正文；
- target screenshot 与浏览器人工观察一致；
- 图表不能用静态占位符或错误截图冒充；
- 通过 HTML Runtime Adapter V2 的 resource audit 和人工视觉复核。

适配器说明：

- [`evals/strategy_report/HTML_RUNTIME_ADAPTER_V2_README.md`](evals/strategy_report/HTML_RUNTIME_ADAPTER_V2_README.md)
- [`evals/strategy_report/html_runtime_adapter_v2.py`](evals/strategy_report/html_runtime_adapter_v2.py)

### 5.3 禁止降级原则

遇到资源本地化、动态渲染、反爬、CSS/JS 重写或浏览器等待问题时：

1. 先定位和调试技术原因；
2. 保存失败证据和日志；
3. 尝试站点级但可泛化的资源归档方案；
4. 如果需要改变范围或接受标准，先与用户讨论；
5. 不得静默关闭图表、只保留文本、降低准入门槛或换成更容易但低价值的样本。

---

## 6. 下一阶段开发目标

### 总目标

将当前 24 份、PDF 主导的测试集重构为 `20–30` 份高质量策略报告核心集，其中
至少 10 份为高质量、离线完整、可由 V2 runtime 正确处理的 HTML。

### 推荐目标分布

建议最终冻结 24–26 份：

| 维度 | 目标 |
| --- | ---: |
| 高质量 HTML | 10–12 |
| PDF | 12–14 |
| 中文 | 约 50% |
| 英文 | 约 50% |
| 自包含生成 HTML 历史对照 | 最多 2 |
| 真实机构 HTML | 至少 8 |
| synthetic fixtures | 独立维护，不计入核心集 |

HTML 应覆盖：

- 年度/中期/季度展望；
- 资产配置或组合实施；
- 宏观/市场策略；
- 权益或行业主题；
- weekly/brief；
- 多图、SVG、canvas、表格、KPI、长页面等不同视觉形态。

---

## 7. 下一轮可执行计划

状态说明：

- `[ ]` 未开始
- `[-]` 进行中
- `[x]` 已完成
- `[!]` 阻塞，必须记录原因和所需决策

### P0：重新清点真实 HTML 候选

- [x] 从
  [`evals/strategy_report/results/v2_html_inventory.json`](evals/strategy_report/results/v2_html_inventory.json)
  和 `dataset_build/raw_html/` 重新建立候选表。
- [x] 排除导航页、聚合页、transcript 列表、重复专题页和内容过短页面。
- [x] 按机构、语言、subtype、正文长度、视觉对象、资源缺失情况排序。
- [x] 对进入本地化候选和冻结集的页面记录原 URL、local path、机构、标题、日期、资源数量、remote
  数量、missing 数量和人工内容判断。
- [x] 从已有信源配置中查找更高质量 HTML：
  [`dataset_tools/strategy_reports/sources.expanded.json`](dataset_tools/strategy_reports/sources.expanded.json)、
  [`strategy_report_source_expansion_report.md`](strategy_report_source_expansion_report.md)。

当前产物：

- [`evals/strategy_report/build_html_candidate_inventory.py`](evals/strategy_report/build_html_candidate_inventory.py)
- [`evals/strategy_report/results/v2_html_candidate_inventory.json`](evals/strategy_report/results/v2_html_candidate_inventory.json)
- [`evals/strategy_report/results/v2_html_candidate_inventory.md`](evals/strategy_report/results/v2_html_candidate_inventory.md)
- [`evals/strategy_report/html_localization_candidates.json`](evals/strategy_report/html_localization_candidates.json)
  已形成 22 个本地化候选，并完成冻结集所需的内容审查；不合格页面在 manifest 中
  以 `enabled: false` 和 `content_review_status` 明确记录。

完成标准：形成至少 20 个值得进一步本地化的真实 HTML 候选，而不是直接凑 10 个。

### P0：实现或增强 HTML 资源本地化

- [x] 检查现有 archive/runtime adapter 是否已有可复用逻辑。
- [x] 为 HTML 快照建立资源下载与 URL 重写流程。
- [x] 支持当前冻结样本所需的 `src`、stylesheet、CSS `url()`、SVG 和字体资源；
  `srcset` 固化为实际渲染资源，必要脚本通过渲染后 DOM 固化处理。
- [x] 对动态内容处理滚动、等待条件和 lazy loading。
- [x] 输出 resource manifest：原 URL、本地路径、状态、MIME、hash、失败原因。
- [x] 保证归档结果离线可复现。
- [x] 为至少 3 个不同机构先做端到端试点，再扩展。

试点结论见
[`evals/strategy_report/HTML_LOCALIZATION_PILOT_20260618.md`](evals/strategy_report/HTML_LOCALIZATION_PILOT_20260618.md)：
四机构完成端到端执行。GSAM、State Street 和 Morgan Stanley 已通过资源完整性、
Runtime 和人工视觉试点；BlackRock 的两个候选经 live 渲染后确认本身是 PDF
报告壳并已排除。三机构试点完成标准已经满足，可以开始批量扩展。

完成标准：试点页面离线打开时正文和关键视觉与原页面一致，resource audit 无
未解释的关键缺失。

### P0：挑选并冻结至少 10 个 HTML 样本

- [x] 逐份做内容审查。
- [x] 逐份做浏览器视觉审查。
- [x] 逐份运行 HTML Runtime Adapter V2。
- [x] 核对 visual object target/context screenshots。
- [x] 核对来源、图表、文字、风险和合规信息是否完整。
- [x] 保证真实机构 HTML 至少 8 份。
- [x] 控制单一机构占比，不让 GSAM/State Street 等一家主导。
- [x] 确认至少覆盖 5 种 subtype/archetype。

冻结结果：

- [`evals/strategy_report/v2_frozen_html_set.json`](evals/strategy_report/v2_frozen_html_set.json)
- 10 份真实机构 HTML，来自 GSAM、State Street、Morgan Stanley；
- 9 个 HTML subtype；
- 单一机构最多 4 份；
- 最新资源审计 10/10 admitted。

完成标准：至少 10 份 HTML 同时满足第 5 节全部门槛。

### P1：重构核心测试集

- [x] 从现有 22 份 PDF 中裁撤重复度高或边际测试价值低的样本。
- [x] 保留能测试 PDF 特有风险的高价值样本，例如 landscape、chartbook、长报告、
  中文券商版式和 parser robustness。
- [x] 将总数控制在 20–30。
- [x] 更新
  [`evals/strategy_report/v2_testset_selection.json`](evals/strategy_report/v2_testset_selection.json)。
- [x] 更新 audit 脚本，使 HTML 的“至少 10 份”和资源完整性成为硬门槛。
- [x] 重新生成 audit、视觉 review artifacts 和 README。

当前核心集：26 份，12 HTML、14 PDF、14 英文、12 中文。最新硬审计 26/26
admitted，hard gate errors 为 0。

完成标准：新 manifest 的 HTML 数量、格式分布和质量门槛全部自动可验证。

### P1：建立统一 V2 基线

- [x] 使用同一 profile 跑 parser/adapter compatibility。
- [x] 跑 rules-only 和 chart extraction。
- [ ] 分层运行 Claim/Numeric、Strategy Reasoning、Chart VLM 和 Compliance。
- [-] 记录每样本耗时、调用量、失败重试和模块完整性；当前已记录批次完成性，
  尚未补齐逐样本耗时。
- [x] 建立按 language/format/archetype/subtype 的结果摘要。
- [x] 对 PDF 与 HTML 的系统性分数差异做初步诊断。

完成说明：

- Runtime Adapter 已改为使用约 49 字符的短临时浏览副本，正式产物仍写回原输出目录；
- adapter manifest 新增 `browser_navigation`，记录正式路径长度、实际浏览 URL、
  浏览路径长度、frame id 和临时副本清理状态；
- `v2_html_gsam_backdrop_2026` 在正式路径长度 282 的完整调用链中恢复到
  text length 50,062、10 个视觉对象、91.65 分、Gold、gate passed；
- `v2_core_26_unified_rules_v2` 已完成 26/26，report-level failure 为 0；
- 12/12 HTML 均使用短临时 `file://` URL，未发现 `chrome-error://chromewebdata/`
  或 text length 46；
- legacy r2 作为 reasoning 修复前对照保留；当前有效规则基线为
  `evals/strategy_report/results/candidate_only_rules_r8/`，完成 26/26、
  0 failures，并包含最新分层摘要。

完成标准：所有核心样本都由同一版本、同一 profile 运行；不存在用旧 smoke
结果拼接的“基线”。

### P2：继续优化 V2

当前已知信号：

- 当前 r8：HTML 平均 78.57、gate 通过率 50.0%；PDF 平均 85.99、
  gate 通过率 92.9%；
- 英文平均 78.85、gate 通过率 50.0%；中文平均 86.90、gate 通过率 100%；
- State Street 的 reasoning 误拒、BlackRock chartbook archetype 和 HTML
  装饰图误计已经修复；
- strategy reasoning 精确 1.0 已从 9/26 降为 0，达到或超过 0.99 的样本为 2；
- 剩余拒绝集中在 State Street 两份临界样本、Morgan Stanley 两份 brief 和
  J.P. Morgan Energy，主要待查 source/numeric/structure、sectionization、
  disclaimer 边界和 context 截断。

下一轮：

- [x] 做 format/language/archetype 分层误差分析；
- [x] 优先检查 State Street HTML、brief commentary、chartbook 和 J.P. Morgan
  Energy 的 sectionization/context binding；
- [x] 修复乱码句子切分、archetype 偶然关键词误判和 HTML 装饰图误计；
- [x] 检查 strategy reasoning 饱和度和 1.0 分辨率；
- [x] 修复 manifest title 丢失和 chart density archetype 误判；
- [x] 修复四位数抽取、数字元数据污染和 source 导航链接伪证据；
- [x] 修复 Morgan Stanley section/disclaimer 边界；
- [ ] 继续审查 J.P. Morgan Energy 样本边界与 context 截断问题；
- [ ] 再考虑 prompt、融合权重和 gate；
- [ ] 每次改动必须在全测试集做回归；
- [ ] 不以提高平均总分为目标，而以减少错误判断和提高跨类型一致性为目标。

---

## 8. 人类对齐的时机

现有对齐设计和导出能力保留：

- [`evals/strategy_report/alignment_export_design.md`](evals/strategy_report/alignment_export_design.md)
- [`evals/strategy_report/VERIFIER_LATEST_FLOWCHART_ALIGNMENT_ZH.md`](evals/strategy_report/VERIFIER_LATEST_FLOWCHART_ALIGNMENT_ZH.md)

但对齐实验应在以下条件大体满足后启动：

- HTML/PDF 核心测试集覆盖充分；
- 低成本工程问题基本收敛；
- 关键模块输出稳定、可审计；
- 同一输入重复运行稳定；
- 明显语言、格式和 archetype 偏差已处理；
- 已明确最值得花专家成本确认的剩余不确定性。

---

## 9. 环境和执行约束

根目录工具必须使用仓库根目录 `.venv`：

```powershell
.\.venv\Scripts\python.exe ...
```

不要使用 `LangAlpha/` 内部环境。完整说明见 [`AGENTS.md`](AGENTS.md)。

数据和产物约定：

- 数据构建代码：`dataset_tools/strategy_reports/`
- 生成/归档数据：`dataset_build/`
- verifier 代码：`evals/strategy_report/`
- verifier 结果：`evals/strategy_report/results/`

不要读取、打印或提交 `api_key.txt` 的内容。

---

## 10. 每轮开发后的强制维护规则

从现在开始，每轮有实质进展的开发都必须更新本文档。

至少更新以下内容：

1. 修改顶部“更新时间”和“当前阶段”。
2. 在第 7 节对应任务上标记 `[x]`、`[-]` 或 `[!]`。
3. 在下方“轮次摘要”追加一条记录。
4. 写明实际完成了什么，而不是只写“优化了一些问题”。
5. 写明验证命令和产物路径。
6. 写明发现的新问题。
7. 更新下一步计划，删除或标记已经过时的建议。
8. 如果用户改变了优先级，以最新用户决策为准，并明确记录变更。

### 轮次摘要模板

```markdown
### YYYY-MM-DD — 轮次标题

状态：完成 / 部分完成 / 阻塞

完成：

- ...

验证：

- 命令：
- 结果：
- 产物：

发现：

- ...

未完成或阻塞：

- ...

下一步：

1. ...
2. ...
```

---

## 11. 轮次摘要

### 2026-06-19 — 分离 HTML 正文与披露并建立 candidate-only rules r8

状态：完成

完成：

- HTML 同时保留 `full_text` 和 `analysis_text`；
- compliance/delivery 使用全文，研究质量维度只使用正文；
- 通过 Discover More、披露标题和连续 related cards 识别正文边界；
- DOM heading 稀少时恢复编号小节；
- 排除 `Source:` 伪 synthetic heading；
- 增加 analysis/forecast/estimate/positioning 等通用结构信号。

验证：

- r8 26/26 completed，0 failures，19/26 gate passed；
- 仅两份 Morgan Stanley HTML 触发正文截断；
- Equity Rally：17,509 → 5,155 字符，最终 74.71，仍拒绝；
- Digital Assets：6,374 → 6,190 字符，结构 0.500 → 0.653，最终 67.28；
- GSAM 与 State Street HTML 未被误截；
- gate 集合与 r7 完全一致；
- HTML 78.57、PDF 85.99；英文 78.85、中文 86.90。

失败与警告：

- 第一版边界从 45% 后开始搜索，错过位于 29% 的 Discover More，只截掉末尾
  17 字符；改为 20% 后正确截掉 12,354 个非正文字符；
- 第一版 synthetic heading 将 GSAM `Source:` 行识别为编号小节并错误增分；
  现已限制为 DOM heading 少于 5 时启用，并排除 `Source:`；
- GSAM Active ETF 仍有已知、非致命 MuPDF structure-tree warning。

产物：

- `evals/strategy_report/results/candidate_only_rules_r8/summary.json`
- `evals/strategy_report/results/candidate_only_rules_r8/layered_summary.json`
- `evals/strategy_report/results/candidate_only_rules_r8/layered_summary.md`
- `evals/strategy_report/SESSION_HANDOFF_20260619_CANDIDATE_ONLY_R8.md`

下一步：

1. 审查 J.P. Morgan Energy 的样本范围与 head/tail 文本压缩；
2. 决定其属于策略质量样本还是 thematic parser robustness case；
3. 继续分析语言/格式差距，不降低 gate；
4. deterministic 收敛后再运行 LLM/VLM。

### 2026-06-19 — 统一 candidate-only 命名并建立 rules r7

状态：完成

命名决策：

- V2 只表示无需 reference 的 candidate-only verifier 变种；
- 工程运行改用 `rN`；
- 历史 `_v1` 至 `_v5` 仅作为 legacy run label；
- 当前产物目录为 `candidate_only_rules_r7`。

完成：

- 修复 `2026` 被抽成 `202` 的三位数正则缺陷；
- 支持货币前缀、billion/trillion、百分比、bps 和期限单位；
- 排除文档编号、页码、年份轴、出版元数据和小列表编号；
- author bio、footer、首页和 generic investment-management 链接不再算 source；
- publisher provenance 与 external source traceability 分离；
- 生成 r6 中间诊断运行和 r7 最终运行。

验证：

- r7 26/26 completed，0 failures，19/26 gate passed；
- GSAM Backdrop 92.87，通过；
- BlackRock chartbook 82.99，通过；
- generated baseline 75.61，optimized 87.16，差距 11.55；
- HTML 78.09、PDF 85.74；英文 78.19、中文 86.90。

失败与警告：

- PowerShell here-string 对中文和欧元微测试出现终端编码问号，真实 UTF-8
  回归数据不受影响；
- r6 尚未过滤年份轴和出版元数据，已保留为中间失败/诊断产物；
- 并行读取摘要时发生写入竞态，首次报路径不存在；串行复核成功；
- GSAM Active ETF 仍有已知、非致命 MuPDF structure-tree warning。

产物：

- `evals/strategy_report/results/candidate_only_rules_r7/summary.json`
- `evals/strategy_report/results/candidate_only_rules_r7/layered_summary.json`
- `evals/strategy_report/results/candidate_only_rules_r7/layered_summary.md`
- `evals/strategy_report/SESSION_HANDOFF_20260619_CANDIDATE_ONLY_R7.md`

下一步：

1. Morgan Stanley sectionization 与 disclaimer leakage；
2. PDF chart-text numeric binding；
3. J.P. Morgan Energy 样本边界与 head/tail 压缩审查；
4. 暂不降低 gate。

### 2026-06-19 — 消除 strategy reasoning 满分饱和并建立 legacy r5 基线

状态：完成

完成：

- reasoning 证据先剔除 disclaimer/boilerplate 并去重；
- 将 4/10/4/4 硬封顶改为 archetype-aware 渐进饱和曲线；
- 删除不可靠的 chart extractor 密度 archetype 捷径；
- 将测试集 manifest title 传入统一 evaluator；
- 补充 `we see`、`we view`、`stands out`、`well placed` 等明确观点表达；
- 保留出现回归的 legacy r4，并在修复后新建 legacy r5。

验证：

- legacy r5 全量 26/26 completed，0 failures，21/26 gate passed；
- strategy reasoning 精确 1.0：9 → 0；
- strategy reasoning >= 0.99：9 → 2；
- State Street Alternatives 在 legacy r4 回归为 74.62 后，legacy r5 恢复为 77.30；
- State Street Equity：74.91 → 77.25，恢复为通过；
- generated optimized 88.29，baseline 76.08，排序与 12.21 分差保持；
- HTML 80.65、PDF 87.25；英文 81.01、中文 87.94。

产物：

- `evals/strategy_report/results/v2_core_26_unified_rules_v5/summary.json`
- `evals/strategy_report/results/v2_core_26_unified_rules_v5/layered_summary.json`
- `evals/strategy_report/results/v2_core_26_unified_rules_v5/layered_summary.md`
- `evals/strategy_report/SESSION_HANDOFF_20260619_V2.md`

失败与警告：

- 初始审计脚本两次因旧 JSON 字段假设触发 `KeyError`，修正后成功；
- 一次证据打印触发 GBK `UnicodeEncodeError`，改用 UTF-8 stdout 后成功；
- 一次 Windows `rg` glob 写法失败，改用目录和 `-g` 后成功；
- legacy r4 出现 State Street Alternatives 临界回归，已保留失败产物并在
  legacy r5 修复；
- GSAM Active ETF 仍有已知、非致命 MuPDF structure-tree warning。

下一步：

1. 审查 State Street Macro/Fixed Income 的 source/numeric；
2. 审查 Morgan Stanley sectionization 和 disclaimer/content 边界；
3. 判断 J.P. Morgan Energy 的任务边界并审计 head/tail 文本压缩；
4. rules-only 收敛后再运行分层 LLM/VLM。

### 2026-06-19 — 修复 reasoning/archetype/HTML 装饰图误判并建立 legacy r3 基线

状态：完成

完成：

- 修复中英文 sentence splitting 与 `v2_checks.py` 中的乱码词表；
- strategy reasoning 改为输出 thesis/mechanism/implication/risk 的句子级证据；
- 修复 `Carbon Brief` 导致 55 页 J.P. Morgan 报告被误判为 brief；
- 使用标题/主标题和图表密度识别 chartbook；
- rules-only HTML visual gate 排除无任何图表元数据的头像、hero 和推荐缩略图；
- 全量生成 `v2_core_26_unified_rules_v3` 与分层摘要。

验证：

- 重点探针全部完成，无 report-level failure；
- 全量 26/26 completed，0 failures；
- `py_compile` 检查 `v2_checks.py`、`chart_qa.py`、`run_v2_testset.py` 和
  `summarize_v2_testset.py`：退出码 0；
- State Street Alternatives：66.00 → 76.49，误拒修复；
- BlackRock chartbook：77.26 → 87.26，误拒修复；
- Morgan Stanley Digital Assets：62.57 → 69.15，仍拒绝；
- J.P. Morgan Energy：66.66 → 69.33，仍拒绝；
- 已知生成质量对照保持 optimized > baseline，差距扩大到 14.62；
- HTML 视觉对象 106 个，72 个计分，34 个高置信装饰图排除。

产物：

- `evals/strategy_report/results/v2_core_26_unified_rules_v3/summary.json`
- `evals/strategy_report/results/v2_core_26_unified_rules_v3/layered_summary.json`
- `evals/strategy_report/results/v2_core_26_unified_rules_v3/layered_summary.md`
- `evals/strategy_report/SESSION_HANDOFF_20260619.md`

发现：

- HTML 平均 80.18，PDF 87.82；
- 英文平均 80.62，中文 88.59；
- gate 通过数从 v2 的 17/26 增至 v3 的 20/26；
- strategy reasoning 有 9/26 达到 1.0，下一轮必须检查饱和度；
- 剩余拒绝集中在 State Street 三份临界样本、Morgan Stanley 两份 brief
  和 J.P. Morgan Energy。
- `git status --short` 被 Git 的 `dubious ownership` 安全检查拒绝；未修改
  全局 `safe.directory`；随后通过单次 `git -c safe.directory=... status`
  完成只读检查，未执行 stage、commit 或其他 Git 写操作；
- 一次合并指标核对命令因 PowerShell 引号转义触发 `SyntaxError`，纠正命令后
  退出码 0，并再次确认 26 completed、0 failures、20 gate pass、9 个
  strategy reasoning 1.0。

下一步：

1. 检查 1.0 strategy reasoning 的饱和与排序能力；
2. 审查 State Street 的 source/numeric/structure；
3. 审查 Morgan Stanley brief 的 sectionization 和正文边界；
4. 审查 J.P. Morgan Energy 26k 文本截断；
5. rules-only 收敛后再运行分层 LLM/VLM。

### 2026-06-18 — 修复 Windows 长路径并建立有效的 26 份统一基线

状态：完成

完成：

- 修改 `html_runtime_adapter_v2.py`，让 Chrome 打开短临时浏览副本；
- 正式 `normalized.html`、截图、JSON 和评估结果仍写回原长路径；
- 增加导航错误检测，若 `Page.navigate` 返回错误或最终 URL 为
  `chrome-error://`，立即抛出异常，避免产生伪成功分数；
- manifest 增加可审计的 `browser_navigation`；
- 新增 `summarize_v2_testset.py`，按 format/language/archetype/subtype
  输出分层均值、范围、gate 通过率和维度均值；
- 完成 26 份核心集统一 rules + chart extraction 新基线。

验证：

- `python -m py_compile`：两个修改/新增脚本均通过；
- canvas fixture：166 字符、2 个视觉对象，动态 canvas 正常捕获；
- 既有 Runtime Adapter 回归集：7/7 completed，耗时 34.97 秒；
- GSAM Backdrop adapter 长路径回归：50,062 字符、24 个标题、10 个视觉对象；
- GSAM Backdrop 完整 Verifier 回归：91.65、Gold、gate passed；
- 全量命令：`run_v2_testset.py --out-dir .../v2_core_26_unified_rules_v2`；
- 全量结果：26/26 completed，0 failures；
- 未发现 `chrome-error://chromewebdata/` 或 `"text_length": 46`；
- GSAM Active ETF 仍输出已知、非致命的 MuPDF structure-tree warning。

产物：

- `evals/strategy_report/results/v2_core_26_unified_rules_v2/summary.json`
- `evals/strategy_report/results/v2_core_26_unified_rules_v2/layered_summary.json`
- `evals/strategy_report/results/v2_core_26_unified_rules_v2/layered_summary.md`

发现：

- HTML 平均分 75.41，PDF 84.07；
- 英文平均分 75.52，中文 85.39；
- 当前最值得优先排查的是 strategy reasoning、sectionization/context binding、
  brief/chartbook archetype 适配和 HTML visual QA，而不是继续改测试集。

下一步：

1. 对 State Street 四份 HTML、两个 Morgan Stanley brief、两个 chartbook 和
   J.P. Morgan Energy 做模块级错误归因；
2. 优先修 extractor/context binding/archetype-aware scoring 的明确错误；
3. 每次修改后重跑完整 26 份 rules 基线；
4. 工程规则稳定后再分层启用 LLM/VLM 模块，暂不启动人类对齐。

### 2026-06-18 — 冻结 10 份真实 HTML、重构 26 核心集并定位统一基线故障

状态：部分完成；测试集阶段完成，统一基线被明确工程故障阻塞

完成：

- 冻结 10 份真实机构高质量 HTML，来自 GSAM、State Street、Morgan Stanley；
- 每份冻结 HTML 均完成内容审查、人工视觉审查、Runtime Adapter V2 和资源审计；
- HTML 资源审计最新复跑 10/10 admitted；
- 将核心集重构为 26 份：12 HTML、14 PDF、14 英文、12 中文；
- HTML 中包含 10 份真实机构样本和 2 份生成历史对照，覆盖 9 个 subtype；
- 核心集硬审计最新复跑 26/26 admitted，文件 hash 全部唯一，hard gate errors 为 0；
- 完成第一版统一 rules + chart extraction 运行，26/26 无 report-level exception；
- 新增 session 交接文档：
  [`evals/strategy_report/SESSION_HANDOFF_20260618.md`](evals/strategy_report/SESSION_HANDOFF_20260618.md)。

验证：

- 命令：`audit_localized_html_resources.py --sample-id ... --out ...localized_html_resource_audit_frozen10.json`
- 结果：10/10 admitted；
- 命令：`audit_v2_testset.py --selection ... --out ...`
- 结果：26/26 admitted，10 份高质量真实 HTML，0 hard gate error；
- 统一运行产物：
  [`evals/strategy_report/results/v2_core_26_unified_rules_v1/summary.json`](evals/strategy_report/results/v2_core_26_unified_rules_v1/summary.json)；
- 核心 review：
  [`evals/strategy_report/results/v2_core_26_review/`](evals/strategy_report/results/v2_core_26_review/)。

发现：

- 第一版统一运行虽然完成 26/26，但 11/12 HTML 的结果无效；
- 这些 HTML 的 Runtime Adapter 实际打开了 `chrome-error://chromewebdata/`，
  报告 `ERR_FILE_NOT_FOUND`，text length 仅 46；
- 典型失败 `normalized.html` 绝对路径长 264 字符，唯一正常真实 HTML 路径长
  258 字符，根因高度指向 Windows/Chrome 长路径处理；
- 11 个 HTML 因此错误得到相同的 26.14 分，不能用于任何质量或格式偏差结论；
- PDF rules 结果可作为诊断参考，但完整统一基线必须整体重跑。

未完成或阻塞：

- Runtime Adapter 尚未使用短临时浏览器工作路径；
- `v2_core_26_unified_rules_v1` 不是有效统一基线；
- LLM/VLM 分层模块尚未在修复后的 26 核心集上运行；
- format/language/archetype/subtype 误差分析尚未开始。

下一步：

1. 修复 `html_runtime_adapter_v2.py` 的长路径导航问题；
2. 先回归 `v2_html_gsam_backdrop_2026`，确认 text 从 46 恢复到约 50k；
3. 全量生成 `v2_core_26_unified_rules_v2`；
4. 建立分层结果摘要，再开始 Verifier 偏差修复；
5. 暂不启动人类对齐。

### 2026-06-18 — 独立资源归档、State Street 收敛与 BlackRock 归因

状态：部分完成

完成：

- 将本地化资源从 data URI 改为独立 `assets/` 文件；
- 新增逐资源 manifest，记录原 URL、本地路径、MIME、SHA-256、字节数、状态和失败原因；
- 新增
  [`evals/strategy_report/audit_localized_html_resources.py`](evals/strategy_report/audit_localized_html_resources.py)，
  自动验证文件存在、hash、远程资源引用和缺失引用；
- 修复 `display:none` 丢失、空视觉壳、固定高度文本溢出和响应式重复内容问题；
- 新增可配置 `flow_layout`，使 State Street 正文、标题和作者区连续离线渲染；
- 新增 `live` 捕获模式，验证浏览器动态渲染后的 DOM 和资源固化路径；
- GSAM 75/75、State Street 14/14 资源成功下载；
- Morgan Stanley 下载 133 个资源，15 个旧版字体变体被标记为已解释的非关键失败；
- 三份样本资源审计 3/3 admitted；
- BlackRock 两个候选经 live 捕获确认均为 PDF 报告壳，已设置 `enabled: false`。

验证：

- 命令：`localize_strategy_html.py --sample-id html_gsam_outlook_backdrop_2026`
- 命令：`localize_strategy_html.py --sample-id html_ssga_macro_outlook_2026`
- 命令：`html_runtime_adapter_v2.py --html ...`
- 命令：`audit_localized_html_resources.py --sample-id ...`
- 结果：GSAM Runtime 无 warning、10 个 visual object；State Street Runtime 无
  warning、3 个 visual object；Morgan Stanley Runtime 无 warning、4 个 visual
  object；资源审计 3/3 admitted。
- 产物：
  [`evals/strategy_report/results/localized_html_resource_audit_pilot.json`](evals/strategy_report/results/localized_html_resource_audit_pilot.json)、
  [`evals/strategy_report/results/html_runtime_v2_pilot_gsam_final/`](evals/strategy_report/results/html_runtime_v2_pilot_gsam_final/)、
  [`evals/strategy_report/results/html_runtime_v2_pilot_ssga_admitted/`](evals/strategy_report/results/html_runtime_v2_pilot_ssga_admitted/)。

发现：

- BlackRock 的 Policy Pivot 和 Europe Investment Renaissance 页面并非完整 HTML
  报告，而是网页摘要、作者信息和 PDF 链接；继续调整捕获器不能把它们变成合格样本；
- live 捕获模式技术上可用，但仍必须由内容审查判断页面是否实际含完整正文；
- `flow_layout` 应作为显式 profile 选项使用，不能默认应用于所有站点；
- 当前已有 GSAM、State Street、Morgan Stanley 三家机构通过试点，可以进入批量扩展。

未完成或阻塞：

- `srcset` 已降级为当前渲染资源，必要脚本尚未作为独立可执行资源归档；
- 中文真实机构 HTML 候选仍不足。

下一步：

1. 将 State Street flow-layout 配置推广到同系列候选并逐份复核；
2. 从 J.P. Morgan 等候选加入第四、第五家机构；
3. 批量本地化首批 8–10 个启用候选；
4. 补充中文真实机构 HTML 来源。

### 2026-06-18 — HTML 候选清点与三机构本地化试点

状态：部分完成

完成：

- 新增可重复运行的 HTML candidate inventory 构建器；
- 清点 110 个唯一归档 URL，记录机构、语言、subtype、正文长度、视觉对象和资源状态；
- 形成 22 个明确值得进一步本地化的报告级候选，覆盖 5 家机构和 15 类 subtype；
- 修复本地化器的删除节点后属性访问异常、CSS 资源重复请求和 computed style
  节点错位问题；
- 对 GSAM、State Street、BlackRock 完成三机构端到端试点和人工截图复核。

验证：

- 命令：`.\.venv\Scripts\python.exe evals/strategy_report/build_html_candidate_inventory.py`
- 结果：110 个候选成功审计，0 个解析失败；
- 命令：`.\.venv\Scripts\python.exe evals/strategy_report/localize_strategy_html.py --sample-id ...`
- 结果：3/3 完成本地化执行；
- 命令：`.\.venv\Scripts\python.exe evals/strategy_report/html_runtime_adapter_v2.py --html ...`
- 产物：
  [`evals/strategy_report/results/v2_html_candidate_inventory.json`](evals/strategy_report/results/v2_html_candidate_inventory.json)、
  [`evals/strategy_report/HTML_LOCALIZATION_PILOT_20260618.md`](evals/strategy_report/HTML_LOCALIZATION_PILOT_20260618.md)。

发现：

- 静态指标会将部分机构首页、聚合页和 transcript 页面误判为高优先级，人工内容判断仍不可省略；
- GSAM 修复后正文和基本布局可读，但视觉对象未完整保留；
- State Street 存在大面积空白和交互控件错误静态化；
- BlackRock 核心正文依赖动态加载，当前静态归档只能恢复页面壳；
- 当前 22 个明确候选全部为英文，中文高质量真实机构 HTML 仍是明显覆盖缺口。

未完成或阻塞：

- 三机构试点尚未达到“正文和关键视觉与原页一致”的完成标准；
- 尚未建立包含 MIME、hash 和失败原因的逐资源本地文件 manifest；
- 全量候选的人工内容判断尚未完成。

下一步：

1. 改造资源本地化为独立文件与逐资源 manifest；
2. 修复 State Street 内容根选择及交互控件静态化；
3. 为 BlackRock 增加浏览器渲染后的 DOM/网络资源归档路径；
4. 补充真实中文机构 HTML 候选并继续人工筛选。

### 2026-06-18 — 建立第一版 24 样本核心集

状态：完成，但该版本因 HTML 覆盖不足，已被判定需要重构。

完成：

- 建立 24 份 V2 报告级样本；
- 12 中文、12 英文；
- 22 PDF、2 自包含 HTML；
- 建立 selection manifest、硬审计脚本和批量 V2 runner；
- 生成 PDF 首/中/末页视觉抽检；
- 完成全量 deterministic V2 和 chart extraction。

验证：

- `audit_v2_testset.py`：24/24 admitted，hash 全部唯一；
- `run_v2_testset.py --no-extract-charts`：24/24 完成；
- `run_v2_testset.py`：24/24 完成；
- 基线：
  [`evals/strategy_report/results/v2_core_24_rules_v1/summary.json`](evals/strategy_report/results/v2_core_24_rules_v1/summary.json)。

发现：

- 测试集过度偏向 PDF；
- 仅有两份 HTML，且都是较早的本地生成报告，不能代表目标质量；
- 高质量英文深度报告和中文短报告之间存在可疑的评分反差；
- GSAM Active ETF PDF 会产生非致命 MuPDF structure-tree warning，但完整解析和
  评测成功，保留为 robustness case。

用户反馈和新决策：

- HTML 是重点测试对象；
- 下一步必须补充至少 10 份高质量 HTML；
- 可以裁撤部分 PDF；
- 后续必须持续维护本开发目标文档，记录每轮摘要、下一步计划和完成状态。

下一步：

1. 执行第 7 节 P0 HTML 候选清点；
2. 实现/增强真实 HTML 资源本地化；
3. 冻结至少 10 份高质量 HTML 后重构核心测试集；
4. 再建立新的统一 V2 基线。
