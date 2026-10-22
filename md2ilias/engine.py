# SPDX-License-Identifier: EUPL-1.2
#!/usr/bin/env python3
"""Vorlagen-Engine: klont Kapitel- und Seiten-Blöcke der Vorlage (aus dem Lehrbuch-Export übernommen)."""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from .kontext import Z

# Feste IDs des Vorlagen-Skeletts (siehe skelett.py); Kapitel, Seite und
# Absatz der Vorlage werden für das erste Kapitel und die erste Seite benutzt.
ORIGINAL_CHAPTER_ID = "90621"
ORIGINAL_PAGE_ID = "90622"
ORIGINAL_PCID = "2264886148164547754"


@dataclass(frozen=True)
class PageSpec:
    id: str
    pcid: str
    title: str
    text: str
    # Optional complete sequence of verified COPage PageContent elements.
    # Existing callers may continue to provide plain ``text`` only.
    content_xml: str | None = None


@dataclass(frozen=True)
class ChapterSpec:
    id: str
    title: str
    pages: list[PageSpec]


def _extract(text: str, pattern: str) -> str:
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        raise RuntimeError(f"Referenzblock nicht gefunden: {pattern}")
    return match.group(0)


def _tree_record_pattern(child_id: str) -> str:
    body = r"(?:(?!</ds:Rec>).)*?"
    return (
        r'<ds:Rec Entity="lm_tree">'
        + body
        + rf'<Child>{re.escape(child_id)}</Child>'
        + body
        + r'</ds:Rec>'
    )


def _append(text: str, block: str, closing_tag: str) -> str:
    marker = text.rfind(closing_tag)
    if marker < 0:
        raise RuntimeError(f"Schließendes XML-Element fehlt: {closing_tag}")
    return text[:marker] + block + text[marker:]


def _replace(block: str, replacements: dict[str, str]) -> str:
    for old, new in replacements.items():
        block = block.replace(old, new)
    return block


