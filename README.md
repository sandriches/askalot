# Askalot

A RAG pipeline over Dutch infrastructure documents, written in vanilla Python and built one stage at a time: ingest → chunk → embed → index → retrieve → generate (with verified citations) → evaluate. It runs on Azure OpenAI, Document Intelligence, AI Search and PostgreSQL/pgvector.

See [PLAN.md](PLAN.md) for the roadmap. Each step's design decisions are written up in [docs/steps/](docs/steps/).

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/), Docker, the Azure CLI (`az login`), and an Azure AI Foundry resource with an embedding and a chat deployment.

```bash
cp .env.example .env          # then fill in your endpoint + deployment names
docker compose up -d          # Postgres + pgvector on localhost:5433
uv run python scripts/01_download.py   # fetch the corpus PDFs
uv run python scripts/00_check_setup.py
uv run pytest
```

## Progress

| Step | Status |
|---|---|
| 0. Setup | ✅ |
| 1a. Ingest & parse (PyMuPDF) | ✅ |
| 1b. Ingest & parse (Document Intelligence) + comparison | ✅ |
| 2. Chunking | ✅ |
| 3. Embedding | ⏳ |
| 4. Index | |
| 5. Retrieval | |
| 6. Generation + citations | |
| 7. Evaluation | |
| 8. Structured extraction | |
| 9. Serve | |
| 10. Production readiness | |
