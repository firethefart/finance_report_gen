# 最新版策略报告 Verifier 流程图

更新时间：2026-06-16

本文对应当前全量测试使用的 `full_best_effort` verifier profile：

```text
evals/strategy_report/results/full_eval_p2clean_20260615_chart4_pdf21/
```

图例：

- 蓝色节点：本次人类对齐实验正在验证的环节。
- 灰色节点：当前 verifier 中启用，但本轮对齐实验暂不验证的环节。
- 虚线节点：当前 profile 中关闭的可选模块。
- 边上的百分比或分值：当前分数融合权重。

```mermaid
flowchart TD
  A["Golden Case 元数据<br/>query、报告类型、key facts、<br/>必备章节、参考图表"] --> B["待测报告<br/>PDF / HTML / 生成报告"]
  B --> C["报告解析器<br/>rule/parser<br/>抽取文本、页码、数字、日期、链接、章节"]

  C --> P{{"并行执行各检查模块"}}

  P --> RD["渲染与交付检查<br/>rule<br/>解析质量、页数、文本可用性"]
  P --> SC["章节覆盖检查<br/>rule<br/>must-have sections 与 required points"]
  P --> SQ["来源质量检查<br/>rule<br/>来源提示、权威来源信号、链接"]
  P --> CCA["事实-证据粗对齐<br/>rule<br/>key fact fuzzy coverage"]
  P --> NEC["数字/实体一致性<br/>rule<br/>数字保留、单位/实体匹配"]
  P --> SRR["策略推理信号<br/>rule<br/>观点、机制、投资含义关键词"]
  P --> SNR["情景与风险检查<br/>rule<br/>情景、敏感性、风险边界信号"]
  P --> CR["合规红线检查<br/>rule<br/>绝对化、保证性、无风险等禁用表述"]

  P --> CE["图表抽取器<br/>rule + rendering<br/>PDF/HTML 图表候选、目标截图、<br/>整页截图、去重"]
  CE --> VG["VLM 图表 Gate<br/>VLM<br/>判断截图是否为真实分析型可视化"]
  VG -- "非图表跳过；不计入图表分" --> CNV["非图表记录<br/>保留供审计，不参与评分"]
  VG -- "真实图表继续检查" --> VCL["VLM 图表 Checklist<br/>VLM<br/>通用 checklist + 情景 checklist，<br/>检查裁剪、可读性、图文一致性"]
  VCL --> CQA["Chart QA 聚合<br/>rule + VLM 融合"]
  CE --> CQA

  P --> CNX["候选 Claim 抽取<br/>LLM flash<br/>从报告正文抽取候选事实/观点"]
  CNX --> EP["证据包构建<br/>retrieval + numeric audit<br/>证据片段、数字/单位归一化"]
  EP --> CNJ["事实与数字 Judge<br/>LLM pro<br/>事实覆盖、数字正确性、表述纪律"]

  P --> SRE["策略推理链抽取<br/>LLM flash<br/>观点、机制、投资含义、风险边界"]
  SRE --> SRA["推理链程序化审计<br/>rule<br/>链条完整度、主题命中"]
  SRA --> SRJ["策略推理 Judge<br/>LLM pro<br/>按策略研究专业 rubric 打分"]

  P -. "当前 profile 关闭" .-> CLJ["综合 LLM Judge<br/>LLM pro<br/>整体专业质量判断"]

  RD -- "22%" --> D_STR["结构维度"]
  SC -- "78%" --> D_STR
  SQ -- "100%" --> D_SRC["来源维度"]

  CCA -- "legacy facts: 52%" --> LF["Legacy 事实分<br/>规则融合"]
  NEC -- "legacy facts: 48%" --> LF
  LF -- "15%" --> D_FACT["事实维度"]
  CNJ -- "85%" --> D_FACT

  SRR -- "35%" --> D_SR["策略推理维度"]
  SRJ -- "65%" --> D_SR

  SNR -- "100%" --> D_RISK["情景风险维度"]
  CQA -- "100%" --> D_CHART["图表维度"]
  RD -- "100%" --> D_LAYOUT["写作与版式维度"]
  CR -- "100%" --> D_COMP["合规维度"]

  D_STR -- "12 分" --> SCORE["加权总分<br/>0-100"]
  D_SRC -- "18 分" --> SCORE
  D_FACT -- "18 分" --> SCORE
  D_SR -- "16 分" --> SCORE
  D_RISK -- "10 分" --> SCORE
  D_CHART -- "14 分" --> SCORE
  D_LAYOUT -- "7 分" --> SCORE
  D_COMP -- "5 分" --> SCORE

  SCORE --> GATE["Gate 通过条件<br/>overall >= 80<br/>sources >= 0.70<br/>facts >= 0.85<br/>charts >= 0.55<br/>compliance >= 0.95<br/>claim coverage >= 0.75<br/>numeric correctness >= 0.85<br/>claim discipline >= 0.65<br/>无红线 blocker"]
  GATE --> OUT["评测输出<br/>*.eval.json / *.eval.md<br/>总分、等级、gate failure、issues"]

  OUT --> ALIGN["人类对齐实验导出 V2<br/>106 个原子任务"]
  VCL -. "35 个图表 QA 任务" .-> ALIGN
  CNJ -. "35 个事实/数字任务" .-> ALIGN
  SRJ -. "35 个策略推理任务" .-> ALIGN
  CR -. "1 个合规红线任务<br/>只保留明确触发文本" .-> ALIGN

  classDef align fill:#e8f1ff,stroke:#155eef,stroke-width:2px,color:#0b2e6f;
  classDef active fill:#f8fafc,stroke:#98a2b3,stroke-width:1px,color:#172033;
  classDef disabled fill:#f2f4f7,stroke:#d0d5dd,stroke-dasharray:4 4,color:#667085;
  classDef score fill:#fff7e6,stroke:#f79009,stroke-width:2px,color:#7a2e0e;

  class VG,VCL,CQA,CNJ,SRJ,CR,ALIGN align;
  class RD,SC,SQ,CCA,NEC,SRR,SNR,CE,CNX,EP,SRE,SRA active;
  class CLJ disabled;
  class SCORE,GATE,OUT,D_STR,D_SRC,D_FACT,D_SR,D_RISK,D_CHART,D_LAYOUT,D_COMP score;
```

