# SPDX-License-Identifier: EUPL-1.2
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

WURZEL = Path(__file__).resolve().parents[1]
BEISPIEL = WURZEL / "beispiel"


@pytest.fixture(scope="session")
def beispiel_ergebnis(tmp_path_factory):
    """Baut beispiel/kurs.md einmal pro Testlauf."""
    from md2ilias import bauen, lade_kurs

    ausgabe = tmp_path_factory.mktemp("beispiel-ausgabe")
    kurs = lade_kurs(BEISPIEL / "kurs.yml")
    return bauen(BEISPIEL / "kurs.md", ausgabe, kurs)


def lies_zip(pfad: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(pfad) as z:
        return {n: z.read(n) for n in z.namelist() if not n.endswith("/")}


def copage_text(members: dict[str, bytes]) -> str:
    return next(v for k, v in members.items() if k.endswith("Services/COPage/set_1/export.xml")).decode("utf-8")


def alle_xml_wohlgeformt(members: dict[str, bytes]) -> int:
    n = 0
    for name, daten in members.items():
        if name.endswith(".xml"):
            ET.fromstring(daten)
            n += 1
    return n


def kopiere_beispiel(ziel: Path) -> Path:
    shutil.copytree(BEISPIEL / "bilder", ziel / "bilder")
    return ziel
