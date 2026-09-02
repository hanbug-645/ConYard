"""Compatibility wrapper for the shared Gemini backend using API-key auth."""

from google import genai

from .gemini import DEFAULT_MODEL, GeminiBackend


class GeminiApiBackend(GeminiBackend):
    def __init__(self, api_key: str, model_id: str = DEFAULT_MODEL) -> None:
        super().__init__(client=genai.Client(api_key=api_key), model_id=model_id)
