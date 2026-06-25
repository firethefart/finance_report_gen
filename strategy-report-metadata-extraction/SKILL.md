---
name: strategy-report-metadata-extraction
description: Extract structured golden-set metadata from professional strategy research PDFs. Use when Codex must convert strategy reports, market outlooks, thematic research, asset-allocation notes, sector strategy reports, or investment outlook PDFs into JSON metadata for benchmark/test-set construction, including query, expected report type, source pack, key facts, must-have sections, prohibited mistakes, reference notes, quality tags, and extraction confidence.
---

# Strategy Report Metadata Extraction

## Purpose

Use this skill to turn real strategy research PDFs into structured metadata for a strategy-report benchmark golden set. The output is not a summary for readers; it is an evaluation-case specification that another agent can use to generate or evaluate a strategy report.

The workflow is designed for PDFs from institutions such as BlackRock, Goldman Sachs AM, J.P. Morgan, Morgan Stanley, Vanguard, Fidelity, State Street, top brokerages, exchanges, regulators, and credible research providers.

## Core Principle

Extract benchmark metadata from the report's actual research design:

- What question could this report answer?
- What report subtype does it represent?
- What evidence and source pack would a future agent need?
- Which facts are critical enough to verify?
- Which sections are mandatory for a generated answer?
- Which mistakes would invalidate the output?
- What makes this report worth learning from?

Do not merely summarize the PDF. Build a reusable eval case.

## Required Output

Produce one JSON object per PDF. Follow the schema in `references/metadata-schema.md`. If extracting many PDFs, produce JSONL with one object per line plus a manifest.

Minimum required top-level fields:

- `case_id`
- `source_pdf`
- `institution`
- `report_title`
- `report_date`
- `strategy_subtype`
- `quality_tier`
- `candidate_query`
- `expected_report_type`
- `source_pack`
- `key_facts`
- `must_have_sections`
- `prohibited_mistakes`
- `reference_notes`
- `extraction_confidence`

## Workflow

### 1. Validate the PDF

Before extraction, inspect the file:

- Confirm it is a real PDF, not an HTML download saved as `.pdf`.
- Record file path, file size, page count if available, and parse method.
- If text extraction is poor, mark `parse_quality` as `poor` and use OCR or visual inspection if available.
- If the report is password-protected, paywalled, corrupted, or mostly image-only and no OCR is available, mark it as `rejected_parse_failure`.

### 2. Classify the Strategy Subtype

Assign one primary subtype and optional secondary tags.

Primary subtype options:

- `annual_outlook`
- `midyear_outlook`
- `quarterly_outlook`
- `monthly_market_outlook`
- `weekly_commentary`
- `thematic_strategy`
- `sector_strategy`
- `asset_allocation`
- `cross_asset_strategy`
- `macro_strategy`
- `rates_fx_credit_strategy`
- `equity_market_strategy`
- `ma_capital_markets_strategy`
- `sustainable_investing_strategy`
- `implementation_guide`

If uncertain, choose the closest subtype and explain in `classification_rationale`.

### 3. Score Report Quality for Sampling

Assign `quality_tier`:

- `A`: strong candidate for golden set. Clear thesis, high-quality sources/data, professional structure, useful charts, explicit risks or scenarios.
- `B`: usable candidate. Good professional report but weaker on evidence, structure, charting, or risk framing.
- `C`: archive only. Too short, too promotional, too narrow, weak evidence, poor parse quality, or not really strategy research.
- `Reject`: not suitable for this benchmark.

Quality is not about whether you agree with the view. It is about usefulness as a benchmark exemplar.

### 4. Generate the Candidate Query

Infer a realistic user query that this PDF could answer. The query should be natural, specific enough to constrain the task, and suitable for report generation.

Good query traits:

- Names the market, theme, asset class, sector, or time horizon.
- Asks for analysis, outlook, implications, or strategy.
- Does not leak the full report answer.
- Can be answered from public sources plus the PDF's research pattern.

Example:

```text
2026 年全球市场不确定性很高，AI 投资、通胀和利率都会影响资产配置。你能帮我写一份跨资产年度投资展望吗？
```

### 5. Extract Source Pack

Create a `source_pack` that future agents would need to reproduce a similar report. Include both observed sources in the PDF and inferred necessary sources.

Source pack categories:

