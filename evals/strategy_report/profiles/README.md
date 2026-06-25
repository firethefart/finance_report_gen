# Strategy Report Verifier Profiles

Verifier profiles are JSON configuration files used by `evals/strategy_report/run_eval.py`.
They collect module switches, extraction limits, model choices, scoring weights, and gate
thresholds in one place so verifier behavior can be reproduced during alignment experiments.

## Available Profiles

- `full_best_effort.json`
  - Intended for pre-alignment and high-quality evaluation runs.
  - Enables Chart QA VLM, Claim/Numeric LLM, and Strategy Reasoning LLM.
  - Uses larger evidence packs and configurable scoring fusion/gate thresholds.

- `rules_only.json`
  - Intended for fast local smoke tests and debugging.
  - Disables paid LLM/VLM modules while keeping deterministic parsing and chart extraction.

## Usage

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_eval.py `
  --case evals/strategy_report/cases_merged33/eastmoney_cn_strategy_005.json `
  --cases-dir evals/strategy_report/cases_merged33 `
  --out-dir evals/strategy_report/results/profile_smoke `
  --verifier-profile rules_only
```

For full evaluation, use:

```powershell
.\.venv\Scripts\python.exe evals/strategy_report/run_eval.py `
  --case evals/strategy_report/cases_merged33/eastmoney_cn_strategy_005.json `
  --cases-dir evals/strategy_report/cases_merged33 `
  --out-dir evals/strategy_report/results/full_best_effort_smoke `
  --verifier-profile full_best_effort
```

`full_best_effort` calls paid LLM/VLM endpoints when the corresponding API key is available.

## Configuration Notes

- `modules`: enables or disables major verifier modules.
- `chart`: controls rendering, chart extraction, and VLM limits.
- `claim_numeric`: controls candidate claim limits, evidence pack retrieval, and numeric matching.
- `strategy_reasoning`: controls reasoning-chain limits and model choice.
- `scoring`: controls dimension weights, LLM/rule fusion weights, and gate thresholds.

Command-line flags still work for ad hoc debugging. Explicit flags can override profile defaults,
but alignment runs should prefer stable profile files.
