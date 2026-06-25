# Latest Strategy Report Verifier Flowchart

Updated: 2026-06-16

This diagram reflects the current `full_best_effort` verifier profile used by:

```text
evals/strategy_report/results/full_eval_p2clean_20260615_chart4_pdf21/
```

Legend:

- Blue nodes are covered by the current human-alignment export.
- Gray nodes are active verifier modules but not included in the current alignment experiment.
- Edge labels show the current scoring/fusion weights where applicable.

```mermaid
flowchart TD
  A["Golden Case Metadata<br/>query, expected type, key facts,<br/>must-have sections, chart references"] --> B["Candidate Report<br/>PDF / HTML / generated report"]
  B --> C["Report Parser<br/>rule/parser<br/>text, pages, numbers, dates, links, sections"]

  C --> P{{"Parallel Module Execution"}}

  P --> RD["Render & Delivery<br/>rule<br/>parse quality, page/text availability"]
  P --> SC["Section Coverage<br/>rule<br/>must-have sections + required points"]
  P --> SQ["Source Quality<br/>rule<br/>source hints, authority signals, links"]
  P --> CCA["Claim-Citation Alignment<br/>rule<br/>key fact fuzzy coverage"]
  P --> NEC["Numeric / Entity Consistency<br/>rule<br/>number preservation + entity match"]
  P --> SRR["Strategy Reasoning Signals<br/>rule<br/>thesis/mechanism/implication keywords"]
  P --> SNR["Scenario & Risk<br/>rule<br/>scenario, sensitivity, risk boundary signals"]
  P --> CR["Compliance Redline<br/>rule<br/>forbidden certainty / guarantee wording"]

  P --> CE["Chart Extractor<br/>rule + rendering<br/>PDF/HTML chart candidates, crops,<br/>full-page screenshots, dedup"]
  CE --> VG["VLM Visual Gate<br/>VLM<br/>is this a real analytical visual?"]
  VG -- "skip non-visual; excluded from chart score" --> CNV["Non-Visual Record<br/>kept for audit, not scored"]
  VG -- "continue" --> VCL["VLM Chart Checklist<br/>VLM<br/>universal + contextual checklist,<br/>crop, readability, text binding"]
  VCL --> CQA["Chart QA Aggregation<br/>rule + VLM fusion"]
  CE --> CQA

  P --> CNX["Claim Extraction<br/>LLM flash<br/>candidate claims from report text"]
  CNX --> EP["Evidence Pack Builder<br/>retrieval + numeric audit<br/>top evidence snippets + unit normalization"]
  EP --> CNJ["Claim/Numeric Judge<br/>LLM pro<br/>fact coverage, numeric correctness,<br/>claim discipline"]

  P --> SRE["Strategy Chain Extraction<br/>LLM flash<br/>thesis, mechanism, implication,<br/>risk boundary"]
  SRE --> SRA["Programmatic Chain Audit<br/>rule<br/>chain completeness + theme overlap"]
  SRA --> SRJ["Strategy Reasoning Judge<br/>LLM pro<br/>professional reasoning rubric"]

  P -. "disabled in current profile" .-> CLJ["Consolidated LLM Judge<br/>LLM pro<br/>broad professional quality judge"]

  RD -- "22%" --> D_STR["structure dimension"]
  SC -- "78%" --> D_STR
  SQ -- "100%" --> D_SRC["sources dimension"]

  CCA -- "legacy facts: 52%" --> LF["Legacy Fact Score<br/>rule fusion"]
  NEC -- "legacy facts: 48%" --> LF
  LF -- "15%" --> D_FACT["facts dimension"]
  CNJ -- "85%" --> D_FACT

  SRR -- "35%" --> D_SR["strategy_reasoning dimension"]
  SRJ -- "65%" --> D_SR

  SNR -- "100%" --> D_RISK["scenario_risk dimension"]
  CQA -- "100%" --> D_CHART["charts dimension"]
  RD -- "100%" --> D_LAYOUT["writing_layout dimension"]
  CR -- "100%" --> D_COMP["compliance dimension"]

  D_STR -- "12 pts" --> SCORE["Weighted Overall Score<br/>0-100"]
  D_SRC -- "18 pts" --> SCORE
  D_FACT -- "18 pts" --> SCORE
  D_SR -- "16 pts" --> SCORE
  D_RISK -- "10 pts" --> SCORE
  D_CHART -- "14 pts" --> SCORE
  D_LAYOUT -- "7 pts" --> SCORE
  D_COMP -- "5 pts" --> SCORE

  SCORE --> GATE["Gate Rules<br/>overall >= 80<br/>sources >= 0.70<br/>facts >= 0.85<br/>charts >= 0.55<br/>compliance >= 0.95<br/>claim coverage >= 0.75<br/>numeric correctness >= 0.85<br/>claim discipline >= 0.65<br/>no redline blocker"]
  GATE --> OUT["Eval Output<br/>*.eval.json / *.eval.md<br/>score, grade, gate failures, issues"]

  OUT --> ALIGN["Human Alignment Export V2<br/>106 atomic tasks"]
  VCL -. "35 Chart QA tasks" .-> ALIGN
  CNJ -. "35 Fact/Numeric tasks" .-> ALIGN
  SRJ -. "35 Strategy Reasoning tasks" .-> ALIGN
  CR -. "1 Compliance Redline task<br/>only explicit redline trigger text" .-> ALIGN

  classDef align fill:#e8f1ff,stroke:#155eef,stroke-width:2px,color:#0b2e6f;
  classDef active fill:#f8fafc,stroke:#98a2b3,stroke-width:1px,color:#172033;
  classDef disabled fill:#f2f4f7,stroke:#d0d5dd,stroke-dasharray:4 4,color:#667085;
  classDef score fill:#fff7e6,stroke:#f79009,stroke-width:2px,color:#7a2e0e;

  class VG,VCL,CQA,CNJ,SRJ,CR,ALIGN align;
  class RD,SC,SQ,CCA,NEC,SRR,SNR,CE,CNX,EP,SRE,SRA active;
  class CLJ disabled;
  class SCORE,GATE,OUT,D_STR,D_SRC,D_FACT,D_SR,D_RISK,D_CHART,D_LAYOUT,D_COMP score;
```

