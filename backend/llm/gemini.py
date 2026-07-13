"""Vertex AI Gemini backend.

Switch models by changing DEFAULT_MODEL or setting the LLM_MODEL_ID env var.
"""

import logging

from vertexai.preview.generative_models import GenerationConfig, GenerativeModel

from .base import LLMBackend

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiBackend(LLMBackend):
    def __init__(self, model_id: str = DEFAULT_MODEL) -> None:
        self.model_id = model_id
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
