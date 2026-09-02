"""LLM backend factory.

Usage in route code:
    from llm import get_llm
    llm = get_llm()
    decision = llm.call_json(prompt)
    code = llm.call(prompt, temperature=0.4)

Auth / backend selection (env vars):
    GOOGLE_API_KEY   set this → uses Google AI API key (no GCP project needed)
    LLM_MODEL_ID     model to use, default: gemini-3.5-flash
    LLM_BACKEND      force backend: "gemini-api" | "gemini-vertex"
                     (auto-detected from GOOGLE_API_KEY when not set)
"""

import os

from .base import LLMBackend
from .gemini import GeminiBackend
from .gemini_api import GeminiApiBackend

_instance: LLMBackend | None = None


def get_llm() -> LLMBackend:
    """Return the singleton LLM backend, creating it on first call."""
    global _instance
    if _instance is None:
        api_key  = os.getenv("GOOGLE_API_KEY", "")
        backend  = os.getenv("LLM_BACKEND", "gemini-api" if api_key else "gemini-vertex")
        model_id = os.getenv("LLM_MODEL_ID", "gemini-3.5-flash")

        if backend == "gemini-api":
            if not api_key:
                raise RuntimeError("LLM_BACKEND=gemini-api but GOOGLE_API_KEY is not set")
            _instance = GeminiApiBackend(api_key=api_key, model_id=model_id)
        elif backend == "gemini-vertex":
            _instance = GeminiBackend(model_id=model_id)
        else:
            raise ValueError(f"Unknown LLM_BACKEND: {backend!r}")

    return _instance


__all__ = ["LLMBackend", "GeminiBackend", "GeminiApiBackend", "get_llm"]