- `primary_report_pdf`: the report itself.
- `institution_page`: official landing page if known.
- `market_data`: indices, yields, spreads, valuations, fund flows.
- `macro_data`: GDP, inflation, labor, PMI, fiscal/monetary policy.
- `company_or_sector_data`: earnings, capex, margins, supply/demand.
- `policy_or_regulatory`: official policy, regulator, exchange, central bank.
- `news_or_events`: reputable event context.
- `methodology`: capital market assumptions, model notes, index definitions.

For each source item, include `name`, `type`, `url_or_path`, `date`, `required`, and `notes`. If a source is inferred rather than explicitly cited, set `observed_in_pdf` to `false`.

### 6. Extract Key Facts

Extract only facts that are important for evaluation. Avoid dumping every statistic.

Each key fact should include:

- the exact claim in concise form
- fact type: `policy`, `macro`, `market`, `company`, `sector`, `transaction`, `forecast`, `valuation`, `risk`, `methodology`
- value and unit if numeric
- date or time window
- source reference
- confidence
- why it matters for the generated report

Do not treat forecasts as facts. Forecasts and assumptions must be labeled as `forecast` or `assumption`.

### 7. Define Must-Have Sections

Infer the sections that a generated report should contain for this case. Use strategy-report structure, not the PDF's page layout verbatim.

Common must-have sections:

- executive summary
- investment thesis / core view
- macro backdrop
- market setup
- asset class views
- sector or theme analysis
- evidence table
- scenario analysis
- risks and counterarguments
- charts and tables
- source list
- compliance / limitation note

For each section, include `section_name`, `purpose`, `required_points`, and `evaluation_focus`.

### 8. Define Prohibited Mistakes

List mistakes that should cause major penalties for this case. These are case-specific redlines, not generic quality issues.

Examples:

- misstate a central-bank policy date
- treat a forecast as historical fact
- confuse nominal and real yields
- omit downside scenario when the report thesis depends on risk asymmetry
- cite the institution's view without identifying it as a view
- generate charts without units or data dates
- claim personalized investment advice

Each prohibited mistake should include `mistake`, `severity`, `why_it_matters`, and `related_eval_dimension`.

### 9. Write Reference Notes

Create short notes for future evaluators and generation agents:

- what this report is especially good at
- what style or structure to learn from
- which charts/tables are exemplary
- what is weak or should not be copied
- what a generated report must preserve to count as successful

Do not copy long text from the PDF. Paraphrase.

### 10. QA the Metadata

Before finalizing:

- Ensure the JSON is valid.
- Ensure required fields are present.
- Ensure every `key_fact` has a source or is explicitly marked as inferred.
- Ensure the `candidate_query` matches the report subtype.
- Ensure `must_have_sections` are evaluation-oriented, not just a table of contents.
- Ensure `prohibited_mistakes` are specific enough to test.
- Ensure confidence scores reflect parse quality and evidence strength.

## Extraction Strategy

Use a three-pass approach for difficult PDFs:

1. **Skim pass**: title, date, institution, authors, subtype, executive summary, headings.
2. **Evidence pass**: charts, tables, footnotes, data sources, forecasts, key facts.
3. **Benchmark pass**: query, required sections, prohibited mistakes, reference notes.

Keep a short extraction log for batch runs. Record parse failures, ambiguity, missing dates, and low-confidence fields.

## Batch Selection Guidance

When building a 20-50 case golden set from 100-200 downloaded reports, bucket by subtype before selecting:

- annual / midyear outlook
- weekly / monthly commentary
- thematic strategy
- sector strategy
- asset allocation / cross-asset
- macro / rates / credit
- capital markets / M&A strategy
- implementation guide

Prefer diversity across institution, geography, asset class, time horizon, and visual style. Avoid selecting many near-duplicate outlooks from the same institution.

## Error Taxonomy

Use these issue tags during extraction:

- `parse_failure`
- `missing_date`
- `ambiguous_subtype`
- `weak_strategy_content`
- `promotional_not_research`
- `insufficient_sources`
- `chart_unreadable`
- `facts_low_confidence`
- `query_too_broad`
- `sections_not_inferable`
- `copyright_risk`

## When Information Is Missing

Do not hallucinate missing metadata.

- Use `null` for unknown exact values.
- Use `inferred_*` fields when making a reasoned inference.
- Add an explanation in `extraction_notes`.
- Lower `extraction_confidence`.
- If too many required fields are unknown, set `quality_tier` to `C` or `Reject`.

