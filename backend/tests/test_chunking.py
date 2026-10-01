import pytest

from app.services.chunking import chunk_text


def test_chunk_text_with_overlap():
    text = "abcdefghij"

    chunks = chunk_text(
        text,
        chunk_size=4,
        overlap=1,
    )

    assert len(chunks) == 3

    assert chunks[0].index == 0
    assert chunks[0].content == "abcd"
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == 4

    assert chunks[1].index == 1
    assert chunks[1].content == "defg"
    assert chunks[1].char_start == 3
    assert chunks[1].char_end == 7

    assert chunks[2].index == 2
    assert chunks[2].content == "ghij"
    assert chunks[2].char_start == 6
    assert chunks[2].char_end == 10


def test_chunk_text_empty():
    assert chunk_text("") == []


def test_chunk_text_rejects_invalid_chunk_size():
    with pytest.raises(
        ValueError,
        match="chunk_size must be greater than 0",
    ):
        chunk_text(
            "hello",
            chunk_size=0,
        )


def test_chunk_text_rejects_invalid_overlap():
    with pytest.raises(
        ValueError,
        match="overlap must be greater than or equal to 0",
    ):
        chunk_text(
            "hello",
            chunk_size=5,
            overlap=5,
        )