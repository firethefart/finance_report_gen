from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from chart_judges import DEFAULT_VL_MODEL
from claim_numeric_verifier import DEFAULT_CLAIM_EXTRACT_MODEL, DEFAULT_CLAIM_JUDGE_MODEL
from eval_utils import ROOT, read_json
from llm_judges import DEFAULT_MODEL
from strategy_reasoning_verifier import DEFAULT_STRATEGY_EXTRACT_MODEL, DEFAULT_STRATEGY_JUDGE_MODEL


PROFILE_DIR = ROOT / "evals" / "strategy_report" / "profiles"


DEFAULT_PROFILE: dict[str, Any] = {
    "profile_name": "default_inline",
    "execution": {
        "render_pages": 1,
        "extract_charts": True,
        "cache": True,
    },
    "models": {
        "consolidated_llm": DEFAULT_MODEL,
        "chart_vl": DEFAULT_VL_MODEL,
        "claim_extract": DEFAULT_CLAIM_EXTRACT_MODEL,
        "claim_judge": DEFAULT_CLAIM_JUDGE_MODEL,
        "strategy_extract": DEFAULT_STRATEGY_EXTRACT_MODEL,
        "strategy_judge": DEFAULT_STRATEGY_JUDGE_MODEL,
    },
    "modules": {
        "enable_chart_vl_judge": False,
        "enable_claim_numeric_llm": False,
        "enable_strategy_reasoning_llm": False,
        "enable_consolidated_llm_judge": False,
    },
    "chart": {
        "max_pages": 40,
        "max_charts": 16,
        "vl_max_charts": 3,
    },
    "claim_numeric": {
        "max_claims": 18,
        "max_key_facts": 12,
        "chunk_chars": 900,
        "top_k_evidence": 5,
        "neighbor_window": 1,
        "weights": {
            "token_overlap": 0.50,
            "number_similarity": 0.35,
            "hint_overlap": 0.10,
            "date_similarity": 0.05,
        },
    },
    "strategy_reasoning": {
        "max_chains": 10,
    },
    "scoring": {
        "dimension_weights": {
            "structure": 12,
            "sources": 18,
            "facts": 18,
            "strategy_reasoning": 16,
            "scenario_risk": 10,
            "charts": 14,
            "writing_layout": 7,
            "compliance": 5,
        },
        "fusion_weights": {
            "fact_legacy": 0.42,
            "fact_claim_numeric_llm": 0.58,
            "strategy_legacy": 0.35,
            "strategy_reasoning_llm": 0.65,
        },
        "gate_thresholds": {
            "overall_min": 80,
            "sources_min": 0.70,
            "facts_min": 0.85,
            "compliance_min": 0.95,
            "charts_min": 0.55,
        },
    },
}


def load_verifier_profile(profile: str | Path | None) -> dict[str, Any]:
    data = deepcopy(DEFAULT_PROFILE)
    if profile:
        profile_path = resolve_profile_path(profile)
        data = deep_merge(data, read_json(profile_path))
        data["profile_path"] = str(profile_path)
    return data


def resolve_profile_path(profile: str | Path) -> Path:
    path = Path(profile)
    if path.suffix:
        candidate = path if path.is_absolute() else ROOT / path
        if candidate.exists():
            return candidate
    candidate = PROFILE_DIR / f"{path.name}.json"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"Verifier profile not found: {profile}")


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


def profile_get(profile: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = profile
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current
