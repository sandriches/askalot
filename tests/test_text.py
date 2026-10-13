from rag.ingest.text import (
    LIST_MARKER,
    clean_text,
    is_unstyled_heading,
    numbering_level,
    table_markdown,
)


def test_merged_cells_are_not_repeated_and_empty_rows_dropped():
    rows = [
        ["SYS-0010", "Ontwerp Topteken", "Geldigheids-", "G"],
        ["", "Het Topteken dient te voldoen", None, None],
        ["", None, None, None],
    ]
    md = table_markdown(rows)
    assert md.count("Het Topteken dient te voldoen") == 1
    assert md.splitlines() == [
        "|SYS-0010|Ontwerp Topteken|Geldigheids-|G|",
        "|---|---|---|---|",
        "||Het Topteken dient te voldoen|||",
    ]


def test_numbering_level():
    assert numbering_level("3.2.1 Geluid") == 3
    assert numbering_level("1 Inleiding") == 1
    assert numbering_level("Inleiding") is None


def test_clean_text_removes_soft_hyphens_and_extra_whitespace():
    assert clean_text("ont\u00adwerp   eisen\n") == "ontwerp eisen"


def test_clean_text_rejoins_words_broken_at_line_ends():
    assert clean_text("projec- tierichtlijnen") == "projectierichtlijnen"
    assert clean_text("Noord- Holland") == "Noord-Holland"


def test_clean_text_keeps_dutch_hyphen_ellipsis():
    # "wet- en regelgeving" is correct Dutch for "wetgeving en regelgeving"
    assert clean_text("wet- en regelgeving") == "wet- en regelgeving"
    assert clean_text("Systeem- of kwaliteitseisen") == "Systeem- of kwaliteitseisen"


def test_symbol_font_bullets_become_list_markers():
    text = clean_text(" Initiatief;")
    assert text == "• Initiatief;"
    assert LIST_MARKER.match(text)


def test_unstyled_numbered_heading():
    assert is_unstyled_heading("3.10 Terugslagklep bij grote dokpomp 1 Noord")
    assert is_unstyled_heading("3.11.1 Eisen uit functieanalyse")
    assert not is_unstyled_heading("2.1 Aanvangssituatie 5")  # ToC line
    assert not is_unstyled_heading("3 Systeemeisen")  # single level: too risky
    assert not is_unstyled_heading("2.2 De opdrachtnemer moet de fundering vervangen.")
