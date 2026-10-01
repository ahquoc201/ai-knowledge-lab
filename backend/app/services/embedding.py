from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.embedding import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL_NAME


class EmbeddingService:
    def __init__(self) -> None:
        self.model = SentenceTransformer(
            EMBEDDING_MODEL_NAME,
            device="cpu",
        )

    def embed_passages(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        if not texts:
            return []

        inputs = [
            f"passage: {text}"
            for text in texts
        ]

        embeddings = self.model.encode(
            inputs,
            normalize_embeddings=True,
        )

        vectors = embeddings.tolist()

        self._validate_dimensions(vectors)

        return vectors

    def embed_query(
        self,
        text: str,
    ) -> list[float]:
        embedding = self.model.encode(
            f"query: {text}",
            normalize_embeddings=True,
        )

        vector = embedding.tolist()

        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                "Unexpected embedding dimensions: "
                f"expected {EMBEDDING_DIMENSIONS}, got {len(vector)}"
            )

        return vector

    @staticmethod
    def _validate_dimensions(
        vectors: list[list[float]],
    ) -> None:
        for vector in vectors:
            if len(vector) != EMBEDDING_DIMENSIONS:
                raise ValueError(
                    "Unexpected embedding dimensions: "
                    f"expected {EMBEDDING_DIMENSIONS}, got {len(vector)}"
                )


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()