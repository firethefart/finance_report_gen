# LangAlpha 架构与 Skill 体系研究报告

## 研究目标

本报告围绕工作区内的 `LangAlpha/` 仓库，回答三个问题：

1. LangAlpha 的财报生成管线是怎样的，如何以工程复现级别描述。
2. LangAlpha 的 skill 库如何组织，包含哪些已有 skill，有什么明显特征与优化空间。
3. 结合 LangAlpha 的完整实现，对我们之前讨论的 skill iteration 方案有哪些新的理解与判断。

## 一、先给结论

LangAlpha 不是单纯的“金融聊天机器人”，而是一个完整的金融研究 agent harness。它的核心是：

- **PTC（Programmatic Tool Calling）**：LLM 写 Python，在 sandbox 内通过 MCP tool wrappers 处理金融数据。
- **持久化 workspace**：每个研究目标对应一个长期 sandbox，文件、线程、历史分析、`agent.md` 都会保留。
- **分层数据生态**：native tools 负责快速查，MCP servers 负责批量/多步分析，workspace 文件负责沉淀。
- **结构化 skills**：技能被建模成可加载、可发现、可版本化的 artifact，而不是 prompt 文本。
- **双轨 skill 机制**：注册表内置 skills + 文件系统发现的用户技能，共同组成技能生态。

对我们的财报生成场景来说，LangAlpha 最有价值的不是“某一个强模型”，而是它把：

1. 数据获取
2. 数值分析
3. 文档写作
4. 图表展示
5. 校验与回滚
6. 技能加载与组合

全部工程化了。

---

## 二、LangAlpha 的财报生成管线

### 1. 顶层工作流

从 `README.md` 和 `CLAUDE.md` 可以把 LangAlpha 的主线抽象为：

1. 用户创建一个 workspace，绑定一个研究目标。
2. agent 在这个 workspace 中持续工作，文件会留存。
3. 用户发起一个请求后，后端进入 PTC workflow。
4. PTC workflow 启动或复用 sandbox。
5. agent 通过 middleware 拿到：
   - 系统上下文
   - 用户画像
   - 记忆
   - memo
   - widgets
   - 已加载 skills
   - subagents
6. agent 在 sandbox 中执行代码，调用 MCP tools，生成中间数据、图表和最终文件。
7. 结果写回 workspace 文件系统，并通过 SSE / UI 反馈给前端。
8. workspace 和 lock/manifest 机制保证后续会话继续沿用已有上下文。

这条链路不是“问答式”，而是“研究项目式”。

### 2. PTC 是核心执行引擎

`CLAUDE.md` 明确写了：LangAlpha 不直接让 LLM 走纯 JSON tool call，而是让它写 Python 代码，再在 Daytona sandbox 中执行。

工程上对应为：

- LLM 决策。
- `execute_code` 把 Python 发到 sandbox。
- sandbox 中生成的 wrapper module 直接调用 MCP server。
- MCP server 通过 stdio / HTTP / WebSocket 连到真实金融数据源。
- 最终结果写入文件、图表或 stdout，再回流给模型。

这意味着 LangAlpha 的“财报生成”不是单轮文本生成，而是一个可重复、可调试、可保存的代码化分析过程。

### 3. 数据层是分层设计

LangAlpha 的数据生态至少分三层：

#### 第一层：native tools

适合低成本、快速查询：

- 公司概览
- SEC filings
- 市场指数
- web search / crawl

#### 第二层：MCP servers

适合批量、结构化、可编程分析：

- price data
- fundamentals
- macro
- options
- Yahoo Finance 系列 MCP
- X/Twitter

#### 第三层：sandbox code

适合：

- 大规模表格清洗
- 多股票比较
- 历史数据合并
- 图表生成
- DCF / comps / 3-statement model

这三层的分工很适合财报工作流，因为财报任务本质上就包含：

- 发现信息
- 清洗信息
- 分析信息
- 组织成专业表达

### 4. 持久 workspace 是 LangAlpha 的关键资产

`README.md` 强调每个 workspace 都有：

- `work/<task>/`：工作中间产物
- `results/`：最终交付
- `data/`：共享数据
- `agent.md`：跨会话维护的工作区笔记
- `.agents/user/memory/`、`.agents/workspace/memory/`：长期记忆
- `.agents/user/memo/`：用户上传资料

这直接改变了 skill iteration 的方式：

- 不是一次性 prompt 调优。
- 而是把 skill 作为长期演化的 workspace 能力。
- 每一轮报告、模型、图表、修订意见都可以沉淀下来，作为后续迭代数据。

### 5. sandbox 同步机制

