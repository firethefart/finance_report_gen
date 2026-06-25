# Skill Iteration 与金融财报生成的工程级报告

## 研究目标

本报告进一步拆解 `skill iteration` 的实现方式，并将其映射到“金融财报生成”这一高精度场景。重点回答两件事：

1. 各类 skill iteration 管线在任务场景、环境设置、迭代机制、产出效果上的工程结构是什么，如何复现。
2. 在“金融财报生成”场景下，应该如何设计 skill iteration 管线，以最大化提升 Agent 的产出质量。

## 研究对象与核心论文

本报告主要参考以下工作：

- [SkillRL: Evolving Agents via Recursive Skill-Augmented Reinforcement Learning](https://arxiv.org/abs/2602.08234)
- [SkillsBench: Benchmarking How Well Agent Skills Work Across Diverse Tasks](https://arxiv.org/abs/2602.12670)
- [Trace2Skill: Distill Trajectory-Local Lessons into Transferable Agent Skills](https://arxiv.org/abs/2603.25158)
- [EvoSkill: Automated Skill Discovery for Multi-Agent Systems](https://arxiv.org/abs/2603.02766)
- [EvoSkills: Self-Evolving Agent Skills via Co-Evolutionary Verification](https://arxiv.org/abs/2604.01687)
- [SkillLearnBench: Benchmarking Continual Learning Methods for Agent Skill Generation on Real-World Tasks](https://arxiv.org/abs/2604.20087)
- [SkillOpt: Executive Strategy for Self-Evolving Agent Skills](https://arxiv.org/abs/2605.23904)
- [CASCADE: Cumulative Agentic Skill Creation through Autonomous Development and Evolution](https://arxiv.org/abs/2512.23880)
- Anthropic 官方技能文档与目录政策：
  - [What are skills?](https://support.claude.com/en/articles/12512176-what-are-skills)
  - [Use Skills in Claude](https://support.claude.com/en/articles/12512180-using-skills-in-claude)
  - [Anthropic Software Directory Policy](https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy)
  - [Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- Agent Skills 规范：
  - [Overview](https://agentskills.io/)
  - [Specification](https://agentskills.io/specification)
  - [Evaluating skill output quality](https://agentskills.io/skill-creation/evaluating-skills)

## 一、skill iteration 的主流实现方式

### 1. 经验蒸馏型：`Trace2Skill`

#### 任务场景

- 面向 office workflows、math reasoning、vision QA 等复杂执行任务。
- 目标是把大量执行轨迹压缩成可迁移 skill。

#### 环境设置

- 输入是一批多样化轨迹。
- 轨迹中包含成功和失败样本。
- 允许并行分析多个轨迹。

#### 迭代机制

1. 收集多轮轨迹。
2. 并行分析每条轨迹中的决策点和失败点。
3. 提炼 trajectory-local lessons。
4. 聚合这些 lessons，生成统一 skill directory。
5. 用这些 skill 去增强后续任务执行。

#### 产出效果

- 轨迹中的碎片经验被压缩为结构化 SOP。
- skill 能被跨模型、跨规模迁移。
- 适合从人工专家轨迹中抽象出通用规则。

#### 复现要点

- 必须保留完整轨迹日志。
- 必须有冲突消解机制，否则 skill 会变成案例堆砌。
- 最重要的是“多轨迹归纳”，而不是单轨迹修补。

---

### 2. 失败驱动编辑型：`EvoSkill`

#### 任务场景

- 面向 grounded QA 和搜索增强任务。
- 论文实验涉及 U.S. Treasury data 和 noisy search QA。

#### 环境设置

- 底层模型冻结。
- agent 在任务上产生失败和成功轨迹。
- skill 以目录/文件夹形式维护。

#### 迭代机制

1. 让 agent 在任务环境中执行。
2. 收集失败样本。
3. 失败分析模块总结错误模式。
4. 基于错误模式生成新 skill 或编辑旧 skill。
5. 用 held-out validation 检查新 skill。
6. 仅接受验证集真正提升的版本。

#### 产出效果

- 在多个任务上取得显著提升。
- 能把单点错误修成跨任务可迁移 skill。
- 底层模型冻结，变化只发生在 skill 层。

#### 复现要点

- 失败归因必须准确，否则会修错方向。
- 需要稳定的验证集，否则会过拟合到局部样本。
- 适合错误类型可以枚举的任务。

---

### 3. 生成器-验证器共进化型：`EvoSkills`

#### 任务场景

- 面向复杂 multi-agent / skill package 场景。
- 解决“测试内容不可直接暴露”的问题。

#### 环境设置

- 生成器负责提出 skill 候选。
- verifier 负责在不泄露标准答案的前提下提供反馈。
- 二者一起迭代。

#### 迭代机制

1. 生成 skill 候选。
2. verifier 基于隐藏评测或代理信号给出反馈。
3. 根据反馈修订候选。
4. 重复直到 skill 质量稳定。

#### 产出效果

- 适合多文件、复杂结构的 skill 资产。
- 适合高保密环境。
- 能绕开“看不到标准答案就无法优化”的问题。

#### 复现要点

- verifier 的质量就是系统上限。
- 需要精心设计代理指标。
- 如果 verifier 偏了，整个 evolution 也会偏。

---

### 4. 文本空间优化型：`SkillOpt`

#### 任务场景

- 面向 agent skills 的通用优化。
- 在多个 benchmark、多个模型、多个 harness 上测试。

#### 环境设置

- skill 是一个可编辑的文本/文件对象。
- 底层模型冻结。
- 独立 optimizer model 负责提出修改。

#### 迭代机制

1. 基于 scored rollout 读取当前 skill 表现。
2. optimizer 生成 bounded edit。
3. 编辑类型通常是 `add`、`delete`、`replace`。
4. 在 held-out validation 上评估。
5. 只有严格提升时才接收。
6. 使用 rejected-edit buffer 防止错误改动反复进入。

#### 产出效果

- 在大量 `(model, benchmark, harness)` 组合上表现优异。
- 更像“训练 skill 文档”而不是写 prompt。
- 部署成本低，因为推理阶段不需要额外调用优化器。

#### 复现要点

- 必须限制每次编辑幅度。
- 必须有严格验证集。
- 必须保留被拒绝编辑，避免回归。

---

### 5. RL + skill 库共演化型：`SkillRL`

#### 任务场景

- 面向长期交互式 agent。
- 任务包括 `ALFWorld`、`WebShop` 以及 search-augmented tasks。

#### 环境设置

- agent 在环境中反复采样轨迹。
- 轨迹被蒸馏为 skill。
- skill 再反过来辅助 policy learning。

#### 迭代机制

1. 先采样轨迹。
2. 将成功模式蒸馏为 skill。
3. 用失败轨迹总结 failure lessons。
4. 形成分层 skill bank。
5. 在 RL 中继续优化 policy。
6. 根据新失败样本更新 skill bank。

#### 产出效果

- 适合长期积累和持续学习。
- token footprint 更低。
- 在任务复杂度提升时更稳。

#### 复现要点

- 需要稳定的 RL 环境。
- 需要 skill 检索与调用机制。
- 如果没有可靠 validation，skill 会漂移。

---

### 6. 长期工作流型：`CASCADE`

#### 任务场景

- 面向科学研究工作流。
- 重点是持续学习、记忆管理、自反思与知识图谱探索。

#### 环境设置

- 任务往往是长链条研究问题。
- 需要 web search、代码抽取、memory 和 introspection。

#### 迭代机制

1. 在任务中执行。
2. 记录经验。
3. 反思并形成可复用 meta-skill。
4. 将 meta-skill 共享给后续任务。

#### 产出效果

- 更适合长期研究 agent。
- 把工具使用升级为 skill acquisition。

#### 复现要点

- 需要长期记忆系统。
- 需要高质量反思模块。
- 不适合只追求短平快的一次性输出。

---

### 7. 评测框架：`SkillsBench` 与 `SkillLearnBench`

#### `SkillsBench`

- 重点证明 curated skills 的有效性。
- 也证明 self-generated skills 平均上并不稳定。
- 提示 skill 设计应以 focused skills 为主，而不是越全越好。

#### `SkillLearnBench`

- 强调 skill quality、execution trajectory、task outcome 三层评估。
- 证明 continual learning methods 比 no-skill baseline 更强，但没有绝对通用赢家。
- 提醒 self-feedback 会带来 recursive drift。

#### 工程意义

这两个 benchmark 告诉我们：

- 不能只看最终输出。
- 必须分开评估 skill、执行过程和最终结果。
- skill iteration 需要稳定的评测门控。

## 二、把这些模式抽象成四类工程范式

### 模式 A：经验压缩成 SOP

- 代表：`Trace2Skill`、`SkillRL` 的蒸馏阶段。
- 输入：大量轨迹。
- 处理：抽取可复用规则。
- 输出：结构化 skill。

### 模式 B：失败驱动修复

- 代表：`EvoSkill`。
- 输入：失败案例。
- 处理：定位缺口并修补。
- 输出：更强 skill folder。

### 模式 C：生成器-验证器共进化

- 代表：`EvoSkills`。
- 输入：候选 skill + 验证反馈。
- 处理：共同演化。
- 输出：复杂 skill package。

### 模式 D：文本空间优化

- 代表：`SkillOpt`。
- 输入：score + rollout + skill 文档。
- 处理：受限编辑。
- 输出：更优 skill 文档。

## 三、金融财报生成场景的适配性评估

### 场景特点

“金融财报生成”不是单一步骤任务，而是一个复合 pipeline，至少包含：

1. DeepResearch。
2. Data Analysis。
3. Writing。
4. Visualization。
5. Quality Assurance / Compliance。

这类任务对数据精确性要求极高，且需要多个环节有机配合。

### 适配性判断

| 方法 | 适配性 | 说明 |
|---|---:|---|
| SkillOpt | 高 | 最适合高精度、可审计、可回滚的 skill 文本优化。 |
| Trace2Skill | 高 | 最适合从大量高质量人类财报中归纳 SOP。 |
| EvoSkill | 高 | 最适合把反复出现的错误模式转成修复规则。 |
| EvoSkills | 高 | 最适合高保密、不能直接暴露标准答案的验证环境。 |
| SkillRL | 中 | 更适合长期研究型 agent，不适合作为最终财报主循环。 |
| CASCADE | 中 | 更适合投资研究、深度分析，不是最直接的财报生成主方案。 |
| SkillsBench / SkillLearnBench | 必需 | 作为评测框架必须引入。 |

### 不建议的做法

- 把整个财报生成当成一个单一巨型 skill。
- 只做 self-generated skills，不做专家验证。
- 只看最终报告，不看轨迹和 skill 本身。
- 没有 holdout 数据就贸然接收新版本。

## 四、建议的金融财报 skill iteration 管线

### 1. 先拆 skill taxonomy

建议至少拆成 6 个一级 skill：

1. `financial-research-skill`
   - 负责搜集来源。
   - 追踪 10-K / 10-Q / earnings call / press release / market data。

2. `financial-analysis-skill`
   - 负责表格计算、同比/环比、口径统一、ratio、bridge analysis。

3. `financial-writing-skill`
   - 负责正式财报语言、结构、语气、免责声明、术语规范。

4. `financial-visualization-skill`
   - 负责图表生成、轴/单位/口径检查、图表与数据一致性。

5. `financial-citation-skill`
   - 负责引用、脚注、来源映射、证据链完整性。

6. `financial-qa-skill`
   - 负责数字一致性、跨段一致性、图表一致性、合规审查。

### 2. skill 目录结构建议

每个 skill 建议采用结构化目录：

- `SKILL.md`
- `references/`
- `scripts/`
- `assets/`
- `evals/`

这与 Agent Skills 规范是兼容的。

### 3. 评测层设计

建议采用三层评估：

#### 层 1：skill quality

检查 skill 文档本身：

- 描述是否足够精确。
- 触发条件是否清晰。
- 步骤是否可执行。
- 是否存在歧义。
- 是否过长、过散、过泛。

#### 层 2：execution trajectory

检查 agent 执行过程：

- 是否先找对来源。
- 是否使用了正确工具。
- 是否避免无效搜索。
- 是否生成了正确的中间表格/图表。
- 是否在失败后正确修正。

#### 层 3：task outcome

检查最终财报：

- 数字是否正确。
- 图表是否一致。
- 引用是否可追溯。
- 叙述是否规范。
- 是否通过专家审核。

### 4. 反馈设计

金融场景不能只依赖 LLM judge，建议采用三类反馈：

#### A. 程序化 verifier

适合自动判断的部分：

- 数字计算。
- 交叉引用。
- 图表与数据一致性。
- 表格字段完整性。
- 时间窗口一致性。
- 币种/单位一致性。

#### B. LLM judge

适合半结构化的部分：

- 文本是否正式。
- 叙述是否连贯。
- 风险描述是否充分。
- 结论是否过度推断。

#### C. 金融专家反馈

适合高价值样本：

- 逻辑是否像专业分析师。
- 论证链是否完整。
- 是否存在不当措辞。
- 是否遗漏关键财务信号。

专家反馈必须结构化，建议统一成：

- factual error
- numerical error
- missing evidence
- wrong tone
- wrong chart
- wrong conclusion
- compliance issue

### 5. 推荐的主循环

建议采用如下闭环：

1. 采样：用当前 skill set 生成财报草稿，保留完整执行轨迹。
2. 分级评估：程序化 verifier -> LLM judge -> 专家抽样审查。
3. 失败归因：将错误拆成可定位模式。
4. 生成修订候选：只修改对应 skill 文档或脚本，不直接“重训模型”。
5. 候选验证：在 holdout 财报集上测试。
6. 接受/拒绝：只有满足主指标提升且关键负指标不恶化才接受。
7. 版本化发布：记录 skill 版本、改动说明和增益。

### 6. 推荐训练策略

#### 第一阶段：从人类财报中做 `Trace2Skill`

- 输入：高质量人类财报、原始材料、专家修改意见、历史修订记录。
- 输出：统一的 SOP skill、失败教训 skill、图表规范 skill、风格规范 skill。

#### 第二阶段：用 `SkillOpt` 做小步迭代

- 增加更明确的触发条件。
- 增加反例。
- 增加数值检查步骤。
- 增加图表校验步骤。
- 增加财报类型分支规则。

#### 第三阶段：用 `EvoSkill` 修补失败模式

对于反复出现的错误：

- 新增 skill。
- 或在现有 skill 中加入修复分支。

例如：

- EPS 与净利润口径冲突时先核对稀释股数。
- 出现非 GAAP 指标时必须回查附注。
- 同比异常时先排除汇率和会计准则变化。

#### 第四阶段：用 `CoEvoSkills` 管高保密验证

如果测试集不能暴露给生成器，就让 verifier 负责把错误转成可操作反馈，而不是直接暴露答案。

## 五、为什么金融财报更适合 skill iteration，而不是直接训练模型

### skill iteration 的优势

- 可审计。
- 可回滚。
- 可分层。
- 可持续迭代。
- 不污染底座模型。

### 直接训练模型的劣势

- 很难解释错误来源。
- 更新成本高。
- 容易把局部风格拟合成泛化能力。
- 版本治理更困难。
- 训练后不易定位是知识错、流程错还是工具错。

### 判断

在金融财报生成里，skill iteration 应该是主方案；模型训练只适合作为补充，用于提升基础推理、格式遵循或某些局部抽取能力。

## 六、最终建议

如果目标是“最大化提升 Agent 的金融财报生成能力”，优先级建议如下：

1. `SkillOpt` 作为主优化框架。
2. `Trace2Skill` 作为专家知识抽取器。
3. `EvoSkill` 作为失败修复器。
4. `CoEvoSkills` 作为高保密验证框架。
5. `SkillLearnBench` 式三层评估作为门控机制。
6. `SkillRL` / `CASCADE` 作为长期增强路线。

## 七、结论

金融财报生成不应该依赖单一更强模型，而应该依赖多个可验证 skill 的持续迭代。最佳实践是：把专家经验压缩成结构化 skill，用严格验证驱动文本级优化，再把失败样本不断回灌到 skill 库中，形成可审计、可回滚、可持续增长的能力系统。
