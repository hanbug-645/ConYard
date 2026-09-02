"""Gemini backend using the Google AI API key (google-genai SDK).

Uses generativelanguage.googleapis.com — no Vertex AI / GCP project needed.
Authenticate by setting GOOGLE_API_KEY in your environment or .env file.
"""

import logging

from google import genai
from google.genai import types

from .base import LLMBackend

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.8-flash"


class GeminiApiBackend(LLMBackend):
    def __init__(self, api_key: str, model_id: str = DEFAULT_MODEL) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model_id = model_id
        logger.info("GeminiApiBackend ready  model=%s  (API key auth)", model_id)

    def call(self, prompt: str, *, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        response = self.client.models.generate_content(
            model=self.model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return (response.text or "").strip()

    def call_json(self, prompt: str, *, temperature: float = 0.1) -> dict:
        response = self.client.models.generate_content(
            model=self.model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=1024,
                response_mime_type="application/json",
            ),
        )
        return self._parse_json((response.text or "").strip())

    def call_interaction(
        self,
        prompt: str,
        *,
        previous_interaction_id: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> tuple[str, str]:
        params = {
            "model": self.model_id,
            "input": prompt,
            "generation_config": {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
            "store": True,
        }
        if previous_interaction_id:
            params["previous_interaction_id"] = previous_interaction_id
        response = self.client.interactions.create(**params)
        return self._interaction_result(response)
