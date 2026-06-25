# Strategy Report Golden Set Status

Updated: 2026-06-11

## Current Canonical Set

The current strategy-report golden sample set is:

```text
dataset_build/golden_samples_merged_cn10_no_landscape/final_cases.jsonl
```

Review dashboard:

```text
dataset_build/golden_samples_merged_cn10_no_landscape/index.html
```

This version merges the 10 Eastmoney Chinese portrait-format strategy reports into
the previous 27-case set, then removes PPT-like landscape PDFs from the previous
set. Source PDFs and HTML files are not physically deleted; removed cases are
excluded from this canonical metadata file only.

## Count Summary

| Item | Count |
|---|---:|
| Previous golden cases | 27 |
| Removed PPT-like landscape PDFs | 4 |
| Kept previous cases | 23 |
| Added Chinese strategy cases | 10 |
| Final canonical cases | 33 |

## Removed Cases

Removal rule: a PDF is treated as PPT-like landscape when the first sampled page
is landscape (`aspect > 1.05`) and at least 75% of the first 12 sampled pages are
landscape. HTML sources are not orientation-screened.

| case_id | Reason |
|---|---|
| `strategy_sample_007` | PPT-like landscape PDF |
| `strategy_sample_012` | PPT-like landscape PDF |
| `strategy_sample_014` | PPT-like landscape PDF |
| `strategy_sample_032` | PPT-like landscape PDF |

Detailed orientation evidence:

```text
dataset_build/golden_samples_merged_cn10_no_landscape/removed_landscape_cases.jsonl
dataset_build/golden_samples_merged_cn10_no_landscape/orientation_screening_profiles.json
```

## Distribution

Quality tier:

| Tier | Count |
|---|---:|
| A | 27 |
| B | 6 |

Broad theme:

| Theme | Count |
|---|---:|
| `macro_market_outlook` | 11 |
| `asset_allocation_portfolio` | 11 |
| `equity_and_bse_strategy` | 7 |
| `thematic_industry_strategy` | 3 |
| `m_and_a_industrial_strategy` | 1 |

Strategy subtype:

| Subtype | Count |
|---|---:|
| `annual_outlook` | 8 |
| `asset_allocation` | 6 |
| `thematic_strategy` | 4 |
| `bse_strategy_thematic` | 4 |
| `asset_allocation_strategy` | 2 |
| `midyear_outlook` | 1 |
| `thematic_research_energy_transition` | 1 |
| `alternative_investments` | 1 |
| `quarterly_outlook` | 1 |
| `equity_strategy` | 1 |
| `北交所行业主题报告` | 1 |
| `宏观策略月报` | 1 |
| `ma_strategy_thematic` | 1 |
| `weekly_investment_strategy` | 1 |

Machine-readable distribution summary:

```text
dataset_build/golden_samples_merged_cn10_no_landscape/distribution_summary.json
```