`src/server/services/workspace_manager.py` 和 `src/ptc_agent/core/sandbox/ptc_sandbox.py` 表明：

- workspace 启动后会同步 tools、skills、tokens、vault secrets。
- `sync_sandbox_assets()` 统一处理这些资产。
- `sync_skills_lock()` 会把技能 lock 与真实文件系统做 reconcile。

也就是说，LangAlpha 的技能不是“前端提示列表”，而是会真实落到 sandbox 文件系统和 manifest 里。

---

## 三、LangAlpha 的 skill 体系如何组织

### 1. 组织方式概览

LangAlpha 的 skill 体系有两条来源：

1. **Registry skills**
   - 在 `src/ptc_agent/agent/middleware/skills/registry.py` 里显式注册。
   - 有的带 tool gating，有的只带说明文档。

2. **Filesystem-discovered skills**
   - 通过 sandbox 文件系统扫描 `.agents/skills/` 或本地 `skills/` 目录。
   - 读取 `SKILL.md` frontmatter。
   - 通过 lock 文件维护元数据。

这意味着它不是封闭 skill 列表，而是一个可扩展的 skill 平台。

### 2. Skill 的标准格式

LangAlpha 的技能目录基本遵循 Agent Skills 规范：

- 一个 skill = 一个目录
- 目录里至少有一个 `SKILL.md`
- `SKILL.md` 包含 YAML frontmatter
- 可包含：
  - `references/`
  - `scripts/`
  - `assets/`
  - 额外文档

`skills/initiating-coverage/SKILL.md`、`skills/dcf-model/SKILL.md`、`skills/earnings-analysis/SKILL.md`、`skills/x-api/SKILL.md` 都体现出这一点。

### 3. Registry 的两类技能

#### A. 具备 tool gating 的技能

这些 skill 在 registry 中持有实际工具，加载后会把特定 tools 暴露给模型。

典型包括：

- `automation`
- `user-profile`
- `onboarding`

它们更像“操作能力组件”。

#### B. 主要是流程文档 / 工作规范的技能

这些 skill 通常没有专门的 LangChain tools，而是通过 `SKILL.md` 约束模型行为。

典型包括：

- `dcf-model`
- `comps-analysis`
- `initiating-coverage`
- `earnings-preview`
- `earnings-analysis`
- `morning-note`
- `catalyst-calendar`
- `check-model`
- `check-deck`
- `thesis-tracker`
- `model-update`
- `3-statements`
- `sector-overview`
- `competitive-analysis`
- `web-scraping`
- `interactive-dashboard`
- `inline-widget`
- `pdf`
- `docx`
- `pptx`
- `xlsx`
- `self-improve`
- `secretary`

这类 skill 的本质是“专业工作协议 + 产出规范 + 约束流程”。

### 4. Registry 中的 skill 清单

从 `src/ptc_agent/agent/middleware/skills/registry.py` 可见内置 registry 包含以下技能：

- `user-profile`
- `onboarding`
- `secretary`
- `automation`
- `pdf`
- `docx`
- `pptx`
- `xlsx`
- `comps-analysis`
- `dcf-model`
- `earnings-preview`
- `idea-generation`
- `check-model`
- `morning-note`
- `catalyst-calendar`
- `check-deck`
- `thesis-tracker`
- `model-update`
- `3-statements`
- `earnings-analysis`
- `sector-overview`
- `competitive-analysis`
- `self-improve`
- `inline-widget`
- `interactive-dashboard`
- `initiating-coverage`
- `web-scraping`

另外，`skills/` 目录里还有不在 registry 中的 `x-api`，说明仓库还支持文件系统发现型 skill。

### 5. Skill 的 mode 分层

LangAlpha 把 skill 按 mode 分为：

- `ptc`
- `flash`
- `both`
- `hidden`

这是个很重要的工程设计。

#### PTC mode

- 没有 `LoadSkill` tool
- agent 读到 `SKILL.md` 时自动加载技能
- sandbox 内可访问 filesystem，因此可以直接读 skill 文件

#### Flash mode

- 暴露 `LoadSkill` tool
- 不能依赖 sandbox 文件系统
- 直接把 `SKILL.md` 内容内嵌到上下文

#### Hidden

- 不出现在列表里
- 只能通过额外上下文激活
- 例如 onboarding 这类内部流程 skill

### 6. skill 的加载与门控机制

`SkillsMiddleware` 是 skill 系统的核心。

它做了三件事：

1. **工具预注册**
   - 所有 skill 的工具在 agent 创建时都可以先注册。
   - 但在模型可见前会被过滤掉。

