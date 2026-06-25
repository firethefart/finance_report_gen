# Agent Skill 研究报告

## 研究目标

本报告聚焦 2025-2026 年 `agent skill`、`skill iteration`、`skill evolution` 方向的最新研究与产品进展，回答以下三个问题：

1. `agent skill` 的研究进展如何，自动化生成与自动化进化是否成熟，现有方案有哪些。
2. 是否已经存在“用 skill 迭代替代模型训练”的类似思想，具体如何阐述。
3. 是否存在公开且覆盖度足够好的 agent skill market。

## 核心结论

### 1. 研究已经从 prompt 技巧走向结构化 skill 资产

`skill` 已经不再只是提示词，而是逐渐演化为可发现、可加载、可验证、可版本化的外部能力单元。最明显的信号来自 Anthropic 的 Agent Skills 规范与目录体系，以及学术界对 skill 的系统评测。

### 2. 自动化生成与进化已经出现多条路线，但尚不成熟

当前最强的方案都依赖以下条件：

- 明确的外部反馈。
- 可验证任务或程序化评测。
- 冻结底层模型，只优化 skill artifact。
- 结构化 skill 目录，而不是单一 prompt。

这意味着自动 skill 生成已经可用，但还远未达到通用成熟阶段。尤其在开放式、不可验证、主观性强的任务上，self-generated skill 的收益并不稳定。

### 3. “skill 迭代替代模型训练”的思想已经出现

多个工作都在明确表达类似思想：把 skill 当成“冻结模型之外的外部状态”，通过验证驱动的迭代来提升能力，而不是改动模型参数本身。最直接的代表是 `SkillOpt`，其思路几乎就是把训练迁移到 skill 文档空间中。

### 4. 目前没有一个真正意义上的高覆盖、高质量公开 skill market

现阶段更接近“标准 + 精选目录 + 社区聚合”的碎片化生态。Anthropic 的目录是最成熟的官方入口，但仍然不是全量市场，更不是“基本能找到任何现存 skill”的统一市场。

## 关键文献

以下工作构成本报告的核心证据链：

