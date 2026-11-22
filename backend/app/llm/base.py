from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

LLMRole = Literal[
    "system",
    "user",
    "assistant",
]


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: LLMRole
    content: str


class LLMProvider(Protocol):
    async def generate(
        self,
        messages: list[LLMMessage],
    ) -> str: ...

    def generate_stream(
        self,
        messages: list[LLMMessage],
    ) -> AsyncIterator[str]: ...


def bind_model(llm: LLMProvider, model: str | None) -> LLMProvider:
    """Return a request-local provider that generates with ``model``.

    Providers are shared across concurrent requests, so routing must never assign
    ``llm.model``. Providers that support model selection expose ``with_model``;
    providers without it (e.g. test doubles) are returned unchanged.
    """
    with_model = getattr(llm, "with_model", None)
    if model and callable(with_model):
        return with_model(model)
    return llm