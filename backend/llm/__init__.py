"""LLM backend factory.

Usage in route code:
    from llm import get_llm
    llm = get_llm()
    decision = llm.call_json(prompt)
    code = llm.call(prompt, temperature=0.4)

Auth / backend selection (env vars):
    GOOGLE_API_KEY   set this → uses Google AI API key (no GCP project needed)
    LLM_MODEL_ID     model to use, default: gemini-3.8-flash
    LLM_BACKEND      force backend: "gemini-api" | "gemini-vertex"
                     (auto-detected from GOOGLE_API_KEY when not set)
"""

import os

from google import genai

from .base import LLMBackend
from .gemini import GeminiBackend

_instance: LLMBackend | None = None


def get_llm() -> LLMBackend:
    """Return the singleton LLM backend, creating it on first call."""
    global _instance
    if _instance is None:
        api_key  = os.getenv("GOOGLE_API_KEY", "")
        backend  = os.getenv("LLM_BACKEND", "gemini-api" if api_key else "gemini-vertex")
        model_id = os.getenv("LLM_MODEL_ID", "gemini-3.8-flash")

        if backend == "gemini-api":
            if not api_key:
                raise RuntimeError("LLM_BACKEND=gemini-api but GOOGLE_API_KEY is not set")
            client = genai.Client(api_key=api_key)
        elif backend == "gemini-vertex":
            client = genai.Client(
                vertexai=True,
                project=os.getenv("GCP_PROJECT_ID", "conyard"),
                location="global",
            )
        else:
            raise ValueError(f"Unknown LLM_BACKEND: {backend!r}")

        _instance = GeminiBackend(client=client, model_id=model_id)

    return _instance


__all__ = ["LLMBackend", "GeminiBackend", "get_llm"]
