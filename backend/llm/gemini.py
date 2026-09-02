"""Shared Gemini backend for API-key and Vertex AI clients.

Switch models by changing DEFAULT_MODEL or setting the LLM_MODEL_ID env var.
"""

import logging

from google import genai
from google.genai import types

from .base import LLMBackend

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.8-flash"


class GeminiBackend(LLMBackend):
    def __init__(self, client: genai.Client, model_id: str = DEFAULT_MODEL) -> None:
        self.client = client
        self.model_id = model_id
        logger.info("GeminiBackend ready  model=%s", model_id)

    def _generate_content(
        self,
        prompt: str,
        *,
        temperature: float,
        max_tokens: int,
        response_mime_type: str | None = None,
    ) -> str:
        response = self.client.models.generate_content(
            model=self.model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
                response_mime_type=response_mime_type,
            ),
        )
        return (response.text or "").strip()

    def call(self, prompt: str, *, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        return self._generate_content(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def call_json(self, prompt: str, *, temperature: float = 0.1) -> dict:
        current_prompt = prompt
        current_temperature = temperature

        for attempt in range(2):
            text = self._generate_content(
                current_prompt,
                temperature=current_temperature,
                max_tokens=2048,
                response_mime_type="application/json",
            )
            try:
                return self._parse_json(text)
            except ValueError:
                if attempt == 1:
                    raise
                logger.warning("Gemini returned invalid JSON; retrying once")
                current_prompt = " ".join((
                    prompt,
                    "The previous response was invalid JSON.",
                    "Correct it and return only one complete JSON object.",
                    "INVALID RESPONSE:",
                    text,
                ))
                current_temperature = 0.0

        raise RuntimeError("JSON generation retry loop exited unexpectedly")

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
