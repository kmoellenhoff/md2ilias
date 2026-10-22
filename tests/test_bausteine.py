# SPDX-License-Identifier: EUPL-1.2
"""Einzelbausteine: Vorlage, Markdown-Zerlegung, Strikt-Modus."""
from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET

from conftest import copage_text, lies_zip
from md2ilias import Kurs, bauen
from md2ilias.kontext import Z
from md2ilias.markdown_quellen import codezeilen, split_h1
from md2ilias.skelett import vorlage_zip


def test_vorlage_ist_leeres_lernmodul():
    daten = vorlage_zip("5__0__lm_42", "42", "https://ilias.example")
    with zipfile.ZipFile(io.BytesIO(daten)) as z:
        namen = z.namelist()
        assert {n.split("/", 1)[0] for n in namen} == {"5__0__lm_42"}
        for n in namen:
            if n.endswith(".xml"):
                ET.fromstring(z.read(n))
                assert b"lernplattform" not in z.read(n)
        lm = z.read("5__0__lm_42/Modules/LearningModule/set_1/export.xml").decode()
    assert "<Id>42</Id>" in lm and "https://ilias.example" in lm


def test_split_h1_ignoriert_code():
    text = "# A\n\ntext\n\n```bash\n# Kommentar\n```\n\n# B\n\nmehr\n"
    assert len(split_h1(text)) == 2


def test_codezeilen_listeneintrag():
    zeilen = ["1. ```text", "   code", "   ```", "danach"]
    assert codezeilen(zeilen) == {0, 1, 2}


def test_bild_attributliste_normal_und_strikt(tmp_path):
    (tmp_path / "b.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>', encoding="utf-8")
    md = tmp_path / "a.md"
    md.write_text(
        '# K\n\n## S\n\n<figure markdown>\n![Alt](b.svg){ width="50%" }\n'
        "<figcaption>Unterschrift</figcaption>\n</figure>\n", encoding="utf-8")
    normal = copage_text(lies_zip(bauen(md, tmp_path / "n", Kurs(zeitstempel=1)).zip_pfad))
    assert "{ width" not in normal
    assert 'Characteristic="Caption">Unterschrift<' in normal
    strikt = copage_text(lies_zip(bauen(md, tmp_path / "s", Kurs(zeitstempel=1, strikt=True)).zip_pfad))
    assert '{ width="50%" }' in strikt  # Verhalten des Lehrbuch-Exports


def test_zustand_wird_zurueckgesetzt(tmp_path):
    md = tmp_path / "a.md"
    md.write_text("# K\n\n## S\n\n```\ncode\n```\n", encoding="utf-8")
    bauen(md, tmp_path / "1", Kurs(zeitstempel=1))
    assert len(Z.code_bloecke) == 1
    bauen(md, tmp_path / "2", Kurs(zeitstempel=1))
    assert len(Z.code_bloecke) == 1


def test_mehrfachauswahl_quiz(tmp_path):
    md = tmp_path / "a.md"
    md.write_text(
        '# K\n\n## S\n\n<div class="quiz" data-question-type="single-choice" markdown>\n'
        "**Welche sind Primzahlen?**\n\n- [x] 2\n- [x] 3\n- [ ] 4\n\n"
        '??? success "Feedback"\n    Zwei und drei.\n</div>\n', encoding="utf-8")
    ergebnis = bauen(md, tmp_path / "o", Kurs(zeitstempel=1))
    assert ergebnis.report["quizzes"][0]["type"] == "multiple_choice"
    qti = next(v for k, v in lies_zip(ergebnis.zip_pfad).items() if k.endswith("qti.xml")).decode()
    assert "MULTIPLE CHOICE QUESTION" in qti


def test_verschachtelte_kaesten(tmp_path):
    md = tmp_path / "a.md"
    md.write_text(
        '# K\n\n## S\n\n!!! note "Außen"\n    Innen\n\n    !!! warning "Innen-Kasten"\n        Tief\n',
        encoding="utf-8")
    text = copage_text(lies_zip(bauen(md, tmp_path / "o", Kurs(zeitstempel=1)).zip_pfad))
    assert text.count("<Section ") == 2 and "!!!" not in text
