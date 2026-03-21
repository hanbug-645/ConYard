from typing import Optional

from google import genai
from google.genai import types

from .config import get_agent_config, load_config


class GeminiClient:
    """Wrapper around the Google Gemini API with per-agent configuration."""

    def __init__(self, role: str, temperature_override: Optional[float] = None):
        self.role = role
        config = load_config()
        self.agent_config = get_agent_config(role, config)

        if temperature_override is not None:
            self.agent_config["temperature"] = temperature_override

        self.client = genai.Client(api_key=self.agent_config["api_key"])

    def generate(
        self,
        prompt: str,
        context: str = "",
        temperature: Optional[float] = None,
    ) -> str:
        """Generate a response from Gemini.

        Args:
            prompt: The user/task prompt.
            context: Additional context (file contents, manifest, etc.).
            temperature: Override temperature for this specific call.
        """
        temp = temperature if temperature is not None else self.agent_config["temperature"]

        contents = []
        if context:
            contents.append(f"<context>\n{context}\n</context>\n\n")
        contents.append(prompt)

        response = self.client.models.generate_content(
            model=self.agent_config["model"],
            contents="".join(contents),
            config=types.GenerateContentConfig(
                system_instruction=self.agent_config["system_prompt"],
                temperature=temp,
                max_output_tokens=self.agent_config["max_output_tokens"],
                top_p=self.agent_config["top_p"],
            ),
        )
        return response.text

    def generate_json(
        self,
        prompt: str,
        context: str = "",
        temperature: Optional[float] = None,
    ) -> str:
        """Generate a JSON response from Gemini."""
        temp = temperature if temperature is not None else self.agent_config["temperature"]

        contents = []
        if context:
            contents.append(f"<context>\n{context}\n</context>\n\n")
        contents.append(prompt)
        contents.append("\n\nRespond with valid JSON only. No markdown fences.")

        response = self.client.models.generate_content(
            model=self.agent_config["model"],
            contents="".join(contents),
            config=types.GenerateContentConfig(
                system_instruction=self.agent_config["system_prompt"],
                temperature=temp,
                max_output_tokens=self.agent_config["max_output_tokens"],
                top_p=self.agent_config["top_p"],
                response_mime_type="application/json",
            ),
        )
        return response.text
