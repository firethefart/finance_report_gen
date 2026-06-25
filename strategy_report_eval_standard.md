# 策略报告评估标准设计

日期：2026-06-08  
适用对象：由 agent / skill pipeline 生成的金融策略研究报告，尤其是主题策略、行业格局策略、资产配置策略、年度/季度展望、市场专题报告。  
核心目标：建立一套可以服务 skill iteration 的评估标准，而不是只给最终报告一个主观总分。

## 0. 设计结论

本项目的策略报告评估应采用三套互相嵌套的标准：

1. **Maximum / Golden Standard 评测方案**  
   这是理想上限，用于定义“什么是最好的策略报告评测”。它要求完整证据池、数据核验、专家评审、自动化校验、同类机构对标、情景反事实测试和 skill patch 映射。它不追求低成本，而是追求最可靠。

2. **自动化评测方案**  
   这是可规模化版本，尽量保留 maximum 方案中可程序化、可 LLM judge、可浏览器验证、可结构抽取的部分。它适合每次 skill 迭代后的 CI / regression test。

3. **人类评审方案**  
   这是专家可执行版本，保留最关键判断项，减少表单负担，重点让专家反馈结构化，以便进入 skill iteration。它适合高价值样本、标杆报告、版本门控和争议样本复核。

优先级是：**Maximum 定义北极星，自动化负责规模，人类评审负责专业判断与校准。**

## 1. 策略报告的垂直场景定义

策略报告不是单家公司财报点评，也不是普通行业文章。它的核心产出是：

- 对某一市场、行业、主题、资产类别或政策变量的系统性判断。
- 对未来一段时间的基准情景、上行情景、下行情景进行推演。
- 将事实和判断映射到投资研究含义，例如行业格局、资产配置、风格偏好、产业链位置或组合动作。
- 明确哪些证据支持结论，以及什么条件会推翻结论。

因此，策略报告评估不能只问“文字通不通顺”，而要问：

- 观点是否像专业策略研究，而不是资讯综述？
- 证据是否足以支持策略判断？
- 是否区分事实、解释、预测和建议？
- 是否给出反证条件和风险情景？
- 图表是否服务于观点，而不是装饰？
- 报告是否有决策价值和合规边界？

## 2. 从现有 benchmark 吸收的方法

根目录 `05_financial_benchmark_eval_report.md` 对现有 benchmark 的总结，可以直接转化为本标准的底层方法。

| 来源方法 | 可吸收思想 | 在策略报告评估中的转化 |
| --- | --- | --- |
| Template-Based Financial Report Generation | coverage、section completion、template adherence | 检查策略报告是否包含核心章节：观点、证据、情景、风险、图表、来源 |
| FinLFQA | evidence support、numerical reasoning trace、attribution quality | 检查每个重要观点是否有证据链，数字推理是否可追溯 |
| Fin-RATE | detail reasoning、cross-entity comparison、longitudinal tracking、error attribution | 检查跨公司、跨行业、跨时间比较是否正确，并区分错误来源 |
| BizFinBench | objective + subjective mixed metrics、bias-reduced judging | 自动指标和专家主观评分并行，避免只靠 LLM judge |
| FinVerBench | arithmetic、cross-statement linkage、YoY、magnitude perturbation | 对报告中的数字、比例、趋势、数量级做程序化核验 |
| FinChart-Bench | chart reasoning、spatial reasoning、chart QA | 检查金融图表是否能被正确理解，是否支持正文观点 |
| Chart2Code | reproduction、editing、long-table to chart、visual fidelity | 检查图表生成是否忠实于底层数据，并符合报告版式 |

本项目的关键增量是：**这些 benchmark 多数评估财务问答、财报生成或图表任务；我们需要把它们聚合成“策略研究报告”的垂直 rubric。**

## 3. 总体评分框架

建议采用 100 分制，并设置硬性红线。总分只用于排序和门控，真正重要的是分项错误类型与 skill patch 映射。

