# Ontario Knowledge Copilot

## What It Is

A private RAG (Retrieval-Augmented Generation) system. Not fine-tuning.

- You own the knowledge base documents (OREA textbooks, RECO guides, internal SOPs)
- Documents are chunked, embedded, and stored in Postgres (`knowledge_chunks` table)
- On query: embed the question, find relevant chunks by cosine similarity, pass to GPT with context
- Returns: answer + source citations + risk level + review flag

**Key principle:** The model does NOT memorize your documents. It retrieves and reasons. This means:
- Safe for licensed use (no permanent training data contamination)
- You control what's in the knowledge base
- Answers are traceable to source documents
- You can update/replace documents anytime

---

## Architecture

```
User Query (agent asks a question)
        │
        ▼
[Embedder]  text-embedding-3-small → 1536-dim vector
        │
        ▼
[Retriever]  cosine similarity search on knowledge_chunks.embedding (JSONB)
        │       → returns top-k most relevant chunks
        ▼
[Context Builder]  assembles chunk text + source attribution + risk flags
        │
        ▼
[GPT-4o-mini]  "answer this question using only the provided context"
        │
        ▼
[Response]  answer + sources + risk_level + requires_review flag
```

---

## Risk Levels

Every chunk is classified on ingest:

| Level | Meaning | Review Required |
|-------|---------|----------------|
| `low` | General info, neighbourhood data | No |
| `medium` | Process guidance, forms, standard procedures | No (agent judgment) |
| `high` | RECO obligations, TRESA requirements, compliance rules | Yes — verify before acting |
| `critical` | Legal advice territory, dual agency, fraud, discrimination | Always — consult lawyer |

The response includes the **highest risk level** across retrieved chunks.  
If any chunk is `high` or `critical`, `requires_review: true` is returned.

---

## Knowledge Base Structure

```
knowledge-base/
├── reco/
│   ├── reco-information-guide.pdf     → registration, complaints, ethics
│   └── tresa-summary.md               → Trust in Real Estate Services Act
├── fsra/
│   └── mortgage-advertising-rules.pdf → relevant for client referrals
├── orea/
│   ├── chapter-3-agency.pdf           → representation agreements, BRA
│   └── chapter-7-offers.pdf           → APS, conditions, deposits
├── brampton/
│   ├── aru-rules.md                   → Additional Residential Unit zoning
│   └── permit-process.md              → basement conversion permits
└── internal/
    ├── buyer-consultation-script.md   → your SOP
    └── objection-handlers.md          → common buyer objections + responses
```

You decide what goes in. Start with RECO guide + OREA chapters you reference most.

---

## Setup

### 1. Ensure knowledge-base/ folder exists

```bash
mkdir -p knowledge-base/{reco,fsra,orea,brampton,internal}
```

### 2. Drop in your PDFs and documents

Copy RECO Information Guide, OREA chapters, internal SOPs into the subfolders.

### 3. Ingest documents via API

**Ingest a PDF:**
```bash
curl -X POST http://localhost:8000/copilot/ingest-pdf \
  -H "Content-Type: application/json" \
  -d '{
    "pdf_path": "/absolute/path/to/knowledge-base/reco/reco-info-guide.pdf",
    "doc_id": "reco-info-guide-2024",
    "topic": "registration",
    "jurisdiction": "ontario",
    "audience": "agent",
    "overwrite": false
  }'
```

**Ingest plain text or markdown:**
```bash
curl -X POST http://localhost:8000/copilot/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "text": "# ARU Rules\n\nBrampton permits Additional Residential Units...",
    "doc_id": "brampton-aru-2024",
    "source_path": "brampton/aru-rules.md",
    "topic": "zoning",
    "jurisdiction": "ontario",
    "audience": "agent",
    "overwrite": false
  }'
```

**Ingest response:**
```json
{
  "doc_id": "reco-info-guide-2024",
  "chunks_generated": 47,
  "inserted": 47,
  "skipped": 0,
  "errors": 0
}
```

### 4. Re-ingesting (overwrite)

Add `"overwrite": true` to delete existing chunks for that `doc_id` before re-inserting.  
Use this when you update a document.

---

## Querying

### Via API

```bash
curl -X POST http://localhost:8000/copilot/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the disclosure requirements when representing both buyer and seller in Ontario?",
    "jurisdiction": "ontario"
  }'
```

**Response:**
```json
{
  "query": "What are the disclosure requirements when representing both buyer and seller?",
  "answer": "Under TRESA and the RECO Code of Ethics, an agent must...[source-backed answer]",
  "risk_level": "critical",
  "requires_review": true,
  "top_k_used": 5,
  "model": "gpt-4o-mini",
  "sources": [
    {
      "doc_id": "reco-info-guide-2024",
      "source_path": "reco/reco-info-guide.pdf",
      "heading": "Multiple Representation",
      "chunk_index": 12,
      "risk_level": "critical",
      "similarity": 0.891
    }
  ]
}
```

---

## Performance Notes

**Embedding storage:** Uses JSONB (not pgvector). Cosine similarity computed in Python.  
- Fast enough for < 5,000 chunks (typical knowledge base)
- If you grow beyond 10,000 chunks: install pgvector extension and switch to native vector type
- The retriever code is built to be swapped — see `app/copilot/retriever.py`

**Cost:** text-embedding-3-small is $0.02/1M tokens.  
- 100-page PDF ≈ ~50,000 tokens to embed ≈ $0.001
- Query embedding ≈ < $0.0001 per query
- GPT-4o-mini for answer generation ≈ $0.001-0.005 per query

A full knowledge base ingest + 100 queries/month ≈ < $0.50

---

## Code Location

```
app/copilot/
├── __init__.py        — exports KnowledgeCopilot, CopilotResponse
├── chunker.py         — PDF/text → semantic chunks (~500 tokens, overlap)
├── embedder.py        — text-embedding-3-small API wrapper
├── retriever.py       — JSONB cosine similarity search
├── classifier.py      — keyword-based risk level classifier
└── copilot.py         — main RAG query + ingest handler
```

Endpoints: `POST /copilot/query`, `POST /copilot/ingest`, `POST /copilot/ingest-pdf`
