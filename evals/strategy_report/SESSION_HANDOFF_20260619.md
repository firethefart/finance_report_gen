# Verifier V2 Session Handoff — 2026-06-19

## 本轮结论

Windows 长路径修复后的统一基线已继续推进到：

```text
evals/strategy_report/results/v2_core_26_unified_rules_v3/
```

执行结果：

- requested：26；
- completed：26；
- report-level failures：0；
- profile：`v2_html_smoke`；
- chart extraction：enabled。

v3 修复了三类确定的规则层误判：

1. `v2_checks.py` 的中英文句子分隔符和中文词表存在乱码；
2. archetype 推断会被正文或来源名中偶然出现的 `brief` 误导；
3. HTML 作者头像、hero image 和推荐文章缩略图会被当成金融图表扣分。

## 已完成修改

### Strategy reasoning

- 恢复 `。！？.!?` 中英文句子切分；
- 不再把单行 HTML 正文视为一个最多 600 字符的句子；
- 清理结构、claim、reasoning、risk 和 archetype 词表中的乱码；
- 增加可泛化的因果表达，例如 `supported by`、`underpinned by`、
  `as a result`、`due to`、`requires` 和 `relies on`；
- thesis、implication 和 risk 信号改为按命中句子计数，而不是只看少数固定词是否出现；
- 输出 thesis、mechanism、implication 和 risk 的句子数量及样例证据。

### Archetype

- `brief` 只从标题和前六个主标题中识别，不再扫描全部标题/来源名；
- 长报告不会因为 `Carbon Brief` 等来源名被误判为 brief；
- chartbook 可由标题信号或高图表密度识别；
- 普通 `outlook` 不再自动等同 deep dive；
- J.P. Morgan Energy 从错误的 `brief_commentary` 恢复为 `deep_dive`；
- BlackRock Outlook in Charts 恢复为 `chartbook`。

### HTML visual gate

在无 VLM 的 rules-only 模式中，高置信非分析型 HTML 图片会被排除：

- 必须是 HTML runtime 的 `<img>`；
- 无来源、单位和数字；
- DOM 上下文无 `chart`、`figure`、`table`、`source`、`data` 等明确图表信号。

排除项保留在结果中，标记：

- `excluded_from_chart_score: true`；
- `chart_extractor_false_positive`；
- `rule_only_visual_gate`。

v3 的 12 份 HTML 共捕获 106 个视觉对象：

- 72 个进入 chart scoring；
- 34 个高置信装饰图被排除；
- GSAM 每份仅排除 1 个非分析图；
- 两份本地生成 HTML 的 6 个分析型视觉全部保留；
- State Street 的作者头像和 Morgan Stanley 的推荐文章缩略图不再作为坏图扣分。

## 关键回归

### State Street Alternatives

- v2：66.00，strategy reasoning 0.177，拒绝；
- v3：76.49，strategy reasoning 0.730，通过；
- 原文中的因果机制、配置含义和风险边界现在能被识别；
- 100×100 作者头像被排除，不再触发 chart data error。

### BlackRock chartbook

- v2：77.26，strategy reasoning 0.237，拒绝；
- v3：87.26，strategy reasoning 0.890，通过；
- archetype 恢复为 chartbook；
- 战术观点、超配/中性/低配和配置理由被识别。

### Morgan Stanley Digital Assets

- v2：62.57，strategy reasoning 0.287，visual QA 0.510；
- v3：69.15，strategy reasoning 0.626，visual QA 0.633；
- 4 个推荐文章/hero 缩略图全部排除；
- 仍因总体结构和 numeric/source 信号不足而拒绝，没有被无条件放行。

### J.P. Morgan Energy

- v2：66.66，错误 archetype 为 brief，strategy reasoning 0.085；
- v3：69.33，archetype 恢复为 deep dive，mechanism signal 0.8；
- 仍因明确投资配置含义和 scenario/risk 信号不足而拒绝；
- 这说明本轮修复恢复证据，但没有把所有高质量长报告直接抬过 gate。

### 已知质量对照

- 本地生成 baseline：73.04 → 75.29；
- 本地生成 optimized：84.87 → 89.91；
- optimized 与 baseline 的排序保持，差距从 11.83 扩大到 14.62。

## 分层结果

v3：

- HTML：平均 80.18，gate 通过 7/12；
- PDF：平均 87.82，gate 通过 13/14；
- 英文：平均 80.62，gate 通过 8/14；
- 中文：平均 88.59，gate 通过 12/12；
- 全集：gate 通过 20/26。

产物：

- `evals/strategy_report/results/v2_core_26_unified_rules_v3/summary.json`
- `evals/strategy_report/results/v2_core_26_unified_rules_v3/layered_summary.json`
- `evals/strategy_report/results/v2_core_26_unified_rules_v3/layered_summary.md`

## 本轮警告和未完成项

- GSAM Active ETF 继续出现已知、非致命的 MuPDF structure-tree warning；
- 最终 `git status --short` 因 Git 的 `dubious ownership` 安全校验被拒绝；
  本轮未修改全局 `safe.directory`，也未执行 stage、commit 或其他 Git 写操作；
- strategy reasoning 有 9/26 样本达到 1.0，后续需要检查饱和度和区分能力；
- HTML/PDF 平均仍相差 7.64 分，英文/中文仍相差 7.97 分；
- State Street Macro、Equity、Fixed Income 现在已通过 strategy gate，但总分仍略低于 75；
- Morgan Stanley 两份 brief 仍受结构和 source/numeric 信号影响；
- J.P. Morgan Energy 的低 implication/scenario 分究竟是报告属性还是截断/context 问题，
  仍需单独审查；
- 尚未运行 Claim/Numeric LLM、Strategy Reasoning LLM、Chart VLM 和 Compliance LLM。

最终语法检查：

```powershell
.\.venv\Scripts\python.exe -m py_compile `
  evals/strategy_report/v2_checks.py `
  evals/strategy_report/chart_qa.py `
  evals/strategy_report/run_v2_testset.py `
  evals/strategy_report/summarize_v2_testset.py
```

结果：通过，无输出、退出码 0。

收口检查中，一次把 `py_compile` 与内联 Python 指标核对合并执行的命令因
PowerShell 引号转义错误触发 `SyntaxError`；该失败没有执行或修改项目代码。
改用不含嵌套 f-string 的命令后退出码为 0，并确认：

- completed 26；
- failures 0；
- gate pass 20；
- strategy reasoning 1.0 共 9 份。

随后使用单次命令参数
`git -c safe.directory=<repository> status --short` 成功完成只读状态检查，
没有修改全局 Git 配置。仓库存在大量既有 staged/untracked 文件，本轮未暂存
或提交任何文件。

## 下一步

1. 检查 strategy reasoning 1.0 的饱和度，避免规则失去排序能力；
2. 审查 State Street 三份临界样本的 source/numeric/structure 证据；
3. 审查 Morgan Stanley brief 的 heading/sectionization 和正文边界；
4. 检查 J.P. Morgan Energy 的 26k 文本截断是否遗漏后半段投资含义；
5. rules-only 收敛后，分层运行 LLM/VLM 模块；
6. 暂不启动人类专家对齐。

## 不要做

- 不要重新选择或扩充核心测试集；
- 不要降低 HTML 资源或视觉准入标准；
- 不要通过降低 gate 来让临界样本通过；
- 不要把本轮目标解释为提高所有平均分；
- 不要读取或打印 `api_key.txt`；
- 根目录脚本继续使用 `.\.venv\Scripts\python.exe`。
