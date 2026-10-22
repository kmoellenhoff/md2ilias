# SPDX-License-Identifier: EUPL-1.2
"""md2ilias - Markdown zu importfertigem ILIAS-Lernmodul-ZIP."""
from __future__ import annotations

from pathlib import Path

from .config import Kurs, kurs_aus_dict, lade_kurs
from .eingabe import sammle_quellen
from .paket import Ergebnis, baue

__version__ = "0.1.1"
__all__ = ["Kurs", "Ergebnis", "bauen", "baue", "lade_kurs", "kurs_aus_dict", "sammle_quellen", "__version__"]


def bauen(eingaben: list[Path | str] | Path | str, ausgabe: Path | str = "build",
          kurs: Kurs | None = None, *, h1_teilen: bool = True) -> Ergebnis:
    """Bequemer Einstieg: Eingabe(n) und Ausgabeordner, optional ein ``Kurs``-Objekt.

    ``eingaben`` darf Dateien (in der gegebenen Reihenfolge) und Ordner enthalten.
    Mit ``h1_teilen=False`` ergibt jede Datei genau ein Kapitel (nur die erste ``#``-
    Überschrift zählt), statt bei jeder ``#``-Überschrift ein neues Kapitel zu beginnen.
    """
    if isinstance(eingaben, (str, Path)):
        eingaben = [eingaben]
    quellen, wurzeln, titel = sammle_quellen([Path(e) for e in eingaben], h1_teilen=h1_teilen)
    return baue(quellen, kurs or Kurs(), Path(ausgabe), bild_wurzeln=wurzeln, standardtitel=titel)
