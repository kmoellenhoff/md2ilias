# SPDX-License-Identifier: EUPL-1.2
"""Ordner- und Einzeldatei-Eingabe, CLI, Konfiguration."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from conftest import BEISPIEL, copage_text, kopiere_beispiel, lies_zip
from md2ilias import Kurs, bauen, lade_kurs
from md2ilias.cli import main
from md2ilias.config import KonfigurationsFehler


def _in_dateien_zerlegen(ordner: Path) -> None:
    """Zerlegt beispiel/kurs.md an den Kapitelüberschriften in nummerierte Dateien."""
    text = (BEISPIEL / "kurs.md").read_text(encoding="utf-8")
    teile = re.split(r"(?m)^(?=# )", text)
    teile = [t for t in teile if t.strip()]
    for nr, teil in enumerate(teile, start=1):
        (ordner / f"{nr:02d}-kapitel.md").write_text(teil, encoding="utf-8")


def test_ordner_eingabe(tmp_path):
    eingabe = kopiere_beispiel(tmp_path / "kurs")
    _in_dateien_zerlegen(eingabe)
    ergebnis = bauen(eingabe, tmp_path / "out", lade_kurs(BEISPIEL / "kurs.yml"))
    r = ergebnis.report
    assert (r["chapters"], r["pages"], r["media_objects"]) == (3, 12, 4)
    assert (r["table_count"], r["quiz_count"], r["exercise_count"]) == (1, 3, 1)
    assert r["befunde"] == []
    assert r["internal_link_count"] == 4  # Links über Dateigrenzen (Kapitel 3 -> 1 und 2)


def test_ordner_nummern_natuerlich_sortiert(tmp_path):
    for nr in (10, 2, 1):
        (tmp_path / f"{nr}-k.md").write_text(f"# Kapitel {nr}\n\n## Seite\n\nText {nr}\n", encoding="utf-8")
    r = bauen(tmp_path, tmp_path / "o", Kurs(zeitstempel=1)).report
    assert r["chapters"] == 3
    lm = next(v for k, v in lies_zip(tmp_path / "o" / r["zip"]).items()
              if k.endswith("LearningModule/set_1/export.xml")).decode()
    titel = re.findall(r"<Type>st</Type><Title>(.*?)</Title>", lm)
    assert titel == ["Kapitel 1", "Kapitel 2", "Kapitel 10"]


def test_einzeldatei_mit_mehreren_kapiteln(beispiel_ergebnis):
    assert beispiel_ergebnis.report["chapters"] == 3


def test_einzeldatei_ohne_h1(tmp_path):
    datei = tmp_path / "mein-text.md"
    datei.write_text("## Erste Seite\n\nHallo Welt.\n\n## Zweite Seite\n\nNoch ein Absatz.\n", encoding="utf-8")
    r = bauen(datei, tmp_path / "o", Kurs(zeitstempel=5)).report
    assert (r["chapters"], r["pages"]) == (1, 2)
    assert r["title"] == "Mein Text"
    assert r["zip"] == "5__0__lm_100001.zip"


def test_fehlendes_bild_ist_befund(tmp_path):
    datei = tmp_path / "a.md"
    datei.write_text("# K\n\n## S\n\n![Alt](gibt-es-nicht.png)\n", encoding="utf-8")
    r = bauen(datei, tmp_path / "o", Kurs(zeitstempel=5)).report
    assert r["missing_images"] == ["gibt-es-nicht.png"]
    assert r["befund_anzahl"] >= 1
    assert "Abbildung nicht gefunden" in copage_text(lies_zip(tmp_path / "o" / r["zip"]))


def test_ungueltiges_quiz_wird_gemeldet(tmp_path):
    datei = tmp_path / "a.md"
    datei.write_text(
        '# K\n\n## S\n\n<div class="li-quiz" data-explanation="E" markdown>\n**F?**\n\n'
        '<button data-answer="wrong">a</button>\n<button data-answer="wrong">b</button>\n'
        '<div class="li-quiz-feedback"></div>\n</div>\n', encoding="utf-8")
    r = bauen(datei, tmp_path / "o", Kurs(zeitstempel=5)).report
    assert r["quiz_count"] == 0
    assert any("Quiz" in b for b in r["befunde"])


def test_code_mit_ueberschriften_und_strichen(tmp_path):
    datei = tmp_path / "a.md"
    datei.write_text(
        "# K\n\n## S\n\n```yaml\n---\n## kein Seitentitel\n> kein Zitat\n```\n", encoding="utf-8")
    r = bauen(datei, tmp_path / "o", Kurs(zeitstempel=5)).report
    assert r["pages"] == 1
    text = copage_text(lies_zip(tmp_path / "o" / r["zip"]))
    assert "## kein Seitentitel" in text and "&gt; kein Zitat" in text


def test_cli_init_und_build(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["--init"]) == 0
    assert (tmp_path / "kurs.yml").is_file()
    assert main(["--init"]) == 1  # nicht überschreiben
    assert main(["--init", "--force"]) == 0
    kurs = lade_kurs(tmp_path / "kurs.yml")
    assert kurs.titel == "Mein Kurs" and kurs.quell_id == 100001
    shutil.copy(BEISPIEL / "kurs.md", tmp_path / "kurs.md")
    shutil.copytree(BEISPIEL / "bilder", tmp_path / "bilder")
    assert main(["kurs.md", "-o", "ausgabe", "--zeitstempel", "42"]) == 0
    out = capsys.readouterr().out
    assert "42__0__lm_100001.zip" in out
    bericht = json.loads((tmp_path / "ausgabe" / "report.json").read_text(encoding="utf-8"))
    assert bericht["title"] == "Mein Kurs"  # kurs.yml neben der Eingabe wurde gefunden


def test_cli_fehler(tmp_path, capsys):
    assert main([str(tmp_path / "gibt-es-nicht.md")]) == 1
    assert "FEHLER" in capsys.readouterr().err
    assert main([]) == 2


def test_kurs_yml_unbekannter_schluessel(tmp_path):
    p = tmp_path / "kurs.yml"
    p.write_text("titell: x\n", encoding="utf-8")
    with pytest.raises(KonfigurationsFehler, match="titell"):
        lade_kurs(p)


def test_kurs_yml_wirkt(tmp_path):
    datei = tmp_path / "a.md"
    datei.write_text("# K\n\n## S\n\nText\n", encoding="utf-8")
    kurs = Kurs(titel="T & Titel", beschreibung="B", sprache="en", quell_id=777,
                zeitstempel=9, schlagwoerter=["eins", "zwei"], autor="A B")
    r = bauen(datei, tmp_path / "o", kurs).report
    assert r["zip"] == "9__0__lm_777.zip"
    m = lies_zip(tmp_path / "o" / r["zip"])
    md = next(v for k, v in m.items() if k.endswith("MetaData/set_1/export.xml")).decode()
    assert '<Title Language="en">T &amp; Titel</Title>' in md
    assert '<Keyword Language="de"' not in md
    assert md.count('<Keyword Language="en">eins</Keyword><Keyword Language="en">zwei</Keyword>') == 1
    assert "il_0_lm_777" in md


def test_bibliothek_dict_und_dateiliste(tmp_path):
    """Bibliotheksnutzung: Dateiliste in fester Reihenfolge, Kurs aus Dict, h1_teilen=False."""
    from md2ilias import kurs_aus_dict

    b = tmp_path / "b.md"
    a = tmp_path / "a.md"
    b.write_text("# Zweites\n\n## Seite\n\nText\n\n# Noch eine H1\n\nmehr\n", encoding="utf-8")
    a.write_text("# Erstes\n\n## Seite\n\nText\n", encoding="utf-8")
    kurs = kurs_aus_dict(
        {"titel": "T", "zeitstempel": 1767225600, "quell_id": 42, "strikt": True,
         "seiten_auslassen": ["Lehrtext"], "bildordner": ["bilder"]},
        basis=tmp_path,
    )
    assert kurs.basis == tmp_path.resolve() and kurs.strikt and kurs.quell_id == 42
    r = bauen([b, a], tmp_path / "o", kurs, h1_teilen=False)
    assert r.report["package_root"] == "1767225600__0__lm_42"
    assert r.report["chapters"] == 2
    lm = next(v for k, v in lies_zip(r.zip_pfad).items()
              if k.endswith("LearningModule/set_1/export.xml")).decode()
    assert re.findall(r"<Type>st</Type><Title>(.*?)</Title>", lm) == ["Zweites", "Erstes"]
    assert (tmp_path / "o" / "report.json").is_file()


def test_kurs_aus_dict_unbekannter_schluessel():
    from md2ilias import kurs_aus_dict

    with pytest.raises(KonfigurationsFehler):
        kurs_aus_dict({"gibtsnicht": 1})
