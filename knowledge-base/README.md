# Knowledge Base

Drop documents into the appropriate subfolder, then ingest via API.

## Subfolders

| Folder | What goes here |
|--------|---------------|
| `reco/` | RECO Information Guide, registration bulletins, TRESA summaries |
| `fsra/` | Mortgage advertising rules, FSRA compliance manual |
| `orea/` | OREA textbook chapters you own (agency, offers, financing, etc.) |
| `brampton/` | ARU/zoning rules, permit processes, neighbourhood guides |
| `internal/` | Your SOPs, buyer consultation scripts, objection handlers |

## How to Ingest

```bash
# PDF
curl -X POST http://localhost:8000/copilot/ingest-pdf \
  -H "Content-Type: application/json" \
  -d '{"pdf_path":"/abs/path/to/knowledge-base/reco/guide.pdf","doc_id":"reco-guide-2024","topic":"registration","jurisdiction":"ontario","audience":"agent"}'

# Text/Markdown
curl -X POST http://localhost:8000/copilot/ingest \
  -H "Content-Type: application/json" \
  -d '{"text":"...","doc_id":"my-doc","source_path":"internal/sop.md"}'
```

## .gitignore Note

PDF documents are gitignored (you own them, they are private).
Only folder structure and this README are tracked.
