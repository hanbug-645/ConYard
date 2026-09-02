"""Vertex AI Gemini backend.

Switch models by changing DEFAULT_MODEL or setting the LLM_MODEL_ID env var.
"""

import logging
import os

from google import genai
from google.genai import types
from vertexai.preview.generative_models import GenerationConfig, GenerativeModel

from .base import LLMBackend

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.8-flash"


class GeminiBackend(LLMBackend):
    def __init__(self, model_id: str = DEFAULT_MODEL) -> None:
        self.model_id = model_id
        self.client = genai.Client(
            vertexai=True,
            project=os.getenv("GCP_PROJECT_ID", "conyard"),
            location=os.getenv("GCP_LOCATION", "us-central1"),
        )
        logger.info("GeminiBackend ready  model=%s", model_id)

    def call(self, prompt: str, *, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        model = GenerativeModel(self.model_id)
        response = model.generate_content(
            prompt,
            generation_config=GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return response.text.strip()

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
