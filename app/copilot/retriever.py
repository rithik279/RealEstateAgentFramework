"""
Retriever — semantic search over knowledge_chunks.

Uses Python cosine similarity on JSONB-stored embeddings.
No pgvector extension required — works on any Postgres instance.

For large knowledge bases (10k+ chunks), consider:
  - Adding pgvector and switching to native vector type
  - Caching embeddings in memory at startup

Usage:
    retriever = Retriever(db=db)
    chunks = retriever.search(query_vector, top_k=5)
    chunks = retriever.search(query_vector, top_k=5, risk_level="low")
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from psycopg.rows import dict_row

from app.db import Database


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length float vectors."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class RetrievedChunk:
    id: int
    doc_id: str
    source_path: str
    chunk_index: int
    heading: str | None
    body: str
    topic: str | None
    jurisdiction: str
    audience: str
    risk_level: str
    requires_professional_review: bool
    similarity: float


@dataclass(frozen=True)
class Retriever:
    db: Database

    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int = 5,
        risk_level: str | None = None,        # filter: low | medium | high | critical
        jurisdiction: str | None = "ontario",
        audience: str | None = None,
        doc_id: str | None = None,
    ) -> list[RetrievedChunk]:
        """
        Return top_k most similar chunks to query_vector.
        All chunks with embeddings are loaded and scored in Python.

        For production with large bases, replace with pgvector ORDER BY <=> LIMIT.
        """
        # Build filter conditions
        conditions = ["embedding is not null"]
        params: list[Any] = []
        if risk_level:
            conditions.append("risk_level = %s")
            params.append(risk_level)
        if jurisdiction:
            conditions.append("jurisdiction = %s")
            params.append(jurisdiction)
        if audience:
            conditions.append("audience = %s")
            params.append(audience)
        if doc_id:
            conditions.append("doc_id = %s")
            params.append(doc_id)

        where = " AND ".join(conditions)
        sql = f"""
            SELECT id, doc_id, source_path, chunk_index, heading, body,
                   topic, jurisdiction, audience, risk_level,
                   requires_professional_review, embedding
            FROM knowledge_chunks
            WHERE {where}
        """

        with self.db.connect() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        # Score in Python
        scored: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            emb = row.get("embedding")
            if isinstance(emb, str):
                try:
                    emb = json.loads(emb)
                except Exception:
                    continue
            if not isinstance(emb, list):
                continue
            sim = cosine_similarity(query_vector, emb)
            scored.append((sim, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        return [
            RetrievedChunk(
                id=int(row["id"]),
                doc_id=str(row["doc_id"]),
                source_path=str(row["source_path"]),
                chunk_index=int(row["chunk_index"]),
                heading=row.get("heading"),
                body=str(row["body"]),
                topic=row.get("topic"),
                jurisdiction=str(row.get("jurisdiction") or "ontario"),
                audience=str(row.get("audience") or "agent"),
                risk_level=str(row.get("risk_level") or "low"),
                requires_professional_review=bool(row.get("requires_professional_review")),
                similarity=sim,
            )
            for sim, row in top
        ]
