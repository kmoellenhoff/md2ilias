# SPDX-License-Identifier: EUPL-1.2
"""kurs.yml: Einstellungen des Lernmoduls mit Standardwerten."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .kontext import STANDARD_KASTEN_TITEL


class KonfigurationsFehler(RuntimeError):
    pass


@dataclass
class Kurs:
    titel: str = ""
    beschreibung: str = ""
    sprache: str = "de"
    autor: str = ""
    schlagwoerter: list[str] = field(default_factory=list)
    quell_id: int = 100001
    startnummer: int = 910100
    fragen_startnummer: int = 930000
    zeitstempel: int | None = None
    installation_url: str = "https://lernplattform.bund.de"
    ilias_version: str = "9.20.0"
    bildordner: list[str] = field(default_factory=list)
    kasten_ueberschriften: list[str] = field(default_factory=lambda: list(STANDARD_KASTEN_TITEL))
    seiten_auslassen: list[str] = field(default_factory=list)
    strikt: bool = False
    basis: Path | None = None  # Ordner der kurs.yml (für relative Pfade)


SCHLUESSEL = {
    "titel", "beschreibung", "sprache", "autor", "schlagwoerter", "quell_id",
    "startnummer", "fragen_startnummer", "zeitstempel", "installation_url",
    "ilias_version", "bildordner", "kasten_ueberschriften", "seiten_auslassen",
    "strikt",
}


def kurs_aus_dict(daten: dict, basis: Path | None = None) -> Kurs:
    """Baut ein ``Kurs``-Objekt aus einem Dict (dieselben Schlüssel und Prüfungen wie kurs.yml).

    ``basis`` ist der Ordner, gegen den relative ``bildordner`` aufgelöst werden.
    """
    if not isinstance(daten, dict):
        raise KonfigurationsFehler("kurs.yml muss ein YAML-Objekt (Schlüssel: Wert) enthalten.")
    unbekannt = sorted(set(daten) - SCHLUESSEL)
    if unbekannt:
        raise KonfigurationsFehler(
            "Unbekannte Schlüssel in kurs.yml: " + ", ".join(unbekannt)
            + ". Erlaubt: " + ", ".join(sorted(SCHLUESSEL))
        )
    kurs = Kurs(basis=Path(basis).resolve() if basis is not None else None)
    for schluessel, wert in daten.items():
        if wert is None:
            continue
        if schluessel in {"schlagwoerter", "bildordner", "kasten_ueberschriften", "seiten_auslassen"}:
            if isinstance(wert, str):
                wert = [w.strip() for w in wert.split(",") if w.strip()]
            wert = [str(w) for w in wert]
        elif schluessel in {"quell_id", "startnummer", "fragen_startnummer", "zeitstempel"}:
            try:
                wert = int(wert)
            except (TypeError, ValueError) as exc:
                raise KonfigurationsFehler(f"{schluessel} muss eine ganze Zahl sein.") from exc
        elif schluessel == "strikt":
            wert = bool(wert)
        else:
            wert = str(wert)
        setattr(kurs, schluessel, wert)
    if kurs.sprache and len(kurs.sprache) > 8:
        raise KonfigurationsFehler("sprache erwartet einen Sprachcode wie 'de' oder 'en'.")
    return kurs


def lade_kurs(pfad: Path | None) -> Kurs:
    if pfad is None:
        return Kurs()
    if not pfad.is_file():
        raise KonfigurationsFehler(f"kurs.yml nicht gefunden: {pfad}")
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    return kurs_aus_dict(daten, basis=pfad.resolve().parent)


BEISPIEL_KURS_YML = """\
# kurs.yml - Einstellungen für md2ilias. Alle Schlüssel sind optional;
# fehlende Angaben werden durch die hier genannten Standardwerte ersetzt.

# Titel des Lernmoduls in ILIAS (Standard: Name der Eingabedatei bzw. des Ordners)
titel: "Mein Kurs"

# Kurzbeschreibung, erscheint in ILIAS unter dem Titel
beschreibung: "Kurze Beschreibung des Lernmoduls"

# Sprachcode für Texte und Metadaten (de, en, ...)
sprache: "de"

# Autorin/Autor; wird in den Metadaten der Fragen (QTI) vermerkt
autor: "Vorname Nachname"

# Schlagwörter des Lernmoduls (leer lassen = Metadaten exakt wie im Referenzexport)
schlagwoerter: []
#  - Beispiel
#  - Lernmodul

# --- technische IDs (meist unverändert lassen) --------------------------------

# Quell-ID: Teil des Dateinamens <Zeitstempel>__0__lm_<Quell-ID>.zip
quell_id: 100001

# erste freie Nummer für weitere Kapitel- und Seiten-IDs
startnummer: 910100

# erste Nummer für Fragen-IDs (il_0_qst_<Nummer>)
fragen_startnummer: 930000

# Zeitstempel im Dateinamen (Unix-Sekunden); leer lassen = Bauzeit (Standard).
# Nur für reproduzierbare Builds einen festen Wert eintragen:
# zeitstempel: 1767225600

# ILIAS-Installation, für die das Paket gebaut wird
installation_url: "https://lernplattform.bund.de"
ilias_version: "9.20.0"

# --- Markdown-Verhalten --------------------------------------------------------

# zusätzliche Ordner für die Suche nach Bilddateien (relativ zu dieser Datei);
# Bildpfade im Markdown gelten zuerst relativ zur jeweiligen .md-Datei.
bildordner: []

# Überschriften (## oder ###), deren Abschnitt als hervorgehobener Kasten erscheint
kasten_ueberschriften:
  - Lernziele
  - Zusammenfassung
  - Executive Summary

# Seiten mit diesen Titeln nicht exportieren (z. B. reine Trennseiten)
seiten_auslassen: []

# true = exakt das Verhalten des Lehrbuch-Exports, auch bei bekannten Macken
# (siehe README, "Verbesserungen gegenüber dem Original")
strikt: false
"""
