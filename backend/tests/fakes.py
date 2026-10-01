from app.llm.base import LLMMessage


class FakeLLMProvider:
    def __init__(
        self,
        *,
        response: str = "Fake LLM response",
    ) -> None:
        self.response = response
        self.received_messages: list[LLMMessage] = []

    async def generate(
        self,
        messages: list[LLMMessage],
    ) -> str:
        self.received_messages = messages
        return self.response