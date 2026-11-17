"""Embedding providers for semantic memory."""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

import httpx

from app.core.exceptions import UpstreamError

TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)


class EmbeddingProvider(ABC):
    model_id: str
    dimensions: int

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class HashingEmbeddings(EmbeddingProvider):
    """Deterministic feature-hashing vectors (unigrams + bigrams).

    This is a **lexical** similarity fallback for development and tests when no embedding model is
    running. It is not semantic and is labelled as `hashing-v1` so it is never mixed with model
    embeddings."""

    def __init__(self, dimensions: int = 768) -> None:
        self.dimensions = dimensions
        self.model_id = "hashing-v1"

    def _vector(self, text: str) -> list[float]:
        tokens = [t.lower() for t in TOKEN_RE.findall(text)]
        features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        vec = [0.0] * self.dimensions
        for feat in features:
            digest = hashlib.blake2b(feat.encode(), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[idx] += sign
        return _normalize(vec)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class OllamaEmbeddings(EmbeddingProvider):
    def __init__(self, http: httpx.AsyncClient, base_url: str, model: str, dimensions: int) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self.model_id = f"ollama:{model}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            res = await self.http.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": texts},
                timeout=httpx.Timeout(30.0, connect=3.0),
            )
        except httpx.HTTPError as exc:
            raise UpstreamError("Embedding model is unreachable", code="embeddings_unavailable") from exc
        if res.status_code >= 400:
            raise UpstreamError(f"Embedding model error ({res.status_code})", code="embeddings_unavailable")
        vectors = res.json().get("embeddings") or []
        if len(vectors) != len(texts) or any(len(v) != self.dimensions for v in vectors):
            raise UpstreamError(
                f"Embedding dimension mismatch: expected {self.dimensions}. Set EMBEDDING_DIMENSIONS and "
                "the memories.embedding column to the model's size.",
                code="embeddings_dimension_mismatch",
            )
        return [_normalize([float(x) for x in v]) for v in vectors]


class ResilientEmbeddings(EmbeddingProvider):
    """Use the primary model; if it is unreachable, report `None` so callers store memories without a
    vector (they stay searchable by text and are re-embedded by /memories/reindex)."""

    def __init__(self, primary: EmbeddingProvider) -> None:
        self.primary = primary
        self.model_id = primary.model_id
        self.dimensions = primary.dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self.primary.embed(texts)

    async def try_embed(self, texts: list[str]) -> list[list[float]] | None:
        try:
            return await self.primary.embed(texts)
        except UpstreamError:
            return None


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True))
