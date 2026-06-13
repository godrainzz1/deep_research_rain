"""Embedding generation via Ollama (qwen3-embedding) or DashScope."""

from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Default embedding dimensions
_QWEN_EMBED_DIM = 4096


class OllamaEmbedder:
    """Generate embeddings using a local Ollama embedding model."""

    def __init__(
        self,
        model: str = "qwen3-embedding:latest",
        base_url: str = "http://localhost:11434",
        timeout: int = 60,
    ) -> None:
        self.model = model
        self._url = f"{base_url.rstrip('/')}/api/embeddings"
        self._timeout = timeout

    @property
    def dimension(self) -> int:
        return _QWEN_EMBED_DIM

    def embed(self, text: str) -> list[float]:
        """Return a single embedding vector for *text*."""
        payload = {"model": self.model, "prompt": text}
        try:
            resp = requests.post(self._url, json=payload, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
            return data["embedding"]
        except Exception:
            logger.exception("Ollama embedding failed for model=%s", self.model)
            raise

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts (sequential — Ollama has no batch endpoint)."""
        return [self.embed(t) for t in texts]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_embedder: Optional[OllamaEmbedder] = None


def get_embedder() -> OllamaEmbedder:
    """Return a singleton OllamaEmbedder, creating it on first call."""
    global _embedder
    if _embedder is None:
        _embedder = OllamaEmbedder()
        # Warm-up: verify model is available
        try:
            _embedder.embed("warmup")
            logger.info("Ollama embedder ready: model=%s dim=%d", _embedder.model, _embedder.dimension)
        except Exception:
            logger.warning("Ollama embedder not available — embedding features disabled")
            _embedder = None  # Reset so future calls retry
            raise
    return _embedder