| 一级维度 | 权重 | 说明 |
| --- | ---: | --- |
| A. 策略问题定义与报告结构 | 10 | 是否明确报告类型、范围、时间窗、研究问题和章节结构 |
| B. 证据池与来源质量 | 15 | 来源是否权威、充分、可追溯，是否区分事实与观点 |
| C. 数据与事实准确性 | 15 | 数字、日期、实体、政策、交易案例、单位和口径是否正确 |
| D. 策略推理与观点质量 | 20 | 是否有清晰 thesis、机制解释、产业/资产映射、反证条件 |
| E. 情景分析与风险控制 | 10 | 是否有基准/上行/下行情景、关键变量、风险披露 |
| F. 图表、表格与可视化 | 15 | 图表是否正确、专业、服务观点，并有标题、单位、来源和口径 |
| G. 写作、版式与读者可用性 | 10 | 是否专业、可扫描、结构清楚、适合策略报告读者 |
| H. 合规与审慎表达 | 5 | 是否避免个性化建议、保证收益、过度结论和缺失披露 |

### 硬性红线

出现以下任一问题，报告不能进入“可交付”状态，即使总分较高：

- 重大事实错误，例如政策、公司、交易对象或日期错误。
- 重大数字错误，例如数量级错误、同比/环比计算错误、单位错配。
- 关键结论没有任何来源支持。
- 将传闻写成事实。
- 给出明确个性化买卖建议或保证收益。
- 图表展示的数据与正文结论相反。
- 来源链接失效且无法追溯核心证据。

## 4. Maximum / Golden Standard 评测方案

### 4.1 定位

Maximum 方案是最完整、最严格的评估方案，用于：

- 定义本项目的质量上限。
- 建立标杆数据集。
- 做重要 skill 版本发布前的门控。
- 训练和校准自动化评测器与人类评审表单。

它不以成本最低为目标，而以“尽可能接近头部金融机构研究质控”为目标。

### 4.2 输入材料

每个评测样本应包含：

- 用户 query。
- 生成的最终报告，例如网页、PDF、PPT、Markdown。
- agent 执行轨迹，包括搜索、文件读取、计算、图表生成、QA。
- 中间文件：sources、data、analysis script、charts、tables。
- 参考资料包：官方来源、可接受的新闻来源、行业资料、同类优秀报告样例。
- 任务元信息：报告类型、时间窗、覆盖市场、目标读者、输出格式。

### 4.3 评测角色

Maximum 方案建议至少包含四类评审角色：

1. **金融策略专家**  
   判断策略 thesis、行业格局、资产/产业映射、情景分析是否专业。

2. **数据核验员 / 财务分析员**  
   检查数字、日期、交易案例、单位、同比环比、来源对应关系。

3. **图表与版式评审**  
   检查图表选择、图表数据、视觉表达、页面布局、可读性。

4. **合规/风险评审**  
   检查是否有过度承诺、个性化建议、利益冲突、免责声明缺失。

### 4.4 Maximum 详细 rubric

#### A. 策略问题定义与报告结构，10 分

| 子项 | 分值 | 5 分/满分标准 |
| --- | ---: | --- |
| 报告类型清晰 | 2 | 明确是主题策略、行业策略、资产配置、年度展望等 |
| 范围与时间窗明确 | 2 | 覆盖对象、时间窗、市场边界清楚 |
| 核心问题明确 | 3 | 开篇能说明报告要解决的策略问题 |
| 章节结构完整 | 3 | 包含摘要、证据、推理、情景、风险、来源 |

典型扣分：

- 把策略报告写成新闻综述。
- 没有时间窗，导致“最近”“未来”模糊。
- 标题和正文研究对象不一致。

#### B. 证据池与来源质量，15 分

| 子项 | 分值 | 满分标准 |
| --- | ---: | --- |
| 来源权威性 | 4 | 优先使用监管、交易所、公司公告、官方政策、可信新闻 |
| 来源充分性 | 3 | 足以支撑主要结论，关键变量不缺证 |
| 来源可追溯性 | 3 | 每个关键事实有链接、日期、出处或文件路径 |
| 事实/观点分离 | 3 | 明确区分公开事实、研究判断、假设 |
| 冲突处理 | 2 | 对不同来源的口径差异有说明 |

典型扣分：

- 来源只有泛泛新闻，没有官方证据。
- 引用链接和正文事实不匹配。
- 把媒体推测写成已发生事实。

#### C. 数据与事实准确性，15 分

