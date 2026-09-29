"""Embedding providers. Any OpenAI-compatible /v1/embeddings endpoint works."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

from openai import OpenAI

from .config import Settings


class Embedder(Protocol):
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAICompatibleEmbedder:
    """SiliconFlow (Qwen3-Embedding) by default; also works with OpenAI and others."""

    def __init__(self, api_key: str, base_url: str, model: str, dimensions: int):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self.client.embeddings.create(
            model=self.model, input=texts, dimensions=self.dimensions
        )
        vectors = [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise ValueError(
                    f"Embedding model returned {len(vector)} dimensions, expected "
                    f"{self.dimensions}. Check EMBEDDING_MODEL / EMBEDDING_DIMENSIONS."
                )
        return vectors


class HashEmbedder:
    """Deterministic bag-of-tokens embedder for tests and offline development."""

    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
            vector[h % self.dimensions] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    word = ""
    for ch in text.lower():
        if ch.isascii() and ch.isalnum():
            word += ch
            continue
        if word:
            out.append(word)
            word = ""
        if not ch.isascii() and ch.isalnum():
            out.append(ch)  # CJK: one token per character
    if word:
        out.append(word)
    return out


def build_embedder(settings: Settings) -> Embedder | None:
    """Return the configured embedder, or None (keyword search only) without an API key."""
    if not settings.embedding_api_key:
        return None
    return OpenAICompatibleEmbedder(
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
    )
