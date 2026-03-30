import logging
import re
import threading
from typing import Optional

from google import genai
from google.genai import types

from .config import get_agent_config, load_config

logger = logging.getLogger("fireant")

# Global semaphore to limit concurrent LLM calls
_llm_semaphore: Optional[threading.Semaphore] = None
_semaphore_lock = threading.Lock()


def _get_llm_semaphore() -> threading.Semaphore:
    """Get or create the global LLM call semaphore."""
    global _llm_semaphore
    if _llm_semaphore is None:
        with _semaphore_lock:
            if _llm_semaphore is None:
                config = load_config()
                max_concurrent = config.get("gemini", {}).get("max_concurrent_llm_calls", 10)
                _llm_semaphore = threading.Semaphore(max_concurrent)
                logger.info(f"[LLM Gateway] Initialized with max_concurrent_llm_calls={max_concurrent}")
    return _llm_semaphore


_FENCE_RE = re.compile(r"^```\w*\n?", re.MULTILINE)

def _strip_markdown_fences(text: str) -> str:
    """Remove ```lang ... ``` wrappers that LLMs sometimes add to code output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # Remove opening fence (```javascript, ```js, ```json, etc.)
        stripped = _FENCE_RE.sub("", stripped, count=1)
        # Remove closing fence
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3].rstrip()
    return stripped


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
        """Generate a text response from Gemini.

        Args:
            prompt: The user/task prompt.
            context: Additional context (file contents, manifest, etc.).
            temperature: Override temperature for this specific call.
        """
        suffix = "\n\n**CRITICAL: Your response MUST be under 500 words. Be extremely concise.**"
        return self._call_api(prompt, context, temperature, suffix, response_format=None)

    def generate_json(
        self,
        prompt: str,
        context: str = "",
        temperature: Optional[float] = None,
    ) -> str:
        """Generate a JSON response from Gemini."""
        suffix = "\n\n**CRITICAL: Response MUST be under 500 words AND valid JSON only. No markdown fences. Be extremely concise.**"
        return self._call_api(prompt, context, temperature, suffix, response_format="application/json")

    def _call_api(
        self,
        prompt: str,
        context: str,
        temperature: Optional[float],
        suffix: str,
        response_format: Optional[str],
    ) -> str:
        """Internal method to call Gemini API with common logic."""
        temp = temperature if temperature is not None else self.agent_config["temperature"]

        contents = []
        if context:
            contents.append(f"<context>\n{context}\n</context>\n\n")
        contents.append(prompt)
        contents.append(suffix)

        full_prompt = "".join(contents)
        log_prefix = "[LLM-JSON]" if response_format else "[LLM]"
        logger.info(
            f"{log_prefix} {self.role} | temp={temp:.1f} | "
            f"prompt_len={len(full_prompt)} chars | "
            f"preview: {full_prompt[:100].replace(chr(10), ' ')}..."
        )

        # Acquire semaphore to limit concurrent calls
        semaphore = _get_llm_semaphore()
        with semaphore:
            logger.debug(f"[LLM Gateway] {self.role} acquired slot")
            
            config_params = {
                "system_instruction": self.agent_config["system_prompt"],
                "temperature": temp,
                "max_output_tokens": self.agent_config["max_output_tokens"],
                "top_p": self.agent_config["top_p"],
            }
            if response_format:
                config_params["response_mime_type"] = response_format

            response = self.client.models.generate_content(
                model=self.agent_config["model"],
                contents=full_prompt,
                config=types.GenerateContentConfig(**config_params),
            )

            response_text = response.text
            # Strip markdown fences that LLMs sometimes wrap code in
            response_text = _strip_markdown_fences(response_text)
            logger.info(
                f"{log_prefix} {self.role} | response_len={len(response_text)} chars | "
                f"preview: {response_text[:100].replace(chr(10), ' ')}..."
            )
            logger.debug(f"[LLM Gateway] {self.role} released slot")
            return response_text