| 子项 | 分值 | 满分标准 |
| --- | ---: | --- |
| 实体准确 | 3 | 公司、交易所、政策、标的名称正确 |
| 时间准确 | 3 | 公告日期、政策日期、报告日期准确 |
| 数字准确 | 4 | 金额、比例、数量级、单位正确 |
| 计算准确 | 3 | 增长率、占比、情景权重等计算正确 |
| 口径一致 | 2 | 币种、单位、时间窗口和样本范围一致 |

典型扣分：

- 用错公司或交易标的。
- 交易状态写错，如“拟收购”写成“已完成”。
- 亿元/万元、千瓦/兆瓦、工作日/自然日混淆。

#### D. 策略推理与观点质量，20 分

| 子项 | 分值 | 满分标准 |
| --- | ---: | --- |
| thesis 清晰 | 4 | 有一句可被复述的核心判断 |
| 传导机制完整 | 4 | 说明政策、产业、交易样本如何传导到格局变化 |
| 产业/资产映射 | 4 | 能落到产业链环节、资产类别、风格或组合含义 |
| 横向比较 | 3 | 能比较公司、行业、区域、资产或历史阶段 |
| 反证条件 | 3 | 说明什么情况下判断失效 |
| 推理克制 | 2 | 不做证据之外的过度外推 |

典型扣分：

- 只有“利好行业”，没有机制。
- 只列案例，不抽象格局影响。
- 没有反证条件。
- 结论明显超出证据支持。

#### E. 情景分析与风险控制，10 分

| 子项 | 分值 | 满分标准 |
| --- | ---: | --- |
| 基准情景 | 2 | 说明最可能路径 |
| 上行/下行情景 | 3 | 至少给出一个上行和一个下行路径 |
| 关键变量 | 2 | 明确政策、订单、回款、估值、利率等驱动变量 |
| 风险披露 | 2 | 覆盖政策、市场、公司、数据和执行风险 |
| 概率/置信表达 | 1 | 使用概率、区间或条件表达，而非绝对判断 |

典型扣分：

- 只有单一乐观路径。
- 风险提示空泛。
- 概率写得像精确预测但没有方法说明。

#### F. 图表、表格与可视化，15 分

| 子项 | 分值 | 满分标准 |
| --- | ---: | --- |
| 图表目标明确 | 2 | 每张图都回答一个分析问题 |
| 图表数据正确 | 4 | 图表与底层数据、正文一致 |
| 图表类型合适 | 2 | 条形、折线、矩阵、表格等选择合理 |
| 标题/单位/来源完整 | 3 | 标题、单位、时间窗、来源、口径齐全 |
| 视觉专业 | 2 | 配色克制、可读、无拥挤和重叠 |
| 图文联动 | 2 | 正文明确解释图表含义 |

典型扣分：

- 图表是装饰，没有分析目的。
- 没有单位或数据截止日期。
- 图表和正文结论不一致。
- 页面在移动端横向溢出或文字重叠。

#### G. 写作、版式与读者可用性，10 分

| 子项 | 分值 | 满分标准 |
| --- | ---: | --- |
| 执行摘要质量 | 2 | 摘要可独立阅读 |
| 语言专业 | 2 | 金融研究语气准确，避免口水化 |
| 结构可扫描 | 2 | 标题、表格、卡片、段落层级清楚 |
| 读者决策价值 | 2 | 能帮助读者判断下一步关注什么 |
| 交付体验 | 2 | 输出格式可直接渲染，无明显排版问题 |

典型扣分：

- 长段堆砌，缺少可扫描结构。
- 使用营销话术或情绪化词汇。
- 首屏看不出报告主题。

#### H. 合规与审慎表达，5 分

| 子项 | 分值 | 满分标准 |
| --- | ---: | --- |
| 非个性化建议边界 | 1 | 明确不构成个性化投资建议 |
| 预测审慎 | 1 | 避免保证收益和确定性表达 |
| 来源与限制说明 | 1 | 说明公开资料限制 |
| 风险与不确定性 | 1 | 关键风险完整 |
| 敏感信息处理 | 1 | 不使用未授权或不可公开信息 |

### 4.5 Maximum 的评测流程

1. **任务归档**  
   固定 query、输出文件、时间戳、模型/skill 版本、数据源版本。

2. **自动预检查**  
   检查文件可打开、链接可访问、章节存在、图表存在、来源数量、HTML/PDF 渲染。

3. **证据核验**  
   对所有关键事实和数字抽样或全量核验，标注来源。

