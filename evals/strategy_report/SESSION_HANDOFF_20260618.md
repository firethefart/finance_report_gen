# Verifier V2 Session Handoff — 2026-06-18

## 当前结论

HTML 测试集扩充阶段已经完成，不要重新从候选清点开始。

当前正式核心测试集为 **26 份**：

- 12 HTML：10 份真实机构高质量离线 HTML + 2 份本地生成历史对照；
- 14 PDF；
- 14 英文、12 中文；
- 10 份真实机构 HTML 来自 GSAM、State Street、Morgan Stanley；
- HTML 覆盖 9 个 subtype；
- 单一 HTML 机构最多 4 份。

权威文件：

- 核心集：`evals/strategy_report/v2_testset_selection.json`
- 冻结 HTML：`evals/strategy_report/v2_frozen_html_set.json`
- 核心集硬审计：`evals/strategy_report/v2_testset_audit.json`
- HTML 资源审计：`evals/strategy_report/results/localized_html_resource_audit_frozen10.json`

2026-06-18 最新复跑结果：

- HTML 资源审计：10/10 admitted；
- 核心集硬审计：26/26 admitted；
- SHA-256 全部唯一；
- hard gate errors：0。

## 已完成的工程

### HTML 本地化

主要入口：

- `evals/strategy_report/localize_strategy_html.py`
- `evals/strategy_report/audit_localized_html_resources.py`
- `evals/strategy_report/build_html_candidate_inventory.py`

已支持：

- 浏览器滚动、等待和 lazy loading；
- computed style 固化；
- `src`、stylesheet、CSS `url()`、图片、SVG、字体资源本地化；
- 独立 `assets/` 文件，而非仅使用 data URI；
- 每样本 `resource_manifest.json`，包含 URL、本地路径、MIME、SHA-256、字节数、
  状态和失败原因；
- critical / noncritical 资源失败分类；
- State Street 的可配置 `flow_layout`；
- 可配置 live 捕获模式；
- 离线引用、文件存在性和 hash 审计。

### 已冻结的 10 份真实 HTML

GSAM：

1. Investment Backdrop 2026
2. Public Markets 2026
3. Portfolio Construction 2026
4. Fed Easing brief

State Street：

5. Macro Outlook 2026
6. Equity Outlook 2026
7. Fixed Income Outlook 2026
8. Alternatives Outlook 2026

Morgan Stanley：

9. Equity Rally 2026
10. Digital Assets and Banking

每份都在 `v2_frozen_html_set.json` 中记录：

- 内容审查：passed；
- 视觉审查：passed；
- resource manifest；
- Runtime Adapter 产物；
- subtype、archetype 和 test roles。

### 已排除候选

不要重新将以下页面计入高质量 HTML：

- BlackRock Policy Pivot：PDF 下载壳；
- BlackRock Europe Investment Renaissance：PDF 报告壳；
- State Street Implementation Guide：营销/下载壳，正文过短；
- Morgan Stanley IPO Market：视觉捕获不完整；
- J.P. Morgan Global Investment Strategy View：动态布局损坏。

详见 `evals/strategy_report/html_localization_candidates.json` 中的
`enabled: false` 和 `content_review_status`。

## 当前统一基线

结果：

`evals/strategy_report/results/v2_core_26_unified_rules_v2/summary.json`

执行状态：

- requested：26；
- completed：26；
- report-level failures：0；
- profile：`v2_html_smoke`；
- chart extraction：enabled。

该基线现在可以用于规则层的 HTML/PDF 和分层诊断。旧目录
`v2_core_26_unified_rules_v1` 继续保留作长路径失败证据。

### 已修复：Windows 长路径导致 HTML Runtime 失败

`html_runtime_adapter_v2.py` 现在：

- 在系统临时目录创建短 `n.html` 浏览副本，典型路径长度约 49；
- 正式 `normalized.html` 和其余产物仍写回原输出目录；
- manifest 记录 `browser_navigation`；
- `Page.navigate` 返回错误或最终 URL 为 `chrome-error://` 时立即失败，
  不再生成伪成功评分；
- 浏览器退出后删除临时副本。

回归结果：

- `v2_html_gsam_backdrop_2026` 正式路径长度 282 时仍成功；
- text length：50,062；
- headings：24；
- visual objects：10；
- 完整 Verifier 分数：91.65，Gold，gate passed；
- 既有 Runtime Adapter 回归集：7/7 completed；
- 全量 26/26 completed，0 failures；
- 12/12 HTML 未发现 `chrome-error://chromewebdata/` 或 text length 46。

全量命令：

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_v2_testset.py `
  --selection evals/strategy_report/v2_testset_selection.json `
  --out-dir evals/strategy_report/results/v2_core_26_unified_rules_v2 `
  --verifier-profile v2_html_smoke
```

分层摘要：

- `evals/strategy_report/results/v2_core_26_unified_rules_v2/layered_summary.json`
- `evals/strategy_report/results/v2_core_26_unified_rules_v2/layered_summary.md`

关键结果：

- HTML：平均 75.41，gate 通过 5/12；
- PDF：平均 84.07，gate 通过 12/14；
- 英文：平均 75.52，gate 通过 6/14；
- 中文：平均 85.39，gate 通过 11/12；
- brief commentary 平均 70.16，chartbook 平均 77.66；
- State Street 四份 HTML 均被 strategy reasoning 或总分 gate 拒绝；
- J.P. Morgan Energy PDF 的 strategy reasoning 也仅 0.085，说明偏差不只来自 HTML。

## 下一 session 的第一任务

不要再次修改测试集或 Runtime 长路径逻辑。开始模块级错误归因：

1. State Street 四份 HTML；
2. Morgan Stanley 两份 brief；
3. 英中两个 chartbook；
4. J.P. Morgan Energy deep dive。

优先检查：

- HTML heading/sectionization 是否丢失正文论证链；
- context binding 是否偏向固定关键词或长文本；
- brief/chartbook 是否被 standard/deep-dive 结构要求误伤；
- strategy reasoning 规则的英文表达覆盖；
- HTML visual QA 是否因 DOM 对象粒度与 PDF chart extractor 不一致而偏低。

## 后续开发顺序

1. 对上述重点样本做模块级证据审查；
2. 修 extractor、adapter、context binding 和 scoring 明显错误；
3. 重跑 26 份 rules 基线并比较分层变化；
4. 每次修改都在 26 份核心集上回归；
5. 再分层运行 Claim/Numeric、Strategy Reasoning、Chart VLM、Compliance；
6. 暂不启动昂贵的人类对齐。

## 不要做的事

- 不要重新凑 HTML 样本，10 份真实 HTML 已冻结；
- 不要降低资源完整性或视觉准入标准；
- 不要用旧的 24 样本 PDF 主导基线继续优化；
- 不要再使用 v1 的 HTML 26.14 分做任何质量判断；
- 不要读取或打印 `api_key.txt`；
- 根目录脚本统一使用 `.\.venv\Scripts\python.exe`。
