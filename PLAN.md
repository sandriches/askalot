# RAG Pipeline — Build Plan

Goal: build a RAG pipeline **one step at a time**, with every step runnable and inspectable on its own, as a portfolio piece for the Strukton *Generative AI Engineer* interview.

## Why this shape (mapped to the vacancy)

| What Strukton asks for | How this project shows it |
|---|---|
| Python, LLMs, RAG, agents, taking work to production | A RAG pipeline written in plain Python, no framework hiding the steps, ending in a deployable API |
| **Traceability**: every AI output links to its source, and a person makes the final call | Every chunk keeps doc / page / section / bounding-box lineage. Answers must cite sources, and the citations are checked automatically |
| Extracting data from specifications and contracts into a pre-filled baseline | A bonus step: structured extraction of requirements from a spec, with each extracted field linked to its source |
| Measuring and improving AI output with test sets and evaluation | A golden test set and an eval harness that compares pipeline variants side by side |
| Azure OpenAI / AI Foundry, AI Search, Document Intelligence, PostgreSQL | Provider interfaces with Azure implementations. pgvector in Postgres first, Azure AI Search as the comparison |
| Container Apps, Terraform, Azure DevOps CI/CD | Dockerfile, a Terraform sketch, and a pipeline YAML that blocks a release when eval scores drop |
| Explaining technical choices to people without a technical background | Each step comes with a short write-up covering what it does, why, the options weighed, and what I'd do at Strukton |

## Guiding principles

1. **Explicit over magic.** No LangChain or LlamaIndex. Every stage is a small module with clear inputs and outputs, which makes it easy to explain in an interview. I can say why I'd bring in a framework later and where it would fit.
2. **Each step writes an artifact you can inspect** (JSONL / Parquet / DB rows), so you can open it, show it, and diff it.
3. **Swappable providers** behind thin interfaces (`Parser`, `Embedder`, `VectorStore`, `LLM`): a local or cheap option for building, and Azure for the "production" story.
4. **Measure before optimising.** Build a naive baseline end to end first, then improve one variable at a time and show the effect on the eval scores.
5. **Dutch-language corpus.** The real documents are Dutch, which affects the choice of embedding model, the chunker, and keyword search (Dutch stemming).

## Corpus

5–15 **public** Dutch construction / infrastructure documents that look like what Strukton works with every day. Candidates to check:
- Public tender documents from TenderNed (vraagspecificaties, UAV-GC contracts)
- Rijkswaterstaat design guidelines (e.g. ROK, the guideline for designing civil structures) and standard specifications
- ProRail public requirement and design documents

Mix in at least: a long contract, a spec with numbered requirements, and a document with tables. Store under `data/raw/` with a `manifest.yaml` (source URL, licence, date).

## Repository layout

```
rag-project/
├── PLAN.md
├── README.md                 # the interview narrative + results table
├── pyproject.toml            # uv, Python 3.12
├── .env.example
├── docker-compose.yml        # Postgres + pgvector (host port 5433)
├── data/
│   ├── raw/                  # source PDFs + manifest.yaml
│   ├── parsed/               # step 1 output
│   ├── chunks/               # step 2 output
│   └── eval/                 # golden set + run results
├── src/rag/
│   ├── config.py             # pydantic-settings
│   ├── clients.py            # Azure OpenAI client (Entra ID auth)
│   ├── models.py             # Document, Element, Chunk, Citation, Answer (Pydantic)
│   ├── ingest/               # parsers: pymupdf.py, docintel.py
│   ├── chunking/             # fixed.py, structural.py
│   ├── embed/                # azure_openai.py, local.py, cache.py
│   ├── store/                # pgvector.py, azure_search.py
│   ├── retrieve/             # dense, keyword, hybrid (RRF), rerank
│   ├── generate/             # prompts, answer, citation validation
│   ├── extract/              # structured requirement extraction
│   ├── eval/                 # metrics, judge, runner
│   └── api/                  # FastAPI app
├── scripts/                  # one CLI entry point per step: 01_ingest.py ...
├── notebooks/                # optional: one per step, for walking through live
├── docs/steps/               # 00-setup.md ... 10-deploy.md (decision write-ups)
├── infra/                    # Dockerfile, db/init.sql, terraform/, azure-pipelines.yml
└── tests/
```

## Steps

Each step has the same parts: **code** in `src/rag/...`, a **runnable script** in `scripts/`, an **output artifact**, and a **write-up** in `docs/steps/`.

### Step 0 — Project setup
- uv project, ruff, pytest; `config.py` loads settings from `.env`
- `docker-compose.yml` with Postgres + pgvector
- Domain models in `models.py`. **The `Chunk` → `Element` → `Document` lineage is decided here**, because the whole traceability story depends on it
- ✅ Done when: `uv run pytest` passes and the database starts

### Step 1 — Ingest & parse
- Baseline: **PyMuPDF**, giving text blocks with page number and bounding box
- Upgrade: **Azure Document Intelligence `prebuilt-layout`**, which adds headings, tables (as Markdown) and reading order
- Normalise both outputs to the same `Element` schema and save to `data/parsed/*.jsonl`
- Compare the two on a page with tables. This is a likely interview topic: why parsing quality limits everything downstream
- ✅ Done when: every element has `doc_id, page, bbox, type, text`