4. **专家打分**  
   金融策略专家按完整 rubric 评分，并写结构化 issue。

5. **图表与版式评审**  
   使用截图、DOM、PDF 渲染或人工视觉检查进行评估。

6. **合规审查**  
   对投资建议、保证收益、风险披露、来源限制做红线检查。

7. **错误归因**  
   每个问题必须标注 error type、pipeline layer、severity、suggested skill patch。

8. **版本门控**  
   只有总分、红线和关键分项都达标，skill 版本才能接受。

### 4.6 Maximum 的接受标准

建议分级：

| 等级 | 条件 |
| --- | --- |
| Gold | 总分 >= 90，无红线问题，D/F/H 单项不低于 80% |
| Silver | 总分 80-89，无红线问题，核心结论可用 |
| Bronze | 总分 70-79，无重大事实错误，但专业性或图表仍需修 |
| Reject | 总分 < 70，或出现任一红线问题 |

对于 skill iteration，建议只有 Gold / Silver 样本可作为正样本沉淀；Reject 样本进入失败库。

## 5. 自动化评测方案

### 5.1 定位

自动化评测不是替代 maximum 方案，而是把其中可规模化的部分变成回归测试。它适合：

- 每次 skill 修改后的快速验证。
- 多版本报告横向比较。
- 自动发现明显错误。
- 生成给专家复核的初筛报告。

### 5.2 自动化可覆盖范围

| 维度 | 自动化可行性 | 推荐方法 |
| --- | --- | --- |
| 文件可渲染 | 高 | HTML/PDF/PPTX 打开检查、截图、DOM 检查 |
| 章节完整性 | 高 | DOM/Markdown 结构解析 |
| 来源链接数量与可访问性 | 高 | URL 抽取、HTTP 状态、来源域名分类 |
| 日期/实体一致性 | 中高 | NER + 规则 + LLM judge |
| 数字/单位一致性 | 中高 | 数字抽取 + 来源表对照 + 规则校验 |
| 证据支持 | 中 | claim extraction + citation matching + LLM judge |
| 策略 thesis 质量 | 中 | LLM rubric judge，需要校准 |
| 情景分析完整性 | 高 | 结构检查 + 关键词/章节检查 |
| 图表数据正确性 | 中 | 结构化图表数据可高；截图图表较难 |
| 视觉专业性 | 中低 | screenshot checks + LLM/VLM judge |
| 合规红线 | 中高 | 规则词表 + LLM safety/compliance judge |

### 5.3 自动化评分结构

自动化版本建议保留 100 分，但权重略向可检验项倾斜。

| 维度 | 权重 | 自动检测信号 |
| --- | ---: | --- |
| Structure completeness | 12 | 是否有标题、摘要、证据、情景、风险、来源 |
| Source and citation quality | 18 | 来源数量、权威来源占比、链接状态、claim-citation 匹配 |
| Fact and numeric checks | 18 | 日期、实体、数字、单位、百分比、交易状态 |
| Strategy reasoning quality | 16 | thesis、机制、产业映射、反证条件，由 LLM judge |
| Scenario and risk coverage | 10 | 基准/上行/下行、关键变量、风险类别 |
| Chart and visual QA | 14 | 图表数量、标题/单位/来源、溢出、可读性、图文一致 |
| Writing and layout | 7 | 可扫描性、专业语气、重复/空话 |
| Compliance | 5 | 非建议声明、禁止性措辞、风险披露 |

### 5.4 自动化评测模块

#### Module 1: Render & Delivery Check

检查：

- HTML 是否可打开。
- 页面是否有横向溢出。
- 移动端/桌面端是否文本重叠。
- 标题、section、table、chart、source 数量。
- 是否存在明显乱码。

输出：

```json
{
  "render_ok": true,
  "sections": 10,
  "tables": 2,
  "sources": 10,
  "has_horizontal_overflow": false,
  "encoding_issue": false
}
```

#### Module 2: Section Coverage Check

必需章节：

- 标题 / 报告类型 / 时间窗。
- 核心观点或执行摘要。
- 证据池或来源支撑。
- 策略推理。
- 情景分析或未来路径。
- 风险提示。
- 来源列表。
- 免责声明。

评分：

- 每个必需章节 0/1。
- 章节存在但内容空泛，LLM judge 可给 0.5。

