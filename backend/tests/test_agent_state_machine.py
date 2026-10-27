"""Unit tests for Agent State Machine transitions."""

import pytest

from app.core.agent_state import (
    ALLOWED_RUN_TRANSITIONS,
    TERMINAL_RUN_STATUSES,
    AgentRunStatus,
    InvalidRunTransitionError,
    ensure_transition,
)


def test_valid_transitions():
    # CREATED -> RUNNING, FAILED, CANCELLED
    ensure_transition(AgentRunStatus.CREATED, AgentRunStatus.RUNNING)
    ensure_transition(AgentRunStatus.CREATED, AgentRunStatus.FAILED)
    ensure_transition(AgentRunStatus.CREATED, AgentRunStatus.CANCELLED)

    # RUNNING -> AWAITING_APPROVAL, COMPLETED, FAILED, CANCELLED
    ensure_transition(AgentRunStatus.RUNNING, AgentRunStatus.AWAITING_APPROVAL)
    ensure_transition(AgentRunStatus.RUNNING, AgentRunStatus.COMPLETED)
    ensure_transition(AgentRunStatus.RUNNING, AgentRunStatus.FAILED)
    ensure_transition(AgentRunStatus.RUNNING, AgentRunStatus.CANCELLED)

    # AWAITING_APPROVAL -> RUNNING, FAILED, CANCELLED
    ensure_transition(AgentRunStatus.AWAITING_APPROVAL, AgentRunStatus.RUNNING)
    ensure_transition(AgentRunStatus.AWAITING_APPROVAL, AgentRunStatus.FAILED)
    ensure_transition(AgentRunStatus.AWAITING_APPROVAL, AgentRunStatus.CANCELLED)


def test_terminal_states_have_no_outbound_transitions():
    for terminal in TERMINAL_RUN_STATUSES:
        assert len(ALLOWED_RUN_TRANSITIONS[terminal]) == 0
        for target in AgentRunStatus:
            with pytest.raises(InvalidRunTransitionError):
                ensure_transition(terminal, target)


def test_invalid_transitions():
    # Cannot jump from CREATED directly to COMPLETED or AWAITING_APPROVAL
    with pytest.raises(InvalidRunTransitionError):
        ensure_transition(AgentRunStatus.CREATED, AgentRunStatus.COMPLETED)
    with pytest.raises(InvalidRunTransitionError):
        ensure_transition(AgentRunStatus.CREATED, AgentRunStatus.AWAITING_APPROVAL)

    # Cannot transition to self
    with pytest.raises(InvalidRunTransitionError):
        ensure_transition(AgentRunStatus.RUNNING, AgentRunStatus.RUNNING)

    # Unknown string raises InvalidRunTransitionError
    with pytest.raises(InvalidRunTransitionError):
        ensure_transition("UNKNOWN", AgentRunStatus.RUNNING)
