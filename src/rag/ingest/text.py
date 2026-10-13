"""Text rules shared by all parsers, so parser comparisons are like for like."""

import re

# Bullets from Word's Symbol/Wingdings fonts land in Unicode's private use area.
SYMBOL_BULLETS = "\uf0b7\uf0a7\uf076\uf0d8\uf0fc\uf06e\uf0a8"

NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+\S")
MULTILEVEL_HEADING = re.compile(r"^\d+(?:\.\d+)+\.?\s+[A-Z]")  # "3.10 Terugslagklep"
LIST_MARKER = re.compile(rf"^(?:[•\-–▪◦·●○■□{SYMBOL_BULLETS}]|\(?[a-z0-9]{{1,2}}[.)])\s+")
CAPTION = re.compile(r"^(Tabel|Figuur|Afbeelding)\s*[\dA-Z][\d.\-]*\s*[:.]", re.IGNORECASE)


def numbering_level(text: str) -> int | None:
    """Heading level from its numbering: '3.2.1 Geluid' -> 3. None if unnumbered."""
    m = NUMBERED_HEADING.match(text)
    return m.group(1).count(".") + 1 if m else None


def is_non_heading(text: str) -> bool:
    """Text that's styled like a heading but isn't one: captions, form labels
    ('Aanvangsdatum:') and bare numbers (e.g. table-of-contents page numbers)."""
    return bool(CAPTION.match(text)) or text.endswith(":") or sum(c.isalpha() for c in text) < 2


def is_unstyled_heading(text: str) -> bool:
    """A heading neither parser recognised from styling or layout, but whose
    multi-level numbering gives it away: short, '3.10 Terugslagklep ...', and
    not a sentence or a table-of-contents line."""
    return (
        bool(MULTILEVEL_HEADING.match(text))
        and len(text) <= 100
        and not text.endswith((".", ",", ";", ":"))
        and "...." not in text
        and not re.search(r"\s\d+$", text)  # ends in a page number: a ToC line
    )


# A hyphen left over from a line break, now followed by a space ("projec- tie").
# Dutch also writes "wet- en regelgeving" (= wetgeving en regelgeving), so a
# hyphen-space before a conjunction is real text and must be kept.
_BROKEN_WORD = re.compile(r"(?<=[a-zà-ÿ])- (?!(?:en|of|tot|noch|als|t/m)\b)(?=[a-zà-ÿ])")
_BROKEN_COMPOUND = re.compile(r"(?<=[a-zà-ÿ])- (?=[A-Z])")  # "Noord- Holland" -> "Noord-Holland"


def clean_text(text: str) -> str:
    """Remove soft hyphens, re-join words split at line breaks, collapse whitespace."""
    text = re.sub(rf"[{SYMBOL_BULLETS}]", "•", text.replace("\u00ad", ""))
    text = re.sub(r"\s+", " ", text).strip()
    text = _BROKEN_WORD.sub("", text)
    return _BROKEN_COMPOUND.sub("-", text)


def table_markdown(rows: list[list[str | None]], min_rows: int = 2) -> str:
    """Render a grid of cells as a Markdown table, first row as the header.

    Cells covered by a merged cell must be None or "" (not a copy of the merged
    text): repeating it would triple the requirement text in RWS requirement
    cards. Fully empty rows are dropped. Fewer than `min_rows` rows gives "".
    """
    clean = [[_clean_cell(c) for c in row] for row in rows]
    clean = [row for row in clean if any(row)]
    if not clean or len(clean) < min_rows:
        return ""
    lines = ["|" + "|".join(clean[0]) + "|", "|" + "|".join("---" for _ in clean[0]) + "|"]
    lines += ["|" + "|".join(row) + "|" for row in clean[1:]]
    return "\n".join(lines)


def _clean_cell(cell: str | None) -> str:
    if not cell:
        return ""
    text = re.sub(r"-\n(?=[a-z])", "", cell)  # undo hyphenation inside a cell
    return clean_text(text.replace("|", "/"))