#### Module 3: Source Quality Check

自动抽取所有链接，分类：

- 官方监管/交易所/政府：高权重。
- 公司公告/投资者关系：高权重。
- 主流新闻/财经媒体：中权重。
- 第三方数据库/转载：中低权重。
- 无来源或失效链接：扣分。

检查：

- 链接是否可访问。
- 来源日期是否出现在正文或来源列表。
- 核心结论附近是否有来源引用。

#### Module 4: Claim-Citation Alignment

流程：

1. 抽取重要 claim。
2. 判断 claim 类型：事实、数字、政策、交易案例、预测、观点。
3. 查找附近 citation 或来源表映射。
4. LLM 判断来源是否支持 claim。

输出：

```json
{
  "claim": "北交所重组简易审核程序下证监会注册决定时间为5个工作日",
  "claim_type": "policy_fact",
  "citation": "北交所重组审核规则修订公告",
  "support": "strong",
  "issue": null
}
```

#### Module 5: Numeric & Entity Consistency

规则检查：

- 数字单位：亿元、万元、%、bp、千瓦、兆瓦。
- 日期格式：绝对日期优先。
- 交易状态：拟收购、已公告、已审核、已注册、已完成。
- 百分比和数量级。
- 同一实体名称是否前后一致。

适合继承 FinVerBench 思路：

- arithmetic error
- temporal mismatch
- magnitude error
- entity mismatch
- unit mismatch

#### Module 6: Strategy Reasoning Judge

使用 LLM judge，但要求结构化评分，而不是一句“好/不好”。

评分项：

- thesis clarity
- mechanism quality
- industry mapping
- investment / research implication
- counterfactual condition
- over-claim discipline

judge prompt 必须要求引用报告中的具体句子作为证据，并输出 JSON。

#### Module 7: Scenario & Risk Check

检查：

- 是否有基准情景。
- 是否有上行/下行情景。
- 是否解释关键变量。
- 是否说明概率或置信度的主观性质。
- 风险是否覆盖政策、执行、市场、财务、数据限制。

#### Module 8: Chart QA

对网页报告：

- 检查 chart/table 是否存在标题。
- 检查是否有 note/source/unit。
- 检查图表附近是否有解释文本。
- 使用 DOM 和截图检查重叠/溢出。

对结构化图表：

- 检查图表数据是否来自表格。
- 检查图表数值和正文引用是否一致。

#### Module 9: Compliance Redline Check

规则词表 + LLM judge：

- 禁止“必涨”“稳赚”“无风险”“保证收益”等。
- 检查是否有“非个性化投资建议”声明。
- 检查预测是否有条件或风险边界。
- 检查是否把主观概率写成确定事实。

### 5.5 自动化评测输出格式

建议输出一个机器可读 JSON 和一个人类可读 Markdown。

JSON 示例：

```json
{
  "report_id": "bse_ma_new_energy_grid_v1",
  "overall_score": 86,
  "grade": "Silver",
  "redline_issues": [],
  "dimension_scores": {
    "structure": 11,
    "sources": 15,
    "facts": 16,
    "strategy_reasoning": 14,
    "scenario_risk": 9,
    "charts": 12,
    "writing_layout": 6,
    "compliance": 5
  },
  "issues": [
    {
      "issue_type": "missing_evidence",
      "severity": "medium",
      "location": "代表性交易样本",
      "description": "旭杰科技案例缺少直接官方公告来源。",
      "suggested_skill_patch": "research skill should require direct announcement or mark as media-reported."
    }
  ]
}
```

### 5.6 自动化门控标准

建议用于 CI 的标准：

- 总分 >= 80 才可进入人工抽检。
- 无 redline issue。
- Source quality >= 70%。
- Numeric/fact checks >= 85%。
- Compliance 必须满分或无高危问题。
- Chart QA 不得出现溢出、重叠、无标题、无单位的关键图表。

## 6. 人类评审方案

### 6.1 定位

人类评审版本要比 maximum 轻，但必须保留策略报告最关键判断：

- 像不像专业策略报告。
- 核心观点是否成立。
- 证据是否充分。
- 图表是否有用。
- 风险是否讲清。
- 哪些问题应该回流到 skill。

它不是让专家重写报告，而是让专家输出结构化反馈。

### 6.2 人类评审表单

