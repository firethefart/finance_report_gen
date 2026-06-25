# Golden Sample Resource Cleanup - 2026-06-15

Policy: remove every HTML golden sample with missing local resources. This keeps the active golden set static, repeatable, and suitable for verifier/chart-QA interpretation.

## Active Set After Cleanup
- Active cases: 21
- Format distribution: {'pdf': 21}
- Filtered previous-eval result dir: `evals/strategy_report/results/full_eval_p2clean_20260615_chart4_pdf21`

## Removed Cases
- `strategy_sample_018`: cookie_or_unstable_html_with_zero_charts
- `strategy_sample_021`: cookie_or_unstable_html_with_zero_charts
- `strategy_sample_033`: cookie_or_unstable_html_with_zero_charts
- `strategy_sample_011`: html_missing_local_resources
- `strategy_sample_013`: html_missing_local_resources
- `strategy_sample_016`: html_missing_local_resources
- `strategy_sample_019`: html_missing_local_resources
- `strategy_sample_020`: html_missing_local_resources
- `strategy_sample_023`: html_missing_local_resources
- `strategy_sample_024`: html_missing_local_resources
- `strategy_sample_026`: html_missing_local_resources
- `strategy_sample_034`: html_missing_local_resources

## Recomputed Previous Full-Eval Summary
- Score distribution: `{'min': 67.13, 'mean': 81.68, 'median': 82.04, 'max': 93.32}`
- Grade counts: `{'Bronze': 4, 'Silver': 14, 'Reject': 2, 'Gold': 1}`
- Gate counts: `{'passed': 9, 'failed': 12}`
- Module success: `{'claim_judge': 21, 'strategy_extraction': 21, 'strategy_judge': 21}`
- Gate failure counts: `{'overall_score_below_80': 5, 'fact_dimension_below_threshold': 7, 'redline_issue_present': 1, 'compliance_not_full_or_near_full': 5, 'fact_coverage_below_threshold': 3, 'numeric_correctness_below_threshold': 3, 'claim_discipline_below_threshold': 3, 'source_quality_below_70pct': 1}`

## Active Case IDs
- `strategy_sample_001`
- `strategy_sample_002`
- `strategy_sample_003`
- `strategy_sample_004`
- `strategy_sample_005`
- `strategy_sample_006`
- `strategy_sample_008`
- `strategy_sample_009`
- `strategy_sample_015`
- `strategy_sample_017`
- `strategy_sample_022`
- `eastmoney_cn_strategy_001`
- `eastmoney_cn_strategy_002`
- `eastmoney_cn_strategy_003`
- `eastmoney_cn_strategy_004`
- `eastmoney_cn_strategy_005`
- `eastmoney_cn_strategy_006`
- `eastmoney_cn_strategy_007`
- `eastmoney_cn_strategy_008`
- `eastmoney_cn_strategy_009`
- `eastmoney_cn_strategy_010`
