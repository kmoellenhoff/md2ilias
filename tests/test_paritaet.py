# SPDX-License-Identifier: EUPL-1.2
"""Parität zum ILIAS-Export des Lehrbuch-Projekts (Modul "netzwerke").

Der Test liest die Kapitel-Markdown-Dateien aus einem Lehrbuch-Checkout, auf den
die Umgebungsvariable LEHRBUCH_DIR zeigt (am besten ein eigener Worktree von
origin/main, weil dort gebaut wird). Ohne LEHRBUCH_DIR wird er übersprungen.
Optional: LEHRBUCH_ILIAS_ZIP = bereits mit ``make ilias MODULE=netzwerke``
erzeugtes Referenzpaket; sonst wird make im Checkout aufgerufen.

Name, Zeitstempel und Quell-ID des Referenzpakets stehen im Lehrbuch selbst
(modules/netzwerke/ilias.yml, Schlüssel output_basename) und werden zur Laufzeit
gelesen; sie sind hier nicht festgeschrieben.

Es werden keine Lehrbuch-Inhalte ins Repo kopiert.
"""
from __future__ import annotations

import functools
import io
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

LEHRBUCH = os.environ.get("LEHRBUCH_DIR")
pytestmark = pytest.mark.skipif(
    not LEHRBUCH or not (Path(LEHRBUCH or "x") / "modules/netzwerke/book.yml").is_file(),
    reason="LEHRBUCH_DIR nicht gesetzt (Paritätstest gegen das Lehrbuch)",
)

_KENNUNG = re.compile(r"(\d+)__0__lm_(\d+)")


@functools.lru_cache(maxsize=None)
def _original() -> tuple[str, int, int]:
    """Name, Zeitstempel und Quell-ID des Referenzpakets aus dem Lehrbuch-Checkout."""
    konfig = yaml.safe_load((Path(LEHRBUCH) / "modules/netzwerke/ilias.yml").read_text(encoding="utf-8"))
    name = str(konfig.get("output_basename", ""))
    treffer = _KENNUNG.fullmatch(name)
    if not treffer:
        pytest.fail("output_basename in modules/netzwerke/ilias.yml hat nicht das Format "
                    f"<Zeitstempel>__0__lm_<Quell-ID>: {name!r}")
    return name, int(treffer.group(1)), int(treffer.group(2))


def _zip(pfad_oder_bytes) -> dict[str, bytes]:
    quelle = io.BytesIO(pfad_oder_bytes) if isinstance(pfad_oder_bytes, bytes) else pfad_oder_bytes
    with zipfile.ZipFile(quelle) as z:
        return {n: z.read(n) for n in z.namelist() if not n.endswith("/")}


@pytest.fixture(scope="module")
def referenz() -> tuple[dict[str, bytes], dict]:
    import json

    wurzel = Path(LEHRBUCH)
    vorgabe = os.environ.get("LEHRBUCH_ILIAS_ZIP")
    if vorgabe:
        zip_pfad = Path(vorgabe)
        report_pfad = zip_pfad.with_name("report.json")
    else:
        ziel = wurzel / "build/netzwerke/ilias"
        lauf = subprocess.run(
            ["make", "ilias", "MODULE=netzwerke", f"PY={sys.executable}"],
            cwd=wurzel, capture_output=True, text=True,
        )
        if lauf.returncode != 0:
            pytest.skip("make ilias im Lehrbuch-Checkout nicht lauffähig: " + lauf.stderr[-300:])
        zip_pfad = ziel / f"{_original()[0]}.zip"
        report_pfad = ziel / "report.json"
    return _zip(zip_pfad), json.loads(report_pfad.read_text(encoding="utf-8"))


def _bauen(strikt: bool, ausgabe: Path):
    from md2ilias import Kurs, baue, sammle_quellen

    wurzel = Path(LEHRBUCH)
    book = yaml.safe_load((wurzel / "modules/netzwerke/book.yml").read_text(encoding="utf-8"))
    ilias = yaml.safe_load((wurzel / "modules/netzwerke/ilias.yml").read_text(encoding="utf-8"))
    # Das Lehrbuch gibt jede Datei als EIN Kapitel aus (nur die erste H1 zählt).
    quellen, _, _ = sammle_quellen([wurzel / s for s in book["sources"]], h1_teilen=False)
    _, zeitstempel, quell_id = _original()
    kurs = Kurs(
        titel=ilias["title"], beschreibung=ilias["description"], autor=ilias["author"],
        zeitstempel=zeitstempel, quell_id=quell_id, strikt=strikt,
        seiten_auslassen=["Lehrtext"],  # Trennseiten-Konvention des Lehrbuchs
    )
    return baue(quellen, kurs, ausgabe, bild_wurzeln=[wurzel / "docs", wurzel / "docs/assets"])


ZAHLEN = ("chapters", "pages", "media_objects", "table_count", "quiz_count", "exercise_count")


def test_strikt_xml_identisch(tmp_path, referenz):
    """Im strikten Modus ist jedes XML-Teil des Pakets byte-identisch zum Lehrbuch-Export."""
    ref_members, ref_report = referenz
    ergebnis = _bauen(True, tmp_path)
    for schluessel in ZAHLEN:
        assert ergebnis.report[schluessel] == ref_report[schluessel], schluessel
    assert ergebnis.report["quality_issue_count"] == ref_report["quality_issue_count"] == 0
    neu = _zip(ergebnis.zip_pfad)
    assert neu.keys() == ref_members.keys()
    for name, daten in ref_members.items():
        if name.endswith(".xml"):
            assert neu[name] == daten, name
        else:  # Rastergrafiken können je nach librsvg-Version abweichen
            assert len(neu[name]) > 0, name


def test_normal_gleiche_struktur(tmp_path, referenz):
    """Im normalen Modus bleiben alle Zählwerte gleich; Unterschiede sind erklärbar."""
    ref_members, ref_report = referenz
    ergebnis = _bauen(False, tmp_path)
    for schluessel in ZAHLEN:
        assert ergebnis.report[schluessel] == ref_report[schluessel], schluessel
    assert ergebnis.report["media_objects"] == 88
    neu = _zip(ergebnis.zip_pfad)
    assert neu.keys() == ref_members.keys() or all(
        n.endswith(".png") for n in neu.keys() ^ ref_members.keys())  # nur Bildnummerierung

    def titel(members):
        lm = next(v for k, v in members.items() if k.endswith("LearningModule/set_1/export.xml")).decode()
        return re.findall(r"<Type>(?:st|pg)</Type><Title>(.*?)</Title>", lm)

    alt, neu_t = titel(ref_members), titel(neu)
    assert len(alt) == len(neu_t)
    unterschiede = [(a, b) for a, b in zip(alt, neu_t) if a != b]
    # einzig erklärter Unterschied: "Mini-Übung Mini-Check 10.1" -> "Mini-Check 10.1"
    assert all(a.replace("Mini-Übung Mini-Check", "Mini-Check") == b for a, b in unterschiede)

    def qti_titel(members):
        q = next(v for k, v in members.items() if k.endswith("/qti.xml")).decode()
        return [re.sub(r"\*\*|`", "", t) for t in re.findall(r'<item ident="[^"]+" title="([^"]*)"', q)]

    assert qti_titel(ref_members) == qti_titel(neu)
