"""The catalog rests on these rules: field keys, the choice of the body, and stale handles."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from xoai import parse_record

OAI = "http://www.openarchives.org/OAI/2.0/"
XOAI = "http://www.lyncode.com/xoai"
Pdf = tuple[str, str, int]


def _field(name: str, value: object) -> str:
    return f'<field name="{name}">{value}</field>'


def _bitstream(handle: str, name: str, description: str, kind: str, size: int) -> str:
    return (
        '<element name="bitstream">'
        + _field("name", name)
        + _field("description", description)
        + _field("format", kind)
        + _field("size", size)
        + _field("url", f"https://dspace.cuni.cz/bitstream/{handle}/1/{name}")
        + _field("checksum", f"md5-{name}")
        + "</element>"
    )


def record(handle: str, pdfs: list[Pdf], texts: list[str], drm: str | None = None) -> ET.Element:
    """One xoai record; every name in `texts` gets a TEXT file ten times the size of its PDF."""
    sizes = {name: size for name, _, size in pdfs}
    original = "".join(_bitstream(handle, n, d, "application/pdf", s) for n, d, s in pdfs)
    extracted = "".join(
        _bitstream(handle, f"{name}.txt", "Extracted text", "text/plain", 10 * sizes[name])
        for name in texts
    )
    others = _field("handle", handle) + (_field("drm", drm) if drm else "")
    return ET.fromstring(
        f'<record xmlns="{OAI}"><header>'
        f"<identifier>oai:https://dspace.cuni.cz:{handle}</identifier>"
        "<datestamp>2026-10-11T00:00:00Z</datestamp><setSpec>col_x</setSpec></header>"
        f'<metadata><metadata xmlns="{XOAI}"><element name="dc">'
        '<element name="title"><element name="cs_CZ">' + _field("value", "Název") + "</element>"
        '<element name="translated"><element name="en_US">'
        + _field("value", "Title")
        + "</element></element></element>"
        '<element name="date"><element name="issued"><element name="none">'
        + _field("value", "2024")
        + "</element></element></element>"
        '<element name="subject"><element name="cs_CZ">'
        + _field("value", "jedna | dvě")
        + "</element></element>"
        '</element><element name="bundles">'
        '<element name="bundle">' + _field("name", "ORIGINAL") + '<element name="bitstreams">'
        f"{original}</element></element>"
        '<element name="bundle">' + _field("name", "TEXT") + '<element name="bitstreams">'
        f"{extracted}</element></element>"
        f'</element><element name="others">{others}</element></metadata></metadata></record>'
    )


BODY = ("body.pdf", "Text práce", 100)
ATTACHMENT = ("attachment.pdf", "Příloha práce", 900)


def test_field_keys_and_thesis_fields() -> None:
    entry = parse_record(record("20.500.11956/1", [BODY], ["body.pdf"]))
    assert entry["fields"]["dc.title"] == [["Název", "cs_CZ"]]
    assert entry["fields"]["dc.title.translated"] == [["Title", "en_US"]]
    assert (entry["title"], entry["title_lang"]) == ("Název", "cs")
    assert entry["title_translated"] == "Title"
    assert entry["year"] == "2024"
    assert entry["keywords_cs"] == ["jedna", "dvě"]


def test_body_is_the_described_pdf_even_when_an_attachment_is_larger() -> None:
    entry = parse_record(
        record("20.500.11956/1", [BODY, ATTACHMENT], ["body.pdf", "attachment.pdf"])
    )
    assert entry["body"]["name"] == "body.pdf.txt"
    assert entry["body"]["rule"] == "description"
    assert entry["body"]["same_as_largest"] is False
    assert entry["body_missing"] is None


def test_without_a_description_the_largest_text_wins() -> None:
    first, second = ("a.pdf", "", 100), ("b.pdf", "", 900)
    entry = parse_record(record("20.500.11956/1", [first, second], ["a.pdf", "b.pdf"]))
    assert entry["body"]["name"] == "b.pdf.txt"
    assert entry["body"]["rule"] == "largest text"


def test_described_body_without_text_gets_no_stand_in() -> None:
    entry = parse_record(record("20.500.11956/1", [BODY, ATTACHMENT], ["attachment.pdf"]))
    assert entry["body"] is None
    assert entry["body_missing"] == "no text"


def test_restricted_item_is_not_downloaded() -> None:
    entry = parse_record(record("20.500.11956/1", [BODY], ["body.pdf"], drm="restricted access"))
    assert entry["body_missing"] == "restricted"


def test_space_after_the_handle_is_removed_from_handle_and_urls() -> None:
    entry = parse_record(record("20.500.11956/1 ", [BODY], ["body.pdf"]))
    assert entry["handle"] == "20.500.11956/1"
    assert entry["body"]["url"] == "https://dspace.cuni.cz/bitstream/20.500.11956/1/1/body.pdf.txt"
