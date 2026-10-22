# SPDX-License-Identifier: EUPL-1.2
"""Das mitgelieferte Beispiel enthält alle unterstützten Elemente."""
from __future__ import annotations

import re
import shutil
import zipfile
from xml.etree import ElementTree as ET

import pytest

from conftest import alle_xml_wohlgeformt, copage_text, lies_zip


def test_dateinamensregel(beispiel_ergebnis):
    pfad = beispiel_ergebnis.zip_pfad
    assert re.fullmatch(r"\d+__0__lm_\d+\.zip", pfad.name)
    with zipfile.ZipFile(pfad) as z:
        oberste = {n.split("/", 1)[0] for n in z.namelist()}
    assert oberste == {pfad.stem}


def test_xml_wohlgeformt_und_manifest(beispiel_ergebnis):
    members = lies_zip(beispiel_ergebnis.zip_pfad)
    assert alle_xml_wohlgeformt(members) >= 10
    wurzel = beispiel_ergebnis.zip_pfad.stem
    manifest = ET.fromstring(members[f"{wurzel}/manifest.xml"])
    pfade = [e.get("Path") for e in manifest.iter("ExportFile")]
    assert pfade, "Manifest ohne ExportFile"
    for p in pfade:
        assert f"{wurzel}/{p}" in members, p


def test_report_ohne_befunde(beispiel_ergebnis):
    r = beispiel_ergebnis.report
    assert r["befunde"] == []
    assert r["befund_anzahl"] == 0
    assert r["quality_issue_count"] == 0
    assert r["math_leak_count"] == 0
    assert r["missing_images"] == []


def test_zahlen(beispiel_ergebnis):
    r = beispiel_ergebnis.report
    assert r["chapters"] == 3
    assert r["pages"] == 12
    assert r["media_objects"] == 4
    assert r["table_count"] == 1
    assert r["quiz_count"] == 3
    assert r["exercise_count"] == 1
    assert r["internal_link_count"] == 4
    assert r["copage_ampersand_protection_count"] > 0


def test_elemente_im_copage(beispiel_ergebnis):
    text = copage_text(lies_zip(beispiel_ergebnis.zip_pfad))
    assert "<Table " in text and 'HeaderRows="1"' in text
    assert 'Characteristic="Code"' in text
    assert "[tex]V = \\frac{4}{3} \\pi \\, a \\, b \\, c[/tex]" in text
    assert "[tex]U = \\frac{T \\cdot O}{L}[/tex]" in text
    assert text.count("<Question QRef=") == 3
    assert text.count("<IntLink ") >= 4 + 2  # vier Seitenlinks + Aufgabe/Lösung
    for charakter in ("Information", "Attention", "Example", "Citation", "Mnemonic", "Confirmation"):
        assert f'<Section Characteristic="{charakter}"' in text, charakter
    assert 'Characteristic="Caption"' in text
    assert "NUR-FÜR-DIE-LEHRPERSON" not in text, "Dozentenblock darf nicht exportiert werden"
    assert "&amp;amp;&amp;amp;" in text, "Ampersand-Schutz für ILIAS 9.20 fehlt"


def test_loesung_auf_eigener_seite(beispiel_ergebnis):
    members = lies_zip(beispiel_ergebnis.zip_pfad)
    lm = next(v for k, v in members.items() if k.endswith("LearningModule/set_1/export.xml")).decode()
    assert "<Title>Lösung zu Aufgabe 1</Title>" in lm
    assert "<Title>Übung · Aufgabe 1</Title>" in lm


def test_qti(beispiel_ergebnis):
    members = lies_zip(beispiel_ergebnis.zip_pfad)
    qti = next(v for k, v in members.items() if k.endswith("/qti.xml")).decode()
    assert qti.count("<item ") == 3
    assert "Wer gräbt den tiefsten Bau?" in qti
    assert "**" not in qti
    assert 'ident="il_0_qst_930000"' in qti


@pytest.mark.skipif(
    shutil.which("rsvg-convert") is None, reason="rsvg-convert nicht installiert"
)
def test_svg_wird_gerastert(beispiel_ergebnis):
    r = beispiel_ergebnis.report
    konv = {b["source"]: b["conversion"] for b in r["images"]}
    assert konv["bilder/dacsbau-querschnitt.svg"] == "svg-to-png"
    assert konv["bilder/dacs-kopf.png"] == "original"
    members = lies_zip(beispiel_ergebnis.zip_pfad)
    assert sum(1 for n in members if n.endswith(".png")) >= 4


def test_audit_bericht(beispiel_ergebnis):
    audit = beispiel_ergebnis.report["audit"]
    assert audit["gesamt"] == 4  # 3 Quizfragen + 1 Aufgabe
    assert (beispiel_ergebnis.report_pfad.parent / audit["datei"]).is_file()


def test_reproduzierbar(tmp_path):
    """Gleiche Eingabe und fester Zeitstempel ergeben gleiche XML-Teile."""
    from md2ilias import bauen, lade_kurs
    from conftest import BEISPIEL

    kurs = lade_kurs(BEISPIEL / "kurs.yml")
    kurs.zeitstempel = 1767225600  # fester Zeitstempel; ohne ihn ist der Name die Bauzeit
    a = lies_zip(bauen(BEISPIEL / "kurs.md", tmp_path / "a", kurs).zip_pfad)
    b = lies_zip(bauen(BEISPIEL / "kurs.md", tmp_path / "b", kurs).zip_pfad)
    assert a.keys() == b.keys()
    assert all(a[k] == b[k] for k in a)
