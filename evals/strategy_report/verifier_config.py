from __future__ import annotations

import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from eval_utils import ROOT


TOOLS_DIR = ROOT / "dataset_tools" / "strategy_reports"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from llm_clients import OpenRouterClient, read_api_key  # noqa: E402


Channel = Literal["llm", "vlm"]


def load_dotenv(path: Path | None = None) -> None:
    """Load simple KEY=VALUE pairs without overriding existing environment variables."""
    env_path = path or ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_api_key(channel: Channel = "llm", api_key_file: Path | None = None) -> str:
    load_dotenv()
    env_names = (
        ["STRATEGY_VERIFIER_VLM_API_KEY", "STRATEGY_VERIFIER_API_KEY", "OPENROUTER_API_KEY"]
        if channel == "vlm"
        else ["STRATEGY_VERIFIER_LLM_API_KEY", "STRATEGY_VERIFIER_API_KEY", "OPENROUTER_API_KEY"]
    )
    for name in env_names:
        value = os.getenv(name)
        if value:
            return value.strip()
    if api_key_file and api_key_file.exists():
        return read_api_key(api_key_file)
    raise ValueError(
        "Missing verifier API key. Set STRATEGY_VERIFIER_LLM_API_KEY/STRATEGY_VERIFIER_VLM_API_KEY "
        "or provide --api-key-file. Do not commit real keys."
    )


def get_base_url(channel: Channel = "llm") -> str:
    load_dotenv()
    env_names = (
        ["STRATEGY_VERIFIER_VLM_BASE_URL", "STRATEGY_VERIFIER_BASE_URL", "OPENROUTER_BASE_URL"]
        if channel == "vlm"
        else ["STRATEGY_VERIFIER_LLM_BASE_URL", "STRATEGY_VERIFIER_BASE_URL", "OPENROUTER_BASE_URL"]
    )
    for name in env_names:
        value = os.getenv(name)
        if value:
            return value.strip().rstrip("/")
    return "https://openrouter.ai/api/v1"


def make_verifier_client(channel: Channel, api_key_file: Path | None, log_dir: Path) -> OpenRouterClient:
    return OpenRouterClient(
        api_key=get_api_key(channel=channel, api_key_file=api_key_file),
        base_url=get_base_url(channel=channel),
        log_dir=log_dir,
    )


def apply_model_config_to_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Overlay production model names from environment onto a loaded verifier profile."""
    load_dotenv()
    data = deepcopy(profile)
    models = dict(data.get("models") or {})
    flash = os.getenv("STRATEGY_VERIFIER_LLM_FLASH_MODEL")
    pro = os.getenv("STRATEGY_VERIFIER_LLM_PRO_MODEL")
    vlm = os.getenv("STRATEGY_VERIFIER_VLM_MODEL")
    if flash:
        models["claim_extract"] = flash
        models["strategy_extract"] = flash
    if pro:
        models["consolidated_llm"] = pro
        models["claim_judge"] = pro
        models["strategy_judge"] = pro
        models["compliance_judge"] = pro
    if vlm:
        models["chart_vl"] = vlm
    data["models"] = models
    data["runtime_config"] = {
        "llm_base_url": redact_url(get_base_url("llm")),
        "vlm_base_url": redact_url(get_base_url("vlm")),
        "llm_key_source": key_source("llm"),
        "vlm_key_source": key_source("vlm"),
        "model_overrides": {
            "llm_flash": bool(flash),
            "llm_pro": bool(pro),
            "vlm": bool(vlm),
        },
    }
    return data


def key_source(channel: Channel) -> str:
    names = (
        ["STRATEGY_VERIFIER_VLM_API_KEY", "STRATEGY_VERIFIER_API_KEY", "OPENROUTER_API_KEY"]
        if channel == "vlm"
        else ["STRATEGY_VERIFIER_LLM_API_KEY", "STRATEGY_VERIFIER_API_KEY", "OPENROUTER_API_KEY"]
    )
    for name in names:
        if os.getenv(name):
            return name
    return "api_key_file_or_missing"


def redact_url(url: str) -> str:
    return url.split("?")[0]
