"""Unit tests for Agent LLM Parser and decision extraction."""

import pytest

from app.services.agent_llm_parser import (
    AgentFinalAnswerDecision,
    AgentToolCallDecision,
    LLMParseError,
    extract_json_block,
    parse_agent_decision,
)


def test_extract_json_block_raw():
    text = '{"action": "final_answer", "answer": "Done"}'
    assert extract_json_block(text) == text


def test_extract_json_block_markdown():
    text = """Here is my decision:
```json
{
  "action": "call_tool",
  "tool_name": "search_workspace_documents",
  "reason": "find docs",
  "arguments": {"query": "backend"}
}
```
Hope this helps!"""
    extracted = extract_json_block(text)
    assert '"action": "call_tool"' in extracted
    assert not extracted.startswith("Here is")


def test_parse_tool_call_decision():
    raw = '{"action": "call_tool", "tool_name": "search_workspace_documents", "arguments": {"query": "test"}}'
    decision = parse_agent_decision(raw)
    assert isinstance(decision, AgentToolCallDecision)
    assert decision.action == "call_tool"
    assert decision.tool_name == "search_workspace_documents"
    assert decision.arguments == {"query": "test"}


def test_parse_final_answer_decision():
    raw = '{"action": "final_answer", "answer": "The answer is 42", "citations": ["Doc A"]}'
    decision = parse_agent_decision(raw)
    assert isinstance(decision, AgentFinalAnswerDecision)
    assert decision.action == "final_answer"
    assert decision.answer == "The answer is 42"
    assert decision.citations == ["Doc A"]


def test_parse_invalid_json():
    with pytest.raises(LLMParseError, match="Malformed JSON"):
        parse_agent_decision("This is not JSON at all")


def test_parse_unknown_action():
    with pytest.raises(LLMParseError, match="Unknown action: 'do_something'"):
        parse_agent_decision('{"action": "do_something"}')


def test_parse_forbid_extra_fields():
    # Model trying to output unexpected fields in decision
    raw = '{"action": "call_tool", "tool_name": "search_workspace_documents", "extra": 123}'
    with pytest.raises(LLMParseError, match="Invalid call_tool schema"):
        parse_agent_decision(raw)
