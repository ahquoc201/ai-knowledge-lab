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