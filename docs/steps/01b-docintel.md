# Step 1b — Azure Document Intelligence, and comparing the two parsers

## What this step builds

| File | Purpose |
|---|---|
| `src/rag/ingest/docintel_parser.py` | Parser using Document Intelligence's `prebuilt-layout` model, with a cache of raw results |
| `src/rag/ingest/text.py` | Text rules **shared by both parsers** (headings, lists, captions, tables, hyphenation), so the comparison is fair |
| `src/rag/ingest/postprocess.py` | Shared header/footer detection |
| `scripts/01_compare.py` | Compares the two parsers per document, or one page side by side |

```bash
uv run python scripts/01_parse.py --parser docintel
uv run python scripts/01_compare.py
uv run python scripts/01_compare.py --page prorail-ovs00112 5
uv run python scripts/01_inspect_page.py prorail-ovs00112 5 --parser docintel
```

## Setup and cost

- **The same Foundry resource** (kind `AIServices`) includes Document Intelligence, but on the `*.cognitiveservices.azure.com` host, not `*.services.ai.azure.com`.
- **It needs a separate role:** `Cognitive Services User`. The `Cognitive Services OpenAI User` role only covers the OpenAI endpoints. The error message names the exact action that's missing (`FormRecognizer/documentmodels:analyze/action`). After assigning the role, it took about 2 minutes to take effect.
- **Cost:** about $10 per 1000 pages, so roughly **$6** for these 595 pages. The analysis took about 2 minutes.
- **Raw results are cached** in `data/parsed/docintel/raw/<doc_id>-<sha256>.json`. Converting them to Elements is free and takes seconds, so the conversion rules could be improved many times without calling the service again. The hash in the filename means a changed PDF is analysed again automatically.

## How Document Intelligence's output maps to our Elements

| Document Intelligence returns | We make |
|---|---|
| paragraph with role `title` / `sectionHeading` | `HEADING` (level from the numbering, otherwise from the depth in the section tree) |
| role `pageHeader` / `pageFooter` / `pageNumber` | `OTHER` |
| paragraph inside a table's span | skipped, because the `TABLE` element already carries that text |
| paragraph inside a figure | `OTHER` (labels in a map or diagram) |
| table (cells with row/column index and spans) | one `TABLE` per page it appears on, so citations point to the exact page; merged cells appear once |
| polygon in inches | `BBox` in PDF points (× 72), the same unit as PyMuPDF |

## What the comparison showed

**Neither parser wins outright.** Each has blind spots the other doesn't, and the side-by-side comparison exposed bugs in *both*.

### Where Document Intelligence is clearly better
- **OCR.** ROK pages 93–100 are scanned images. PyMuPDF gets nothing from them; Document Intelligence reads the full text. For Strukton's real archive (older contracts, scanned drawings) this alone decides it.
- **Tables:** cleaner cells, and merged cells come back as structure instead of being guessed.
- **Reading order** comes from a layout model rather than "top to bottom, left to right".
- **Lists** with Word Symbol-font bullets: Document Intelligence found 119 in RTD 1004, against 0 for the original PyMuPDF rules.

### Where Document Intelligence needed help
- **Boxed page headers become tables.** The ROK's boxed header (`Richtlijnen Ontwerp Kunstwerken | Pagina: 61 van 255 | ...`) came out as a table on almost every page, and was cut differently from page to page. Shared header detection now compares *words* rather than exact text, which brought tables in the ROK down from 353 to 103.
- **Some numbered headings were typed as body text** (`3.10 Terugslagklep...`). The shared rule for unnumbered-style headings now catches these.
- **Line-break hyphens are kept** as `projec- tierichtlijnen`. This has a Dutch catch: `wet- en regelgeving` is *correct* (shorthand for "wetgeving en regelgeving"), so the fix only joins words when the next word isn't a conjunction (`en`, `of`, `tot`, ...).

### Bugs the comparison exposed in the PyMuPDF baseline
- **Silent data loss:** PyMuPDF put a table's cells, its caption *and the next paragraph* in one block, and the old "skip blocks that overlap a table" rule threw it all away. The summary numbers looked fine; only the side-by-side view of `prorail-ovs00112` page 5 showed it. *Fix:* filter per line instead of per block, and add a regression test.
- **Consecutive headings glued together:** `3.3.1 Casco algemeen 3.3.2 Waterdichte kruipruimte ...` came out as one paragraph. *Fix:* lines starting with multi-level numbering always start a new element.
- **Symbol-font bullets** (``) weren't recognised as list markers.

### Result after the shared fixes (numbered headings found by both / only PyMuPDF / only Document Intelligence)

| Document | Before | After |
|---|---|---|
| rws-vse-waterbeheersysteem | 32 / 31 / 3 | **66 / 0 / 0** |
| rws-vse-krammersluizen-vaarweg | 31 / 1 / 66 | **128 / 1 / 0** |
| prorail-ovs00112 | 32 / 1 / 0 | **78 / 1 / 0** |
| rws-rok-1-4 | 82 / 16 / 25 | 82 / 19 / 26 |

### A metric that misled
"Characters extracted" made it look as if Document Intelligence lost about 12% of the Kribbakens spec. In fact the difference was the table of contents: PyMuPDF counted 4,700 characters of dot leaders (`2.2 Realisatiefase ........`), while Document Intelligence turned the contents page into a compact table. Counts are only a starting point; they still have to be checked by looking at the pages.

## Decision

**Document Intelligence is the default parser from step 2 on**, mainly because of OCR, table structure and reading order. PyMuPDF stays available as a free, local option and as a comparison: chunking takes the parser as a parameter, and in step 7 the evaluation will measure whether the difference in parsing actually shows up in answer quality.

## Still open (handled in step 2, chunking)
- **Table of contents:** it repeats every heading, so it would match many queries without containing any answers. The contents pages should be left out of chunking.
- **Headings over-promoted or missed** in the ROK (about 20 per parser). Small, and it only affects the section path, not the text itself.

## For the interview
- *"How do you choose a document parser?"* → Run both on the same pages, compare them on numbers **and** by eye, fix what is fixable in shared code, and let the evaluation decide.
- *"What does Document Intelligence cost and how do you keep re-runs cheap?"* → About $10 per 1000 pages; cache the raw result by file hash, so improving the conversion costs nothing.
- *"Why separate roles?"* → Least privilege: the OpenAI role and the Document Intelligence role are different data-plane permissions on the same resource. (In this personal setup `Cognitive Services User` is assigned at subscription level; in production it would be scoped to the resource, or given to the app's managed identity.)
