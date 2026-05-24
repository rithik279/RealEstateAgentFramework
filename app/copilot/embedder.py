"""
Embedder — OpenAI text-embedding-3-small wrapper.

Usage:
    embedder = Embedder(api_key="sk-...", model="text-embedding-3-small")
    vector = embedder.embed("What are RECO registration requirements?")
    vectors = embedder.embed_batch(["text 1", "text 2"])

Returns float lists (not numpy arrays) for storage as JSONB.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx


@dataclass
class Embedder:
    api_key: str
    model: str = "text-embedding-3-small"
    base_url: str = "https://api.openai.com/v1"
    dimensions: int = 1536   # text-embedding-3-small native dims

    def embed(self, text: str) -> list[float]:
        """Embed single text. Returns float list."""
        results = self.embed_batch([text])
        return results[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Embed multiple texts in one API call.
        OpenAI supports up to 2048 inputs per request (we batch at 100 for safety).
        """
        all_vectors: list[list[float]] = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            vectors = self._call_api(batch)
            all_vectors.extend(vectors)
        return all_vectors

    def _call_api(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            f"{self.base_url.rstrip('/')}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": texts,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        # Sort by index to preserve order
        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]