## Current Scoring Details

### Overall Dimension Weights

| Dimension | Weight |
|---|---:|
| structure | 12 |
| sources | 18 |
| facts | 18 |
| strategy_reasoning | 16 |
| scenario_risk | 10 |
| charts | 14 |
| writing_layout | 7 |
| compliance | 5 |

### Dimension Construction

| Dimension | Current construction |
|---|---|
| structure | `0.78 * section_coverage + 0.22 * render_delivery` |
| sources | `source_quality`; consolidated LLM source score is disabled |
| facts | `0.15 * legacy_fact_rules + 0.85 * claim_numeric_llm` |
| legacy_fact_rules | `0.52 * claim_citation_alignment + 0.48 * numeric_entity_consistency` |
| strategy_reasoning | `0.35 * strategy_reasoning_rule + 0.65 * strategy_reasoning_llm` |
| scenario_risk | `scenario_risk`; consolidated LLM scenario score is disabled |
| charts | `chart_qa`; chart VLM judge is enabled inside this module |
| writing_layout | `render_delivery`; consolidated LLM layout score is disabled |
| compliance | `compliance_redline`; consolidated LLM compliance score is disabled |

### Chart QA Internal Weights

Report-level chart score:

| Chart component | Weight |
|---|---:|
| inventory | 0.15 |
| spec_completeness | 0.15 |
| data_faithfulness | 0.25 |
| chart_text_alignment | 0.20 |
| visual_clarity | 0.15 |
| financial_appropriateness | 0.10 |

Chart-level rule/VLM fusion:

| Subscore | Rule/VLM fusion |
|---|---|
| spec_completeness | `0.35 * rule + 0.65 * VLM metadata completeness` |
| data_faithfulness | `0.30 * rule + 0.70 * VLM data faithfulness` |
| chart_text_alignment | `0.50 * rule + 0.50 * VLM alignment/claim support` |
| visual_clarity | `0.50 * rule + 0.50 * VLM crop/readability/professionalism` |
| financial_appropriateness | `0.45 * rule + 0.55 * VLM suitability/usefulness/appropriateness` |

### Claim/Numeric LLM Internal Weights

| Subscore | Weight |
|---|---:|
| claim_coverage | 0.42 |
| numeric_correctness | 0.40 |
| claim_discipline | 0.18 |

The evidence retrieval pre-score uses:

| Signal | Weight |
|---|---:|
| token_overlap | 0.46 |
| number_similarity | 0.34 |
| hint_overlap | 0.12 |
| date_similarity | 0.08 |

### Strategy Reasoning LLM Internal Weights

| Subscore | Weight |
|---|---:|
| thesis_clarity | 0.15 |
| mechanism_depth | 0.20 |
| evidence_to_conclusion | 0.18 |
| investment_implication | 0.17 |
| scenario_risk_boundary | 0.13 |
| overclaim_control | 0.07 |
| theme_alignment | 0.10 |

## Current Human Alignment Coverage

Current export:

```text
evals/strategy_report/alignment_exports/pdf21_alignment_v2/
```

Covered by the current alignment experiment:

- Chart QA / VLM judgement: 35 atomic tasks.
- Claim/Numeric fact judgement: 35 atomic tasks.
- Strategy Reasoning chain judgement: 35 atomic tasks.
- Compliance Redline: 1 atomic task, only explicit redline trigger text.

Not covered in this round:

- Section coverage and generic rule-hit tasks, because they require broad report-level context.
- Overclaim / claim discipline standalone tasks, because current saved context is too short for expert review.
- Source quality and strict claim-citation audit, because full professional evidence verification is out of current scope.
- Consolidated LLM judge, because it is disabled in the current verifier profile.
