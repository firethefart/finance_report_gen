# HTML Sample Expansion Handoff — 2026-06-26

## Context

The verifier needs a larger local/offline HTML development set before large production
runs. Current committed HTML samples are useful for smoke testing, but not rich enough
for high-confidence generalization. The target after expansion is close to 1:1
Chinese/English admitted HTML samples.

## Implemented

- Added `dataset_tools/strategy_reports/discover_html_strategy_pages.py`.
  - Reads existing source configs.
  - Discovers report-like HTML URLs from seed pages.
  - Scores candidates using English/Chinese strategy-report signals.
  - Emits `html_strategy_candidates.jsonl` and a summary JSON.
- Added `dataset_tools/strategy_reports/build_html_localization_manifest.py`.
  - Converts discovery JSONL into `localize_strategy_html.py` manifest format.
  - Supports `--per-language` quota for near 1:1 Chinese/English selection.
  - Supports max-per-institution selection.
  - Handles UTF-8 BOM JSONL files generated on Windows.
- Added `dataset_tools/strategy_reports/audit_html_candidate_set.py`.
  - Audits localized HTML directories.
  - Checks text length, local resource availability, remote resource refs, and critical
    localization failures.
  - Optionally runs the HTML runtime adapter through Chrome.
  - Emits audit JSON/CSV and `html_production_manifest.csv` for `run_html_batch.py`.
- Added `evals/strategy_report/HTML_SAMPLE_EXPANSION_RUNBOOK.md`.
  - Documents source discovery, localization, audit/admission, 1:1 language policy,
    and verifier baseline commands.
- Linked the expansion runbook from the root README and agent runbook.

## Validation

Successful:

- `py_compile` passed for all three new dataset tools.
- `--help` smoke passed for:
  - `discover_html_strategy_pages.py`
  - `build_html_localization_manifest.py`
  - `audit_html_candidate_set.py`
- Audit smoke against existing localized HTML:
  - Command used `dataset_build/v2_localized_html`.
  - Candidate count: 19
  - Admitted count: 16
  - Selected count with `--per-language 3`: 3
  - Selected language counts: `en=3`
- Localization manifest smoke with a synthetic JSONL fixture:
  - Selected samples: 2
  - Language counts: `en=1`, `zh=1`

Failed then fixed:

- `build_html_localization_manifest.py` initially failed on a PowerShell-generated
  JSONL fixture because it contained a UTF-8 BOM. The reader now uses `utf-8-sig`.

## Important observation

The existing localized HTML set is heavily English. The audit smoke selected only
English samples because no admitted Chinese localized HTML was available from that
directory. To reach a true 1:1 expanded set, the next data pass must add Chinese HTML
sources or controlled Chinese generated HTML samples; do not admit weak pages merely to
force the ratio.

## Next recommended steps

1. Run discovery on `sources.expanded.json` and Chinese source configs with a small
   request budget.
2. Review `html_strategy_candidates.jsonl`, especially Chinese candidates.
3. Build a balanced localization manifest with `--per-language 15`.
4. Localize candidates with `localize_strategy_html.py`.
5. Audit with `audit_html_candidate_set.py`; use `--runtime` once static audit looks
   clean.
6. Run `run_html_batch.py` with `html_skill_iteration` over the admitted manifest and
   inspect score distribution by language.

## First live crawl/localization batch

Run directory:

- `migration_smoke_outputs/html_expansion_prod/`

Commands/results:

- Discovery:
  - Configs: `sources.expanded.json`, `sources.china.json`
  - Candidate count: 136
  - Failure count: 15
  - Language counts: `en=133`, `zh=3`
- Localization manifest:
  - Target: `--per-language 15`
  - Selected samples: 18
  - Language counts: `en=15`, `zh=3`
- Live localization:
  - Requested: 18
  - Localized: 14
  - Failed: 4
  - Failures were short/landing-page-like pages, including all 3 GF Securities Chinese
    official research entry pages.
- Static audit:
  - Candidate count: 14
  - Admitted count: 11
  - Selected count: 11
  - Selected language counts: `en=11`
- Verifier baseline with `html_skill_iteration`:
  - Requested: 11
  - Completed: 11
  - Execution failures: 0
  - Score min/max/mean: 48.06 / 83.07 / 57.63
  - Gate pass: 1/11