2. **根据 loaded_skills 过滤工具**
   - 每次 model call 前，根据 state 里的 `loaded_skills` 决定哪些工具可见。

3. **构建 skill manifest**
   - 把所有可用 skill 列到 system message 里。
   - PTC 模式提示“读 `SKILL.md` 激活”。
   - Flash 模式提示“调用 `LoadSkill` 激活”。

这说明 LangAlpha 的 skill 不是静态 prompt，而是可运行时切换的能力层。

### 7. skill 的自动发现与锁文件

`src/ptc_agent/agent/middleware/skills/discovery.py` 和 `lock.py` 说明：

- 通过扫描 sandbox 中的 skill 目录发现新 skill。
- 读取 `SKILL.md` frontmatter。
- 生成 `skills-lock.json`。
- 记录：
  - `owner`
  - `source`
  - `sourceType`
  - `computedHash`
  - `confirmed`
  - `allowed_tools`
  - `installedAt`
  - `updatedAt`

这个 lock 文件是技能生态的关键，因为它把“已知 skill”与“文件系统中新的 skill”连接起来。

### 8. 发现型 skill 的特殊性

`skills/` 中存在 `x-api` 这类未进入 registry 的 skill，说明 LangAlpha 支持：

- 平台内置 skill
- 用户安装 skill
- 文件系统自动发现 skill

这对我们非常有价值，因为 skill iteration 不必强依赖核心代码改动，很多 skill 可以通过文件系统和 lock 直接演化。

---

## 四、各 skill 的明显特征

### 1. 金融专业 skill 占据主轴

`skills/` 中绝大多数 registry skill 都是金融研究相关：

- 估值
- 研究报告
- 业绩分析
- 选题 / 想法生成
- 行业分析
- 组合对比
- 事件跟踪
- 风格审核

这和 LangAlpha 的目标完全一致：构建一套能支持“投资研究工作流”的 agent harness。

### 2. 每个 skill 都是强约束流程

很多 skill 不是“给一些信息然后自由生成”，而是明确规定：

- 先做什么
- 后做什么
- 需要什么 prerequisites
- 产出什么格式
- 不允许什么 shortcut

例如 `initiating-coverage` 明确要求：

- 单任务模式
- 5 个任务分开执行
- 不允许自动串联
- 最终 deliverable 严格限定

这类 skill 的本质是“专业流程模板”，不是普通提示词。

### 3. 文档/格式 skills 具有强工具导向

`pdf`、`docx`、`pptx`、`xlsx` 都不是泛泛的“文件处理”，而是：

- 格式规范
- 验证脚本
- 拆包/重包
- 校验脚本
- 样式约束

这非常适合高质量报告生成，因为财报生成的最后一公里经常出在：

- Word 格式
- Excel 公式
- PPT 图表
- PDF 导出

### 4. x-api 是一个很好的外部扩展样本

`x-api` skill 的组织方式说明 LangAlpha 允许：

- 独立技能包
- 明确 auth 约束
- 严格的 do/don’t 规则
- 使用指导
- 错误说明

它不是 registry 内置，却可以作为现成的扩展技能加入 workspace。

---

## 五、LangAlpha 对 skill iteration 的新启发

这一部分是我研究完仓库后对前面方案的新理解。

### 1. skill iteration 最适合在 LangAlpha 里做“分层优化”

LangAlpha 的结构已经把财报生成拆成多个层次：

- 数据层
- 研究层
- 分析层
- 写作层
- 图表层
- 审核层
- 交付层

所以 skill iteration 不应针对一个“大而全 skill”做，而应该：

1. 分别优化每一层的 skill
2. 让 subagents 各自继承不同 skill 组合
3. 对输出做分层评测

这比“一个超级 prompt”更符合 LangAlpha 的架构。

### 2. `report-builder` subagent 是一个很强的系统切分点

`src/ptc_agent/agent/subagents/builtins.py` 里的 `report-builder` 明确要求：

- 专门负责文档生产
- 会先激活 format skill
- 负责 DOCX / XLSX / PPTX / PDF 交付

这意味着：

- 分析和写作可以分离
- 最终文档生产可以独立迭代
- skill iteration 可以在“分析 skill”和“格式 skill”之间独立进行

对金融财报任务来说，这个切分特别有利于质量控制。

### 3. “技能 + 工具”的边界很清晰

LangAlpha 的设计不是让 skill 直接做所有事，而是：

- skill 决定流程
- tool 决定能力
- sandbox 决定执行
- memory / memo 决定持续性

这意味着 skill iteration 的目标应该是：

- 改善流程规则
- 改善工具选择策略
- 改善任务分解
- 改善验证逻辑

