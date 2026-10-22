# SPDX-License-Identifier: EUPL-1.2
"""Medienobjekte: Bilder auflösen, SVG rastern, MediaObject-XML erzeugen."""
from __future__ import annotations

import io
import mimetypes
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .copage import ImageSpec, xml_text
from .kontext import Z

MAX_DISPLAY_WIDTH = 1000
SVG_RENDER_WIDTH = 1600


def _number(value: str | None) -> int | None:
    if not value:
        return None
    match = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)", value)
    return int(float(match.group(1))) if match else None


def _svg_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None, None
    width = _number(root.get("width"))
    height = _number(root.get("height"))
    if width and height:
        return width, height
    view_box = root.get("viewBox")
    if view_box:
        parts = re.split(r"[\s,]+", view_box.strip())
        if len(parts) == 4:
            try:
                return int(float(parts[2])), int(float(parts[3]))
            except ValueError:
                pass
    return width, height


def _png_dimensions(data: bytes) -> tuple[int | None, int | None]:
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    return None, None


def _safe_filename(source: Path, index: int, suffix: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", source.stem).strip("-._") or "abbildung"
    return f"{index + 1:03d}-{stem}{suffix}"


def svg_rastern(quelle: Path, breite: int) -> bytes | None:
    """Rastert SVG zu PNG: rsvg-convert, sonst cairosvg; ``None`` ohne Werkzeug."""
    if shutil.which("rsvg-convert"):
        with tempfile.TemporaryDirectory() as tmp:
            ziel = Path(tmp) / "rendered.png"
            subprocess.run(
                ["rsvg-convert", "-w", str(breite), "-f", "png", "-o", str(ziel), str(quelle)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            return ziel.read_bytes()
    try:
        import cairosvg  # type: ignore
    except (ImportError, OSError):
        return None
    return cairosvg.svg2png(url=str(quelle), output_width=breite)


def resolve_image(source: str, base_dir: Path | None) -> Path | None:
    if re.match(r"https?://", source):
        return None
    clean = source.split("#", 1)[0].split("?", 1)[0]
    kandidaten: list[Path] = []
    if base_dir is not None:
        kandidaten.append(base_dir / clean)
    for suchpfad in Z.bild_suchpfade:
        kandidaten.append(suchpfad / clean)
        kandidaten.append(suchpfad / re.sub(r"^(?:\.\./)+", "", clean).lstrip("/"))
    for kandidat in kandidaten:
        if kandidat.is_file():
            return kandidat.resolve()
    name = Path(clean).name
    for suchpfad in Z.bild_suchpfade:
        treffer = [p for p in suchpfad.rglob(name) if p.is_file()]
        if len(treffer) == 1:
            return treffer[0]
    return None


def prepare_image(image: ImageSpec, index: int) -> None:
    image.path = resolve_image(image.source, image.base_dir)
    image.mob_id = 1_230_000 + index
    image.width_px = image.height_px = image.display_width = image.display_height = None
    image.conversion = "missing"
    if image.path is None:
        Z.warnungen.append(f"Abbildung nicht gefunden: {image.source}")
        return

    source = image.path
    suffix = source.suffix.lower()
    source_width: int | None = None
    source_height: int | None = None

    if suffix == ".svg":
        source_width, source_height = _svg_dimensions(source)
        render_width = max(source_width, SVG_RENDER_WIDTH) if source_width else SVG_RENDER_WIDTH
        png = svg_rastern(source, render_width)
        if png is not None:
            image.data = png
            image.filename = _safe_filename(source, index, ".png")
            image.mime_type = "image/png"
            image.width_px, image.height_px = _png_dimensions(png)
            image.conversion = "svg-to-png"
        else:
            image.data = source.read_bytes()
            image.filename = _safe_filename(source, index, ".svg")
            image.mime_type = "image/svg+xml"
            image.width_px, image.height_px = source_width, source_height
            image.conversion = "svg-original"
            Z.warnungen.append(
                f"{source.name}: SVG nicht gerastert (weder rsvg-convert noch cairosvg gefunden); "
                "ILIAS zeigt eingebettetes SVG je nach Installation nicht an."
            )
    else:
        image.data = source.read_bytes()
        image.filename = _safe_filename(source, index, suffix or ".bin")
        image.mime_type = mimetypes.guess_type(image.filename)[0] or "application/octet-stream"
        if suffix == ".png":
            image.width_px, image.height_px = _png_dimensions(image.data)
        image.conversion = "original"

    logical_width = source_width or image.width_px
    logical_height = source_height or image.height_px
    if logical_width:
        image.display_width = min(logical_width, MAX_DISPLAY_WIDTH)
        if logical_height:
            image.display_height = max(1, round(logical_height * image.display_width / logical_width))


def append_before(text: str, closing: str, block: str) -> str:
    pos = text.rfind(closing)
    if pos < 0:
        raise RuntimeError(f"Schließendes XML-Element fehlt: {closing}")
    return text[:pos] + block + text[pos:]


def add_media_objects(members: dict[str, bytes]) -> None:
    """Ergänzt MediaObjects-/MetaData-Export und legt die Bilddateien ab (in ``members``)."""
    root = Z.wurzel
    media_name = f"{root}/Services/MediaObjects/set_1/export.xml"
    metadata_name = f"{root}/Services/MetaData/set_1/export.xml"
    media_xml = members[media_name].decode("utf-8")
    metadata_xml = members[metadata_name].decode("utf-8")

    exported_index = 0
    for image_index, image in enumerate(Z.bilder):
        if image.mob_id == 0 or image.path is None:
            prepare_image(image, image_index)
        if image.path is None:
            continue

        exported_index += 1
        relative_dir = f"Services/MediaObjects/set_1/expDir_1/dsDir_{exported_index}"
        media_item_id = 39_102 + exported_index - 1
        description = xml_text((image.caption or image.alt or "").strip())
        title = xml_text(image.filename)
        alt = xml_text((image.alt or image.caption or "Abbildung").strip())
        width = str(image.display_width or "")
        height = str(image.display_height or "")

        media_block = (
            f'<exp:ExportItem Id="{image.mob_id}">'
            f'<ds:DataSet InstallationId="0" InstallationUrl="{Z.url}" '
            'TopEntity="mob" xmlns:ds="http://www.ilias.de/Services/DataSet/ds/4_3">'
            '<ds:Rec Entity="mob"><Mob>'
            f'<Id>{image.mob_id}</Id><Title>{title}</Title>'
            f'<Description>{description}</Description><ImportId></ImportId>'
            f'<Dir>{relative_dir}</Dir></Mob></ds:Rec>'
            '<ds:Rec Entity="mob_media_item"><MobMediaItem>'
            f'<Id>{media_item_id}</Id><MobId>{image.mob_id}</MobId>'
            f'<Width>{width}</Width><Height>{height}</Height><Halign>Center</Halign>'
            '<Caption></Caption><Nr>1</Nr><Purpose>Standard</Purpose>'
            f'<Location>{title}</Location><LocationType>LocalFile</LocationType>'
            f'<Format>{image.mime_type}</Format><TextRepresentation>{alt}</TextRepresentation>'
            '</MobMediaItem></ds:Rec></ds:DataSet></exp:ExportItem>'
        )
        media_xml = append_before(media_xml, "</exp:Export>", media_block)

        metadata_block = (
            f'<exp:ExportItem Id="0:{image.mob_id}:mob"><MetaData>'
            '<General Structure="Hierarchical">'
            f'<Identifier Catalog="ILIAS" Entry="il_0_mob_{image.mob_id}"/>'
            f'<Title Language="de">{title}</Title><Language Language="de"/>'
            f'<Description Language="de">{description}</Description>'
            '<Keyword Language="de"></Keyword></General></MetaData></exp:ExportItem>'
        )
        metadata_xml = append_before(metadata_xml, "</exp:Export>", metadata_block)
        members[f"{root}/{relative_dir}/{image.filename}"] = image.data

    members[media_name] = media_xml.encode("utf-8")
    members[metadata_name] = metadata_xml.encode("utf-8")
