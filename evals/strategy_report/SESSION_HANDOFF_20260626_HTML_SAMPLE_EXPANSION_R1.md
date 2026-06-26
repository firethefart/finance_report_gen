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