## 总体评分权重

| 维度 | 权重 |
|---|---:|
| 结构完整性 `structure` | 12 |
| 来源质量 `sources` | 18 |
| 事实与数字 `facts` | 18 |
| 策略推理 `strategy_reasoning` | 16 |
| 情景与风险 `scenario_risk` | 10 |
| 图表质量 `charts` | 14 |
| 写作与版式 `writing_layout` | 7 |
| 合规 `compliance` | 5 |

## 各维度如何构成

| 维度 | 当前构成方式 |
|---|---|
| 结构完整性 | `0.78 * 章节覆盖 + 0.22 * 渲染与交付` |
| 来源质量 | `source_quality`，当前综合 LLM 来源判断关闭 |
| 事实与数字 | `0.15 * legacy fact rules + 0.85 * Claim/Numeric LLM` |
| legacy fact rules | `0.52 * 事实-证据粗对齐 + 0.48 * 数字/实体一致性` |
| 策略推理 | `0.35 * 规则策略信号 + 0.65 * Strategy Reasoning LLM` |
| 情景与风险 | `scenario_risk`，当前综合 LLM 情景判断关闭 |
| 图表质量 | `chart_qa`，内部启用 VLM gate 和 checklist |
| 写作与版式 | `render_delivery`，当前综合 LLM 版式判断关闭 |
| 合规 | `compliance_redline`，当前综合 LLM 合规判断关闭 |

## Chart QA 内部权重

报告级图表分：

| 图表子项 | 权重 |
|---|---:|
| 图表覆盖/库存 `inventory` | 0.15 |
| 规格完整性 `spec_completeness` | 0.15 |
| 数据可信度 `data_faithfulness` | 0.25 |
| 图文一致性 `chart_text_alignment` | 0.20 |
| 视觉清晰度 `visual_clarity` | 0.15 |
| 金融专业适配度 `financial_appropriateness` | 0.10 |

图表级 rule/VLM 融合：

| 子分 | 融合方式 |
|---|---|
| 规格完整性 | `0.35 * rule + 0.65 * VLM metadata completeness` |
| 数据可信度 | `0.30 * rule + 0.70 * VLM data faithfulness` |
| 图文一致性 | `0.50 * rule + 0.50 * VLM alignment/claim support` |
| 视觉清晰度 | `0.50 * rule + 0.50 * VLM crop/readability/professionalism` |
| 金融专业适配度 | `0.45 * rule + 0.55 * VLM suitability/usefulness/appropriateness` |

## Claim/Numeric LLM 内部权重

| 子分 | 权重 |
|---|---:|
| 事实覆盖 `claim_coverage` | 0.42 |
| 数字正确性 `numeric_correctness` | 0.40 |
| 表述纪律 `claim_discipline` | 0.18 |

证据包检索预评分使用：

| 信号 | 权重 |
|---|---:|
| 文本重合 `token_overlap` | 0.46 |
| 数字相似 `number_similarity` | 0.34 |
| 提示词重合 `hint_overlap` | 0.12 |
| 日期相似 `date_similarity` | 0.08 |

## Strategy Reasoning LLM 内部权重

| 子分 | 权重 |
|---|---:|
| 观点清晰度 `thesis_clarity` | 0.15 |
| 机制深度 `mechanism_depth` | 0.20 |
| 证据到结论 `evidence_to_conclusion` | 0.18 |
| 投资含义 `investment_implication` | 0.17 |
| 情景/风险边界 `scenario_risk_boundary` | 0.13 |
| 过度宣称控制 `overclaim_control` | 0.07 |
| 主题一致性 `theme_alignment` | 0.10 |

## 本次人类对齐实验覆盖范围

当前导出位置：

```text
evals/strategy_report/alignment_exports/pdf21_alignment_v2/
```

本轮会验证：

- 图表 QA / VLM 判断：35 个原子任务。
- 事实与数字核查：35 个原子任务。
- 策略推理链判断：35 个原子任务。
- 合规红线：1 个原子任务，仅保留明确触发红线的文本段。

本轮暂不验证：

- 章节覆盖、规则命中类任务：需要太多报告级上下文，不适合拆成原子任务。
- 过度宣称独立任务：当前保存的上下文不足，容易让专家被迫猜测。
- 来源质量与严格证据核验：完整 source audit 暂不属于本阶段目标。
- 综合 LLM Judge：当前 profile 中未启用。
