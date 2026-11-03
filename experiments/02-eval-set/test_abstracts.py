"""Cleaning and completing the abstracts of v2, on short texts written by hand."""

from __future__ import annotations

from abstracts import (
    complete,
    cut_keywords,
    find_blocks,
    finish,
    from_metadata,
    pick,
    running_headers,
    strip_lead,
    strip_title_page,
    unescape,
)

CZECH = (
    "Práce se zabývá vlivem pohybové aktivity na zdraví dětí mladšího školního věku. "
    "V teoretické části shrnuje dosavadní poznatky o pohybu a jeho vztahu k obezitě, "
    "v praktické části porovnává dvě skupiny žáků podle dotazníku a měření."
)
ENGLISH = (
    "The thesis deals with the influence of physical activity on the health of children "
    "of younger school age. The theoretical part sums up what is known about movement and "
    "obesity, the practical part compares two groups of pupils by a questionnaire."
)


def test_entities_escaped_twice() -> None:
    assert unescape("Ross&amp;apos;s &amp;quot;curse&amp;quot;") == 'Ross\'s "curse"'


def test_title_page_before_heading() -> None:
    titles = ["Identifikace mrtvol", "Identification of cadavers"]
    text = 'Identification of cadavers Abstract "Identification" is an act of declaration.'
    assert strip_lead(text, titles) == '"Identification" is an act of declaration.'
    labelled = "NÁZEV: Něco jiného AUTOR: Jan Novák ABSTRAKT: Záměrem práce je objasnit."
    assert strip_lead(labelled, titles) == "Záměrem práce je objasnit."


def test_abstract_that_mentions_the_word_stays() -> None:
    text = "This thesis studies painting. Abstract Expressionism is its main subject."
    assert strip_lead(text, ["Painting"]) == text


def test_labelled_title_page_without_heading() -> None:
    title = "Interakce alkaloidů s přechodnými kovy II"
    text = (
        "Univerzita Karlova Farmaceutická fakulta v Hradci Králové Školitel: Ing. Jana Malá "
        f"Název diplomové práce: {title}. Měď je důležitou složkou lidského organismu."
    )
    assert strip_title_page(text, [title]) == "Měď je důležitou složkou lidského organismu."


def test_keywords_after_the_abstract() -> None:
    text = f"{CZECH} Klíčová slova: pohyb, obezita, děti"
    assert cut_keywords(text) == (CZECH, True)
    assert cut_keywords(f"Keywords in the first sentence. {CZECH}") == (
        f"Keywords in the first sentence. {CZECH}",
        False,
    )


def test_split_words_and_lost_r() -> None:
    assert finish("opti- malizace portfolia", "cs")[0] == "optimalizace portfolia"
    assert finish("dvou- a tříleté děti", "cs")[0] == "dvou- a tříleté děti"
    assert finish("after post- termination care", "en")[0] == "after post-termination care"
    assert finish("tématem pZezkumu sankcí", "cs")[0] == "tématem přezkumu sankcí"
    assert finish("the CamelZebra case", "en")[0] == "the CamelZebra case"


def test_cut_abstract_marked_by_dots() -> None:
    body, cut, _ = from_metadata(f"{CZECH[:120]}...", ["Pohyb dětí"])
    assert cut and body.endswith("...")
    _, cut, _ = from_metadata(CZECH, ["Pohyb dětí"])
    assert not cut


def thesis_text() -> str:
    return "\n".join(
        [
            "Univerzita Karlova",
            "Abstrakt ......................... 3",
            "Pohyb dětí školního věku",
            "2",
            "Abstrakt",
            "Název práce: Pohyb dětí",
            "Zpracovala: Jana Nováková",
            "Práce se zabývá vlivem pohybové aktivity na zdraví dětí mladšího školního",
            "věku. V teoretické části shrnuje dosavadní poznatky o pohybu a jeho vzta-",
            "hu k obezitě, v praktické části porovnává dvě skupiny žáků podle dotazníku",
            "Pohyb dětí školního věku",
            "- 3 -",
            "a měření.",
            "Klíčová slova: pohyb, obezita",
            "Abstract",
            ENGLISH,
            "Keywords: movement",
            "Pohyb dětí školního věku",
            "4",
            "Obsah",
            "Pohyb dětí školního věku",
            "5",
            "Závěr: Práce se zabývá vlivem pohybové aktivity na zdraví dětí mladšího školního",
            "věku a dospěla k tomu, že pohyb pomáhá.",
        ]
    )