而不是只改写作风格。

### 4. `skills-lock.json` 让 skill 版本化有了自然落点

这个仓库已经有：

- lock 文件
- manifest
- source type
- hash
- owner
- confirmed flag

因此我们后续做 skill iteration 时，完全可以沿用这个结构：

- 每个 skill 一份版本记录
- 每次变更都保留 hash
- 验证通过才升级 lock
- 失败样本保留在 rejected edits 中

这比纯 prompt 工程成熟得多。

### 5. 文档化 skill 非常适合专家反馈闭环

很多技能都以 `SKILL.md` 为主，且包含大量可读规则与示例。

这意味着金融专家的反馈也应该进入 skill 文档，而不是只留在聊天历史里。

建议的反馈形式是：

- 增补规则
- 增补反例
- 增补检查清单
- 增补错误示范
- 增补格式约束

这和 `SkillOpt`、`Trace2Skill`、`EvoSkill` 的研究方向完全一致，但在 LangAlpha 上更容易工程化实现。

### 6. 当前最值得优先初始化的 skill 集合

如果以“财报生成”为目标，LangAlpha 现有 skill 中最应该作为初始化 skill set 的是：

- `initiating-coverage`
- `earnings-analysis`
- `earnings-preview`
- `dcf-model`
- `comps-analysis`
- `3-statements`
- `model-update`
- `check-model`
- `check-deck`
- `sector-overview`
- `competitive-analysis`
- `morning-note`
- `catalyst-calendar`
- `interactive-dashboard`
- `inline-widget`
- `xlsx`
- `docx`
- `pptx`
- `pdf`
- `web-scraping`
- `x-api`
- `self-improve`

如果以后做财报生成 skill iteration，最好的起点不是“从零建 skill”，而是基于这套已有 skill 继续做：

1. 财报数据验证
2. 数值一致性检查
3. 写作风格标准化
4. 图表/表格一体化校验
5. 专家反馈驱动修订

---

## 六、我对我们后续 skill iteration 方案的更新判断

### 1. LangAlpha 让“skill iteration”更像软件工程

在这个仓库里，skill 不只是学习对象，而是：

- 有目录结构
- 有 frontmatter
- 有锁文件
- 有发现机制
- 有模式约束
- 有工具绑定
- 有装配流程

所以 skill iteration 最合理的表述是：

> 不是迭代 prompt，而是在迭代一套可版本化的软件化能力模块。

### 2. 真正需要迭代的是 skill 之间的编排关系

对于财报生成，难点未必在单个 skill 本身，而在：

- research skill 如何喂给 analysis skill
- analysis skill 如何喂给 writing skill
- writing skill 如何喂给 report-builder
- QA skill 如何拦截错误

也就是说，应该迭代：

- skill composition
- handoff protocol
- validation protocol
- acceptance criteria

而不仅是 skill 文本内容。

### 3. 应该把 “专家反馈” 结构化地写回 skill

LangAlpha 的 skill 形态非常适合“专家校审 -> skill patch -> lock update”的闭环。

建议把反馈结构统一成：

- factual error
- numerical error
- source mismatch
- compliance issue
- wording issue
- chart mismatch
- missing caveat
- wrong inference

然后将其映射到：

- 规则新增
- 规则收紧
- 反例新增
- 验证脚本新增

### 4. 先做 focused skill，再考虑大一统 skill

`SkillsBench` 的结论在这里非常贴切：focused skills 比 comprehensive skills 更可靠。

LangAlpha 的 skill 结构也印证了这一点：

- 每个 skill 都很窄
- 每个 skill 任务边界明确
- 每个 skill 都有清晰触发条件

因此我们做财报生成 skill iteration 时，第一阶段应优先做 focused skills，而不是一上来追求一个“全自动财报生成总 skill”。

---

## 七、总结

LangAlpha 已经把“金融 agent harness”做成了一个相当成熟的工程系统。它的关键价值不在于某一个模型，而在于：

- PTC 执行范式
- sandbox 持久化
- 金融数据生态
- skill 的目录化 / 版本化 / 发现化
- subagent 分工
- 文档化交付

对我们来说，这意味着后续的 skill iteration 应该基于 LangAlpha 的现有架构演化，而不是重做一套抽象的 agent 框架。

最优路线是：

1. 先把现有 skill 作为初始化 skill set
2. 用财报样本和专家反馈做 focused iteration
3. 通过 lock / manifest / validation 把 skill 版本化
4. 逐步优化 skill composition 与 report-builder 流程

这会比从零开始训练一个“会写财报的模型”更可控，也更符合 LangAlpha 的系统哲学。

