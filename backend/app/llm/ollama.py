"""Ollama chat provider.

The provider is an immutable value object: one process-wide default instance is shared
by all requests (``get_ollama_llm_provider``), so per-request model routing must never
mutate it. Use :meth:`OllamaLLMProvider.with_model` (or ``app.llm.base.bind_model``) to
obtain a request-local provider bound to the routed model (T260040).
"""

import asyncio
import dataclasses
import json
import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import get_settings
from app.llm.base import LLMMessage

logger = logging.getLogger(__name__)

_NS_PER_MS = 1_000_000


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class OllamaLLMProvider:
    base_url: str | None = None
    model: str | None = None
    # Read timeout: maximum silence between bytes. For streaming this bounds prompt
    # evaluation (time to first token); for non-streaming it bounds the whole generation.
    timeout_seconds: float | None = None
    connect_timeout_seconds: float | None = None
    # Hard deadline for one generation, enforced in addition to the read timeout.
    total_timeout_seconds: float | None = None
    num_ctx: int | None = None
    num_predict: int | None = None
    temperature: float | None = None
    keep_alive: str | None = None

    def __post_init__(self) -> None:
        settings = get_settings()
        resolved = {
            "base_url": (self.base_url or settings.ollama_base_url).rstrip("/"),
            "model": self.model or settings.ollama_model,
            "timeout_seconds": _first(self.timeout_seconds, settings.ollama_timeout_seconds),
            "connect_timeout_seconds": _first(
                self.connect_timeout_seconds, settings.ollama_connect_timeout_seconds
            ),
            "total_timeout_seconds": _first(
                self.total_timeout_seconds, settings.ollama_total_timeout_seconds
            ),
            "num_ctx": _first(self.num_ctx, settings.ollama_num_ctx),
            "num_predict": _first(self.num_predict, settings.ollama_num_predict),
            "temperature": _first(self.temperature, settings.ollama_temperature),
            "keep_alive": _first(self.keep_alive, settings.ollama_keep_alive),
        }
        for name, value in resolved.items():
            object.__setattr__(self, name, value)

    def with_model(self, model: str | None) -> "OllamaLLMProvider":
        """Return a request-local provider bound to ``model``; ``self`` is left untouched."""
        if not model or model == self.model:
            return self
        return dataclasses.replace(self, model=model)

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            self.timeout_seconds,
            connect=self.connect_timeout_seconds,
        )

    def _payload(self, messages: list[LLMMessage], *, stream: bool) -> dict[str, Any]:
        options: dict[str, Any] = {}
        if self.num_ctx:
            options["num_ctx"] = self.num_ctx
        if self.num_predict:
            options["num_predict"] = self.num_predict
        if self.temperature is not None:
            options["temperature"] = self.temperature
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": message.role,
                    "content": message.content,
                }
                for message in messages
            ],
            "stream": stream,
            "think": False,
        }
        if options:
            payload["options"] = options
        if self.keep_alive:
            payload["keep_alive"] = self.keep_alive
        return payload

    def _log_metrics(self, data: dict[str, Any], *, stream: bool) -> None:
        """Log Ollama's own counters so prompt-eval vs generation latency is observable."""
        if "prompt_eval_count" not in data and "eval_count" not in data:
            return
        logger.info(
            "ollama_generation model=%s stream=%s prompt_tokens=%s prompt_eval_ms=%s "
            "gen_tokens=%s gen_ms=%s load_ms=%s total_ms=%s",
            self.model,
            stream,
            data.get("prompt_eval_count"),
            _ms(data.get("prompt_eval_duration")),
            data.get("eval_count"),
            _ms(data.get("eval_duration")),
            _ms(data.get("load_duration")),
            _ms(data.get("total_duration")),
        )

    async def generate(
        self,
        messages: list[LLMMessage],
    ) -> str:
        payload = self._payload(messages, stream=False)

        async with httpx.AsyncClient(timeout=self._timeout()) as client:
            try:
                response = await asyncio.wait_for(
                    client.post(f"{self.base_url}/api/chat", json=payload),
                    timeout=self.total_timeout_seconds,
                )
            except TimeoutError as exc:
                raise httpx.ReadTimeout(
                    f"Ollama generation exceeded {self.total_timeout_seconds}s"
                ) from exc

            response.raise_for_status()

        data = response.json()
        self._log_metrics(data, stream=False)

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

    async def generate_stream(
        self,
        messages: list[LLMMessage],
    ) -> AsyncIterator[str]:
        payload = self._payload(messages, stream=True)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.total_timeout_seconds

        # Closing this generator (client disconnect / cancellation) exits both context
        # managers, which closes the HTTP stream and makes Ollama abort the generation.
        async with httpx.AsyncClient(timeout=self._timeout()) as client, client.stream(
            "POST",
            f"{self.base_url}/api/chat",
            json=payload,
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if loop.time() > deadline:
                    raise httpx.ReadTimeout(
                        f"Ollama generation exceeded {self.total_timeout_seconds}s"
                    )
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if data.get("error"):
                    raise httpx.HTTPError("Ollama reported an error during streaming")

                message = data.get("message")
                if isinstance(message, dict):
                    token = message.get("content")
                    if isinstance(token, str) and token:
                        yield token

                if data.get("done"):
                    self._log_metrics(data, stream=True)


def _first(value: Any, default: Any) -> Any:
    return value if value is not None else default


def _ms(nanoseconds: Any) -> int | None:
    return int(nanoseconds) // _NS_PER_MS if isinstance(nanoseconds, int) else None


@lru_cache
def get_ollama_llm_provider() -> OllamaLLMProvider:
    return OllamaLLMProvider()
