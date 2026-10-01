from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextChunk:
    index: int
    content: str
    char_start: int
    char_end: int


def chunk_text(
    text: str,
    *,
    chunk_size: int = 1000,
    overlap: int = 200,
) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be greater than or equal to 0 "
            "and smaller than chunk_size"
        )

    if not text:
        return []

    chunks: list[TextChunk] = []

    start = 0
    index = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        chunks.append(
            TextChunk(
                index=index,
                content=text[start:end],
                char_start=start,
                char_end=end,
            )
        )

        if end == len(text):
            break

        start = end - overlap
        index += 1

    return chunks