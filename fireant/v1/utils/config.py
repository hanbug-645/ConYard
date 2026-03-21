import os
from pathlib import Path
from typing import Any, Optional

import yaml


_config_cache: Optional[dict] = None


def load_config(config_path: Optional[str] = None) -> dict:
    """Load configuration from YAML file. Caches after first load."""
    global _config_cache
    if _config_cache is not None and config_path is None:
        return _config_cache

    if config_path is None:
        config_path = os.environ.get(
            "FIREANT_CONFIG",
            str(Path(__file__).parent.parent / "config.yaml"),
        )

    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)

    api_key_env = os.environ.get("GEMINI_API_KEY")
    if api_key_env:
        cfg["gemini"]["api_key"] = api_key_env

    _config_cache = cfg
    return cfg


def get_agent_config(role: str, config: Optional[dict] = None) -> dict:
    """Get merged config for a specific agent role.

    Returns a dict with keys: temperature, system_prompt, model, max_output_tokens, top_p.
    Agent-level overrides take precedence over gemini defaults.
    """
    if config is None:
        config = load_config()

    gemini = config.get("gemini", {})
    agent_cfg = config.get("agents", {}).get(role, {})

    return {
        "model": agent_cfg.get("model", gemini.get("model", "gemini-2.0-flash")),
        "temperature": agent_cfg.get("temperature", gemini.get("default_temperature", 0.7)),
        "max_output_tokens": agent_cfg.get("max_output_tokens", gemini.get("max_output_tokens", 8192)),
        "top_p": agent_cfg.get("top_p", gemini.get("top_p", 0.95)),
        "system_prompt": agent_cfg.get("system_prompt", ""),
        "api_key": gemini.get("api_key", ""),
    }


def get_parallel_config(config: Optional[dict] = None) -> dict:
    if config is None:
        config = load_config()
    return config.get("parallel", {
        "default_candidates": 3,
        "max_candidates": 5,
        "temperature_spread": [0.3, 0.7, 1.0],
    })


def get_escalation_config(config: Optional[dict] = None) -> dict:
    if config is None:
        config = load_config()
    return config.get("escalation", {
        "max_retries": 3,
        "fail_threshold": 3,
    })
