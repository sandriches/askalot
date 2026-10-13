# Step 0 — Project setup

## What this step builds

| File | Purpose |
|---|---|
| `pyproject.toml` | uv project, Python 3.12, ruff + pytest config |
| `src/rag/config.py` | All settings in one typed `Settings` class, loaded from `.env` |
| `src/rag/clients.py` | One factory for the OpenAI client pointed at Azure |
| `src/rag/models.py` | The domain models: `Document`, `Element`, `Chunk`, `BBox` |
| `docker-compose.yml` + `infra/db/init.sql` | Local Postgres 17 with pgvector, on host port 5433 |
| `scripts/00_check_setup.py` | Smoke test: config, database, embedding call, chat call |
| `tests/test_models.py` | Unit tests for the model rules |

Run it:

```bash
docker compose up -d
uv run python scripts/00_check_setup.py
uv run pytest
```

## Key decisions

### 1. The data model is designed around traceability
Strukton requires every AI output to link back to its source. That can't be added at the end: if a chunk doesn't know where it came from, no answer built on it can either. So the lineage is fixed now:

```
Document  1──*  Element  *──*  Chunk
```

- An **Element** is one block on one page (a heading, paragraph, table). It holds `doc_id`, a 1-based `page`, and a `bbox` in PDF points. That's enough to open the PDF at the right page and highlight the exact region.
- A **Chunk** is the unit we embed and retrieve. It lists the `element_ids` and `pages` it was built from, and must have at least one element (the validator enforces this).
- **Element IDs are deterministic** (`doc:p3:e7`). Re-parsing gives the same IDs, so results stay comparable between runs.
- `parser` and `chunker` are recorded on every record. When we compare variants in step 7, the data says which pipeline produced it.

### 2. Plain Python and Pydantic, no RAG framework
LangChain and LlamaIndex would save some typing. But they hide the decisions this project is meant to show: how documents are split, what metadata survives, what the prompt looks like. Pydantic gives validated, serialisable models that also work as LLM structured-output schemas in steps 6 and 8.
*When would I add a framework?* For agent orchestration, or when a team already standardises on one. Not to hide a pipeline I need to be able to debug.

### 3. Entra ID instead of API keys
`DefaultAzureCredential` uses `az login` on a laptop and a **managed identity** once deployed to Container Apps. The same code runs in both places, there are no secrets to rotate or leak, and access is managed through Azure roles (`Cognitive Services OpenAI User`). An API key is supported as a fallback, held in a `SecretStr` so it doesn't end up in logs.

### 4. Azure's v1 API with the standard OpenAI SDK
Instead of the older `AzureOpenAI` client with an `api-version` date, we use the plain `OpenAI` client pointed at `<endpoint>/openai/v1/`. The code is the same as against openai.com, with no API version to pin, and the deployment name goes in the `model` parameter.

### 5. Data residency
Both models are deployed as **Data Zone Standard (EU)**, so requests are processed inside the EU. *Global Standard* is cheaper, and has higher limits, but may route requests anywhere in the world. For contract and tender documents, staying in the EU is the safer default, and it's a question a Security & Infra team will ask.

### 6. Postgres + pgvector, matching their stack
One database holds the vectors, the keyword index (Postgres full-text search with Dutch stemming) and the metadata, all queryable together in SQL. Azure AI Search comes in as a comparison in step 4. Postgres runs on host port **5433** so it doesn't clash with other local databases.

## What I'd do differently in production
- Postgres → Azure Database for PostgreSQL Flexible Server (it supports pgvector), with Entra ID auth for the database too
- Settings come from Container Apps environment variables / Key Vault references instead of `.env`
- Pre-commit hooks and CI running ruff + pytest (step 10)
