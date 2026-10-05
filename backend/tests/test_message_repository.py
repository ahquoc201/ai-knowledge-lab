from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.repositories.message import (
    list_recent_messages_by_conversation_for_user,
)


@pytest.mark.anyio
async def test_list_recent_messages_returns_chronological_order():
    newest = SimpleNamespace(
        id=uuid4(),
        content="Newest",
    )

    older = SimpleNamespace(
        id=uuid4(),
        content="Older",
    )

    scalars = MagicMock()
    scalars.all.return_value = [
        newest,
        older,
    ]

    result = MagicMock()
    result.scalars.return_value = scalars

    session = MagicMock()
    session.execute = AsyncMock(
        return_value=result,
    )

    messages = await list_recent_messages_by_conversation_for_user(
        session,
        conversation_id=uuid4(),
        user_id=uuid4(),
        limit=10,
    )

    assert messages == [
        older,
        newest,
    ]

    statement = session.execute.await_args.args[0]

    compiled = str(
        statement.compile(
            compile_kwargs={
                "literal_binds": True,
            }
        )
    )

    assert "LIMIT 10" in compiled.upper()