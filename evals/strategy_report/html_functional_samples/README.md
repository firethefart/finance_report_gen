# HTML Functional Samples

This directory contains a small user-reviewed functional test set for the
candidate-only/no-reference HTML verifier path.

These samples are intentionally not labeled as the main golden set. They are retained
because they are closer to report-like HTML than the broader crawl output and are useful
for verifier feature regression while the production target shifts toward model-generated
HTML reports.

Entry manifest:

```text
evals/strategy_report/html_functional_manifest.csv
```

Run:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_html_batch.py `
  --manifest evals/strategy_report/html_functional_manifest.csv `
  --out-dir migration_smoke_outputs/html_functional_baseline `
  --verifier-profile html_skill_iteration `
  --resume
```

Selection note:

- The broader public-HTML crawl is paused.
- User review rejected most crawl outputs as home/navigation/web-display pages rather
  than financial-report-like documents.
- Items 3, 4, 9, and 10 from `html_expansion_target10` were kept as a temporary
  functional test group.
- Synthetic/generated reports are intentionally not included here.
