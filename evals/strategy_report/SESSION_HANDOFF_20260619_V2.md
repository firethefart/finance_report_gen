# Verifier V2 Session Handoff — 2026-06-19 Iteration 5

## 最新结论

当前有效 rules-only 基线：

```text
evals/strategy_report/results/v2_core_26_unified_rules_v5/
```

结果：

- requested 26；
- completed 26；
- report-level failures 0；
- gate passed 21/26；
- strategy reasoning 精确 1.0 从 v3 的 9 份降为 0；
- strategy reasoning 大于等于 0.99 的样本为 2 份。

## 本轮修改

### Strategy reasoning 饱和

旧规则在 thesis/mechanism/implication/risk 分别达到 4/10/4/4 句后直接封顶，
不同强报告因此大量得到 1.0。

新规则：

- 先排除免责声明、制裁说明和 past-performance 等 boilerplate；
- 对完全重复的句子去重；
- 使用渐进饱和曲线，而不是线性计数后硬截断；
- 每个 archetype 使用不同目标句数；
- 达到目标句数时信号约为 0.8，更多独立证据继续加分但边际递减；
- metrics 记录 `eligible_sentence_count`、`signal_targets` 和 `signal_curve`。

### Archetype

删除基于 chart extractor 候选数的 chartbook 密度捷径。该捷径有两个问题：

- HTML 没有 page count 时分母退化为 1；
- PDF chart extractor 会保留 full-page/fallback 等候选，不能等同真实图表密度。

chartbook 现在需要标题或主标题中的明确证据，例如 `in charts`、`chartbook`
或中文图表专题表达。

### Manifest title

`run_v2_testset.py` 过去没有把 selection manifest 的 `title` 传给 evaluator。
当 PDF parser 无法抽取标题时，archetype 会丢失最可靠的元数据。

现在：

- `run_one_v2()` 接受 `report_title`；
- PDF parser 使用 manifest title 作为 fallback；
- HTML runtime 优先使用页面标题，缺失时使用 manifest title。

BlackRock 样本因此恢复为 chartbook，不再依赖图表候选数量猜测。

### Thesis 表达覆盖

补充通用观点表达：

- `we see`、`we view`、`we favor`、`we prefer`、`we remain`；
- `our base case`、`our conviction`；
- `stands out`、`well placed`。

这些表达用于恢复不采用 `we believe/we expect` 模板的明确配置观点。

## 关键回归

- GSAM Backdrop：strategy 1.000 → 0.996，仍通过；
- BlackRock chartbook：内部 archetype 恢复为 chartbook，strategy 0.846，
  总分 87.17，通过；
- State Street Alternatives：v4 一度回归为 74.62、拒绝；补充明确 thesis
  表达后 v5 为 77.30、通过；
- State Street Equity：74.91 → 77.25，明确观点证据恢复后通过；
- Morgan Stanley Digital Assets：69.15 → 69.72，仍拒绝；
- J.P. Morgan Energy：69.33 → 69.28，仍因低 implication/scenario 信号拒绝；
- generated baseline：75.29 → 76.08；
- generated optimized：89.91 → 88.29；
- optimized 仍高于 baseline 12.21 分。

## 分层结果

- HTML：平均 80.65，gate 8/12；
- PDF：平均 87.25，gate 13/14；
- 英文：平均 81.01，gate 9/14；
- 中文：平均 87.94，gate 12/12；
- strategy reasoning 均值：0.831；
- strategy reasoning population standard deviation：0.149。

产物：

- `evals/strategy_report/results/v2_core_26_unified_rules_v5/summary.json`
- `evals/strategy_report/results/v2_core_26_unified_rules_v5/layered_summary.json`
- `evals/strategy_report/results/v2_core_26_unified_rules_v5/layered_summary.md`

## 失败与警告记录

- 两个初始审计脚本按旧 JSON 层级读取，触发 `KeyError: 'score'`；修正为实际
  `overall_score`、`dimension_score_normalized` 和 `module_results` 后成功；
- 一次中文证据打印触发 Windows GBK `UnicodeEncodeError`；显式将 stdout
  设置为 UTF-8 后成功；
- 一次 PowerShell `rg` glob 写法触发 Windows 路径错误；改用目录加 `-g '*.py'`
  后成功；
- v4 全量虽然 26/26 成功，但 State Street Alternatives 回归为临界拒绝；
  保留 v4 作为失败证据，修复后另建 v5，没有覆盖；
- GSAM Active ETF 继续出现已知、非致命的 MuPDF structure-tree warning；
- 最终 `py_compile` 通过。

## 剩余拒绝

1. State Street Macro：74.87；
2. State Street Fixed Income：74.13；
3. Morgan Stanley Equity Rally：仍低于 75；
4. Morgan Stanley Digital Assets：69.72；
5. J.P. Morgan Energy：69.28。

下一轮应优先审查：

1. State Street 两份 74 分临界样本的 source/numeric，而不是继续抬 reasoning；
2. Morgan Stanley 的 heading/sectionization、正文来源边界和 disclaimer 混入；
3. J.P. Morgan Energy 是否本质上是能源专题而非投资策略报告，以及当前
   head/tail 文本压缩是否遗漏中段策略含义；
4. rules-only 收敛后再分层启用 LLM/VLM。

## 不要做

- 不要降低总分或 strategy gate；
- 不要重新选择核心测试集；
- 不要为了消除语言差距而机械压低中文样本；
- 不要读取或打印 `api_key.txt`；
- 根目录脚本继续使用 `.\.venv\Scripts\python.exe`。
