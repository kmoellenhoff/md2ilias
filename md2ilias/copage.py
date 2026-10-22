# SPDX-License-Identifier: EUPL-1.2
"""Rendering von Markdown in ILIAS-COPage-XML.

Zusammengeführt aus den Stufen template, visual, tables_media und den
"polished"-Stufen (Bilder, Tabellen, Mathematik) der Lehrbuch-Builder-Kette.
Das erzeugte XML entspricht dem der Kette; Abweichungen sind im README
unter "Verbesserungen gegenüber dem Original" aufgeführt und nur im
nicht-strikten Modus aktiv.
"""
from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .kontext import Z

# --- Konstanten -----------------------------------------------------------

SECTION_MAP = {
    "mission": "Information", "success": "Confirmation", "warning": "Attention",
    "idea": "Example", "note": "Remark", "teaching": "Background",
    "tip": "Mnemonic", "abstract": "Information", "info": "Information",
    "question": "Interaction", "example": "Example", "quote": "Citation",
    "cite": "Citation", "literature": "Literature", "deep-dive": "Additional",
    "deepdive": "Additional", "deep": "Additional", "expert": "Special", "special": "Special",
    "adler": "Example", "summary": "Information", "definition": "Information",
    "danger": "Attention", "security": "Attention", "counterexample": "Example",
    "practical": "Interaction", "tool": "Information",
}
ADMONITION_RE = re.compile(
    r'^(?P<indent>[ \t]*)(?P<marker>!!!|\?\?\?)\s+'
    r'(?P<kind>[A-Za-z0-9_-]+)(?:\s+"(?P<title>[^"]*)")?\s*$'
)
ANY_HEADING_RE = re.compile(r'^[ \t]*#{1,6}\s+\S')
SECTION_START_RE = re.compile(r"^@@ILIASSECTIONSTART\|([^|]+)\|(.*)@@$")
SECTION_END = "@@ILIASSECTIONEND@@"
MATH_TOKEN_RE = re.compile(r"@@ILIASMATH(\d+)@@")
CODE_TOKEN_RE = re.compile(r"^@@ILIASCODE(\d+)@@$")
IMAGE_TOKEN_RE = re.compile(r"^@@ILIASIMAGE(\d+)@@$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_ATTR = r'(?:\s*\{[^}\n]*\})?'
FIGURE_STRIKT_RE = re.compile(
    r"<figure\b[^>]*>\s*!\[(?P<alt>[^\]]*)\]\((?P<path>[^)\s]+)(?:\s+\"[^\"]*\")?\)\s*"
    r"<figcaption>(?P<caption>.*?)</figcaption>\s*</figure>",
    re.IGNORECASE | re.DOTALL,
)
FIGURE_RE = re.compile(
    r"<figure\b[^>]*>\s*!\[(?P<alt>[^\]]*)\]\((?P<path>[^)\s]+)(?:\s+\"[^\"]*\")?\)"
    + _ATTR + r"\s*<figcaption>(?P<caption>.*?)</figcaption>\s*</figure>",
    re.IGNORECASE | re.DOTALL,
)
IMAGE_STRIKT_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<path>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMAGE_RE = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<path>[^)\s]+)(?:\s+\"[^\"]*\")?\)" + _ATTR
)


def xml_text(value: str) -> str:
    return html.escape(value, quote=False)


def remove_controls(value: str) -> str:
    return "".join(
        char for char in value
        if char in "\n\t" or not unicodedata.category(char).startswith("C")
    )


# --- Mathematik -----------------------------------------------------------

COMMON_TEX_COMMANDS = (
    "varepsilon", "epsilon", "emptyset", "Sigma", "sigma", "delta", "lambda",
    "in", "notin", "subset", "subseteq", "supseteq", "cup", "cap", "setminus",
    "rightarrow", "Rightarrow", "leftrightarrow", "Leftrightarrow", "times",
    "mathcal", "text", "ldots", "cdots", "quad", "mid", "neg",
)
COMMAND_PATTERN = "|".join(sorted((re.escape(x) for x in COMMON_TEX_COMMANDS), key=len, reverse=True))
RAW_COMMAND_RE = re.compile(rf"(?<!\[tex\])\\({COMMAND_PATTERN})(?:\{{([^{{}}]*)\}})?")
BARE_LEAK_RE = re.compile(r"(?<![A-Za-z])varepsilon(?![A-Za-z])")


