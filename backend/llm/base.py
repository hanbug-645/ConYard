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

    def call_json(self, prompt: str, *, temperature: float = 0.1) -> dict:
        """Send a prompt, parse the response as JSON, and return a dict.

        Strips Markdown fences if the model added them, then extracts the
        first `{ … }` block so surrounding explanation text is tolerated.
        """
        text = self.call(prompt, temperature=temperature, max_tokens=1024)
        text = re.sub(r'^```(?:json)?\s*\n?', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE).strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        return json.loads(match.group() if match else text)
