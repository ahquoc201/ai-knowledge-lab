from functools import lru_cache

import httpx

from app.core.config import get_settings
from app.llm.base import LLMMessage


class OllamaLLMProvider:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings()

        self.base_url = (
            base_url or settings.ollama_base_url
        ).rstrip("/")

        self.model = model or settings.ollama_model

        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.ollama_timeout_seconds
        )

    async def generate(
        self,
        messages: list[LLMMessage],
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in messages
            ],
            "stream": False,
            "think": False,
        }

        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
        ) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )

            response.raise_for_status()

        data = response.json()

        message = data.get("message")

        if not isinstance(message, dict):
            raise TypeError(
                "Ollama response does not contain a valid message"
            )

        content = message.get("content")

        if not isinstance(content, str):
            raise TypeError(
                "Ollama response content must be a string"
            )

        if not content.strip():
            raise ValueError(
                "Ollama response content must not be empty"
            )

        return content.strip()

@lru_cache
def get_ollama_llm_provider() -> OllamaLLMProvider:
    return OllamaLLMProvider()