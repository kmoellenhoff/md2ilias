# SPDX-License-Identifier: EUPL-1.2
"""Gemeinsamer Zustand eines Bauvorgangs (wird pro Build zurückgesetzt)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Boxen für Standard-Überschriften (siehe README, "Kästen aus Überschriften").
STANDARD_KASTEN_TITEL = ("Executive Summary", "Zusammenfassung", "Lernziele")


@dataclass
class Zustand:
    wurzel: str = ""
    zip_name: str = ""
    quell_id: str = "100001"
    url: str = "https://lernplattform.bund.de"
    sprache: str = "de"
    autor: str = ""
    ilias_version: str = "9.20.0"
    strikt: bool = False
    kasten_titel: tuple[str, ...] = STANDARD_KASTEN_TITEL
    entferne_seiten: tuple[str, ...] = ()
    bild_suchpfade: list[Path] = field(default_factory=list)
    aktuelles_verzeichnis: Path | None = None
    aktuelle_quelle: str = ""
    quellnamen: set[str] = field(default_factory=set)
    seitenindex: list[Any] = field(default_factory=list)
    interne_links: int = 0
    startnummer: int = 910100
    seiten_export: dict[int, str] = field(default_factory=dict)
    bilder: list[Any] = field(default_factory=list)
    code_bloecke: list[str] = field(default_factory=list)
    tabellen: list[dict[str, Any]] = field(default_factory=list)
    link_ziele: dict[str, str] = field(default_factory=dict)
    uebungen: list[dict[str, Any]] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)

    def zuruecksetzen(self, **werte: Any) -> None:
        neu = Zustand(**werte)
        self.__dict__.clear()
        self.__dict__.update(neu.__dict__)


Z = Zustand()
