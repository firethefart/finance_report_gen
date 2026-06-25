# Candidate-Only Verifier Session Handoff — 2026-06-19 — Rules Run r7

## Naming

`V2` means the candidate-only verifier variant that does not require a
reference report. It is not a version number.

From this run onward:

- engineering runs use `rN`;
- new result directories use `candidate_only_rules_rN`;
- historical directories ending in `_v1` through `_v5` are legacy run labels,
  not verifier versions.

## Current baseline

```text
evals/strategy_report/results/candidate_only_rules_r7/
```

Results:

- requested 26;
- completed 26;
- report-level failures 0;
- gate passed 19/26.

## Changes

### Numeric extraction

- Fixed the old three-digit ceiling that extracted `2026` as `202`.
- Added currency prefixes, large-number units, percentages, basis points and
  duration units such as `10-year`.
- Added analytical numeric-sentence filtering.
- Document IDs, page markers, publication metadata, year-only headings and
  small list/figure indices no longer count as quantitative claims.
- Metrics now expose raw, retained and filtered numeric sentence counts.

### Source evidence

- `source additional return avenues` no longer matches the source-marker regex.
- Author bios, footer links, home pages, social links and generic
  investment-management entry pages no longer count as traceable sources.
- Publisher provenance is separated from external data traceability.
- Publisher provenance contributes at most 12% of the source dimension and
  cannot substitute for citations.
- Manifest institution metadata is passed into the candidate parser as
  provenance metadata, not reference-report content.

### Output naming

- Layered summary title now says `Candidate-Only Verifier`.
- Per-report Markdown now says `Strategy Report Candidate-Only Verifier`.

## Key results

- GSAM Backdrop: 92.87, passed.
- BlackRock chartbook: 82.99, passed.
- generated baseline: 75.61, passed.
- generated optimized: 87.16, passed.
- optimized remains 11.55 points above baseline.
- State Street Macro: 71.64, rejected.
- State Street Fixed Income: 65.52, rejected.
- State Street Equity: 69.53, rejected.
- State Street Alternatives: 72.01, rejected.

The State Street decline is caused mainly by removing author/navigation links
from source evidence. Only the Macro page contains a genuine external
reference. Official publisher identity is preserved as provenance but does not
stand in for data sourcing.

## Layered results

- HTML: 78.09, gate 6/12.
- PDF: 85.74, gate 13/14.
- English: 78.19, gate 7/14.
- Chinese: 86.90, gate 12/12.

The remaining format gap is 7.65 points and the language gap is 8.71 points.
These remain open calibration concerns.

Artifacts:

- `evals/strategy_report/results/candidate_only_rules_r7/summary.json`
- `evals/strategy_report/results/candidate_only_rules_r7/layered_summary.json`
- `evals/strategy_report/results/candidate_only_rules_r7/layered_summary.md`

## Failures and warnings

- A PowerShell here-string displayed a Chinese regex test as question marks due
  to terminal encoding; real UTF-8 report data was used in regression runs.
- The first currency-prefix micro-test displayed `€` as `?` for the same
  terminal reason; PDF/HTML regression data verified the code path.
- r6 corrected source evidence but still counted year axes and document
  metadata as numeric claims. It is retained as an intermediate diagnostic run.
- A parallel read of `layered_summary.md` raced ahead of the writer and briefly
  returned “path not found”; serial verification confirmed the artifact exists.
- GSAM Active ETF continues to emit the known non-fatal MuPDF structure-tree
  warning.
- Final Python compilation passed.

## Next work

1. Audit Morgan Stanley heading/section boundaries and disclaimer leakage.
2. Improve PDF chart-text binding so visual axis values do not distort textual
   numeric discipline.
3. Reassess whether J.P. Morgan Energy belongs in the strategy-report quality
   gate or should remain only as a thematic robustness case.
4. Keep gate thresholds unchanged.
5. Run LLM/VLM layers only after deterministic checks converge further.
