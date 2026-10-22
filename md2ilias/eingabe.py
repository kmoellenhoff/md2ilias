# SPDX-License-Identifier: EUPL-1.2
"""Eingabe einsammeln: eine .md-Datei oder ein Ordner mit nummerierten .md-Dateien."""
from __future__ import annotations

import re
from pathlib import Path

from .markdown_quellen import BuildError, Quelle, split_h1


def _natuerlich(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def huebscher_name(stem: str) -> str:
    name = re.sub(r"^\d+[-_ .]*", "", stem).replace("-", " ").replace("_", " ").strip()
    return name.title() if name else "Kapitel"


def sammle_quellen(eingaben: list[Path], h1_teilen: bool = True) -> tuple[list[Quelle], list[Path], str]:
    """Liefert Kapitel-Quellen, Bild-Suchwurzeln und einen Standardtitel."""
    if not eingaben:
        raise BuildError("Keine Eingabe angegeben.")
    dateien: list[Path] = []
    wurzeln: list[Path] = []
    standardtitel = ""
    for eingabe in eingaben:
        eingabe = eingabe.expanduser()
        if eingabe.is_dir():
            gefunden = sorted(
                (p for p in eingabe.glob("*.md") if not p.name.startswith(("_", "."))),
                key=lambda p: _natuerlich(p.name),
            )
            if not gefunden:
                raise BuildError(f"Keine .md-Dateien im Ordner {eingabe}")
            dateien.extend(gefunden)
            wurzeln.append(eingabe.resolve())
            standardtitel = standardtitel or huebscher_name(eingabe.resolve().name)
        elif eingabe.is_file():
            dateien.append(eingabe)
            wurzeln.append(eingabe.resolve().parent)
            standardtitel = standardtitel or huebscher_name(eingabe.stem)
        else:
            raise BuildError(f"Eingabe nicht gefunden: {eingabe}")

    quellen: list[Quelle] = []
    for datei in dateien:
        text = datei.read_text(encoding="utf-8")
        teile = split_h1(text) if h1_teilen else [text]
        for nummer, teil in enumerate(teile, start=1):
            schluessel = datei.name if len(teile) == 1 else f"{datei.name}#{nummer}"
            quellen.append(Quelle(
                text=teil,
                schluessel=schluessel,
                verzeichnis=datei.resolve().parent,
                standardtitel=huebscher_name(datei.stem),
            ))
    eindeutig = list(dict.fromkeys(wurzeln))
    return quellen, eindeutig, standardtitel
