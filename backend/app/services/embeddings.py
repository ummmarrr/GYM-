"""Turning text into vectors, via Gemini rather than a local model.

Embedding locally would mean shipping a model and a few hundred megabytes of runtime, which
does not fit the 512 MB the free hosting tier allows. Calling the API keeps the service small
at the cost of a network round trip.
"""

import logging
import math
from functools import lru_cache

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# The API rejects very large batches, and a gym's PDF is measured in hundreds of chunks.
BATCH_SIZE = 50
QUERY_CACHE_SIZE = 512


class EmbeddingUnavailable(RuntimeError):
    """Raised when text could not be embedded, so callers can degrade instead of failing."""


def _unit(vector: list[float]) -> list[float]:
    """Scale to unit length.

    Gemini only returns normalised vectors at its native 3072 dimensions; anything shorter has
    to be normalised here or cosine distance is measured against inconsistent magnitudes.
    """
    length = math.sqrt(sum(value * value for value in vector))
    return [value / length for value in vector] if length else vector


class GeminiEmbedder:
    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.gemini_embedding_model
        self.dimensions = settings.embedding_dimensions
        self._api_key = settings.gemini_api_key

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _client(self):
        from google import genai

        return genai.Client(api_key=self._api_key)

    def _embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        if not self.is_configured:
            raise EmbeddingUnavailable("GEMINI_API_KEY is not set, so text cannot be embedded.")

        client = self._client()
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = texts[start : start + BATCH_SIZE]
            try:
                response = client.models.embed_content(
                    model=self.model,
                    contents=batch,
                    config={
                        "task_type": task_type,
                        "output_dimensionality": self.dimensions,
                    },
                )
            except Exception as caught:
                logger.exception("Embedding failed for %d texts", len(batch))
                raise EmbeddingUnavailable(str(caught)) from caught
            vectors.extend(_unit(list(item.values)) for item in response.embeddings)

        logger.info("embedded %d texts as %s", len(vectors), task_type)
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed passages for storage."""
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> list[float]:
        """Embed a question for search.

        Asymmetric task types matter: a question and the passage answering it are worded
        differently, and telling the model which is which measurably improves the match.
        Repeated questions are served from the cache, which costs no quota at all.
        """
        return list(_cached_query_embedding(" ".join(text.lower().split())))


@lru_cache(maxsize=QUERY_CACHE_SIZE)
def _cached_query_embedding(normalised_question: str) -> tuple[float, ...]:
    vectors = GeminiEmbedder()._embed([normalised_question], "RETRIEVAL_QUERY")
    return tuple(vectors[0])
