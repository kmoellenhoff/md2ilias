# SPDX-License-Identifier: EUPL-1.2
"""md2ilias - Markdown zu importfertigem ILIAS-Lernmodul-ZIP."""
from __future__ import annotations

from pathlib import Path

from .config import Kurs, lade_kurs
from .eingabe import sammle_quellen
from .paket import Ergebnis, baue

__version__ = "0.1.0"
__all__ = ["Kurs", "Ergebnis", "bauen", "baue", "lade_kurs", "sammle_quellen", "__version__"]


def bauen(eingaben: list[Path | str] | Path | str, ausgabe: Path | str = "build",
          kurs: Kurs | None = None) -> Ergebnis:
    """Bequemer Einstieg: Eingabe(n) und Ausgabeordner, optional ein ``Kurs``-Objekt."""
    if isinstance(eingaben, (str, Path)):
        eingaben = [eingaben]
    quellen, wurzeln, titel = sammle_quellen([Path(e) for e in eingaben])
    return baue(quellen, kurs or Kurs(), Path(ausgabe), bild_wurzeln=wurzeln, standardtitel=titel)