def normalize_formula(value: str) -> str:
    """Entschärft problematische TeX-Umgebungen, behält gültige Kommandos."""
    text = remove_controls(value).strip()
    text = re.sub(r"\\begin\{(?:aligned|align\*?|array|cases|gathered|equation\*?)\}", "", text)
    text = re.sub(r"\\end\{(?:aligned|align\*?|array|cases|gathered|equation\*?)\}", "", text)
    text = text.replace("\\\\", r"\quad ")
    text = text.replace("&=", "=").replace("&", " ")
    return re.sub(r"\s+", " ", text).strip()


def protect_math(text: str) -> tuple[str, list[str]]:
    formulas: list[str] = []

    def store(value: str) -> str:
        formulas.append(normalize_formula(value))
        return f"@@ILIASMATH{len(formulas) - 1}@@"

    for pattern in (
        re.compile(r"\\\[(.*?)\\\]", re.S),
        re.compile(r"\$\$(.*?)\$\$", re.S),
        re.compile(r"\\\((.*?)\\\)", re.S),
        re.compile(r"(?<!\\)\$([^$\n]+?)(?<!\\)\$"),
    ):
        text = pattern.sub(lambda match: store(match.group(1)), text)
    return text, formulas


def restore_math(text: str, formulas: list[str]) -> str:
    return MATH_TOKEN_RE.sub(lambda m: f"[tex]{formulas[int(m.group(1))]}[/tex]", text)


