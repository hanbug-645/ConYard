import os
from pathlib import Path
from typing import Optional

import yaml


_config_cache: Optional[dict] = None


def load_config() -> dict:
    """Load configuration from config.yaml and secrets.yaml.
    
    Loads main config from config.yaml, then merges secrets from secrets.yaml.
    Environment variables take highest precedence.
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    config_path = Path(__file__).parent.parent / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)

    # Load secrets from secrets.yaml if it exists
    secrets_path = Path(__file__).parent.parent / "secrets.yaml"
    if secrets_path.exists():
        with open(secrets_path, "r") as f:
            secrets = yaml.safe_load(f)
            # Merge secrets into config (deep merge for gemini section)
            if "gemini" in secrets:
                if "gemini" not in cfg:
                    cfg["gemini"] = {}
                cfg["gemini"].update(secrets["gemini"])

    # Environment variable takes highest precedence
    api_key_env = os.environ.get("GEMINI_API_KEY")
    if api_key_env:
        if "gemini" not in cfg:
            cfg["gemini"] = {}
        cfg["gemini"]["api_key"] = api_key_env

    _config_cache = cfg
    return cfg


def get_meta_prompt(config: Optional[dict] = None) -> str:
    """Get the meta prompt that applies to all agents."""
    if config is None:
        config = load_config()
    return config.get("meta_prompt", "")


def get_agent_config(role: str, config: Optional[dict] = None) -> dict:
    """Get merged config for a specific agent role.

    Returns a dict with keys: temperature, system_prompt, model, max_output_tokens, top_p.
    Agent-level overrides take precedence over gemini defaults.
    """
    if config is None:
        config = load_config()

    gemini = config.get("gemini", {})
    agent_cfg = config.get("agents", {}).get(role, {})
    meta_prompt = get_meta_prompt(config)

    # Combine meta_prompt with agent-specific system_prompt
    agent_system_prompt = agent_cfg.get("system_prompt", "")
    combined_prompt = f"{meta_prompt}\n\n{agent_system_prompt}" if meta_prompt else agent_system_prompt

    return {
        "model": agent_cfg.get("model", gemini.get("model", "gemini-2.0-flash")),
        "temperature": agent_cfg.get("temperature", gemini.get("default_temperature", 0.7)),
        "max_output_tokens": agent_cfg.get("max_output_tokens", gemini.get("max_output_tokens", 8192)),
        "top_p": agent_cfg.get("top_p", gemini.get("top_p", 0.95)),
        "system_prompt": combined_prompt,
        "api_key": gemini.get("api_key", ""),
    }


def get_escalation_config(config: Optional[dict] = None) -> dict:
    if config is None:
        config = load_config()
    return config.get("escalation", {
        "max_retries": 3,
        "fail_threshold": 3,
    })


def get_llm_config(config: Optional[dict] = None) -> dict:
    if config is None:
        config = load_config()
    return config.get("gemini", {})
