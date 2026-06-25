# Strategy Report Metadata JSON Schema Guide

Use this schema guide when extracting metadata from a strategy research PDF. The output does not need to be formal JSON Schema syntax, but it must be valid JSON and follow these field meanings.

## Top-Level Shape

```json
{
  "case_id": "string",
  "source_pdf": {
    "file_path": "string",
    "file_name": "string",
    "sha256": "string|null",
    "file_size_bytes": 0,
    "page_count": 0,
    "parse_method": "text|ocr|hybrid|manual|unknown",
    "parse_quality": "excellent|good|fair|poor|failed"
  },
  "institution": {
    "name": "string",
    "business_type": "asset_manager|investment_bank|private_bank|brokerage|research_provider|regulator|exchange|other",
    "country_or_region": "string|null",
    "official_url": "string|null"
  },
  "report_title": "string",
  "report_date": "YYYY-MM-DD|null",
  "publication_period": "string|null",
  "authors_or_team": ["string"],
  "strategy_subtype": "string",
  "secondary_tags": ["string"],
  "classification_rationale": "string",
  "quality_tier": "A|B|C|Reject",
  "quality_rationale": "string",
  "candidate_query": {
    "query": "string",
    "language": "zh|en|mixed",
    "query_style": "retail_user|institutional_client|analyst_request|portfolio_committee|other",
    "scope_constraints": ["string"]
  },
  "expected_report_type": {
    "type": "string",
    "depth": "quick_brief|standard_report|institutional_style",
    "output_format": "webpage|markdown|pdf|pptx|docx|dashboard|unspecified",
    "expected_time_horizon": "string|null",
    "target_reader": "string|null"
  },
  "source_pack": [],
  "key_facts": [],
  "must_have_sections": [],
  "prohibited_mistakes": [],
  "reference_notes": {},
  "charts_and_tables_to_learn_from": [],
  "evaluation_hooks": {},
  "extraction_confidence": {
    "overall": 0.0,
    "classification": 0.0,
    "key_facts": 0.0,
    "source_pack": 0.0,
    "query": 0.0
  },
  "extraction_notes": "string"
}
```

## Source Pack Item

```json
{
  "name": "string",
  "type": "primary_report_pdf|institution_page|market_data|macro_data|company_or_sector_data|policy_or_regulatory|news_or_events|methodology|other",
  "url_or_path": "string|null",
  "date": "YYYY-MM-DD|null",
  "required": true,
  "observed_in_pdf": true,
  "notes": "string"
}
```

## Key Fact Item

```json
{
  "fact_id": "string",
  "claim": "string",
  "fact_type": "policy|macro|market|company|sector|transaction|forecast|valuation|risk|methodology|other",
  "value": "string|null",
  "unit": "string|null",
  "time_window": "string|null",
  "source_ref": "string",
  "confidence": 0.0,
  "why_it_matters": "string",
  "verification_hint": "string"
}
```

## Must-Have Section Item

```json
{
  "section_name": "string",
  "required": true,
  "purpose": "string",
  "required_points": ["string"],
  "evaluation_focus": "string"
}
```

## Prohibited Mistake Item

```json
{
  "mistake": "string",
  "severity": "blocker|high|medium|low",
  "why_it_matters": "string",
  "related_eval_dimension": "structure|sources|facts|strategy_reasoning|scenario_risk|charts|writing_layout|compliance"
}
```

## Reference Notes

```json
{
  "what_to_learn": ["string"],
  "style_notes": ["string"],
  "strong_sections": ["string"],
  "weaknesses_or_cautions": ["string"],
  "do_not_copy": ["string"]
}
```

## Charts and Tables

```json
{
  "chart_or_table_id": "string",
  "title_or_description": "string",
  "type": "line|bar|stacked_bar|scatter|heatmap|matrix|table|scenario_table|other",
  "why_exemplary": "string",
  "data_or_source_note": "string|null",
  "expected_eval_use": "chart_style|chart_logic|data_source|layout|do_not_use"
}
```

## Evaluation Hooks

Use this field to help future benchmark construction.

```json
{
  "automatic_checks": ["string"],
  "human_review_focus": ["string"],
  "likely_failure_modes": ["string"],
  "skill_patch_targets": ["research|analysis|strategy_writing|visualization|assembly|qa"]
}
```

## Confidence Scale

Use 0.0 to 1.0:

- `0.9-1.0`: directly supported by clean extracted text and/or official source.
- `0.7-0.89`: strongly supported but requires minor inference.
- `0.5-0.69`: plausible but extraction is incomplete or source support is indirect.
- `<0.5`: uncertain; mark clearly and avoid using as a golden key fact.