def repair_math_text(value: str, characteristic: str | None = None) -> str:
    """Repariert TeX, das der Formelschutz nicht erfasst hat (Code bleibt unberührt)."""
    if characteristic == "Code" or not value:
        return value
    protected: list[str] = []

    def hold(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"@@ILIASKEEPTEX{len(protected) - 1}@@"

    text = re.sub(r"\[tex\].*?\[/tex\]", hold, value, flags=re.S)

    def wrap_command(match: re.Match[str]) -> str:
        formula = f"\\{match.group(1)}"
        if match.group(2) is not None:
            formula += "{" + match.group(2) + "}"
        return f"[tex]{formula}[/tex]"

    text = RAW_COMMAND_RE.sub(wrap_command, text)
    text = BARE_LEAK_RE.sub(r"[tex]\\varepsilon[/tex]", text)
    return re.sub(r"@@ILIASKEEPTEX(\d+)@@", lambda m: protected[int(m.group(1))], text)


# --- Grundbausteine -------------------------------------------------------

def page_content(pcid: int, inner: str) -> str:
    return f'<PageContent PCID="{pcid}">{inner}</PageContent>'


def paragraph_xml(pcid: int, text: str, characteristic: str = "Standard") -> str:
    text = repair_math_text(text, characteristic)
    return page_content(
        pcid,
        f'<Paragraph Language="{Z.sprache}" Characteristic="{characteristic}">{xml_text(text)}</Paragraph>',
    )


def list_xml(pcid: int, items: list[str], *, numbered: bool = False) -> str:
    list_tag = "SimpleNumberedList" if numbered else "SimpleBulletList"
    list_class = "NumberedList" if numbered else "BulletedList"
    body = "".join(
        f'<SimpleListItem Class="StandardListItem">{xml_text(item)}</SimpleListItem>'
        for item in items
    )
    return page_content(
        pcid,
        f'<Paragraph Language="{Z.sprache}" Characteristic="Standard">'
        f'<{list_tag} Class="{list_class}">{body}</{list_tag}>'
        '</Paragraph>',
    )


def section_xml(outer_pcid: int, section_pcid: int, characteristic: str,
                title: str, body_xml: str, title_pcid: int) -> str:
    title_xml = paragraph_xml(title_pcid, title, "Headline3")
    return page_content(
        outer_pcid,
        f'<Section Characteristic="{characteristic}" PCID="{section_pcid}">'
        f"{title_xml}{body_xml}</Section>",
    )


# --- Kästen (Admonitions) ---------------------------------------------------

def clean_box_title(title: str) -> str:
    """Entfernt führende Emojis/Symbole, die ILIAS-Titel nicht darstellen."""
    value = remove_controls(title).strip()
    while value:
        category = unicodedata.category(value[0])
        if category in {"So", "Sk", "Cf"} or value[0] in "✓✔✗✘⚠❓❗":
            value = value[1:].lstrip()
            continue
        break
    value = re.sub(r"^\?\s+(?=\S)", "", value)
    return value or "Hinweis"


def _kasten_regex() -> re.Pattern[str]:
    titel = "|".join(re.escape(t) for t in Z.kasten_titel) or "(?!)"
    return re.compile(rf'^[ \t]*#{{2,3}}\s+(?P<title>{titel})\s*$')


def convert_admonitions(text: str) -> str:
    """Wandelt ``!!!``/``???``-Blöcke und Standardüberschriften in Section-Marker."""
    # Titel bereinigen (Emoji entfernen), wie in der Original-Kette.
    bereinigt: list[str] = []
    for line in text.splitlines():
        m = ADMONITION_RE.match(line)
        if not m or m.group("title") is None:
            bereinigt.append(line)
            continue
        bereinigt.append(
            f'{m.group("indent")}{m.group("marker")} {m.group("kind")} '
            f'"{clean_box_title(m.group("title"))}"'
        )
    lines = bereinigt
    key_points_re = _kasten_regex()
    output: list[str] = []
    index = 0
    while index < len(lines):
        key_points_match = key_points_re.match(lines[index])
        if key_points_match:
            title = key_points_match.group("title")
            body: list[str] = []
            index += 1
            while (
                index < len(lines)
                and not ANY_HEADING_RE.match(lines[index])
                and not ADMONITION_RE.match(lines[index])
            ):
                body.append(lines[index])
                index += 1
            output.append(f"@@ILIASSECTIONSTART|Information|{title}@@")
            output.extend(body)
            output.append(SECTION_END)
            continue

        match = ADMONITION_RE.match(lines[index])
        if not match:
            output.append(lines[index])
            index += 1
            continue

        indent = len(match.group("indent").replace("\t", "    "))
        kind = match.group("kind").lower()
        title = match.group("title") or kind.replace("-", " ").title()
        characteristic = SECTION_MAP.get(kind, "Block")
        if match.group("marker") == "???" and "lösung" not in title.lower():
            title = f"Lösung: {title}"

        body = []
        index += 1
        while index < len(lines):
            candidate = lines[index]
            if not candidate.strip():
                body.append("")
                index += 1
                continue
            leading = len(candidate) - len(candidate.lstrip(" "))
            if candidate.startswith("\t"):
                body.append(candidate[1:])
                index += 1
            elif leading >= indent + 4:
                body.append(candidate[indent + 4:])
                index += 1
            else:
                break

        output.append(f"@@ILIASSECTIONSTART|{characteristic}|{title}@@")
        if Z.strikt:
            output.extend(body)
        else:  # verschachtelte Kästen ebenfalls umwandeln
            output.extend(convert_admonitions("\n".join(body)).split("\n"))
        output.append(SECTION_END)
    return "\n".join(output)


# --- Bilder ----------------------------------------------------------------

@dataclass
class ImageSpec:
    source: str
    alt: str
    caption: str
    base_dir: Path | None = None
    path: Path | None = None
    mob_id: int = 0
    filename: str = ""
    mime_type: str = "application/octet-stream"
    data: bytes = b""
    width_px: int | None = None
    height_px: int | None = None
    display_width: int | None = None
    display_height: int | None = None
    conversion: str = "missing"


def register_image(path: str, alt: str, caption: str = "") -> str:
    Z.bilder.append(ImageSpec(
        path, alt.strip(), re.sub(r"<[^>]+>", "", caption).strip(),
        base_dir=Z.aktuelles_verzeichnis,
    ))
    return f"@@ILIASIMAGE{len(Z.bilder) - 1}@@"


MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def slug(titel: str) -> str:
    """Anker eines Seitentitels: klein, Leerzeichen zu Bindestrichen, ohne Satzzeichen."""
    t = re.sub(r"[`*_~]", "", titel).strip().lower()
    t = re.sub(r"[^\w\s-]", "", t)
    return re.sub(r"[\s]+", "-", t)


def _umschrift(t: str) -> str:
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    return t


def _interner_link(label: str, ziel: str) -> str | None:
    """Markdown-Link auf eine andere Seite des Lernmoduls als Link-Platzhalter."""
    if "://" in ziel or ziel.startswith("mailto:") or "@" in label or "¦" in label:
        return None
    pfad, _, anker = ziel.partition("#")
    pfad = pfad.strip()
    if pfad and not pfad.endswith(".md"):
        return None
    dateiname = Path(pfad).name if pfad else ""
    kandidaten = [
        e for e in Z.seitenindex
        if (not dateiname or Path(e["quelle"]).name == dateiname)
    ]
    if not pfad:
        kandidaten = [e for e in Z.seitenindex if e["quelle"] == Z.aktuelle_quelle] or Z.seitenindex
    if anker:
        passend = [e for e in kandidaten if e["slug"] == slug(anker) or e["slug"] == anker.lower()
                  or _umschrift(e["slug"]) == _umschrift(slug(anker))]
        if not passend and not pfad:
            passend = [e for e in Z.seitenindex
                       if _umschrift(e["slug"]) == _umschrift(slug(anker))]
        kandidaten = passend
    if not kandidaten:
        Z.warnungen.append(f"Interner Link ohne Ziel: [{label}]({ziel}) in {Z.aktuelle_quelle}")
        return None
    Z.interne_links += 1
    schluessel = f"link-{Z.interne_links}"
    Z.link_ziele[schluessel] = ("seite", id(kandidaten[0]["seite"]))
    return f"@@ILIASINTLINK¦{schluessel}¦{label}@@"


def markdown_link_text(match: re.Match[str]) -> str:
    """Darstellung eines Markdown-Links im ILIAS-Text.

    Links auf Markdown-Dateien, die nicht Teil des Lernmoduls sind, haben in
    ILIAS kein Ziel; dort bleibt nur der Linktext stehen. Alle übrigen Links
    behalten die Form ``Text (Ziel)``. Im nicht-strikten Modus werden Links
    auf Seiten des Lernmoduls zu ILIAS-Seitenlinks.
    """
    label, target = match.group(1), match.group(2)
    if not Z.strikt:
        intern = _interner_link(label, target)
        if intern is not None:
            return intern
    path = target.split("#", 1)[0].strip()
    if (
        Z.quellnamen
        and path.endswith(".md")
        and "://" not in path
        and Path(path).name not in Z.quellnamen
    ):
        return label
    return f"{label} ({target})"


def _inline_bereinigen(text: str) -> str:
    """Bildunterschriften wie Fließtext säubern (Links, HTML, Auszeichnung, Umbrüche)."""
    text = MARKDOWN_LINK_RE.sub(lambda m: f"{m.group(1)} ({m.group(2)})", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[*_`~]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def prepared_markdown(markdown: str) -> str:
    text = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", markdown, count=1, flags=re.S)
    text = convert_admonitions(text)

    def store_code(match: re.Match[str]) -> str:
        Z.code_bloecke.append(match.group(1).strip("\n"))
        return f"\n\n@@ILIASCODE{len(Z.code_bloecke) - 1}@@\n\n"

    text = re.sub(r"```[^\n]*\n(.*?)```", store_code, text, flags=re.S)
    # Code wird vor der Formelerkennung geschützt ($HOME_NET ist keine Formel).
    text, formulas = protect_math(text)
    figure_re = FIGURE_STRIKT_RE if Z.strikt else FIGURE_RE
    image_re = IMAGE_STRIKT_RE if Z.strikt else IMAGE_RE
    sauber = (lambda t: t) if Z.strikt else _inline_bereinigen
    text = figure_re.sub(
        lambda m: "\n\n" + register_image(
            m.group("path"),
            restore_math(sauber(m.group("alt")), formulas),
            restore_math(sauber(m.group("caption")), formulas),
        ) + "\n\n",
        text,
    )
    text = image_re.sub(
        lambda m: "\n\n" + register_image(
            m.group("path"), restore_math(sauber(m.group("alt")), formulas)
        ) + "\n\n",
        text,
    )
    text = MARKDOWN_LINK_RE.sub(markdown_link_text, text)
    # Inline-Code mit "<...>" (z. B. BNF-Nichtterminale) ist kein HTML-Tag.
    inline_angle: list[str] = []

    def store_inline_angle(match: re.Match[str]) -> str:
        inline_angle.append(match.group(0))
        return f"@@ILIASINLINEANGLE{len(inline_angle) - 1}@@"

    text = re.sub(r"`[^`\n]*<[^`\n]*`", store_inline_angle, text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"@@ILIASINLINEANGLE(\d+)@@", lambda m: inline_angle[int(m.group(1))], text)
    text = re.sub(r"[*_`~]", "", text)
    text = restore_math(text, formulas)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# --- Tabellen ----------------------------------------------------------------

def split_table_row(line: str) -> list[str]:
    """Zerlegt eine Tabellenzeile; Pipes in Code, [tex] und ``\\|`` bleiben Zelleninhalt."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith(r"\|"):
        text = text[:-1]

    cells: list[str] = []
    current: list[str] = []
    in_code = False
    in_tex = False
    index = 0

    while index < len(text):
        if text.startswith("[tex]", index):
            in_tex = True
            current.append("[tex]")
            index += 5
            continue
        if text.startswith("[/tex]", index):
            in_tex = False
            current.append("[/tex]")
            index += 6
            continue

        char = text[index]
        if char == "\\" and index + 1 < len(text):
            following = text[index + 1]
            if following in {"|", "`", "\\"}:
                current.append(following)
                index += 2
                continue
            current.append("\\")
            index += 1
            continue
        if char == "`" and not in_tex:
            in_code = not in_code
            current.append(char)
        elif char == "|" and not in_code and not in_tex:
            cells.append(repair_math_text("".join(current).strip()))
            current = []
        else:
            current.append(char)
        index += 1

    cells.append(repair_math_text("".join(current).strip()))
    return cells


def _plain_length(value: str) -> int:
    value = re.sub(r"\[/?tex\]", "", value)
    value = re.sub(r"[`*_~]", "", value)
    return len(value.strip())


def table_xml(pcid: int, rows: list[list[str]]) -> tuple[str, int]:
    """Native ILIAS-Datentabelle mit Kopfzeile."""
    if not rows:
        return "", pcid
    column_count = max((len(row) for row in rows), default=0)
    if column_count == 0:
        return "", pcid

    normalized = [row + [""] * (column_count - len(row)) for row in rows]
    keep_columns = [
        i for i in range(column_count) if any(row[i].strip() for row in normalized)
    ]
    if keep_columns and len(keep_columns) != column_count:
        normalized = [[row[i] for i in keep_columns] for row in normalized]
        column_count = len(keep_columns)

    table_pcid = pcid
    pcid += 1
    rendered_rows: list[str] = []
    for row in normalized:
        row_pcid = pcid
        pcid += 1
        cells: list[str] = []
        for cell in row:
            data_pcid = pcid
            content_pcid = pcid + 1
            pcid += 2
            cells.append(
                f'<TableData PCID="{data_pcid}"><PageContent PCID="{content_pcid}">'
                f'<Paragraph Characteristic="TableContent" Language="{Z.sprache}">'
                f'{xml_text(cell)}</Paragraph></PageContent></TableData>'
            )
        rendered_rows.append(f'<TableRow PCID="{row_pcid}">{"".join(cells)}</TableRow>')

    table = (
        f'<Table Language="{Z.sprache}" DataTable="y" HeaderRows="1" '
        'Class="StandardTable" HorizontalAlign="Center">'
        + "".join(rendered_rows)
        + "</Table>"
    )
    Z.tabellen.append({
        "rows": len(normalized),
        "columns": column_count,
        "max_cell_length": max((_plain_length(c) for r in normalized for c in r), default=0),
        "ragged_rows_normalized": any(len(r) != column_count for r in rows),
    })
    return page_content(table_pcid, table), pcid


def image_xml(pcid: int, image_index: int) -> tuple[str, int]:
    from .medien import prepare_image
    image = Z.bilder[image_index]
    if image.mob_id == 0 or image.path is None:
        prepare_image(image, image_index)
    if image.path is None:
        warning = f"Abbildung nicht gefunden: {image.alt or image.source} ({image.source})"
        return paragraph_xml(pcid, warning, "Attention"), pcid + 1

    layout_attributes = ['HorizontalAlign="Center"']
    if image.display_width:
        layout_attributes.append(f'Width="{image.display_width}"')
    if image.display_height:
        layout_attributes.append(f'Height="{image.display_height}"')
    body = (
        "<MediaObject>"
        f'<MediaAlias OriginId="il_0_mob_{image.mob_id}"/>'
        '<MediaAliasItem Purpose="Standard"><Layout '
        + " ".join(layout_attributes)
        + "/></MediaAliasItem></MediaObject>"
    )
    result = [page_content(pcid, body)]
    pcid += 1
    caption = (image.caption or image.alt or "").strip()
    if caption:
        result.append(paragraph_xml(pcid, caption, "Caption"))
        pcid += 1
    return "".join(result), pcid


# --- Seiteninhalt ------------------------------------------------------------

def render_structured_content(markdown: str, base_pcid: int) -> tuple[str, int]:
    lines = prepared_markdown(markdown).splitlines()

    def render_range(start: int, end: int, pcid: int) -> tuple[str, int]:
        rendered: list[str] = []
        paragraph_lines: list[str] = []
        list_items: list[str] = []
        list_numbered: bool | None = None
        index = start

        def flush_paragraph() -> None:
            nonlocal pcid
            if paragraph_lines:
                value = " ".join(x.strip() for x in paragraph_lines if x.strip()).strip()
                paragraph_lines.clear()
                if value:
                    rendered.append(paragraph_xml(pcid, value))
                    pcid += 1

        def flush_list() -> None:
            nonlocal pcid, list_numbered
            if list_items:
                rendered.append(list_xml(pcid, list_items.copy(), numbered=bool(list_numbered)))
                pcid += 1
                list_items.clear()
                list_numbered = None

        while index < end:
            line = lines[index].strip()

            section_match = SECTION_START_RE.match(line)
            if section_match:
                flush_paragraph()
                flush_list()
                depth = 1
                closing = index + 1
                while closing < end:
                    current = lines[closing].strip()
                    if SECTION_START_RE.match(current):
                        depth += 1
                    elif current == SECTION_END:
                        depth -= 1
                        if depth == 0:
                            break
                    closing += 1
                if closing >= end:
                    raise RuntimeError("Nicht geschlossene ILIAS-Section-Markierung.")
                outer_pcid, section_pcid, title_pcid = pcid, pcid + 1, pcid + 2
                body_xml, next_pcid = render_range(index + 1, closing, pcid + 3)
                rendered.append(section_xml(
                    outer_pcid, section_pcid, section_match.group(1),
                    section_match.group(2), body_xml, title_pcid,
                ))
                pcid = next_pcid
                index = closing + 1
                continue

            if line == SECTION_END:
                index += 1
                continue
            if not line:
                flush_paragraph()
                flush_list()
                index += 1
                continue

            code_match = CODE_TOKEN_RE.match(line)
            if code_match:
                flush_paragraph()
                flush_list()
                rendered.append(paragraph_xml(pcid, Z.code_bloecke[int(code_match.group(1))], "Code"))
                pcid += 1
                index += 1
                continue

            image_match = IMAGE_TOKEN_RE.match(line)
            if image_match:
                flush_paragraph()
                flush_list()
                block, pcid = image_xml(pcid, int(image_match.group(1)))
                rendered.append(block)
                index += 1
                continue

            if index + 1 < end and "|" in line and TABLE_SEPARATOR_RE.match(lines[index + 1]):
                flush_paragraph()
                flush_list()
                rows = [split_table_row(line)]
                index += 2
                while index < end and "|" in lines[index] and lines[index].strip():
                    rows.append(split_table_row(lines[index]))
                    index += 1
                width = max(len(row) for row in rows)
                rows = [row + [""] * (width - len(row)) for row in rows]
                block, pcid = table_xml(pcid, rows)
                rendered.append(block)
                continue

            heading = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading:
                flush_paragraph()
                flush_list()
                characteristic = "Headline2" if len(heading.group(1)) <= 3 else "Headline3"
                rendered.append(paragraph_xml(pcid, heading.group(2).strip(), characteristic))
                pcid += 1
                index += 1
                continue

            bullet = re.match(r"^[-*+]\s+(.+)$", line)
            numbered = re.match(r"^\d+[.)]\s+(.+)$", line)
            if bullet or numbered:
                flush_paragraph()
                this_numbered = numbered is not None
                if list_items and list_numbered != this_numbered:
                    flush_list()
                list_numbered = this_numbered
                list_items.append((numbered or bullet).group(1).strip())
                index += 1
                continue

            flush_list()
            paragraph_lines.append(line)
            index += 1

        flush_paragraph()
        flush_list()
        return "".join(rendered), pcid

    result, next_pcid = render_range(0, len(lines), base_pcid)
    if not result:
        return paragraph_xml(base_pcid, "Diese Seite enthält derzeit keinen exportierbaren Text."), base_pcid + 1
    return result, next_pcid
