# Step 1a — Ingest & parse (PyMuPDF baseline)

## What this step builds

| File | Purpose |
|---|---|
| `data/raw/manifest.yaml` | The corpus: 8 public Dutch infrastructure PDFs (links + metadata only) |
| `scripts/01_download.py` | Fetches the PDFs into `data/raw/` (skips existing files, rejects anything that isn't a PDF) |
| `src/rag/ingest/manifest.py` | Loads the manifest; builds a `Document` (sha256, page count) per file |
| `src/rag/ingest/base.py` | The `Parser` interface: PDF in, `list[Element]` out |
| `src/rag/ingest/pymupdf_parser.py` | The baseline parser |
| `src/rag/io.py` | JSONL read/write for any Pydantic model |
| `scripts/01_parse.py` | Parses the corpus and prints a per-document summary |
| `scripts/01_inspect_page.py` | Draws the parsed elements onto a page image, to check quality by eye |

```bash
uv run python scripts/01_download.py
uv run python scripts/01_parse.py
uv run python scripts/01_inspect_page.py rws-vse-kribbakens 18   # -> data/parsed/inspect/...
```

## The corpus

8 documents, 595 pages: the ROK design guideline (255 pages) and its FAQ, RTD 1004, three Rijkswaterstaat requirements specs (*Vraagspecificatie Eisen*), a ProRail design specification (OVS) and a ProRail programme of requirements. The PDFs are public but copyrighted, so they're **gitignored**: only the manifest is committed, and the download script recreates the corpus.

## How the baseline works

PyMuPDF reads the PDF's text layer and returns *blocks* with exact coordinates and font information, but it doesn't know what a block *is*. We add structure with heuristics:

1. **Tables:** PyMuPDF's line-based table finder. We render the Markdown ourselves (see finding 2), and drop text blocks inside the table area so the text isn't duplicated.
2. **Split blocks into runs of lines:** a new run starts when the style switches between heading and body text, or when a line starts with a list marker (see finding 1).
3. **Classify each run:** *heading* if it's short and in a larger or bold font (level from the numbering `3.2.1` → 3, otherwise from font size); *list item* if it starts with a bullet or `1.` / `a)`; otherwise *paragraph*.
4. **Headers and footers:** a block near the top or bottom edge whose text (with digits ignored) repeats on ≥30% of pages is typed `OTHER`. It's kept for traceability, and chunking will skip it.

## Findings on the real documents

Checking the output on real documents turned up three problems that the first version didn't handle. Each one was fixed and given a test.

**1. Headings were merged into paragraphs.** PyMuPDF groups lines that are close together, so `2.2 Realisatiefase` and the paragraph below it came out as one block. That would have lost the section structure that chunking (step 2) depends on. *Fix:* split blocks at line level when the style changes. Headings found in the ROK went from 96 to 139 real headings.

**2. Requirement text was repeated three times.** The requirements specs put each requirement in a small table, a *requirement card*: `SYS-0015 | title | ...`, then the requirement text, then the verification conditions (*V&V-voorwaarden*). The text sits in a merged cell, and PyMuPDF's `to_markdown()` repeats a merged cell's text in every column it spans. That would triple the tokens and add noise to the embeddings. *Fix:* render the Markdown from the raw cells, where covered cells are `None`. As a side effect, parsing got about 2× faster.

**3. Bold text that isn't a heading.** Captions (`Tabel 6-5: ...`), labels inside the requirement cards (`Aanvangsdatum:`) and table-of-contents page numbers were being typed as headings. *Fix:* three simple exclusion rules.

**Not a problem: scans.** Every page has a text layer. The few "empty" pages are figure pages or blank, so no OCR is needed for this corpus. For Strukton's real documents (scanned drawings, older contracts) OCR would matter, which is a point in favour of Document Intelligence.

## Known limitations (deliberately left for the comparison)

- **Table of contents** entries are typed as headings or paragraphs. They'll need to be filtered out, or handled better by a layout model.
- **Unnumbered and italic sub-headings** (e.g. `2.2.3.1 ...` in italics) are sometimes merged with their paragraph, because the heuristic only looks at bold and size.
- **Reading order** is top-to-bottom then left-to-right. That's fine for these single-column documents, but it fails on multi-column layouts.
- **Tables without gridlines** aren't detected, because the table finder looks for drawn lines.
- **Images and figures** are ignored, including any text inside them.

These are exactly what a layout model is built for. **Step 1b** runs Azure Document Intelligence (`prebuilt-layout`) on the same pages and compares the results.

## Decisions worth explaining

- **Why a heuristic baseline first?** It's free, fast (595 pages in about 40 seconds), runs locally, and gives a reference point. The work in step 1b then has to *show* it's better on the same pages, rather than being assumed to be.
- **Why look at pages by eye?** The summary numbers looked fine. Only looking at real pages showed that the requirement text was tripled. `01_inspect_page.py` makes that check take seconds.
- **Licence:** PyMuPDF is **AGPL**. That's fine here, but in a commercial setting it needs a commercial licence, or an alternative such as `pypdf` / `pdfplumber` (MIT) or a managed service like Document Intelligence. Its optional `pymupdf_layout` add-on (suggested in its log output) is a layout model, but would need the same licence check.
- **Keeping headers and footers as `OTHER`** rather than deleting them: nothing is silently thrown away, and the decision to skip them is made, and visible, in chunking.
