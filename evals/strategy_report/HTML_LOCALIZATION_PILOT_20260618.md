# HTML 资源本地化三机构试点（2026-06-18）

## 结论

本轮验证了 Goldman Sachs AM、State Street、Morgan Stanley 和 BlackRock
四种站点的端到端本地化。GSAM、State Street 与 Morgan Stanley 已形成正文完整、
资源独立落盘、无远程资源依赖且可由 Runtime Adapter V2 正确处理的离线快照。
BlackRock 的两个候选经 live
浏览器渲染后确认均为“网页摘要/作者信息 + PDF 正文链接”，不属于高质量 HTML
报告，已从启用候选中排除。

| 样本 | Runtime 结果 | 人工视觉复核 | 当前判断 |
| --- | --- | --- | --- |
| GSAM 2026 Investment Backdrop | 正文约 50k 字符；24 个标题；10 个 visual object；75/75 资源成功 | 正文、KPI、背景图和图表可读；无远程依赖 | 通过本轮离线资源与视觉试点 |
| State Street 2026 Macro Outlook | 正文约 10.5k 字符；7 个标题；3 个 visual object；14/14 资源成功 | flow-layout 清理后正文连续可读，作者图片和章节层级正常 | 通过本轮离线资源与视觉试点 |
| Morgan Stanley Equity Rally 2026 | 正文约 17.5k 字符；3 个标题；4 个 visual object；133 个资源成功 | 主图、Key Takeaways、五段论证和尾部推荐区均可读 | 通过；15 个旧版字体变体为已解释的非关键失败 |
| BlackRock Policy Pivot | live 捕获正文仍仅约 0.5k 字符 | 页面仅含标题、下载 PDF、作者和订阅壳 | 排除：PDF 下载壳 |
| BlackRock Europe Investment Renaissance | live 捕获正文约 1.2k 字符 | 页面仅含摘要、PDF 链接和作者信息 | 排除：PDF 报告壳 |

## 本轮修复

- 修复资源下载失败后已删除节点仍访问 `attrs` 导致的异常。
- 修复 CSS 资源 URL 被重复请求的问题。
- 修复先清理克隆 DOM、再按索引复制 computed style 导致的大规模样式错位。
- 修复丢弃 `display:none` 导致响应式重复内容同时显示的问题。
- 新增独立 `assets/` 目录和逐资源 `resource_manifest.json`，记录 URL、本地路径、
  MIME、SHA-256、字节数、状态和失败原因。
- 新增可配置 `flow_layout` 和 `live` 捕获模式。
- 新增资源完整性、hash、远程引用和本地引用审计脚本。

## 验证命令

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/localize_strategy_html.py `
  --sample-id html_gsam_outlook_backdrop_2026 `
  --sample-id html_ssga_macro_outlook_2026 `
  --sample-id html_blackrock_policy_pivot

.\.venv\Scripts\python.exe evals/strategy_report/html_runtime_adapter_v2.py `
  --html dataset_build/v2_localized_html/<sample-id>/index.html `
  --out-dir evals/strategy_report/results/<pilot-result> `
  --report-id <report-id>
```

## 产物

- 本地化页面：`dataset_build/v2_localized_html/`
- GSAM runtime：`evals/strategy_report/results/html_runtime_v2_pilot_gsam_final/`
- State Street runtime：`evals/strategy_report/results/html_runtime_v2_pilot_ssga_admitted/`
- Morgan Stanley runtime：`evals/strategy_report/results/html_runtime_v2_pilot_morgan_stanley/`
- 资源审计：`evals/strategy_report/results/localized_html_resource_audit_pilot.json`
- BlackRock 失败证据：`evals/strategy_report/results/html_runtime_v2_pilot_blackrock_live/`

## 下一步

1. 将已验证模式扩展到其余启用候选。
2. 为 State Street 同系列页面复用 flow-layout 配置并逐份视觉复核。
3. 批量扩展到 J.P. Morgan 等第四、第五家机构。
4. 扩充中文真实机构 HTML 候选。
