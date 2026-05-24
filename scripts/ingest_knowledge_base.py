#!/usr/bin/env python3
"""
Bulk Knowledge Base Ingest Script
===================================
Walks the knowledge-base/ folder and ingests all .pdf, .txt, .md files
into the knowledge_chunks table.

Usage:
    python scripts/ingest_knowledge_base.py
    python scripts/ingest_knowledge_base.py --folder knowledge-base/reco
    python scripts/ingest_knowledge_base.py --overwrite
    python scripts/ingest_knowledge_base.py --dry-run

Requires:
    DATABASE_URL and OPENAI_API_KEY set in .env or environment.
    pip install pypdf (for PDFs)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings
from app.db import create_database, migrate
from app.orchestrator.openai_extract import OpenAIClient
from app.copilot.chunker import chunk_text, chunk_pdf
from app.copilot.embedder import Embedder
from app.copilot.copilot import KnowledgeCopilot


# Folder → topic + audience mapping
FOLDER_METADATA: dict[str, dict] = {
    "reco": {"topic": "registration_compliance", "jurisdiction": "ontario", "audience": "agent"},
    "fsra": {"topic": "mortgage_advertising", "jurisdiction": "ontario", "audience": "agent"},
    "orea": {"topic": "real_estate_fundamentals", "jurisdiction": "ontario", "audience": "agent"},
    "brampton": {"topic": "local_market", "jurisdiction": "ontario", "audience": "agent"},
    "internal": {"topic": "sop", "jurisdiction": "ontario", "audience": "agent"},
}


def infer_metadata(path: Path) -> dict:
    """Infer topic/audience from folder name."""
    for folder_name, meta in FOLDER_METADATA.items():
        if folder_name in path.parts:
            return meta
    return {"topic": None, "jurisdiction": "ontario", "audience": "agent"}


def make_doc_id(path: Path, root: Path) -> str:
    """Create a stable doc_id from relative path."""
    rel = path.relative_to(root)
    return str(rel).replace("\\", "/").replace(" ", "_").replace(".pdf", "").replace(".txt", "").replace(".md", "")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest knowledge base into Copilot.")
    parser.add_argument("--folder", default=str(ROOT / "knowledge-base"),
                        help="Root folder to scan (default: knowledge-base/)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing chunks for each doc_id")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be ingested without actually doing it")
    parser.add_argument("--doc-id-prefix", default="",
                        help="Optional prefix to add to all doc_ids")
    args = parser.parse_args()

    # Validate config (skip for dry-run)
    if not args.dry_run:
        if not settings.database_url:
            print("ERROR: DATABASE_URL not set. Add to .env file.")
            sys.exit(1)
        if not settings.openai_api_key:
            print("ERROR: OPENAI_API_KEY not set. Add to .env file.")
            sys.exit(1)

    folder = Path(args.folder)
    if not folder.exists():
        print(f"ERROR: Folder not found: {folder}")
        sys.exit(1)

    # Collect files
    extensions = {".pdf", ".txt", ".md"}
    files = [f for f in folder.rglob("*") if f.suffix.lower() in extensions and f.is_file()]

    # Filter out README files and .gitkeep
    files = [f for f in files if f.name not in ("README.md", ".gitkeep")]

    if not files:
        print(f"No documents found in {folder}")
        print("Drop .pdf, .txt, or .md files into knowledge-base/ subfolders.")
        sys.exit(0)

    print(f"Found {len(files)} document(s) to ingest:")
    for f in files:
        print(f"  {f.relative_to(ROOT)}")

    if args.dry_run:
        print("\n[DRY RUN] — no changes made.")
        return

    # Initialize copilot
    print("\nInitializing database and copilot...")
    db = create_database(settings.database_url)
    migrate(db)

    oai = OpenAIClient(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.openai_model,
        temperature=settings.openai_temperature,
    )
    embedder = Embedder(api_key=settings.openai_api_key, model=settings.embedding_model)
    copilot = KnowledgeCopilot(db=db, openai_client=oai, embedder=embedder, top_k=5)

    # Ingest each file
    total_inserted = 0
    total_errors = 0

    for file_path in files:
        doc_id = args.doc_id_prefix + make_doc_id(file_path, ROOT / "knowledge-base")
        meta = infer_metadata(file_path)
        print(f"\n→ {file_path.name} [{doc_id}]")

        try:
            if file_path.suffix.lower() == ".pdf":
                chunks = chunk_pdf(
                    file_path, doc_id=doc_id,
                    topic=meta["topic"],
                    jurisdiction=meta["jurisdiction"],
                    audience=meta["audience"],
                )
            else:
                text = file_path.read_text(encoding="utf-8", errors="replace")
                chunks = chunk_text(
                    text, doc_id=doc_id, source_path=str(file_path),
                    topic=meta["topic"],
                    jurisdiction=meta["jurisdiction"],
                    audience=meta["audience"],
                )

            print(f"  Chunked: {len(chunks)} chunks")
            result = copilot.ingest_chunks(chunks, overwrite=args.overwrite)
            print(f"  Inserted: {result['inserted']}, Errors: {result['errors']}")
            total_inserted += result["inserted"]
            total_errors += result["errors"]

        except Exception as exc:
            print(f"  ERROR: {exc}")
            total_errors += 1

    print(f"\n{'='*50}")
    print(f"Total inserted: {total_inserted}")
    print(f"Total errors:   {total_errors}")
    print(f"\nKnowledge base ready. Query via POST /copilot/query")


if __name__ == "__main__":
    main()
