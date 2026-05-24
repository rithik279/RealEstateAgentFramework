"""
Ontario Knowledge Copilot — main RAG query handler.

Flow:
  1. Embed the query (text-embedding-3-small)
  2. Retrieve top-k relevant chunks from knowledge_chunks (cosine sim)
  3. Build context from chunks, noting risk levels
  4. Call GPT-4o-mini with context + query
  5. Return answer + sources + risk level + review flag

Usage:
    copilot = KnowledgeCopilot(db=db, openai_client=openai_client, embedder=embedder)
    response = copilot.query("What must I disclose about dual agency in Ontario?")
    print(response.answer)
    print(response.risk_level)          # "critical"
    print(response.requires_review)    # True
    print(response.sources)            # list of source docs
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.copilot.classifier import RiskClassifier
from app.copilot.embedder import Embedder
from app.copilot.retriever import Retriever, RetrievedChunk
from app.db import Database
from app.orchestrator.openai_extract import OpenAIClient


@dataclass
class CopilotSource:
    doc_id: str
    source_path: str
    heading: str | None
    chunk_index: int
    risk_level: str
    similarity: float


@dataclass
class CopilotResponse:
    query: str
    answer: str
    sources: list[CopilotSource]
    risk_level: str          # highest risk level among sources
    requires_review: bool    # True if any source is high/critical
    top_k_used: int
    model_used: str


@dataclass
class KnowledgeCopilot:
    db: Database
    openai_client: OpenAIClient
    embedder: Embedder
    top_k: int = 5
    max_context_chars: int = 8000

    def __post_init__(self) -> None:
        self._retriever = Retriever(db=self.db)
        self._classifier = RiskClassifier()

    def query(
        self,
        user_query: str,
        *,
        jurisdiction: str = "ontario",
        audience: str | None = None,
    ) -> CopilotResponse:
        """
        Answer a real estate question using the private knowledge base.

        Args:
            user_query: natural language question from agent
            jurisdiction: filter chunks by jurisdiction (default 'ontario')
            audience: filter by intended audience ('agent', 'buyer', etc.)

        Returns:
            CopilotResponse with answer, sources, risk level
        """
        # 1. Embed query
        query_vector = self.embedder.embed(user_query)

        # 2. Retrieve chunks
        chunks = self._retriever.search(
            query_vector,
            top_k=self.top_k,
            jurisdiction=jurisdiction,
            audience=audience,
        )

        if not chunks:
            return CopilotResponse(
                query=user_query,
                answer=(
                    "I don't have any relevant information in the knowledge base for this question. "
                    "Please consult RECO, OREA, or a real estate lawyer directly."
                ),
                sources=[],
                risk_level="low",
                requires_review=False,
                top_k_used=0,
                model_used=self.openai_client.model,
            )

        # 3. Build context
        context = self._build_context(chunks)
        risk_level = self._aggregate_risk(chunks)
        requires_review = self._classifier.requires_review(risk_level)

        # 4. Query GPT
        answer = self._generate_answer(user_query, context, risk_level, requires_review)

        sources = [
            CopilotSource(
                doc_id=c.doc_id,
                source_path=c.source_path,
                heading=c.heading,
                chunk_index=c.chunk_index,
                risk_level=c.risk_level,
                similarity=round(c.similarity, 3),
            )
            for c in chunks
        ]

        return CopilotResponse(
            query=user_query,
            answer=answer,
            sources=sources,
            risk_level=risk_level,
            requires_review=requires_review,
            top_k_used=len(chunks),
            model_used=self.openai_client.model,
        )

    def _build_context(self, chunks: list[RetrievedChunk]) -> str:
        parts: list[str] = []
        total_chars = 0
        for chunk in chunks:
            heading_str = f"[{chunk.heading}] " if chunk.heading else ""
            risk_str = f"[RISK: {chunk.risk_level.upper()}] " if chunk.risk_level != "low" else ""
            entry = f"SOURCE: {chunk.doc_id} (chunk {chunk.chunk_index})\n{risk_str}{heading_str}{chunk.body}"
            if total_chars + len(entry) > self.max_context_chars:
                break
            parts.append(entry)
            total_chars += len(entry)
        return "\n\n---\n\n".join(parts)

    def _aggregate_risk(self, chunks: list[RetrievedChunk]) -> str:
        order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        highest = max(chunks, key=lambda c: order.get(c.risk_level, 0))
        return highest.risk_level

    def _generate_answer(
        self,
        query: str,
        context: str,
        risk_level: str,
        requires_review: bool,
    ) -> str:
        review_warning = (
            "\n\nIMPORTANT: This topic is flagged as HIGH/CRITICAL risk. "
            "The information above is for reference only — do not act on it without "
            "review by a licensed real estate professional or legal counsel."
            if requires_review else ""
        )

        system_prompt = (
            "You are a real estate compliance and knowledge assistant for a licensed Ontario real estate agent. "
            "Your role is to provide accurate, source-backed answers based ONLY on the provided context. "
            "If the context doesn't fully answer the question, say so clearly. "
            "Never fabricate rules, regulations, or legal requirements. "
            "Always cite the source document when possible. "
            "Be concise and practical — the agent needs to act on this information."
        )

        user_prompt = (
            f"CONTEXT FROM KNOWLEDGE BASE:\n{context}\n\n"
            f"QUESTION: {query}\n\n"
            f"Provide a clear, practical answer based on the context above. "
            f"Cite the source documents. "
            f"If the answer touches on legal/compliance obligations (risk level: {risk_level}), "
            f"include an appropriate caution.{review_warning}"
        )

        # Use the existing OpenAI client (Responses API)
        # Build a combined prompt for the responses endpoint
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        try:
            payload = self.openai_client._responses(full_prompt)
            answer = self.openai_client._extract_text(payload).strip()
            return answer if answer else "Unable to generate answer. Please check the knowledge base and try again."
        except Exception as exc:
            return f"Error generating answer: {exc}. Please consult the source documents directly."

    # -----------------------------------------------------------------------
    # Ingestion helpers
    # -----------------------------------------------------------------------

    def ingest_chunks(
        self,
        chunks: list[dict[str, Any]],
        *,
        overwrite: bool = False,
    ) -> dict[str, int]:
        """
        Embed and store chunks in knowledge_chunks table.

        Args:
            chunks: list of dicts from chunker.chunk_text() or chunk_pdf()
            overwrite: if True, delete existing chunks for same doc_id first

        Returns:
            {"inserted": N, "skipped": N, "errors": N}
        """
        if not chunks:
            return {"inserted": 0, "skipped": 0, "errors": 0}

        doc_id = chunks[0]["doc_id"]

        if overwrite:
            with self.db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM knowledge_chunks WHERE doc_id = %s", (doc_id,))
                conn.commit()

        # Embed all bodies in batch
        bodies = [c["body"] for c in chunks]
        try:
            vectors = self.embedder.embed_batch(bodies)
        except Exception as exc:
            return {"inserted": 0, "skipped": 0, "errors": len(chunks), "error": str(exc)}

        inserted = 0
        skipped = 0
        errors = 0

        classifier = RiskClassifier()

        for chunk, vector in zip(chunks, vectors):
            risk_level = classifier.classify(chunk["body"], chunk.get("heading"))
            needs_review = classifier.requires_review(risk_level)
            try:
                with self.db.connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO knowledge_chunks
                              (doc_id, source_path, chunk_index, heading, body,
                               topic, jurisdiction, audience,
                               risk_level, requires_professional_review, embedding)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                            ON CONFLICT (doc_id, chunk_index) DO UPDATE SET
                              body = EXCLUDED.body,
                              heading = EXCLUDED.heading,
                              risk_level = EXCLUDED.risk_level,
                              requires_professional_review = EXCLUDED.requires_professional_review,
                              embedding = EXCLUDED.embedding
                            """,
                            (
                                chunk["doc_id"],
                                chunk["source_path"],
                                chunk["chunk_index"],
                                chunk.get("heading"),
                                chunk["body"],
                                chunk.get("topic"),
                                chunk.get("jurisdiction", "ontario"),
                                chunk.get("audience", "agent"),
                                risk_level,
                                needs_review,
                                json.dumps(vector),
                            ),
                        )
                    conn.commit()
                inserted += 1
            except Exception:
                errors += 1

        return {"inserted": inserted, "skipped": skipped, "errors": errors}