- Review dashboard:
  - `migration_smoke_outputs/html_expansion_prod/review_dashboard.html`
  - Served locally at:
    `http://127.0.0.1:8765/migration_smoke_outputs/html_expansion_prod/review_dashboard.html`

Tool fixes made during the live batch:

- `localize_strategy_html.py`
  - Fixed relative `--out-dir` handling when writing metadata paths.
  - Added `--min-text-length` so localization and audit thresholds can be staged.
- `build_html_localization_manifest.py`
  - Added sample ID uniquification to avoid overwriting repeated landing-page URLs.
- Added `build_html_candidate_review_dashboard.py`
  - Merges static audit, localization failures, and verifier baseline scores.
  - Provides an iframe-based local preview plus admitted/rejected filters.

Important live-batch conclusion:

- The crawler/localizer can now produce usable English local HTML samples, but the
  current Chinese official seed config does not produce admitted Chinese HTML strategy
  reports. The next iteration should focus on Chinese HTML source discovery:
  - repair mojibake Chinese source configs/keywords;
  - add public Chinese article-style sources, not only broker landing pages;
  - consider controlled Chinese generated HTML samples if public official HTML remains
    sparse;
  - avoid admitting weak landing pages merely to force the 1:1 ratio.

## Strict target-10 repair pass

The first live batch was manually reviewed and judged unacceptable because the accepted
pages still included home/navigation/index-like pages. A stricter report-like detection
mechanism was then implemented.

Implemented repair:

- Added `dataset_tools/strategy_reports/html_article_quality.py`.
  - Extracts the best article/main/body container.
  - Computes text length, Chinese character count, paragraph counts, link density,
    report signal count, landing signal count, visual count, and text preview.
  - Hard-rejects navigation/index pages, generic landing titles, link-heavy pages,
    podcast/video/webcast/profile pages, implausibly large aggregate pages, weak
    strategy-signal pages, and short/blank pages.
- Updated `discover_html_strategy_pages.py`.
  - Candidate links are fetched and validated as article-like pages before entering the
    main candidates JSONL.
  - Rejected candidates are written separately for diagnostics.
- Updated `build_html_localization_manifest.py`.
  - Defaults to article-like candidates only.
  - Keeps `article_quality` metadata in generated localizer samples.
- Updated `audit_html_candidate_set.py`.
  - Re-runs the same article quality gate after localization.
  - Fails localized pages that degrade into shell/navigation pages.
- Updated `build_html_candidate_review_dashboard.py`.
  - Shows article length, article quality score, paragraph count, link ratio, and text
    preview to support human review.

Strict batch outputs:

- Working directory: `migration_smoke_outputs/html_expansion_target10/`
- Source candidate pool: reused the prior strict discovery output after adding stronger
  post-localization gates.
- Localization manifest:
  - Selected candidates: 23
  - Language: `en=23`
- Live localization:
  - Requested: 23
  - Localized: 17
  - Failed: 6
- Strict static audit:
  - Candidate count: 17
  - Admitted count: 17
  - Selected count: 17
- Manual de-duplication:
  - Selected 10 distinct real HTML report/commentary samples across J.P. Morgan, GSAM,
    State Street, BlackRock, and Vanguard.
  - Manifest: `migration_smoke_outputs/html_expansion_target10/audit/html_target10_manifest.csv`
  - Review dashboard:
    `migration_smoke_outputs/html_expansion_target10/review_dashboard_target10.html`
- Verifier baseline on target 10:
  - Requested: 10
  - Completed: 10
  - Execution failures: 0
  - Score min/max/mean: 48.06 / 91.76 / 68.58
  - Verifier gate pass: 1/10

Interpretation:

- The target-10 set now passes the stricter sample-quality gate and is suitable for
  human review as real HTML report-like content.
- The verifier gate results remain conservative. Most failures are caused by
  `html_visual_resources_broken`, HTML text-boundary warnings, or strategy reasoning
  rule thresholds. Treat this as a verifier refinement signal, not as evidence that the
  samples are navigation pages.
- No Chinese samples were admitted in this repair pass. Per the user's instruction,
  synthetic Chinese reports were not used. Chinese real-HTML discovery remains a
  separate source-acquisition problem.
