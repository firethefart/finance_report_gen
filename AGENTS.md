# Agent Environment Notes

本仓库的根目录 Python 环境统一使用 `.venv`。当前机器上 `uv` 不在 PATH，因此已采用 `python -m venv .venv` 创建环境；如果后续机器可用 `uv`，也可以用 `uv venv .venv`。

## Virtual Environment

Create or refresh the environment from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r dataset_tools/strategy_reports/requirements.txt
```

Alternative when `uv` is available:

```powershell
uv venv .venv
uv pip install -r dataset_tools/strategy_reports/requirements.txt
```

Run scripts through the environment:

```powershell
.\.venv\Scripts\python.exe dataset_tools/strategy_reports/download_reports.py --config dataset_tools/strategy_reports/sources.seed.json --out dataset_build --limit 30
```

Do not use the nested `LangAlpha/` virtual environment or `LangAlpha/pyproject.toml` for the root-level dataset-building tools. Those belong to the cloned LangAlpha project.

## Dataset Tooling

Strategy-report dataset construction code lives in:

```text
dataset_tools/strategy_reports/
```

Generated data should live in:

```text
dataset_build/
```

The intended flow is:

1. Download or crawl public strategy research PDFs.
2. Validate that files are real PDFs.
3. Screen and bucket reports by strategy subtype and quality tier.
4. Extract metadata JSON for golden-set candidates.