- [CASCADE: Cumulative Agentic Skill Creation through Autonomous Development and Evolution](https://arxiv.org/abs/2512.23880)
- [Agent Skills: A Data-Driven Analysis of Claude Skills for Extending Large Language Model Functionality](https://arxiv.org/abs/2602.08004)
- [SkillsBench: Benchmarking How Well Agent Skills Work Across Diverse Tasks](https://arxiv.org/abs/2602.12670)
- [SkillRL: Evolving Agents via Recursive Skill-Augmented Reinforcement Learning](https://arxiv.org/abs/2602.08234)
- [Trace2Skill: Distill Trajectory-Local Lessons into Transferable Agent Skills](https://arxiv.org/abs/2603.25158)
- [EvoSkill: Automated Skill Discovery for Multi-Agent Systems](https://arxiv.org/abs/2603.02766)
- [EvoSkills: Self-Evolving Agent Skills via Co-Evolutionary Verification](https://arxiv.org/abs/2604.01687)
- [SkillLearnBench: Benchmarking Continual Learning Methods for Agent Skill Generation on Real-World Tasks](https://arxiv.org/abs/2604.20087)
- [SkillOpt: Executive Strategy for Self-Evolving Agent Skills](https://arxiv.org/abs/2605.23904)

## 研究进展拆解

### 1. 标准化层

Anthropic 已经把 skill 推向标准化方向：

- [What are skills?](https://support.claude.com/en/articles/12512176-what-are-skills)
- [Use Skills in Claude](https://support.claude.com/en/articles/12512180-using-skills-in-claude)
- [Anthropic Software Directory Policy](https://support.claude.com/en/articles/13145358-anthropic-software-directory-policy)
- [Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

同时，Agent Skills 官方规范页提供了更通用的结构参考：

- [Overview](https://agentskills.io/)
- [Specification](https://agentskills.io/specification)
- [Evaluating skill output quality](https://agentskills.io/skill-creation/evaluating-skills)

这类规范意味着 skill 正在变成可工程化管理的 artifact，而不是零散 prompt。

### 2. 评测层

`SkillsBench` 与 `SkillLearnBench` 是两个关键评测工作。

- `SkillsBench` 说明 curated skills 普遍有效，但 self-generated skills 平均无明显收益。
- `SkillLearnBench` 进一步说明：continual learning methods 通常优于 no-skill baseline，但没有任何方法能在所有任务和模型上稳定领先；self-feedback 容易导致 recursive drift。

这说明研究重点正在从“是否能生成 skill”转向“在什么条件下 skill 真的稳定有效”。

### 3. 自动化生成层

当前最常见的自动生成路线包括：

- 轨迹蒸馏：从执行轨迹中总结可复用规则。
- 失败驱动编辑：根据失败样本修补 skill。
- 生成器-验证器共进化：让 candidate skill 和 verifier 一起迭代。
- 文本空间优化：把 skill 文档作为外部状态做受限优化。

这些方法的共同点是：底层模型通常冻结，优化对象是 skill artifact 本身。

## 对问题一的回答

### 目前进展如何

可以概括为三个层次：

1. `skill` 标准化。
2. `skill` 可验证化。
3. `skill` 可进化化。

### 自动生成 / 自动进化是否成熟

结论是不成熟，但已经可用。

适合自动化的前提是：

- 任务有明确反馈。
- 可以定义成功/失败。
- 可以做 held-out validation。
- 可以把错误归因到具体环节。

不适合自动化的情况包括：

- 目标高度主观。
- 输出难以验证。
- 反馈过于稀疏。
- 任务分布变化太大。

### 现有技术方案

主要有以下几类：

- `Trace2Skill` 风格的轨迹蒸馏。
- `EvoSkill` 风格的失败驱动编辑。
- `EvoSkills` 风格的 co-evolutionary verification。
- `SkillOpt` 风格的文本空间优化。
- `SkillRL` 风格的 skill library + policy 共演化。
- `CASCADE` 风格的长期 agentic skill acquisition。

## 对问题二的回答

### 是否已有“用 skill 迭代替代模型训练”的思想

有，而且已经非常明确。

最直接的表达是：

- 不改参数。
- 只改 skill 文档 / skill package。
- 用验证集决定是否接受修改。
- 让 skill 成为冻结模型之外的外部状态。

### 代表性阐述

- `SkillOpt` 几乎就是把训练过程迁移到 skill 文本空间。
- `EvoSkill` 强调底层模型保持冻结，skill 通过失败分析和验证集驱动进化。
- `Trace2Skill` 通过轨迹归纳把经验压缩为可迁移 skill。
- `CASCADE` 则更宏观地提出从工具使用走向 skill acquisition。

这些工作共同指向一个结论：

> 在某些任务上，skill iteration 可以部分替代或显著减少模型训练需求，但还不能通用地替代模型训练。

## 对问题三的回答

### 是否存在公开且覆盖度好的 agent skill market

结论是否定的。

### 当前最接近的生态

1. Anthropic 官方 skill 目录。
2. Agent Skills 开放标准与客户端生态。
3. 社区聚合站与部分第三方目录。

### 为什么不是“真正的市场”

- 覆盖不全。
- 审核制导致不是全量收录。
- 质量分布不均。
- skill 类型、格式、版本兼容性并不统一。

### 结论

当前没有一个“基本能找到任何现存 skill 且质量优异”的统一公开市场。现阶段生态仍是碎片化的。

## 总结

agent skill 方向已经进入快速成长期，但仍处于“标准化 + 自动化生成 + 自动化进化”的早期工程化阶段。最重要的趋势不是“更大的模型”，而是“可验证、可迭代、可版本化的技能资产层”。