def test_running_header_beside_page_numbers() -> None:
    text = thesis_text()
    assert running_headers(text) == {"Pohyb dětí školního věku"}
    assert running_headers("Escherichia coli\nrostla.\nEscherichia coli\nEscherichia coli") == set()


def test_blocks_under_headings() -> None:
    text = thesis_text()
    blocks = find_blocks(text, running_headers(text))
    czech, english = pick(blocks, "cs"), pick(blocks, "en")
    assert czech is not None and czech.text == CZECH
    assert english is not None and english.text == ENGLISH


def test_cut_abstract_completed_from_the_text() -> None:
    text = thesis_text()
    cut = CZECH[: CZECH.index(" porovnává")] + "..."
    assert complete(cut, text, running_headers(text)) == CZECH


def test_cut_at_the_end_of_a_line_keeps_the_space() -> None:
    lines = [
        "Abstract",
        "The thesis deals with the influence of physical activity on the health of children",
        "of younger school age. The theoretical part sums up what is known about movement and",
        "obesity, the practical part compares two groups of pupils by a questionnaire.",
        "Keywords: movement",
    ]
    cut = ENGLISH[: ENGLISH.index(" obesity")] + "..."
    assert complete(cut, "\n".join(lines), set()) == ENGLISH


def test_cut_after_a_hyphen_keeps_one_hyphen() -> None:
    whole = f"{CZECH} Reakce proběhla s 1-hydroxybenzotriazolem a výtěžek byl vysoký."
    text = f"Abstrakt\n{whole}\nKlíčová slova: reakce"
    cut = whole[: whole.index("hydroxy")] + "..."
    assert complete(cut, text, set()) == whole


def test_completion_stops_where_the_abstract_ends() -> None:
    czech = [
        "Práce se zabývá vlivem pohybové aktivity na zdraví dětí mladšího školního věku.",
        "V teoretické části shrnuje dosavadní poznatky o pohybu a jeho vztahu k obezitě,",
        "v praktické části porovnává dvě skupiny žáků podle dotazníku a měření.",
    ]
    cut = CZECH[: CZECH.index(" porovnává")] + "..."
    endings = (ENGLISH, "1 Teoretická východiska", "TEORETICKÁ ČÁST", "Seznam zkratek", "Obr. 2.")
    for after in endings:
        text = "\n".join(["Abstrakt", *czech, " ", after, "Pohyb dětí je důležitý pro zdraví."])
        assert complete(cut, text, set()) == CZECH, after


def test_heading_in_the_middle_of_the_text_is_not_the_abstract() -> None:
    filler = "Text kapitoly o pohybu dětí a jejich zdraví ve škole.\n" * 800
    middle = f"{filler}Abstract\n{ENGLISH}\nKeywords: movement\n{filler}"
    assert find_blocks(middle, set()) == []
    end = f"{filler}{filler}{filler}Abstract\n{ENGLISH}\nKeywords: movement\n"
    assert [block.text for block in find_blocks(end, set())] == [ENGLISH]


def test_particle_and_unknown_words_keep_their_form() -> None:
    assert finish("zjistit, je- li možné", "cs")[0] == "zjistit, je-li možné"
    assert finish("dvoj- alebo trojnásobný", "cs")[0] == "dvoj- alebo trojnásobný"
    assert finish("systém ProZone3 a pZezkumu", "cs")[0] == "systém ProZone3 a přezkumu"


def test_cut_abstract_not_in_the_text() -> None:
    assert complete(f"{ENGLISH[:-20]}...", thesis_text().replace(ENGLISH, ""), set()) is None
    other = f"Úplně jiný text, který v práci není, a jeho konec také ne, takže nic.{' x' * 40}..."
    assert complete(other, thesis_text(), set()) is None
