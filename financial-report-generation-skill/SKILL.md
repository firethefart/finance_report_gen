---
name: financial-report-generation
description: Use this skill when generating financial reports, earnings updates, equity research notes, valuation memos, chart packs, or financial dashboards with a code agent. It guides evidence collection, code-based financial analysis, professional narrative writing, chart/table generation, document assembly, and QA.
---

# Financial Report Generation

## Purpose

Use this skill to generate high-quality financial reports with code-assisted research, analysis, visualization, and QA. Behave like a junior equity research analyst with strong engineering discipline: gather evidence, compute carefully, generate charts and tables from source data, and produce a professional, traceable report.

## Core Principle

Do not treat the report as one-shot writing. Treat it as a pipeline:

1. Research and source collection
2. Data cleaning and numerical analysis
3. Narrative writing
4. Charts, tables, and visual layout
5. Document assembly
6. QA and revision

Always separate facts, calculations, interpretation, and presentation.

## Required Workflow

### 1. Clarify Scope

Before starting, identify:

- Company / ticker
- Report type: earnings update, initiation, sector note, morning note, model update, valuation memo, etc.
- Time period
- Output format: markdown, PDF, DOCX, PPTX, XLSX, dashboard, or chart pack
- Required depth: quick brief, standard report, or institutional-style report

If any of these are missing, make a reasonable assumption and state it briefly.

### 2. Build Evidence Pool

Collect and save the source material before writing conclusions.

Prefer sources in this order:

1. SEC filings: 10-K, 10-Q, 8-K
2. Earnings releases and transcripts
3. Company investor presentations
4. Financial statements and market data
5. Reputable news and industry sources
6. Analyst or third-party data only as supporting context

For every important claim, preserve:

- Source name
- Date
- URL or file path
- Relevant section, table, or quote summary

Do not invent citations.

### 3. Compute Before Writing

Use code for numerical work whenever possible.

Required checks:

- Revenue, gross margin, EBIT/EBITDA margin, net income, EPS
- YoY / QoQ growth
- Free cash flow and cash conversion
- Debt, cash, net debt
- Segment or geography mix when relevant
- Valuation multiples if relevant: P/E, EV/EBITDA, EV/Sales, P/FCF
- Peer comparison if relevant

Avoid doing arithmetic mentally in prose. Generate tables from computed data.

### 4. Maintain a Clear Analysis Trail

Create intermediate files when doing non-trivial work:

```text
work/<task>/
  sources.md
  data/
  analysis.py
  tables/
  charts/
results/
  report.md
```

Use scripts for repeatable calculations. If a value appears in the report, it should be traceable to source data or a computation.

### 5. Write the Report

Structure depends on report type, but a standard equity report should include:

1. Executive summary
2. Key thesis / conclusion
3. Business overview
4. Recent financial performance
5. Segment / driver analysis
6. Valuation or peer comparison
7. Catalysts
8. Risks
9. Appendix: tables, sources, methodology

Writing rules:

- Use professional financial language.
- Separate observation from interpretation.
- Avoid over-claiming.
- Do not provide personalized investment advice unless explicitly requested and legally appropriate.
- Use cautious language for uncertainty.
- Tie conclusions back to evidence and numbers.

### 6. Generate Charts and Tables

Charts must answer a specific analytical question.

For each chart, define:

- Chart goal
- Source data
- Metric
- Time window
- Unit
- Interpretation

Good chart types:

- Line chart: time-series price, revenue, margin, FCF
- Bar chart: quarterly revenue, segment contribution, peer comparison
- Waterfall: margin bridge, revenue bridge, cash flow bridge
- Scatter: valuation vs growth, margin vs multiple
- Table: financial summary, assumptions, peer comps

Chart QA:

- Axis labels must include units.
- Titles must describe the analytical point.
- Data must match the report text.
- Do not use decorative charts without analytical purpose.

### 7. Perform QA Before Delivery

Run a final review using this checklist.

Data and facts:

- Are company name, ticker, period, and dates correct?
- Are all key financial numbers traceable?
- Are units consistent: millions, billions, %, per-share?
- Are YoY/QoQ calculations correct?

Reasoning and evidence:

- Does each conclusion follow from evidence?
- Are risks and caveats included?
- Are claims supported by sources?
- Are conflicting data points handled honestly?

Writing and structure:

- Is the report complete for its type?
- Are sections ordered logically?
- Is the tone professional?
- Are there unsupported predictions or overstatements?

Charts and tables:

- Do charts match the underlying data?
- Are labels, titles, legends, and units correct?
- Are charts referenced correctly in the text?
- Does each chart improve understanding?

Compliance and prudence:

- Avoid personalized investment advice.
- Avoid guarantees.
- Include uncertainty and risk disclosure.
- Distinguish factual reporting from opinion.

## Error Taxonomy

When revising, classify errors as:

- factual error
- numerical error
- source mismatch
- missing evidence
- reasoning gap
- over-claim
- template violation
- chart mismatch
- label / unit error
- layout issue
- compliance issue

Map each error to a fix:

- factual / source issue -> update research step
- numerical issue -> update calculation script
- reasoning issue -> revise analysis logic
- writing issue -> revise narrative section
- chart issue -> regenerate chart or fix chart spec
- layout issue -> revise assembly

## Final Output Requirements

At delivery, include:

1. The final report or document
2. A short source list
3. A short note on assumptions and limitations
4. Any generated files: tables, charts, models, scripts

Do not include unnecessary completion summaries unless requested. Keep the final answer focused on the deliverable.

## Short Prompt

Use this condensed prompt when a code agent needs a compact instruction block:

```text
You are generating a financial report. Do not write first. Work as a pipeline: collect sources, compute with code, create tables/charts from data, then write and QA.

Use this order:
1. Clarify company, period, report type, output format.
2. Build a source pool from SEC filings, earnings releases, transcripts, investor presentations, financial data, and reputable news.
3. Use code for all material calculations: growth, margins, EPS, FCF, multiples, peer comps.
4. Save intermediate data, scripts, tables, and charts.
5. Write a professional report with executive summary, thesis, financial performance, valuation/comps, catalysts, risks, and appendix.
6. Generate only charts that answer analytical questions; every chart needs title, source, unit, axis labels, and text alignment.
7. QA for factual errors, numerical errors, source mismatch, missing evidence, over-claiming, chart mismatch, unit errors, and compliance risk.

Every major claim must be traceable to a source or calculation. Avoid unsupported investment advice. Separate facts, calculations, interpretation, and presentation.
```
