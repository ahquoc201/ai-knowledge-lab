"""LLM schemas and structured output parser for Agent decisions.

The model is instructed to output JSON conforming strictly to either a tool call
decision or a final response decision. No arbitrary regex or code execution.
"""

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class AgentToolCallDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["call_tool"]
    tool_name: str = Field(min_length=1, max_length=100)
    reason: str = Field(default="", max_length=500)
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentFinalAnswerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["final_answer"]
    answer: str = Field(min_length=1)
    citations: list[str] = Field(default_factory=list)


class LLMParseError(Exception):
    def __init__(self, message: str, raw_output: str) -> None:
        super().__init__(message)
        self.raw_output = raw_output


def extract_json_block(text: str) -> str:
    """Extract a JSON object from text, handling markdown fences if present."""
    text = text.strip()
    # Match markdown code block ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # Try finding outer braces
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1].strip()

    return text


def parse_agent_decision(
    raw_output: str,
) -> AgentToolCallDecision | AgentFinalAnswerDecision:
    cleaned = extract_json_block(raw_output)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMParseError(f"Malformed JSON: {exc}", raw_output) from exc

    if not isinstance(data, dict):
        raise LLMParseError("Output JSON must be an object", raw_output)

    action = data.get("action")
    if action == "call_tool":
        try:
            return AgentToolCallDecision.model_validate(data)
        except ValidationError as exc:
            raise LLMParseError(f"Invalid call_tool schema: {exc}", raw_output) from exc
    elif action == "final_answer":
        try:
            return AgentFinalAnswerDecision.model_validate(data)
        except ValidationError as exc:
            raise LLMParseError(f"Invalid final_answer schema: {exc}", raw_output) from exc
    else:
        raise LLMParseError(
            f"Unknown action: '{action}'. Expected 'call_tool' or 'final_answer'",
            raw_output,
        )
