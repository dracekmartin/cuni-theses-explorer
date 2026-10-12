"""One xoai record of the repository turned into a catalog entry.

xoai nests metadata as elements: schema, element, optional qualifier, and innermost the
language ("none" when there is none), which holds the values. The path of names down to
the language gives the DSpace field key, such as dc.title.translated.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from common import short_lang

OAI_NS = "{http://www.openarchives.org/OAI/2.0/}"
XOAI_NS = "{http://www.lyncode.com/xoai}"
BODY_DESCRIPTION = "Text práce"
OPEN_ACCESS = "open access"
KEPT_BUNDLES = ("ORIGINAL", "TEXT")
Fields = dict[str, list[list[str | None]]]


def parse_record(record: ET.Element) -> dict[str, Any]:
    """Catalog entry of one record. A deleted record keeps only its header."""
    header = record.find(f"{OAI_NS}header")
    if header is None:
        raise ValueError("record without header")
    identifier = header.findtext(f"{OAI_NS}identifier") or ""
    raw_handle = identifier.rsplit(":", 1)[-1]
    entry: dict[str, Any] = {
        "handle": raw_handle.strip(),
        "datestamp": header.findtext(f"{OAI_NS}datestamp"),
        "sets": [spec.text for spec in header.findall(f"{OAI_NS}setSpec")],
        "deleted": header.get("status") == "deleted",
    }
    metadata = record.find(f"{OAI_NS}metadata/{XOAI_NS}metadata")
    if entry["deleted"] or metadata is None:
        entry["deleted"] = True
        return entry
    fields: Fields = {}
    others: dict[str, str | None] = {}
    files: list[dict[str, Any]] = []
    for top in metadata.findall(f"{XOAI_NS}element"):
        name = top.get("name") or ""
        if name == "bundles":
            files = parse_bundles(top)
        elif name == "others":
            others = {field.get("name") or "": field.text for field in _fields(top)}
        elif name != "repository":
            collect_fields(top, [name], fields)
    if raw_handle != entry["handle"]:
        # A few stale index records carry a space after the handle, which breaks their URLs.
        for file in files:
            file["url"] = (file["url"] or "").replace(raw_handle, entry["handle"])
    entry.update(thesis_fields(fields))
    entry["collection"] = others.get("owningCollection")
    entry["last_modified"] = others.get("lastModifyDate")
    entry["access"] = others.get("drm")
    entry["file_availability"] = _first(fields, "uk.file-availability")
    entry["body"], entry["body_missing"] = choose_body(files, others.get("drm"))
    entry["files"] = files
    entry["fields"] = fields
    return entry


def _fields(element: ET.Element) -> list[ET.Element]:
    return element.findall(f"{XOAI_NS}field")


def collect_fields(element: ET.Element, path: list[str], fields: Fields) -> None:
    for child in element.findall(f"{XOAI_NS}element"):
        name = child.get("name") or ""
        values = [
            field.text for field in _fields(child) if field.get("name") == "value" and field.text
        ]
        if values:
            lang = None if name == "none" else name
            fields.setdefault(".".join(path), []).extend([value, lang] for value in values)
        else:
            collect_fields(child, [*path, name], fields)


def parse_bundles(element: ET.Element) -> list[dict[str, Any]]:
    """Files of the ORIGINAL and TEXT bundles, without thumbnails and licences."""
    files: list[dict[str, Any]] = []
    for bundle in element.findall(f"{XOAI_NS}element"):
        bundle_name = bundle.findtext(f"{XOAI_NS}field[@name='name']")
        if bundle_name not in KEPT_BUNDLES:
            continue
        for bitstream in bundle.iter(f"{XOAI_NS}element"):
            if bitstream.get("name") != "bitstream":
                continue
            info = {field.get("name"): field.text for field in _fields(bitstream)}
            files.append(
                {
                    "bundle": bundle_name,
                    "name": info.get("name"),
                    "description": info.get("description"),
                    "format": info.get("format"),
                    "size": int(info.get("size") or 0),
                    "url": info.get("url"),
                    "md5": info.get("checksum"),
                    "sid": info.get("sid"),
                    "access": info.get("drm"),
                }
            )
    return files


def choose_body(
    files: list[dict[str, Any]], item_access: str | None
) -> tuple[dict[str, Any] | None, str | None]:
    """The TEXT file of the thesis body, and why there is none when there is none.

    The body is the PDF described as "Text práce". Only items without such a description
    fall back to the rule of experiment 01, the PDF with the largest paired TEXT file.
    When the described body has no TEXT, a review or an attachment must not stand in.
    """
    pdfs = [f for f in files if f["bundle"] == "ORIGINAL" and f["format"] == "application/pdf"]
    texts = {f["name"]: f for f in files if f["bundle"] == "TEXT"}
    paired_all = [texts[p["name"] + ".txt"] for p in pdfs if p["name"] + ".txt" in texts]
    largest = max(paired_all, key=lambda text: text["size"]) if paired_all else None
    described = [p for p in pdfs if p.get("description") == BODY_DESCRIPTION]
    rule = "description" if described else "largest text"
    paired = [texts[p["name"] + ".txt"] for p in described or pdfs if p["name"] + ".txt" in texts]
    if not paired:
        return None, "no pdf" if not pdfs else "no text"
    text = max(paired, key=lambda candidate: candidate["size"])
    access = text.get("access") or item_access
    body = {
        "name": text["name"],
        "url": text["url"],
        "size": text["size"],
        "md5": text["md5"],
        "access": access,
        "rule": rule,
        "same_as_largest": largest is not None and largest["name"] == text["name"],
    }
    return body, None if access in (None, OPEN_ACCESS) else "restricted"


def _values(fields: Fields, key: str) -> list[list[str | None]]:
    return fields.get(key, [])


def _first(fields: Fields, key: str) -> str | None:
    values = _values(fields, key)
    return values[0][0] if values else None


def _in_language(fields: Fields, key: str, lang: str) -> str | None:
    for value, language in _values(fields, key):
        if short_lang(language) == lang:
            return value
    return None


def _keywords(fields: Fields, lang: str) -> list[str]:
    """Keywords of one language. DSpace stores them as one value separated by '|'."""
    keywords: list[str] = []
    for value, language in _values(fields, "dc.subject"):
        if value and short_lang(language) == lang:
            keywords.extend(part.strip() for part in value.split("|") if part.strip())
    return keywords


def thesis_fields(fields: Fields) -> dict[str, Any]:
    """The fields of the Thesis record of experiment 02, read from xoai instead of REST."""
    titles = _values(fields, "dc.title")
    translated = _values(fields, "dc.title.translated")
    return {
        "faculty": _first(fields, "uk.faculty-name.cs")
        or _in_language(fields, "dc.description.faculty", "cs")
        or _first(fields, "dc.description.faculty"),
        "department": _in_language(fields, "dc.description.department", "cs")
        or _first(fields, "dc.description.department"),
        "thesis_type": _first(fields, "dc.type"),
        "year": _first(fields, "dc.date.issued"),
        "language": short_lang(_first(fields, "dc.language.iso")),
        "title": titles[0][0] if titles else "",
        "title_lang": short_lang(titles[0][1]) if titles else None,
        "title_translated": translated[0][0] if translated else None,
        "title_translated_lang": short_lang(translated[0][1]) if translated else None,
        "abstract_cs": _first(fields, "uk.abstract.cs")
        or _in_language(fields, "dc.description.abstract", "cs"),
        "abstract_en": _first(fields, "uk.abstract.en")
        or _in_language(fields, "dc.description.abstract", "en"),
        "keywords_cs": _keywords(fields, "cs"),
        "keywords_en": _keywords(fields, "en"),
        "defence_status": _first(fields, "uk.thesis.defenceStatus"),
    }
