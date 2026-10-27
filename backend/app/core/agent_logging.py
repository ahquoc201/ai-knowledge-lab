"""Structured (JSON) logging helper for the agent runtime.

Only identifiers, codes and counts are logged. Never pass document content, tool
output, prompts or tokens to ``log_event``.
"""

import json
import logging
from typing import Any

_SAFE_VALUE_LIMIT = 200


def _clean(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    text = str(value)
    return text[:_SAFE_VALUE_LIMIT]


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    payload = {"event": event, **{k: _clean(v) for k, v in fields.items()}}
    logger.log(
        level,
        json.dumps(payload, sort_keys=True),
        exc_info=exc_info,
    )
