"""Abstract interface for LLM backends.

New backends (OpenAI, Anthropic, etc.) just subclass LLMBackend and
implement `call`. The `call_json` helper is provided for free on top of it.
"""

import json
import re
from abc import ABC, abstractmethod


class LLMBackend(ABC):
    @abstractmethod
    def call(self, prompt: str, *, temperature: float = 0.7, max_tokens: int = 4096) -> str:
        """Send a prompt and return the raw text response."""
        ...

    @abstractmethod
    def call_interaction(
        self,
        prompt: str,
        *,
        previous_interaction_id: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> tuple[str, str]:
        ...

    def call_json(self, prompt: str, *, temperature: float = 0.1) -> dict:
        text = self.call(prompt, temperature=temperature, max_tokens=1024)
        return self._parse_json(text)

    def call_json_interaction(
        self,
        prompt: str,
        *,
        previous_interaction_id: str | None = None,
        temperature: float = 0.1,
    ) -> tuple[dict, str]:
        text, interaction_id = self.call_interaction(
            prompt,
            previous_interaction_id=previous_interaction_id,
            temperature=temperature,
            max_tokens=1024,
        )
        return self._parse_json(text), interaction_id

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE).strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        return json.loads(match.group() if match else text)

    @staticmethod
    def _interaction_result(response) -> tuple[str, str]:
        text = getattr(response, "output_text", None)
        if text is None:
            text = "".join(
                getattr(output, "text", "") or ""
                for output in (getattr(response, "outputs", None) or [])
                if getattr(output, "type", None) == "text"
            )
        interaction_id = getattr(response, "id", "")
        if not interaction_id:
            raise ValueError("Gemini interaction response did not include an ID")
        return text.strip(), interaction_id
