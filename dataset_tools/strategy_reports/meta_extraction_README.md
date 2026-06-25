# Strategy Report Metadata Extraction

This tool converts curated strategy-report samples into benchmark metadata JSON with local extraction plus OpenRouter LLM calls.

## Entry Point

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/llm_extract_metadata.py --smoke-test --enable-vl --vl-limit 2
```

Default input:

```text
dataset_build/curated_strategy_samples_verified/metadata.jsonl
```

Default output:

```text
dataset_build/meta_extraction/final_cases.jsonl
```

## Model Routing

- `deepseek/deepseek-v4-flash`: high-volume text screening and candidate extraction.
- `deepseek/deepseek-v4-pro`: final schema synthesis, reasoning, validation repair.
- `qwen/qwen3-vl-235b-a22b-instruct`: screenshots for layout, charts, cover pages, and PDFs where the text layer is weak.

## Token Controls

- `--max-chars` limits local text excerpts sent to LLMs.
- `--local-only` runs PDF/HTML extraction without model calls.
- `--enable-vl --vl-limit N` caps visual calls by actual VL call count.
- Cached intermediate files live under the chosen `--work-dir`; omit `--no-cache` to reuse them.

## Useful Commands

Local extraction only:

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/llm_extract_metadata.py --sample-ids strategy_sample_001 strategy_sample_024 --local-only --work-dir dataset_build/meta_extraction_local
```

Small paid smoke test:

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/llm_extract_metadata.py --sample-ids strategy_sample_001 strategy_sample_024 --enable-vl --vl-limit 1 --work-dir dataset_build/meta_extraction_smoke2 --out dataset_build/meta_extraction_smoke2/final_cases.jsonl
```

Six-sample mixed smoke set:

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/llm_extract_metadata.py --smoke-test --enable-vl --vl-limit 2 --max-chars 10000 --render-pages 1 --work-dir dataset_build/meta_extraction_smoke6 --out dataset_build/meta_extraction_smoke6/final_cases.jsonl
```

## Current Smoke Result

Combined six-sample output:

```text
dataset_build/meta_extraction_smoke6_combined.jsonl
dataset_build/meta_extraction_smoke6_combined.json
```

Covered IDs:

```text
strategy_sample_001
strategy_sample_002
strategy_sample_003
strategy_sample_024
strategy_sample_028
strategy_sample_032
```
