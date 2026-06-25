# HTML Golden Sample Resource Audit - 2026-06-15

Purpose: identify HTML golden samples that are not stable/self-contained enough for repeatable verifier and chart-QA experiments.

## Removed From Active Golden Set
- `strategy_sample_018`: removed. Reason: non-self-contained HTML, cookie/consent surface, chart_count=0. missing_refs=8, cookie=5, consent=6.
- `strategy_sample_021`: removed. Reason: non-self-contained HTML, cookie/consent surface, chart_count=0. missing_refs=8, cookie=0, consent=2.
- `strategy_sample_033`: removed. Reason: non-self-contained HTML, cookie/consent surface, chart_count=0. missing_refs=25, cookie=5, consent=2.

## Delete Next - Strong Recommendation
- `strategy_sample_013`: delete next. Reason: non-self-contained HTML and chart_count=0, so it cannot support visual/chart evaluation. missing_refs=10, cookie=5, consent=6.
- `strategy_sample_026`: delete next. Reason: non-self-contained HTML and chart_count=0, so it cannot support visual/chart evaluation. missing_refs=64, cookie=1, consent=1.
- `strategy_sample_034`: delete next. Reason: non-self-contained HTML and chart_count=0, so it cannot support visual/chart evaluation. missing_refs=27, cookie=5, consent=2.

## Review Or Replace
- `strategy_sample_011`: review or replace. Reason: non-self-contained HTML with many missing local assets, but some chart candidates were extracted. missing_refs=50, external=28, chart_count=3, vl=3.
- `strategy_sample_016`: review or replace. Reason: non-self-contained HTML with many missing local assets, but some chart candidates were extracted. missing_refs=62, external=13, chart_count=6, vl=6.
- `strategy_sample_019`: review or replace. Reason: non-self-contained HTML with many missing local assets, but some chart candidates were extracted. missing_refs=52, external=28, chart_count=3, vl=3.
- `strategy_sample_020`: review or replace. Reason: non-self-contained HTML with many missing local assets, but some chart candidates were extracted. missing_refs=54, external=28, chart_count=7, vl=7.
- `strategy_sample_023`: review or replace. Reason: non-self-contained HTML with many missing local assets, but some chart candidates were extracted. missing_refs=54, external=13, chart_count=2, vl=2.
- `strategy_sample_024`: review or replace. Reason: non-self-contained HTML with many missing local assets, but some chart candidates were extracted. missing_refs=57, external=13, chart_count=5, vl=5.

## Detail Table
| case_id | status | recommendation | chart_count | vl_judged | cookie | consent | resources | external | root_relative | missing_local_refs |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `strategy_sample_018` | removed | removed_active_set | 0 | 0 | 5 | 6 | 61 | 53 | 8 | 8 |
| `strategy_sample_021` | removed | removed_active_set | 0 | 0 | 0 | 2 | 48 | 40 | 8 | 8 |
| `strategy_sample_033` | removed | removed_active_set | 0 | 0 | 5 | 2 | 29 | 4 | 25 | 25 |
| `strategy_sample_013` | active | delete_next | 0 | 0 | 5 | 6 | 63 | 53 | 10 | 10 |
| `strategy_sample_026` | active | delete_next | 0 | 0 | 1 | 1 | 68 | 4 | 64 | 64 |
| `strategy_sample_034` | active | delete_next | 0 | 0 | 5 | 2 | 30 | 3 | 27 | 27 |
| `strategy_sample_011` | active | review_or_replace | 3 | 3 | 0 | 2 | 78 | 28 | 50 | 50 |
| `strategy_sample_016` | active | review_or_replace | 6 | 6 | 0 | 2 | 75 | 13 | 62 | 62 |
| `strategy_sample_019` | active | review_or_replace | 3 | 3 | 0 | 3 | 80 | 28 | 52 | 52 |
| `strategy_sample_020` | active | review_or_replace | 7 | 7 | 0 | 3 | 82 | 28 | 54 | 54 |
| `strategy_sample_023` | active | review_or_replace | 2 | 2 | 0 | 3 | 67 | 13 | 54 | 54 |
| `strategy_sample_024` | active | review_or_replace | 5 | 5 | 0 | 1 | 70 | 13 | 57 | 57 |

## Rules
- delete_next: HTML is not self-contained and Chart QA extracted zero chart candidates.
- review_or_replace: HTML is not self-contained but some chart candidates exist; keep only for temporary text-only testing, not for stable visual golden evaluation.
- Raw source HTML files were not deleted; only active case membership was changed.
