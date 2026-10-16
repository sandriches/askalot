# Step 2 — Chunking

## What this step builds

| File | Purpose |
|---|---|
| `src/rag/tokens.py` | Token counting with `cl100k_base`, the tokenizer of `text-embedding-3-*` |
| `src/rag/chunking/base.py` | `Chunker` interface, and `chunkable()`: which elements are worth retrieving at all |
| `src/rag/chunking/fixed.py` | Baseline: fixed windows of 512 tokens with 64 tokens of overlap |
| `src/rag/chunking/structural.py` | Structure-aware: split along sections, keep tables whole |
| `scripts/02_chunk.py` | Chunks the corpus with both strategies, prints statistics |
| `scripts/02_inspect_chunks.py` | Shows chunks for a page or a search string |

```bash
uv run python scripts/02_chunk.py                    # Document Intelligence output (default)
uv run python scripts/02_chunk.py --parser pymupdf   # PyMuPDF output, for the step 7 comparison
uv run python scripts/02_inspect_chunks.py rws-vse-kribbakens --grep SYS-0015
uv run python scripts/02_inspect_chunks.py rws-vse-kribbakens --grep SYS-0015 --chunker fixed-512-64
```

Output: `data/chunks/<parser>/<chunker>.jsonl`, so 2 parsers × 2 chunkers = 4 variants to evaluate in step 7.

## Why chunking matters

Embedding a whole 255-page document into one vector doesn't work: the vector becomes an average of everything and matches nothing in particular. And whatever we retrieve has to fit in the LLM's context. So documents are cut into **chunks**: the unit we embed, retrieve, and cite.

A good chunk is **self-contained** (it can be understood without its neighbours), **about one thing**, and **traceable** (we know exactly which pages it came from).

## Step 1: what not to chunk (`chunkable()`)

Both chunkers get the same input, so the comparison is only about *how* to split:

- **Headers and footers** (`OTHER`), as marked in step 1.
- **The table of contents.** It repeats every heading in the document, so it would match almost any question while containing no answers. Detection: a front page with an "Inhoud" title, or mostly lines ending in page numbers, continuing onto following pages while they still look like contents. *Front of the document only*: RTD 1004 has a real section called "Inhoudsopgave" on page 14 (about what a design report must contain), and a naive rule would have thrown it away. Result: 1–3 pages skipped per document, all checked by hand.
- **Loose numbering** (`11.1`, `1.1 (3)`): fragments where the parser separated a number from its text.

## The two strategies

### Baseline: fixed windows (`fixed-512-64`)
Glue the text together and cut it every 512 tokens, with 64 tokens of overlap so a sentence on a boundary appears in both windows. Simple and predictable, but blind to structure.

Traceability still works: we track where each element's text sits in the glued string, so each window knows which elements, and therefore which pages, it overlaps.

### Structure-aware (`structure-512`)
- **A heading always closes the current chunk.** A chunk never spans two sections.
- Headings don't go into the chunk text but into **`section_path`**, e.g. `['3 Systeemeisen', '3.2 Kribbaken', '3.2.2 Kribbaken - Conserveren']`. Step 3 adds this back as context when embedding (a "contextual chunk header"). Kept separate, it's also available for display and for filtering.
- Elements are **packed** into a chunk up to 512 tokens and **never cut**, except when a single element is on its own over budget:
  - a **table** is split by rows, *repeating the header row* in each part, so every part can still be read on its own;
  - **text** is split by sentences.
- No overlap is needed: sections are natural boundaries.

## Results

| | fixed-512-64 | structure-512 |
|---|---|---|
| chunks | 879 | 1279 |
| tokens: median / p90 / max | 512 / 512 / 512 | 321 / 491 / 512 |
| chunks under 50 tokens | 0 | 75 |
| chunks spanning several pages | 583 | 274 |
| chunks with a section path | 0 | 1275 |

### The example that says it all: requirement SYS-0015 (Kribbakens)

**Fixed:** the window starts mid-text (`V-voorwaarden bepaald.|||`), mixes section 3.2.1 (design) with 3.2.2 (conservation), cuts SYS-0016 off at `|SYS-0016|Conserveren Stalen`, and has no section context.

**Structure-aware:** exactly section `3 Systeemeisen > 3.2 Kribbaken > 3.2.2 Kribbaken - Conserveren`, with its three requirements (SYS-0015, -0016, -0017) complete, verification conditions included.

### The small chunks (< 50 tokens)
Mostly **meaningful**: `Geen eisen bepaald` ("no requirements defined") under `3.9.4 Ontwerprandvoorwaarden`. That's small, but it *is* the answer to "are there design constraints for 3.9.4?", and the section path supplies the context. Merging them into a neighbouring section would muddy that, so they stay. Step 7 will show whether they get in the way during retrieval.

## Bugs found along the way
- **Over budget because of separators.** The budget counted elements but not the blank lines between them, and table splitting didn't count the line breaks between rows. Chunks reached 525 tokens. *Fix:* count separators, and measure the actual joined text when splitting. Covered by a test.
- **An assumption about Dutch.** A test assumed 40 × "woord" ≈ 40 tokens; it's 79. See below.

## Dutch and tokens
`cl100k_base` was trained mostly on English. A Dutch sentence needed **2.2 tokens per word**, against 1.2 for a comparable English one. Long compound words (*Conserveringssysteem*, *Vaarwegmarkering*) get split into many pieces. In practice:
- 512 tokens of Dutch holds noticeably less text than 512 tokens of English;
- embedding and LLM costs are higher per page;
- a budget estimated "in words" will overflow. Always measure in tokens.

## Known exceptions
- **One table row bigger than the budget** isn't cut, because a requirement or question split in half is worse than a large chunk. This happens 3 times, in the PyMuPDF output of the FAQ, where a whole question sits in one cell (up to 656 tokens). The embedding model accepts 8,191 tokens, so it isn't a technical problem.
- **Heading levels** come from step 1. Where a parser got a level wrong, the `section_path` is wrong too. The text and pages are still correct.

## Open questions for step 7 (evaluation)
- **512 vs 256 tokens:** smaller chunks give more precise matches; larger ones give more context per hit.
- **One requirement per chunk** (each requirement card on its own) versus a whole section per chunk.
- **Parser × chunker:** does Document Intelligence's better structure pay off in retrieval?

These aren't decided by intuition: `StructureChunker(max_tokens=...)` and `FixedChunker(size, overlap)` are parameters, and the evaluation in step 7 will compare the variants.

## For the interview
- *"How do you chunk documents?"* → Along the structure: sections as boundaries, tables kept whole, headings as context. But start with a naive baseline so the improvement can be measured.
- *"How do you keep traceability through chunking?"* → Every chunk lists the elements and pages it came from; even a fixed window maps back to its elements through character offsets.
- *"What's different about Dutch?"* → Roughly twice the tokens per word with OpenAI's tokenizer, so measure budgets in tokens, and use a multilingual embedding model.
