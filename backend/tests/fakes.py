from collections.abc import AsyncIterator

from app.llm.base import LLMMessage


class FakeLLMProvider:
    def __init__(
        self,
        *,
        response: str = "Fake LLM response",
        stream_chunks: list[str] | None = None,
    ) -> None:
        self.response = response
        self.stream_chunks = stream_chunks
        self.received_messages: list[LLMMessage] = []

    async def generate(
        self,
        messages: list[LLMMessage],
    ) -> str:
        self.received_messages = messages
        return self.response

    async def generate_stream(
        self,
        messages: list[LLMMessage],
    ) -> AsyncIterator[str]:
        self.received_messages = messages
        if self.stream_chunks is not None:
            for chunk in self.stream_chunks:
                yield chunk
        else:
            tokens = self.response.split(" ")
            for i, token in enumerate(tokens):
                if i > 0:
                    yield " "
                yield token