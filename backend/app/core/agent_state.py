"""Agent run / step / approval state definitions and the run state machine.

The state machine is the single source of truth for which run transitions are
legal. Persistence layers must perform transitions through
``app.repositories.agent.transition_run`` which enforces these rules with an
atomic compare-and-set so concurrent writers cannot violate them.
"""

from enum import StrEnum


class AgentRunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_RUN_STATUSES: frozenset[AgentRunStatus] = frozenset(
    {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
    }
)

ALLOWED_RUN_TRANSITIONS: dict[AgentRunStatus, frozenset[AgentRunStatus]] = {
    AgentRunStatus.CREATED: frozenset(
        {
            AgentRunStatus.RUNNING,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
    ),
    AgentRunStatus.RUNNING: frozenset(
        {
            AgentRunStatus.AWAITING_APPROVAL,
            AgentRunStatus.COMPLETED,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
    ),
    AgentRunStatus.AWAITING_APPROVAL: frozenset(
        {
            AgentRunStatus.RUNNING,
            AgentRunStatus.FAILED,
            AgentRunStatus.CANCELLED,
        }
    ),
    AgentRunStatus.COMPLETED: frozenset(),
    AgentRunStatus.FAILED: frozenset(),
    AgentRunStatus.CANCELLED: frozenset(),
}


class InvalidRunTransitionError(Exception):
    """Raised when a run transition violates the state machine."""

    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"Invalid agent run transition: {current} -> {target}")
        self.current = current
        self.target = target


def ensure_transition(
    current: AgentRunStatus | str,
    target: AgentRunStatus | str,
) -> None:
    try:
        current_status = AgentRunStatus(current)
        target_status = AgentRunStatus(target)
    except ValueError as exc:
        raise InvalidRunTransitionError(str(current), str(target)) from exc

    if target_status not in ALLOWED_RUN_TRANSITIONS[current_status]:
        raise InvalidRunTransitionError(current_status.value, target_status.value)


class StepStatus(StrEnum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DENIED = "denied"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    EXECUTED = "executed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ToolSideEffect(StrEnum):
    READ_ONLY = "read_only"
    WRITE = "write"
