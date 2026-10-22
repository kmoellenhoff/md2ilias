# SPDX-License-Identifier: EUPL-1.2
"""Orchestrierung: Markdown-Quellen -> ILIAS-Lernmodul-ZIP."""
from __future__ import annotations

import io
import json
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from . import audit, copage, engine, fragen, medien, uebungen
from .config import Kurs
from .copage import xml_text
from .kontext import Z
from .markdown_quellen import (
    BuildError, IdAllocator, Quelle, split_source,
)
from .skelett import vorlage_zip

NAECHSTE_PCID = 3_000_000_000_000_000_000


@dataclass
class Ergebnis:
    zip_pfad: Path
    report_pfad: Path
    report: dict


def _lies_zip(daten: bytes) -> tuple[list[zipfile.ZipInfo], dict[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(daten), "r") as archiv:
        infos = archiv.infolist()
        return infos, {i.filename: archiv.read(i.filename) for i in infos}


def _schreibe_zip(infos: list[zipfile.ZipInfo], members: dict[str, bytes]) -> bytes:
    ausgabe = io.BytesIO()
    with zipfile.ZipFile(ausgabe, "w", compression=zipfile.ZIP_DEFLATED) as ziel:
        geschrieben: set[str] = set()
        for info in infos:
            kopie = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            kopie.compress_type = info.compress_type
            kopie.external_attr = info.external_attr
            kopie.internal_attr = info.internal_attr
            kopie.comment = info.comment
            kopie.extra = info.extra
            kopie.create_system = info.create_system
            ziel.writestr(kopie, members[info.filename])
            geschrieben.add(info.filename)
        for name, daten in members.items():
            if name not in geschrieben:
                ziel.writestr(name, daten)
    return ausgabe.getvalue()


def _alle_seiten(kapitel):
    return [(k, s) for k in kapitel for s in k.pages]


def _baue_seitenindex(kapitel) -> None:
    Z.seitenindex = [
        {"quelle": s.source_key, "slug": copage.slug(s.original_title or s.title),
         "seite": s}
        for _, s in _alle_seiten(kapitel) if s.id != 0
    ]


def _inhalt_xml(kapitel) -> tuple[list[engine.ChapterSpec], int]:
    next_id = Z.startnummer
    next_pcid = NAECHSTE_PCID
    specs: list[engine.ChapterSpec] = []
    for kapitel_index, kap in enumerate(kapitel):
        kapitel_id = engine.ORIGINAL_CHAPTER_ID if kapitel_index == 0 else str(next_id)
        if kapitel_index > 0:
            next_id += 1
        vergeben = []
        for seiten_index, seite in enumerate(kap.pages):
            if kapitel_index == 0 and seiten_index == 0:
                seiten_id = engine.ORIGINAL_PAGE_ID
                pcid = engine.ORIGINAL_PCID
            else:
                seiten_id = str(next_id)
                next_id += 1
                pcid = str(next_pcid)
                next_pcid += 1000
            Z.seiten_export[id(seite)] = seiten_id
            vergeben.append((seite, seiten_id, pcid))

        seiten_specs = []
        for seite, seiten_id, pcid in vergeben:
            markdown = seite.markdown
            if seite.title in Z.kasten_titel and not markdown.lstrip().startswith("#"):
                markdown = f"## {seite.title}\n\n{markdown}"
            Z.aktuelles_verzeichnis = seite.source_dir
            Z.aktuelle_quelle = seite.source_key
            body_xml, _ = copage.render_structured_content(markdown, int(pcid))
            seiten_specs.append(engine.PageSpec(
                id=seiten_id, pcid=pcid, title=xml_text(seite.title),
                text="", content_xml=body_xml,
            ))
        specs.append(engine.ChapterSpec(
            id=kapitel_id, title=xml_text(kap.title), pages=seiten_specs))
    return specs, next_id


def _tocmode_seiten(members: dict[str, bytes]) -> None:
    name = f"{Z.wurzel}/Modules/LearningModule/set_1/export.xml"
    text = members[name].decode("utf-8")
    text = text.replace("<TocMode>chapters</TocMode>", "<TocMode>pages</TocMode>", 1)
    members[name] = text.encode("utf-8")


def _schlagwoerter(members: dict[str, bytes], woerter: list[str]) -> None:
    if not woerter:
        return
    name = f"{Z.wurzel}/Services/MetaData/set_1/export.xml"
    text = members[name].decode("utf-8")
    ersatz = "".join(f'<Keyword Language="de">{xml_text(w)}</Keyword>' for w in woerter)
    text = text.replace('<Keyword Language="de"></Keyword>', ersatz, 1)
    members[name] = text.encode("utf-8")


def _math_reste(members: dict[str, bytes]) -> list[str]:
    funde: list[str] = []
    muster = (
        r"(?<![A-Za-z])varepsilon(?![A-Za-z])",
        r"@@ILIASMATH\d+@@",
        rf"\\(?:{copage.COMMAND_PATTERN})\b",
    )
    for name, daten in members.items():
        if "/Services/COPage/" not in name or not name.endswith(".xml"):
            continue
        text = daten.decode("utf-8", errors="replace")
        if not Z.strikt:
            # Formeln in [tex]...[/tex] sind gewollt, nur Reste außerhalb zählen.
            text = re.sub(r"\[tex\].*?\[/tex\]", "[tex][/tex]", text, flags=re.S)
        for m_ in muster:
            for treffer in re.finditer(m_, text):
                ausschnitt = re.sub(r"\s+", " ", text[max(0, treffer.start() - 45):treffer.end() + 45])
                funde.append(f"{Path(name).name}: {ausschnitt}")
                if len(funde) >= 100:
                    return funde
    return funde


def _ampersands_schuetzen(members: dict[str, bytes]) -> int:
    """Zusätzliche Escape-Ebene für ``&`` in COPage (ILIAS 9.20 entfernt eine vor dem Parsen)."""
    namen = [n for n in members if n.endswith("/Services/COPage/set_1/export.xml")]
    if len(namen) != 1:
        raise RuntimeError("ILIAS-Paket enthält nicht genau einen COPage-Export.")
    name = namen[0]
    copage_text = members[name].decode("utf-8")
    anzahl = copage_text.count("&amp;")
    geschuetzt = copage_text.replace("&amp;", "&amp;amp;")
    ET.fromstring(geschuetzt)
    seiten = re.findall(r"<PageObject\b.*?</PageObject>", geschuetzt, re.DOTALL)
    if not seiten:
        raise RuntimeError("COPage-Export enthält keine PageObjects.")
    for nummer, seite in enumerate(seiten, start=1):
        try:
            ET.fromstring(seite.replace("&amp;", "&"))
        except ET.ParseError as exc:
            raise RuntimeError(
                f"COPage-Seite {nummer} wäre nach der ILIAS-Ampersand-Transformation ungültig: {exc}"
            ) from exc
    if anzahl:
        members[name] = geschuetzt.encode("utf-8")
    return anzahl


def validiere_paket(daten: bytes, wurzel: str) -> dict[str, object]:
    with zipfile.ZipFile(io.BytesIO(daten), "r") as archiv:
        namen = archiv.namelist()
        pflicht = {
            f"{wurzel}/manifest.xml",
            f"{wurzel}/Modules/LearningModule/set_1/export.xml",
            f"{wurzel}/Services/COPage/set_1/export.xml",
            f"{wurzel}/Services/MetaData/set_1/export.xml",
            f"{wurzel}/Services/Object/set_1/export.xml",
        }
        fehlt = sorted(pflicht.difference(namen))
        if fehlt:
            raise RuntimeError(f"Paket unvollständig: {fehlt}")
        for name in namen:
            if name.endswith(".xml"):
                ET.fromstring(archiv.read(name))
        oberste = {n.split("/", 1)[0] for n in namen if n}
        if oberste != {wurzel}:
            raise RuntimeError(f"Unerwartete ZIP-Wurzel: {sorted(oberste)}")
    return {"members": len(namen), "top_level": wurzel}


def baue(quellen: list[Quelle], kurs: Kurs, ausgabe: Path,
         bild_wurzeln: list[Path] | None = None, standardtitel: str = "") -> Ergebnis:
    """Baut aus den Quellen das ILIAS-ZIP und schreibt ZIP und report.json."""
    zeitstempel = kurs.zeitstempel if kurs.zeitstempel is not None else int(time.time())
    wurzel = f"{zeitstempel}__0__lm_{kurs.quell_id}"
    suchpfade = list(bild_wurzeln or [])
    for ordner in kurs.bildordner:
        p = Path(ordner)
        suchpfade.append(p if p.is_absolute() or kurs.basis is None else kurs.basis / p)
    Z.zuruecksetzen(
        wurzel=wurzel, zip_name=f"{wurzel}.zip", quell_id=str(kurs.quell_id),
        url=kurs.installation_url.rstrip("/"), sprache=kurs.sprache, autor=kurs.autor,
        ilias_version=kurs.ilias_version, strikt=kurs.strikt,
        kasten_titel=tuple(kurs.kasten_ueberschriften),
        entferne_seiten=tuple(kurs.seiten_auslassen),
        bild_suchpfade=[Path(p).resolve() for p in suchpfade],
    )
    Z.startnummer = kurs.startnummer
    Z.quellnamen = {Path(q.schluessel.split("#")[0]).name for q in quellen}

    allocator = IdAllocator(910000, 920000, kurs.fragen_startnummer)
    kapitel = [split_source(q, allocator, Z.warnungen, 0) for q in quellen]
    auslassen = {t.strip().casefold() for t in kurs.seiten_auslassen}
    for kap in kapitel:
        kap.pages = [s for s in kap.pages if s.title.strip().casefold() not in auslassen]
    kapitel = [k for k in kapitel if k.pages]
    if not kapitel:
        raise BuildError("Keine Kapitel und Seiten aus den Markdown-Quellen ermittelt.")

    audit_bericht = audit.build_audit(kapitel)
    uebungen.split_exercises(kapitel)
    _baue_seitenindex(kapitel)
    specs, _ = _inhalt_xml(kapitel)

    titel = kurs.titel or standardtitel or "Lernmodul"
    vorlage = vorlage_zip(wurzel, str(kurs.quell_id), Z.url)
    paket = engine.build_module(
        vorlage, xml_text(titel), xml_text(kurs.beschreibung), specs)
    infos, members = _lies_zip(paket)

    _tocmode_seiten(members)
    _schlagwoerter(members, kurs.schlagwoerter)
    medien.add_media_objects(members)
    reste = _math_reste(members)
    uebungen.replace_link_tokens(members, Z.seiten_export)
    qualitaet = uebungen.quality_audit(members)
    if qualitaet["quality_issue_count"]:
        zusammenfassung = ", ".join(
            f"{n}: {len(v)}" for n, v in qualitaet["quality_findings"].items() if v)
        raise RuntimeError(
            "ILIAS-Qualitätsprüfung fehlgeschlagen; sichtbare Exportartefakte: " + zusammenfassung)

    fragenliste = [fragen.clean_question(q) for k in kapitel for s in k.pages for q in s.questions]
    quiz_stats = fragen.embed_questions(members, fragenliste)
    text_alle = "\n".join(d.decode("utf-8", errors="replace")
                          for n, d in members.items() if n.endswith(".xml"))
    uebrig = re.findall(r"ILIASQUESTION\d{4}TOKEN", text_alle)
    if uebrig:
        raise RuntimeError("Sichtbare Quiz-Platzhalter im Export: " + ", ".join(sorted(set(uebrig))))
    checkbox_reste = re.findall(r"(?:^|\s)[-+*]?\s*\[[ xX]\]", text_alle)

    if Z.sprache != "de":
        for name, daten in list(members.items()):
            if name.endswith(".xml") and not name.endswith("/qti.xml"):
                members[name] = daten.decode("utf-8").replace(
                    'Language="de"', f'Language="{Z.sprache}"').encode("utf-8")

    ampersands = _ampersands_schuetzen(members)
    ergebnis_zip = _schreibe_zip(infos, members)
    validierung = validiere_paket(ergebnis_zip, wurzel)

    ausgabe.mkdir(parents=True, exist_ok=True)
    zip_pfad = ausgabe / Z.zip_name
    zip_pfad.write_bytes(ergebnis_zip)

    audit_pfad = audit.schreibe_audit(audit_bericht, ausgabe / "audit")
    bilder_ok = [b for b in Z.bilder if b.path is not None]
    befunde: list[str] = []
    befunde += [f"Warnung: {w}" for w in dict.fromkeys(Z.warnungen)]
    befunde += [f"Bild nicht gefunden: {b.source}" for b in Z.bilder if b.path is None]
    befunde += [f"TeX-Rest: {r}" for r in reste]
    if checkbox_reste:
        befunde.append(f"{len(checkbox_reste)} unverarbeitete Checkbox-Zeilen im Export")

    report = {
        "title": titel,
        "package_root": wurzel,
        "zip": zip_pfad.name,
        "mode": "strikt (wie Lehrbuch-Export)" if Z.strikt else "md2ilias",
        "chapters": len(specs),
        "pages": sum(len(c.pages) for c in specs),
        "media_objects": len(bilder_ok),
        "missing_images": [b.source for b in Z.bilder if b.path is None],
        "images": [
            {
                "source": b.source, "file": b.filename, "conversion": b.conversion,
                "display_width": b.display_width, "display_height": b.display_height,
                "caption": b.caption, "alt": b.alt, "found": b.path is not None,
            } for b in Z.bilder
        ],
        "table_count": len(Z.tabellen),
        "tables": list(Z.tabellen),
        "math_leak_count": len(reste),
        "math_leaks": reste,
        "quality_issue_count": qualitaet["quality_issue_count"],
        "quality_findings": qualitaet["quality_findings"],
        "exercise_count": len(Z.uebungen),
        "exercises": list(Z.uebungen),
        "internal_link_count": Z.interne_links,
        "quiz_count": len(fragenliste),
        "quizzes": quiz_stats,
        "raw_quiz_checkbox_count": len(checkbox_reste),
        "copage_ampersand_protection_count": ampersands,
        "validation": validierung,
        "warnings": list(dict.fromkeys(Z.warnungen)),
        "audit": {"gesamt": audit_bericht["total"], "klassen": audit_bericht["counts"],
                  "ausgabe": audit_bericht["delivery_counts"],
                  "zu_pruefen": audit_bericht["review_required"],
                  "datei": str(audit_pfad.relative_to(ausgabe))},
        "befund_anzahl": len(befunde),
        "befunde": befunde,
    }
    report_pfad = ausgabe / "report.json"
    report_pfad.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return Ergebnis(zip_pfad, report_pfad, report)
