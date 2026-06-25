# Verifier V2 Core Strategy-Report Test Set

Version: 2026-06-18  
Status: frozen 26-report HTML-balanced core set

Naming note: **Verifier V2 means the candidate-only verifier variant that does
not require a reference report. It is not a software version number.** Historical
result directories ending in `_v1` through `_v5` are legacy run labels only.
New result directories use `candidate_only_rules_rN`.

## Distribution

| Dimension | Current set |
| --- | ---: |
| Total | 26 |
| HTML | 12 |
| PDF | 14 |
| High-quality real-institution HTML | 10 |
| Generated historical-control HTML | 2 |
| English | 14 |
| Chinese | 12 |
| HTML subtypes | 9 |
| Maximum HTML count from one institution | 4 |

The authoritative files are:

- `v2_testset_selection.json`
- `v2_frozen_html_set.json`
- `v2_testset_audit.json`

The 10 real HTML reports come from Goldman Sachs Asset Management, State Street
Global Advisors, and Morgan Stanley. Every frozen HTML sample has passed content
review, visual review, Runtime Adapter V2, and offline resource auditing.

## Hard audit

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/audit_v2_testset.py `
  --selection evals/strategy_report/v2_testset_selection.json `
  --out evals/strategy_report/v2_testset_audit.json
```

Latest verified status:

- 26/26 admitted;
- 10/10 high-quality HTML admitted;
- no hard-gate errors;
- all files unique by SHA-256.

HTML resource audit:

```text
evals/strategy_report/results/localized_html_resource_audit_frozen10.json
```

Latest status: 10/10 admitted, no remote dependencies or unexplained critical
resource failures.

Visual artifacts:

```text
evals/strategy_report/results/v2_core_26_review/
```

## Current baseline

The current candidate-only rules baseline is:

```text
evals/strategy_report/results/candidate_only_rules_r8/summary.json
```

It completed 26/26 with zero report-level failures. The Runtime Adapter now
opens a short temporary browser work copy and records navigation evidence in
`browser_navigation`. All 12 HTML reports rendered without
`chrome-error://chromewebdata/`.

Layered summaries:

```text
evals/strategy_report/results/candidate_only_rules_r8/layered_summary.json
evals/strategy_report/results/candidate_only_rules_r8/layered_summary.md
```

Legacy run `r1` remains evidence of the Windows long-path bug. Legacy run `r2`
is the valid pre-reasoning-fix comparison baseline. Legacy run `r3` is the
first sentence/archetype repair baseline; legacy run `r4` is retained as
evidence of a detected State Street regression before corrected legacy run
`r5`:

```text
evals/strategy_report/results/v2_core_26_unified_rules_v1/
evals/strategy_report/results/v2_core_26_unified_rules_v2/
evals/strategy_report/results/v2_core_26_unified_rules_v3/
evals/strategy_report/results/v2_core_26_unified_rules_v4/
evals/strategy_report/results/v2_core_26_unified_rules_v5/
```

`candidate_only_rules_r6` is retained as the intermediate run that fixed source
false positives before numeric metadata filtering was completed.

## Fixtures

Synthetic adapter fixtures remain separate:

```text
evals/strategy_report/html_fixtures/
evals/strategy_report/html_runtime_test_set.json
```

They do not count toward the 26 report-level samples.
