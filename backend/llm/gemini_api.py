"""Gemini backend using the Google AI API key (google-generativeai SDK).

Uses generativelanguage.googleapis.com — no Vertex AI / GCP project needed.
Authenticate by setting GOOGLE_API_KEY in your environment or .env file.
"""

import logging
import os

import google.generativeai as genai

from .base import LLMBackend

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiApiBackend(LLMBackend):
    def __init__(self, api_key: str, model_id: str = DEFAULT_MODEL) -> None:
        genai.configure(api_key=api_key)
        self.model_id = model_id
        logger.info("GeminiApiBackend ready  model=%s  (API key auth)", model_id)

    def call(self, prompt: str, *, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        model = genai.GenerativeModel(self.model_id)
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return response.text.strip()
