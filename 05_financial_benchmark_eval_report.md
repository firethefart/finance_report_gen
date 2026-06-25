# 金融财报 / 图表 / 报表生成评测调研报告

## 目标

本报告调研 2025-2026 年与以下主题直接相关的 benchmark 与评测工作：

- 金融财报生成
- 金融长文本问答 / 报告生成
- 金融报表一致性验证
- 金融图表理解 / 图表生成

报告重点不是“谁分数最高”，而是总结这些工作使用了什么评测模式、什么 rubric 结构，以及这些 rubric 如何转化为我们后续的：

1. 专家评审模板
2. 结构化反馈格式
3. 自动化评测模板

## 选取原则

我优先选取 2025-2026 的公开工作，覆盖三类能力：

1. **财报 / 报告生成**
2. **金融文本与 SEC 披露理解**
3. **金融图表理解 / 图表生成**

最终选出 6 篇主工作，再补 1 篇通用图表生成 benchmark 作为方法学参考。

---

## 一、核心工作清单

| 工作 | 类型 | 主要评测对象 | 核心 rubric 关键词 |
|---|---|---:|---|
| [Template-Based Financial Report Generation in Agentic and Decomposed Information Retrieval](https://arxiv.org/abs/2504.14233) | 财报生成 | 模板化金融报告 | coverage, section completion, template adherence |
| [FinLFQA: Evaluating Attributed Text Generation of LLMs in Financial Long-Form Question Answering](https://arxiv.org/abs/2510.06426) | 金融长文本生成 | 带引用的长答案 | evidence, numerical reasoning, domain knowledge, attribution quality |
| [Fin-RATE: A Real-world Financial Analytics and Tracking Evaluation Benchmark for LLMs on SEC Filings](https://arxiv.org/abs/2602.07294) | SEC / 披露分析 | 多文档、跨时期、跨主体分析 | detail reasoning, cross-entity comparison, longitudinal tracking, error attribution |
| [BizFinBench: A Business-Driven Real-World Financial Benchmark for Evaluating LLMs](https://arxiv.org/abs/2505.19457) | 广义金融能力 | 数值 / 推理 / 抽取 / 预测 / QA | objective + subjective metrics, bias-reduced judging |
| [FinVerBench: Benchmark Validity and Calibration in Large Language Model Financial Statement Verification](https://arxiv.org/abs/2605.29586) | 财务报表验证 | 数值一致性与校准 | arithmetic, cross-statement linkage, year-over-year, magnitude perturbations |
| [FinChart-Bench: Benchmarking Financial Chart Comprehension in Vision-Language Models](https://arxiv.org/abs/2507.14823) | 金融图表理解 | 真实金融图表 | TF / MC / QA, chart reasoning, spatial reasoning |
| [Chart2Code: From Charts to Code: A Hierarchical Benchmark for Multimodal Models](https://arxiv.org/abs/2510.17932) | 通用图表生成参考 | 图表复现 / 编辑 / 长表转图 | reproduction, editing, long-table to chart, code correctness, visual fidelity |

---

## 二、逐篇工作梳理

### 1. Template-Based Financial Report Generation in Agentic and Decomposed IR

链接: [arXiv](https://arxiv.org/abs/2504.14233)

#### 任务设定

这篇工作聚焦“模板化金融报告生成”，输入是 earnings release，输出是遵循预定义多 section 模板的结构化财报。

论文比较了两种工业常见路线：

- `AgenticIR`: 多 agent 协作，整体读完整模板
- `DecomposedIR`: 把模板拆开，每个 section 变成独立 query 再逐段生成

#### 评测模式

论文在两个场景中做定量评估：

1. 金融数据集，没有直接 human reference
2. weather 数据集，有 expert-written reports

这说明它不是只测“像不像参考答案”，而是兼容：

- 无参考场景的覆盖型评估
- 有参考场景的更传统生成评估

#### rubric 范式

从摘要可直接归纳出的 rubric 关键词是：

- `broader coverage`
- `more detailed coverage`
- `template adherence`
- `section completeness`

#### 对我们的启发

这篇工作最有价值的不是模型结构，而是它明确告诉我们：

- 财报生成不适合只看摘要质量
- 应该按模板分 section 评
- coverage 和 detail 不能被一句“总体正确”替代

---

### 2. FinLFQA

链接: [arXiv](https://arxiv.org/abs/2510.06426)

#### 任务设定

FinLFQA 是金融领域的长文本问答 / 生成 benchmark，重点是：

- 回答复杂金融问题
- 输出长文本
- 要求可靠 attribution

#### 评测模式

它用 human annotation 评估 attribution 的三个关键方面：

1. 支持性证据是否来自 financial reports
2. 中间数值推理步骤是否合理
3. 领域知识是否真正参与了推理

这意味着它不是只看最终文本，而是同时看：

- 证据链
- 推理链
- 知识链

#### rubric 范式

FinLFQA 的 rubric 可以拆成两组：

##### Answer quality

- 正确性
- 完整性
- 逻辑连贯性

##### Attribution quality

- evidence support
- numerical reasoning trace
- domain knowledge grounding

论文还强调：

- fine-grained metrics 比粗粒度指标更能区分模型
- iterative refinement 只有在 external feedback 约束下才有帮助

#### 对我们的启发

这篇工作非常适合我们后续做“专家反馈结构化”时参考，因为它天然适合把专家意见拆成：

- 哪句缺证据
- 哪一步数值推理有问题
- 哪个领域知识用错了

---

### 3. Fin-RATE

链接: [arXiv](https://arxiv.org/abs/2602.07294)

#### 任务设定

Fin-RATE 基于 SEC filings，模拟金融分析师的真实工作流，覆盖三类任务：

1. 单文档内的细节推理
2. 跨主体比较
3. 同一公司跨时期 longitudinal tracking

#### 评测模式

论文明确指出，现有 benchmark 的问题在于：

- 只看孤立细节
- 不区分 retrieval failure / generation failure / reasoning failure / query misunderstanding

Fin-RATE 刻意把这些错误来源区分开。

#### rubric 范式

Fin-RATE 的 rubric 不是简单 QA，而是路径式诊断：

- detail-oriented reasoning
- cross-entity comparison
- longitudinal tracking

同时它强调错误可归因：

- retrieval failure
- generation inaccuracy
- domain reasoning mistake
- misunderstanding of context/query

#### 对我们的启发

这对专家标注特别重要，因为它告诉我们：

- 错误必须分类
- 不能只标“错了”
- 要标明是找错、算错、比错、时间线错，还是问题理解错

这会直接影响后续 skill iteration 的修补方向。

---

### 4. BizFinBench

链接: [arXiv](https://arxiv.org/abs/2505.19457)

#### 任务设定

BizFinBench 是一个更广义的真实金融 benchmark，覆盖 6,781 个中文金融问题，五大维度：

- numerical calculation
- reasoning
- information extraction
- prediction recognition
- knowledge-based QA

#### 评测模式

它采用 objective + subjective 的混合评测。

更重要的是，它引入了 `IteraJudge`，目的是减少 LLM 作为 judge 时的偏差。

#### rubric 范式

BizFinBench 的 rubric 很适合做“分项结构化反馈”：

- 数值计算是否正确
- 推理链是否合理
- 抽取是否完整
- 预测识别是否正确
- 知识问答是否符合金融常识

#### 对我们的启发

这篇工作最适合做我们未来的“专家评审表单骨架”：

- 一张表里可以分成数值、推理、抽取、预测、知识五块
- 每块都可以单独打分和写反馈

这比单一 overall score 更适合迭代 skill。

---

### 5. FinVerBench

链接: [arXiv](https://arxiv.org/abs/2605.29586)

#### 任务设定

FinVerBench 专注于 financial statement verification，也就是：

- 给定一组财务报表
- 判断是否数值一致
- 是否存在结构性错误

数据来自 43 家 S&P 500 公司的 SEC 10-K XBRL filings。

#### 评测模式

它定义了四类错误注入：

1. arithmetic
2. cross-statement linkage
3. year-over-year
4. magnitude perturbation

这是一个非常实用的错误 taxonomy，因为它直接对应财报生成中的高频风险。

#### rubric 范式

FinVerBench 的 rubric 不是生成质量，而是 verification 与 calibration：

- 能不能识别错误
- 会不会对完好报表产生假阳性
- 在不同 rendering 条件下是否稳健

它还指出：

- prompt 形式会显著影响 false positive
- 现实化的 rounding 会改变 recall
- 这说明“评测构造”本身就是评测的一部分

#### 对我们的启发

这篇非常适合转化为我们后续的 QA skill：

- 数字是否一致
- 跨表是否一致
- 年度变化是否合理
- 数量级是否异常

如果我们要做自动化评测，这会是最直接的基础模块之一。

---

### 6. FinChart-Bench

链接: [arXiv](https://arxiv.org/abs/2507.14823)

#### 任务设定

FinChart-Bench 聚焦真实金融图表理解。

数据规模：

- 1,200 张金融图表
- 2015-2024
- 7,016 道题
- 题型包括 TF / MC / QA

#### 评测模式

它评测的是金融图表 comprehension，而不是生成。

不过它对我们仍然很关键，因为金融财报里的图表质量，生成前提是理解对了图表中的数值关系与时间结构。

#### rubric 范式

FinChart-Bench 的 rubric 是多任务混合：

- True / False
- Multiple Choice
- Question Answering

并且它强调：

- instruction following
- spatial reasoning
- chart reasoning
- automated evaluator 不够可靠

#### 对我们的启发

这说明金融图表相关任务，不能只靠一个简单 similarity score。

如果后续我们做可视化 skill 的迭代，至少要区分：

- 图表是否读对
- 图表是否生成对
- 图表是否在报告里嵌入对

---

### 7. Chart2Code

链接: [arXiv](https://arxiv.org/abs/2510.17932)

#### 任务设定

这不是金融专属 benchmark，但它是 chart generation rubric 设计里非常重要的参考模板。

它把 chart 生成拆成三层：

1. Chart reproduction
2. Chart editing
3. Long-table to chart generation

#### 评测模式

它同时评：

- code correctness
- visual fidelity

这比单纯看图更接近真实 chart production 需求。

#### rubric 范式

Chart2Code 的核心是 hierarchical evaluation：

- 先看能不能重现
- 再看能不能编辑
- 再看能不能把长表转成 faithful chart

#### 对我们的启发

虽然不是金融专属，但它非常适合成为我们未来“金融图表生成”自动评测的结构模板：

- 是否画对
- 是否改对
- 是否忠实

---

## 三、这些工作共同暴露出的评测模式

把上述工作放在一起，可以抽象出 6 种评测范式。

### 1. 模板覆盖型

代表：

- Template-Based Financial Report Generation

特点：

- 关注 section coverage
- 关注 template adherence
- 关注信息是否足够展开

适合：

- 财报正文
- 模板报告

---

### 2. 证据链型

代表：

- FinLFQA

特点：

- 关注 supporting evidence
- 关注 numerical reasoning trace
- 关注 domain knowledge grounding

适合：

- 带引用的财报写作
- research memo
- long-form analysis

---

### 3. 任务路径型

代表：

- Fin-RATE

特点：

- 把分析任务拆成不同路径
- 区分 retrieval / generation / reasoning / context misunderstanding

适合：

- SEC filing analysis
- 多文档追踪
- 跨公司比较

---

### 4. 多维分类型

代表：

- BizFinBench

特点：

- 数值、推理、抽取、预测、知识问答并行
- objective + subjective 混合
- 可用 LLM judge，但要做偏差控制

适合：

- 通用金融能力评测
- 多任务能力地图

---

### 5. 错误注入 / 验证型

代表：

- FinVerBench

特点：

- 用可控 perturbation 构造错误
- 关注 false positive / recall / calibration
- 重点是“能不能稳健识别错误”

适合：

- 财报数字审计
- 模型校验
- 表格一致性检查

---

### 6. 图表感知型

代表：

- FinChart-Bench
- Chart2Code

特点：

- FinChart-Bench 偏理解
- Chart2Code 偏生成
- 一个看图答题，一个看图作图

适合：

- 金融图表理解
- 图表复现
- 图表编辑
- 表格转图

---

## 四、对我们最有用的 rubric 设计范式

从“专家评审 + 自动化评测”的角度，我建议优先吸收以下结构。

### 1. 先分层，再总评

不要只给一个 overall score。

应至少拆为：

- 数据正确性
- 推理正确性
- 证据质量
- 写作质量
- 图表质量
- 版式与交付质量

这与 FinLFQA、Fin-RATE、BizFinBench 的思想一致。

### 2. 把错误分型，而不是一句话概括

FinVerBench 和 Fin-RATE 都很强调 error taxonomy。

我们后续专家标注建议至少区分：

- factual error
- numerical error
- cross-statement inconsistency
- temporal mismatch
- entity mismatch
- missing evidence
- chart mismatch
- template violation
- over-claim / under-claim

### 3. 让 rubric 对应 skill patch

每一类反馈最好能直接映射到：

- 规则新增
- 规则收紧
- 反例补充
- 检查脚本补充
- 图表规范补充

这样反馈才能进入 skill iteration，而不是停留在主观评论。

### 4. 自动评测要区分“答案正确”和“过程可靠”

FinLFQA 和 Fin-RATE 都提示，最终答案对不等于过程好。

因此自动评测最好至少分成：

- output correctness
- attribution / evidence
- reasoning trace
- robustness to rendering / prompt / retrieval

### 5. 图表任务不能只做视觉相似度

Chart2Code 和 FinChart-Bench 都说明：

- chart correctness
- chart fidelity
- chart comprehension

是不同层次。

对我们后续金融可视化迭代来说，建议至少区分：

- 图表数值是否正确
- 图表语义是否正确
- 图表样式是否符合财报语境
- 图表在文档中的嵌入是否清晰

---

## 五、建议的专家反馈样板

为了便于后续专家评审，我建议把反馈意见按以下字段结构化。

### A. 财报正文类

- section_name
- issue_type
- severity
- evidence
- suggested_fix

### B. 数值类

- metric_name
- expected_value
- observed_value
- error_type
- source_of_truth

### C. 图表类

- chart_id
- chart_goal
- issue_type
- x_axis
- y_axis
- label_error
- data_mismatch

### D. 引用类

- claim
- missing_source
- wrong_source
- support_strength

### E. 结构类

- template_section
- missing_element
- extra_element
- ordering_issue

这类结构化反馈最适合后续进入 skill patch 流程。

---

## 六、结论

对我们这个项目来说，最有价值的不是某一篇 benchmark 的总分，而是这些工作已经给出了清晰的评测设计趋势：

1. **模板覆盖比单段摘要更重要**
2. **证据链与数值推理必须分开评**
3. **错误要有 taxonomy，而不是只给总分**
4. **金融图表既要看理解，也要看生成**
5. **自动评测必须和人工结构化反馈共存**

如果后续我们要为 LangAlpha 设计专家评审和自动评测，这些工作已经足够提供一个基础样板。

---

## 七、专家评审表单草案

下面是把前述 rubric 进一步压成“可直接给专家用”的表单草案。目标不是一次评完所有东西，而是让专家的反馈天然可结构化，后续可以直接进入 skill iteration 和自动化评测管线。

### 1. 表单设计原则

- 一张表对应一篇财报 / 一个图表包 / 一个报告片段。
- 每个维度都允许单独打分和单独备注。
- 每个问题都尽量能映射到明确的 error type。
- 每条反馈都尽量能写出可执行修复建议。

### 2. 基本信息区

| 字段 | 说明 |
|---|---|
| report_id | 报告编号 |
| report_type | 例如 initiation / earnings update / morning note / sector report |
| company | 公司名 / ticker |
| period | 报告覆盖时间范围 |
| reviewer | 专家姓名或编号 |
| review_date | 审核日期 |
| version | 报告版本号 |

### 3. 总体评价区

| 维度 | 评分建议 | 说明 |
|---|---:|---|
| overall quality | 1-5 | 整体可用性 |
| professional tone | 1-5 | 是否像专业分析师产出 |
| decision usefulness | 1-5 | 是否对投资决策有帮助 |
| publish readiness | 1-5 | 是否可直接交付 |

### 4. 分项 rubric 区

#### A. 数据与事实

| 字段 | 说明 | 可能问题类型 |
|---|---|---|
| factual correctness | 事实是否准确 | factual error |
| numerical correctness | 数字是否准确 | numerical error |
| cross-source consistency | 多来源是否一致 | source mismatch |
| temporal correctness | 时间点是否正确 | temporal mismatch |

#### B. 推理与证据

| 字段 | 说明 | 可能问题类型 |
|---|---|---|
| reasoning quality | 推理是否连贯、充分 | reasoning gap |
| evidence support | 结论是否有证据支撑 | missing evidence |
| attribution quality | 引用是否准确、足够 | attribution issue |
| scope discipline | 是否过度外推 | over-claim |

#### C. 写作与结构

| 字段 | 说明 | 可能问题类型 |
|---|---|---|
| section completeness | 章节是否完整 | template violation |
| structure clarity | 结构是否清晰 | ordering issue |
| professional wording | 用语是否符合金融语境 | wording issue |
| transition quality | 段落衔接是否自然 | narrative gap |

#### D. 图表与视觉

| 字段 | 说明 | 可能问题类型 |
|---|---|---|
| chart correctness | 图表数据是否正确 | chart mismatch |
| chart choice | 图表类型是否合适 | chart design issue |
| axis / unit correctness | 轴与单位是否正确 | label / unit error |
| visual clarity | 可读性是否足够 | layout issue |
| chart-text alignment | 图表与正文是否一致 | inconsistency |

#### E. 合规与审慎

| 字段 | 说明 | 可能问题类型 |
|---|---|---|
| citation completeness | 引用是否完整 | missing citation |
| claim discipline | 是否有不当结论 | compliance issue |
| risk disclosure | 风险提示是否充分 | missing caveat |
| conflict handling | 冲突信息是否处理得当 | contradiction handling |

### 5. 每个问题的反馈格式

建议专家对每个问题都尽量按下面格式填写：

```text
Issue Type:
Location:
Why it is a problem:
Suggested fix:
Severity:
```

### 6. 推荐的结构化输出格式

如果要直接进入后续 skill iteration，建议最终导出的反馈记录包含这些字段：

```json
{
  "report_id": "...",
  "company": "...",
  "section": "...",
  "issue_type": "...",
  "severity": "...",
  "evidence": "...",
  "suggested_fix": "...",
  "tag": ["factual", "numerical", "chart", "style"]
}
```

### 7. 评审时的最小可用流程

1. 先给总体评分。
2. 再按数据 / 推理 / 写作 / 图表 / 合规分项打分。
3. 对每个低分项写 1-3 条结构化问题。
4. 标出哪些问题是“必须修”，哪些是“建议修”。
5. 输出可供后续 skill patch 使用的反馈记录。

### 8. 这个表单的作用

这个草案的目的不是替代最终测评系统，而是先把专家脑中的判断转成结构化信号，方便后面两件事：

- 进入 skill iteration 的回流闭环
- 逐步沉淀成自动化评测模板