### Step 2 — Chunking
- Variant A: fixed-size token windows with overlap (naive baseline)
- Variant B: **structure-aware**: split on the heading hierarchy, keep tables whole, attach the section path ("3.2 Eisen > 3.2.4 Geluid") to each chunk's text and metadata
- Each chunk records the element IDs and pages it came from, so citations can point back to the exact place
- Print stats: token-length histogram, chunks per document
- ✅ Done when: `data/chunks/{variant}.jsonl` exists for both variants

### Step 3 — Embedding
- `Embedder` interface. Azure OpenAI `text-embedding-3-large` / `-small` (both multilingual). Optionally a local multilingual model (e.g. `multilingual-e5`) for comparison
- Batching, retry with backoff, and a **content-hash cache** so re-runs are free
- Track tokens and cost per run
- ✅ Done when: every chunk has a vector and re-running the step makes no API calls

### Step 4 — Index / vector store
- **pgvector** first: a `chunks` table with vector + HNSW index, plus a `tsvector` column with Dutch full-text config for keyword search. One database for both, matching their PostgreSQL stack
- **Azure AI Search** second: the same data in an index with vector + BM25 + semantic ranker
- Write-up: when you'd choose each (operational overhead, hybrid search quality, cost, security / network setup)
- ✅ Done when: both stores answer a top-k query for the same input

### Step 5 — Retrieval
- Dense only → keyword only → **hybrid with Reciprocal Rank Fusion** → **reranking** (cross-encoder or the AI Search semantic ranker)
- Metadata filters (by document, by type)
- Optional: query rewriting (Dutch/English, expanding abbreviations such as "UAV-GC")
- A debug view that prints retrieved chunks with scores and sources
- ✅ Done when: `scripts/05_retrieve.py "vraag"` prints ranked, sourced results for each strategy

### Step 6 — Generation with enforced citations
- Prompt with numbered context blocks. Answers use **structured output** (Pydantic): `answer`, `citations[{chunk_id, quote}]`, `confidence`, `not_found`
- **Citation validation:** every cited `chunk_id` must be among the retrieved chunks, and each `quote` must actually appear in that chunk's text (fuzzy match). Anything that fails is flagged rather than shown
- Explicit "I can't find this in the documents" behaviour instead of guessing
- ✅ Done when: answers come back with page-level sources that pass validation

### Step 7 — Evaluation (the centrepiece)
- **Golden set:** 30–50 questions, each with expected answer and source page(s), written by hand. Optionally add LLM-generated questions, reviewed by hand. Cover these types: factual lookup, table lookup, comparing documents, and unanswerable
- **Retrieval metrics:** recall@k, MRR, hit rate (by page)
- **Generation metrics:** faithfulness / groundedness (LLM-as-judge with a rubric), answer correctness, citation precision, correct refusal on unanswerable questions
- **Runner:** run each config (chunker × retriever × reranker) and produce a results table plus latency and cost per query. Results go in `data/eval/runs/` and the README
- ✅ Done when: one command reproduces the comparison table, and the README tells the story of what improved scores and why

### Step 8 — Bonus: structured extraction ("pre-filled baseline")
- Directly mirrors their current work: extract requirements from a spec into a schema (`id, text, category, verifiable, source{doc, page, bbox}`)
- A human-review output (CSV / simple UI) where every row links to its source and can be accepted or rejected
- Evaluated against a small hand-labelled sample (precision / recall on extracted requirements)

### Step 9 — Serve
- FastAPI endpoints: `/ask`, `/search`, `/extract`
- A minimal UI (Streamlit) that shows the answer next to the cited source passages and page numbers
- Logs each request (query, retrieved IDs, answer, latency, tokens) for monitoring and for adding to the test set

### Step 10 — Production readiness (sketch, deploy if time allows)
- Dockerfile → **Azure Container Apps**
- **Terraform** for: resource group, Azure OpenAI, AI Search, Postgres Flexible Server, Container App, Key Vault, managed identity
- **Azure DevOps pipeline:** lint → tests → **eval gate** (fail the release if faithfulness / recall drop below a threshold) → deploy
- Observability: OpenTelemetry → Application Insights
- Write-up: security (private endpoints, managed identity, no data leaving the tenant), cost controls, and how to take over and harden code from an external partner

## Suggested order & time budget

| Phase | Steps | Rough effort |
|---|---|---|
| Naive baseline end to end | 0, 1 (PyMuPDF), 2A, 3, 4 (pgvector), 5 (dense), 6 | 1–2 days |
| Measure it | 7 | 1 day |
| Improve & compare | 1 (Document Intelligence), 2B, 5 (hybrid + rerank), re-run 7 | 1–2 days |
| Strukton-specific polish | 8, 9 | 1 day |
| Production story | 10 (at least written up; deploy if Azure access) | 0.5–1 day |

If time runs short, cut from the bottom. Steps 0–7 alone are a strong demo, because the eval table backs every claim with numbers.

## Interview deliverables
- README with an architecture diagram, the eval results table, and the key decisions and trade-offs
- A 5-minute live demo: ask a question → see a cited answer → click through to the source page
- Prepared answers for the two application questions: an AI solution taken to production, and a codebase taken over. This project can support both