#### Basic Info

| 字段 | 内容 |
| --- | --- |
| report_id | 报告编号 |
| report_type | 主题策略 / 行业策略 / 年度展望 / 资产配置等 |
| query | 用户原始问题 |
| reviewer | 评审人 |
| review_date | 日期 |
| version | 报告版本 |

#### Overall Ratings

| 项目 | 评分 1-5 | 说明 |
| --- | ---: | --- |
| Overall publish readiness |  | 是否可交付 |
| Strategy professionalism |  | 是否像专业策略研究 |
| Decision usefulness |  | 是否有研究/投资决策价值 |
| Evidence reliability |  | 证据是否可靠 |
| Visual communication |  | 图表和布局是否帮助理解 |

#### Core Rubric

| 维度 | 评分 1-5 | 专家需要判断的问题 |
| --- | ---: | --- |
| Strategy thesis |  | 核心观点是否清楚、有洞察、可被反驳 |
| Evidence support |  | 主要结论是否有足够证据 |
| Fact and data accuracy |  | 是否存在事实、日期、数字、单位错误 |
| Reasoning chain |  | 从事实到结论的逻辑是否完整 |
| Scenario and risk |  | 是否有基准/上行/下行情景和风险边界 |
| Charts and tables |  | 图表是否正确、专业、服务观点 |
| Writing and structure |  | 章节、语言、摘要、版式是否专业 |
| Compliance discipline |  | 是否有不当投资建议或过度承诺 |

### 6.3 Issue 标注格式

每条问题必须结构化：

```text
Issue Type:
Severity: blocker / high / medium / low
Location:
Evidence:
Why it matters:
Suggested fix:
Suggested skill patch:
```

### 6.4 Issue Type Taxonomy

建议固定以下错误类型：

| issue_type | 说明 | 回流层 |
| --- | --- | --- |
| query_misunderstanding | 误解用户问题或范围 | Layer 0/3 |
| missing_source | 缺少关键来源 | Layer 1 |
| wrong_source | 来源不支持 claim | Layer 1 |
| factual_error | 事实错误 | Layer 1/6 |
| numerical_error | 数字或计算错误 | Layer 2 |
| temporal_mismatch | 时间窗或日期错误 | Layer 1/2 |
| entity_mismatch | 公司、标的、行业对象错配 | Layer 1 |
| reasoning_gap | 推理链断裂 | Layer 3 |
| over_claim | 结论超出证据 | Layer 3/6 |
| missing_counterfactual | 缺少反证条件 | Layer 3 |
| missing_scenario | 缺少情景分析 | Layer 3 |
| weak_strategy_thesis | 核心观点弱或像资讯综述 | Layer 3 |
| chart_mismatch | 图表和数据/正文不一致 | Layer 4 |
| chart_design_issue | 图表类型或呈现不合适 | Layer 4 |
| label_unit_error | 标题、轴、单位、来源缺失或错误 | Layer 4 |
| layout_issue | 页面排版、重叠、可读性问题 | Layer 5 |
| compliance_issue | 投资建议、保证收益、披露不足 | Layer 6 |

### 6.5 人类评审门控

建议：

- 任何 blocker 直接 Reject。
- high 问题超过 2 个，Reject 或 Major Revision。
- 核心维度 Strategy thesis / Evidence support / Fact accuracy 任一低于 3 分，不能交付。
- Charts and tables 低于 3 分，若报告依赖图表，则不能交付。
- Compliance discipline 低于 4 分，不能交付。

### 6.6 人类评审输出

人类评审最终输出：

```json
{
  "report_id": "...",
  "publish_decision": "accept | minor_revision | major_revision | reject",
  "overall_scores": {
    "publish_readiness": 4,
    "strategy_professionalism": 4,
    "decision_usefulness": 4,
    "evidence_reliability": 3,
    "visual_communication": 4
  },
  "issues": [
    {
      "issue_type": "missing_source",
      "severity": "high",
      "location": "交易样本",
      "evidence": "某交易案例只有媒体概述，无公告链接",
      "suggested_fix": "补官方公告或降级为媒体报道观察",
      "suggested_skill_patch": "source collection rule: M&A transaction claims require official announcement when available"
    }
  ]
}
```

## 7. 三版方案之间的映射

