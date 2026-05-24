"""
Chunker — PDF/text to semantic chunks for the Knowledge Copilot.

Strategy:
- Target ~400-600 tokens per chunk (≈ 300-450 words)
- Preserve section headings as chunk metadata
- Overlap: 1 sentence between chunks to avoid context breaks
- Handles: plain text, markdown, basic PDF text extraction

Usage:
    from app.copilot.chunker import chunk_text, chunk_pdf

    chunks = chunk_text(text, doc_id="reco-guide", source_path="reco/guide.txt")
    chunks = chunk_pdf(pdf_path, doc_id="orea-chapter-3")

Each chunk is a dict matching the knowledge_chunks table columns.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


# Approximate chars-per-token for English text (conservative estimate)
CHARS_PER_TOKEN = 4
TARGET_TOKENS = 500
TARGET_CHARS = TARGET_TOKENS * CHARS_PER_TOKEN   # 2000 chars
OVERLAP_SENTENCES = 1


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences. Handles abbreviations reasonably well."""
    # Split on . ! ? followed by whitespace+capital or end of string
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z\d"])', text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _extract_heading(paragraph: str) -> str | None:
    """Extract markdown-style or ALL CAPS headings."""
    lines = paragraph.strip().splitlines()
    if not lines:
        return None
    first = lines[0].strip()
    # Markdown headings
    if first.startswith("#"):
        return first.lstrip("#").strip()
    # ALL CAPS heading (min 4 chars, no lowercase)
    if len(first) >= 4 and first == first.upper() and re.search(r"[A-Z]", first):
        return first
    return None


def chunk_text(
    text: str,
    *,
    doc_id: str,
    source_path: str,
    topic: str | None = None,
    jurisdiction: str = "ontario",
    audience: str = "agent",
) -> list[dict[str, Any]]:
    """
    Split raw text into overlapping chunks for embedding.

    Returns list of dicts matching knowledge_chunks schema (without embedding).
    """
    # Split into paragraphs first
    paragraphs = re.split(r"\n{2,}", text.strip())
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks: list[dict[str, Any]] = []
    current_heading: str | None = None
    current_sentences: list[str] = []
    current_chars = 0
    chunk_index = 0

    def flush(sentences: list[str], heading: str | None) -> None:
        nonlocal chunk_index
        body = " ".join(sentences).strip()
        if not body:
            return
        chunks.append({
            "doc_id": doc_id,
            "source_path": source_path,
            "chunk_index": chunk_index,
            "heading": heading,
            "body": body,
            "topic": topic,
            "jurisdiction": jurisdiction,
            "audience": audience,
        })
        chunk_index += 1

    for paragraph in paragraphs:
        heading_candidate = _extract_heading(paragraph)
        if heading_candidate:
            current_heading = heading_candidate

        sentences = _split_sentences(paragraph)
        for sentence in sentences:
            sentence_chars = len(sentence)
            if current_chars + sentence_chars > TARGET_CHARS and current_sentences:
                # Flush current chunk
                flush(current_sentences, current_heading)
                # Overlap: keep last N sentences
                current_sentences = current_sentences[-OVERLAP_SENTENCES:] if OVERLAP_SENTENCES > 0 else []
                current_chars = sum(len(s) for s in current_sentences)
            current_sentences.append(sentence)
            current_chars += sentence_chars

    # Final chunk
    if current_sentences:
        flush(current_sentences, current_heading)

    return chunks


def chunk_pdf(
    pdf_path: str | Path,
    *,
    doc_id: str,
    topic: str | None = None,
    jurisdiction: str = "ontario",
    audience: str = "agent",
) -> list[dict[str, Any]]:
    """
    Extract text from PDF and chunk it.
    Requires: pypdf (pip install pypdf)
    Falls back gracefully if pypdf not installed.
    """
    pdf_path = Path(pdf_path)
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(str(pdf_path))
        pages_text: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages_text.append(text)
        full_text = "\n\n".join(pages_text)
    except ImportError:
        raise RuntimeError(
            "pypdf not installed. Run: pip install pypdf\n"
            "Or extract text manually and use chunk_text()."
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to read PDF {pdf_path}: {exc}") from exc

    return chunk_text(
        full_text,
        doc_id=doc_id,
        source_path=str(pdf_path),
        topic=topic,
        jurisdiction=jurisdiction,
        audience=audience,
    )