def _split_plain_paragraphs(text: str) -> list[str]:
    """Split conservative plain-text content into readable ILIAS paragraphs."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [block.strip() for block in re.split(r"\n\s*\n+", normalized)]
    return [re.sub(r"[ \t]*\n[ \t]*", " ", block).strip() for block in blocks if block.strip()]


def _render_page_contents(page_copage_tpl: str, page: PageSpec) -> str:
    """Insert structured COPage XML or clone the verified paragraph template."""
    page_content_tpl = _extract(page_copage_tpl, r'<PageContent\b.*?</PageContent>')

    if page.content_xml is not None:
        if not page.content_xml.strip():
            raise RuntimeError(f"Strukturierter Inhalt für Seite {page.id} ist leer.")
        return page_copage_tpl.replace(page_content_tpl, page.content_xml, 1)

    paragraphs = _split_plain_paragraphs(page.text)
    if not paragraphs:
        paragraphs = ["Diese Seite enthält derzeit keinen exportierbaren Text."]

    rendered: list[str] = []
    base_pcid = int(page.pcid)
    for index, paragraph in enumerate(paragraphs):
        pcid = str(base_pcid + index)
        block = _replace(
            page_content_tpl,
            {
                ORIGINAL_PCID: pcid,
                "Hallo Welt": paragraph,
            },
        )
        rendered.append(block)

    return page_copage_tpl.replace(page_content_tpl, "".join(rendered), 1)


def _validate_requested_tree(members: dict[str, bytes], chapters: list[ChapterSpec]) -> None:
    ORIGINAL_ROOT = Z.wurzel
    lm_name = f"{ORIGINAL_ROOT}/Modules/LearningModule/set_1/export.xml"
    text = members[lm_name].decode("utf-8")
    expected_ids = [chapter.id for chapter in chapters]
    expected_ids.extend(page.id for chapter in chapters for page in chapter.pages)

    for item_id in expected_ids:
        count = len(re.findall(rf"<Child>{re.escape(item_id)}</Child>", text))
        if count != 1:
            raise RuntimeError(
                f"ILIAS-Baum enthält ID {item_id} {count}-mal statt genau einmal."
            )

    dummy_count = len(re.findall(r"<Type>du</Type>", text))
    if dummy_count != 1:
        raise RuntimeError(
            f"ILIAS-Baum enthält {dummy_count} Dummy-Wurzeln statt genau einer."
        )


def build_module(template: bytes, module_title: str, description: str, chapters: list[ChapterSpec]) -> bytes:
    if not chapters or not chapters[0].pages:
        raise RuntimeError("Mindestens ein Kapitel mit einer Seite ist erforderlich.")

    ORIGINAL_ROOT, MODULE_ID = Z.wurzel, Z.quell_id
    with zipfile.ZipFile(io.BytesIO(template), "r") as archive:
        infos = archive.infolist()
        pristine = {info.filename: archive.read(info.filename) for info in infos}
    members = dict(pristine)

    lm_name = f"{ORIGINAL_ROOT}/Modules/LearningModule/set_1/export.xml"
    copage_name = f"{ORIGINAL_ROOT}/Services/COPage/set_1/export.xml"
    metadata_name = f"{ORIGINAL_ROOT}/Services/MetaData/set_1/export.xml"
    object_name = f"{ORIGINAL_ROOT}/Services/Object/set_1/export.xml"

    pristine_lm = pristine[lm_name].decode("utf-8")
    pristine_copage = pristine[copage_name].decode("utf-8")
    pristine_metadata = pristine[metadata_name].decode("utf-8")
    pristine_object = pristine[object_name].decode("utf-8")

    chapter_lm_tpl = _extract(pristine_lm, _tree_record_pattern(ORIGINAL_CHAPTER_ID))
    page_lm_tpl = _extract(pristine_lm, _tree_record_pattern(ORIGINAL_PAGE_ID))
    page_copage_tpl = _extract(pristine_copage, rf'<exp:ExportItem Id="lm:{ORIGINAL_PAGE_ID}">.*?</exp:ExportItem>')
    chapter_metadata_tpl = _extract(pristine_metadata, rf'<exp:ExportItem Id="{MODULE_ID}:{ORIGINAL_CHAPTER_ID}:st">.*?</exp:ExportItem>')
    page_metadata_tpl = _extract(pristine_metadata, rf'<exp:ExportItem Id="{MODULE_ID}:{ORIGINAL_PAGE_ID}:pg">.*?</exp:ExportItem>')
    chapter_object_tpl = _extract(pristine_object, rf'<exp:ExportItem Id="{MODULE_ID}:{ORIGINAL_CHAPTER_ID}:st">.*?</exp:ExportItem>')
    page_object_tpl = _extract(pristine_object, rf'<exp:ExportItem Id="{MODULE_ID}:{ORIGINAL_PAGE_ID}:pg">.*?</exp:ExportItem>')

    first_chapter = chapters[0]
    first_page = first_chapter.pages[0]
    global_replacements = {
        "test1 beschreibung": description,
        "test1": module_title,
        "Neues Kapitel": first_chapter.title,
        "Neue Seite": first_page.title,
    }
    for name, data in list(members.items()):
        if name.endswith(".xml"):
            members[name] = _replace(data.decode("utf-8"), global_replacements).encode("utf-8")

    cp = members[copage_name].decode("utf-8")
    first_item = _extract(cp, rf'<exp:ExportItem Id="lm:{ORIGINAL_PAGE_ID}">.*?</exp:ExportItem>')
    rendered_first = _render_page_contents(first_item, first_page)
    members[copage_name] = cp.replace(first_item, rendered_first, 1).encode("utf-8")

    for chapter_index, chapter in enumerate(chapters):
        if chapter_index > 0:
            lm = members[lm_name].decode("utf-8")
            block = _replace(chapter_lm_tpl, {
                ORIGINAL_CHAPTER_ID: chapter.id,
                "<Title>Neues Kapitel</Title>": f"<Title>{chapter.title}</Title>",
                f"il_0_st_{ORIGINAL_CHAPTER_ID}": f"il_0_st_{chapter.id}",
            })
            members[lm_name] = _append(lm, block, "</ds:DataSet>").encode("utf-8")

            md = members[metadata_name].decode("utf-8")
            block = _replace(chapter_metadata_tpl, {
                f"{MODULE_ID}:{ORIGINAL_CHAPTER_ID}:st": f"{MODULE_ID}:{chapter.id}:st",
                f"il_0_st_{ORIGINAL_CHAPTER_ID}": f"il_0_st_{chapter.id}",
                '<Title Language="de">Neues Kapitel</Title>': f'<Title Language="de">{chapter.title}</Title>',
            })
            members[metadata_name] = _append(md, block, "</exp:Export>").encode("utf-8")

            obj = members[object_name].decode("utf-8")
            block = _replace(chapter_object_tpl, {f"{MODULE_ID}:{ORIGINAL_CHAPTER_ID}:st": f"{MODULE_ID}:{chapter.id}:st"})
            members[object_name] = _append(obj, block, "</exp:Export>").encode("utf-8")

        start = 1 if chapter_index == 0 else 0
        for page in chapter.pages[start:]:
            lm = members[lm_name].decode("utf-8")
            block = _replace(page_lm_tpl, {
                ORIGINAL_PAGE_ID: page.id,
                f"<Parent>{ORIGINAL_CHAPTER_ID}</Parent>": f"<Parent>{chapter.id}</Parent>",
                "<Title>Neue Seite</Title>": f"<Title>{page.title}</Title>",
                f"il_0_pg_{ORIGINAL_PAGE_ID}": f"il_0_pg_{page.id}",
            })
            members[lm_name] = _append(lm, block, "</ds:DataSet>").encode("utf-8")

            cp = members[copage_name].decode("utf-8")
            block = _replace(page_copage_tpl, {
                f"lm:{ORIGINAL_PAGE_ID}": f"lm:{page.id}",
            })
            block = _render_page_contents(block, page)
            members[copage_name] = _append(cp, block, "</exp:Export>").encode("utf-8")

            md = members[metadata_name].decode("utf-8")
            block = _replace(page_metadata_tpl, {
                f"{MODULE_ID}:{ORIGINAL_PAGE_ID}:pg": f"{MODULE_ID}:{page.id}:pg",
                f"il_0_pg_{ORIGINAL_PAGE_ID}": f"il_0_pg_{page.id}",
                '<Title Language="de">Neue Seite</Title>': f'<Title Language="de">{page.title}</Title>',
            })
            members[metadata_name] = _append(md, block, "</exp:Export>").encode("utf-8")

            obj = members[object_name].decode("utf-8")
            block = _replace(page_object_tpl, {f"{MODULE_ID}:{ORIGINAL_PAGE_ID}:pg": f"{MODULE_ID}:{page.id}:pg"})
            members[object_name] = _append(obj, block, "</exp:Export>").encode("utf-8")

    _validate_requested_tree(members, chapters)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for info in infos:
            data = members[info.filename]
            if info.filename.endswith(".xml"):
                ET.fromstring(data)
            copied = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            copied.compress_type = info.compress_type
            copied.external_attr = info.external_attr
            copied.internal_attr = info.internal_attr
            copied.comment = info.comment
            copied.extra = info.extra
            copied.create_system = info.create_system
            dst.writestr(copied, data)
    return out.getvalue()