| Maximum 维度 | 自动化保留方式 | 人类评审保留方式 |
| --- | --- | --- |
| 完整证据池 | 链接抽取、来源分类、claim-citation judge | 专家检查关键结论来源是否充分 |
| 数据核验 | 数字/单位/日期/实体规则检查 | 专家抽查关键数字 |
| 策略 thesis | LLM rubric judge | 专家 1-5 分 + issue |
| 传导机制 | LLM judge 检查政策/产业/交易/格局链条 | 专家判断逻辑是否像策略研究 |
| 情景分析 | 章节和关键词检查 + LLM judge | 专家判断情景是否合理 |
| 图表 QA | DOM、截图、标题/单位/来源检查 | 专家判断图表是否有用 |
| 合规审查 | 禁止词 + LLM compliance judge | 专家红线复核 |
| skill patch 映射 | issue_type 自动映射到 layer | 专家填写 suggested skill patch |

## 8. 面向本项目的落地建议

### 8.1 第一阶段：以两版北交所报告作为种子样本

已有样本：

- `generation_test/0/index.html`
- `generation_test/1/index.html`
- `generation_test/1/comparison.md`
- `generation_test/strategy_research_framework.md`

建议先用这两个版本做一次人工标注演练：

- 第 0 版作为 Bronze/Silver 之间样本。
- 第 1 版作为 Silver/Gold 候选样本。
- `comparison.md` 作为 skill iteration 的示范反馈。

### 8.2 第二阶段：建立小型 golden set

建议 20-50 个策略报告任务：

- 5 个宏观策略。
- 5 个行业格局策略。
- 5 个主题策略，例如 AI、新能源、并购重组、出海。
- 5 个资产配置/市场展望。
- 后续扩展到 50 个。

每个任务保留：

- query
- expected report type
- source pack
- key facts
- must-have sections
- prohibited mistakes
- reference reports or human notes

### 8.3 第三阶段：建立自动化 eval harness

建议目录：

```text
evals/strategy_report/
  cases/
    bse_ma_new_energy_grid.json
  rubrics/
    maximum_rubric.md
    auto_rubric.md
    human_review_form.md
  scripts/
    render_check.py
    source_check.py
    claim_citation_check.py
    numeric_entity_check.py
    chart_layout_check.py
    compliance_check.py
  results/
```

### 8.4 第四阶段：把评测结果接入 skill iteration

每个 issue 都映射到：

- pipeline layer
- skill name
- patch type
- severity
- acceptance gate

示例：

| issue_type | patch target | patch type |
| --- | --- | --- |
| missing_source | research skill | add source hierarchy rule |
| numerical_error | analysis skill / script | add verifier |
| weak_strategy_thesis | strategy-writing skill | add thesis template and examples |
| missing_counterfactual | strategy-writing skill | add counterfactual requirement |
| chart_mismatch | visualization skill | add data-chart consistency check |
| layout_issue | report-builder / web output skill | add responsive layout QA |
| compliance_issue | QA skill | add redline rule |

## 9. 推荐的最小可用版本

如果要快速落地，建议从以下最小闭环开始：

1. 人类评审表单先上线，收集 10-20 个结构化反馈。
2. 自动化先做 5 个模块：
   - render check
   - section coverage
   - source link check
   - compliance redline check
   - chart/layout overflow check
3. 将 issue taxonomy 固定下来。
4. 每次报告生成后产出：
   - `report.html`
   - `sources.json`
   - `eval_auto.json`
   - `human_review.json`
   - `skill_patch_suggestions.md`

这样就可以把“评估标准”转化为“可迭代系统”。

## 10. 最终建议

策略报告评估的难点不是写一个评分表，而是保证评分能反向推动 skill evolution。本项目应该坚持三条原则：

1. **从 maximum 方案定义质量上限。**  
   不被自动化能力限制住，先定义什么叫真正好的策略报告。

2. **自动化评测优先覆盖硬错误和结构问题。**  
   包括渲染、章节、来源、数字、图表、合规红线。自动化不要过度冒充专家。

3. **人类评审必须结构化。**  
   专家反馈不应停留在“写得不够专业”，而要落到 issue_type、location、severity、suggested_fix 和 suggested_skill_patch。

这套三层标准可以承接现有 benchmark 的方法，也能贴合策略报告这个垂直场景，并且天然服务后续 skill iteration。

