from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.context_builder import ContextSource
from app.services.message_source import (
    get_message_sources_by_message_ids,
    save_assistant_message_sources,
)


@pytest.mark.anyio
async def test_save_assistant_message_sources_maps_context_sources(
    monkeypatch,
):
    message = SimpleNamespace(id=uuid4())

    source = ContextSource(
        source_index=1,
        document_id=uuid4(),
        chunk_id=uuid4(),
        chunk_index=2,
        content="Persisted source content",
        similarity=0.91,
    )

    captured_sources = []

    async def fake_save_message_sources(
        session,
        *,
        sources,
    ):
        captured_sources.extend(sources)
        return sources

    monkeypatch.setattr(
        "app.services.message_source.save_message_sources",
        fake_save_message_sources,
    )

    result = await save_assistant_message_sources(
        None,
        message=message,
        sources=[source],
    )

    assert len(result) == 1
    assert len(captured_sources) == 1

    saved = captured_sources[0]

    assert saved.message_id == message.id
    assert saved.source_index == 1
    assert saved.document_id == source.document_id
    assert saved.chunk_id == source.chunk_id
    assert saved.chunk_index == 2
    assert saved.content == "Persisted source content"
    assert saved.similarity == 0.91


@pytest.mark.anyio
async def test_get_message_sources_by_message_ids_groups_sources(
    monkeypatch,
):
    message_a_id = uuid4()
    message_b_id = uuid4()

    source_a_1 = SimpleNamespace(
        message_id=message_a_id,
        source_index=1,
    )

    source_a_2 = SimpleNamespace(
        message_id=message_a_id,
        source_index=2,
    )

    async def fake_list_message_sources_by_message_ids(
        session,
        *,
        message_ids,
    ):
        assert message_ids == [
            message_a_id,
            message_b_id,
        ]

        return [
            source_a_1,
            source_a_2,
        ]

    monkeypatch.setattr(
        (
            "app.services.message_source."
            "list_message_sources_by_message_ids"
        ),
        fake_list_message_sources_by_message_ids,
    )

    grouped = await get_message_sources_by_message_ids(
        None,
        message_ids=[
            message_a_id,
            message_b_id,
        ],
    )

    assert grouped[message_a_id] == [
        source_a_1,
        source_a_2,
    ]

    assert grouped[message_b_id] == []