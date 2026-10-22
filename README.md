# md2ilias

**md2ilias** wandelt Markdown-Texte in ein **importfertiges ILIAS-Lernmodul** (ZIP) um.
Das Paket entspricht dem Exportformat von **ILIAS 9.20** auf der Lernplattform
`lernplattform.bund.de` und lässt sich dort über *Magazin → Hinzufügen → Lernmodul ILIAS →
Importieren* einspielen.

Umgesetzt werden: Kapitel und Seiten mit Navigation, Überschriften, Absätze, Listen,
native Tabellen, Bilder (auch SVG), Formeln, Code, Zitate, Hinweiskästen, interne
Seitenlinks, Single-Choice-Fragen und Übungen mit separater Lösungsseite. Zu jedem Lauf
gehören ein `report.json` (Zahlen und Befunde) und ein Audit-Bericht zu den Übungen.

Das Werkzeug ist eigenständig: Sie brauchen nur Python und Ihre Markdown-Dateien. Ein
`make` oder ein anderes Projekt ist nicht nötig.

## Installation

Voraussetzung: Python ab 3.11.

```bash
git clone https://github.com/kmoellenhoff/md2ilias.git
cd md2ilias
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .                   # oder: pip install -r requirements.txt
```

Die einzige Python-Abhängigkeit ist PyYAML. Ohne Installation funktioniert auch
`python -m md2ilias` direkt im Projektordner (nach `pip install -r requirements.txt`).

### SVG-Bilder (Systemabhängigkeit)

ILIAS zeigt SVG-Grafiken nicht zuverlässig an. md2ilias rastert SVG deshalb zu PNG
(Breite mindestens 1600 Pixel, Anzeige höchstens 1000 Pixel breit). Dazu wird das
Programm `rsvg-convert` benutzt:

| System | Installation |
|---|---|
| Debian/Ubuntu | `sudo apt install librsvg2-bin` |
| macOS | `brew install librsvg` |
| Windows | `pip install cairosvg` (Ersatz; benötigt die Cairo-Bibliothek) |

Findet md2ilias weder `rsvg-convert` noch `cairosvg`, wird das SVG unverändert
eingebettet und im Bericht als Befund gemeldet. PNG-, JPG- und GIF-Bilder brauchen
keine Zusatzprogramme.

## Schnellstart

```bash
python -m md2ilias beispiel/kurs.md -o build
```

Ergebnis in `build/`:

```text
build/
├── <Zeitstempel>__0__lm_100001.zip  <- dieses ZIP in ILIAS importieren
├── report.json                      <- Zahlen und Befunde
└── audit/exercise-classification.md <- Übungs- und Fragenbericht
```

Der Dateiname folgt dem Muster `<Zeitstempel>__<Installations-ID>__lm_<Quell-ID>`. Der
Zeitstempel ist die Bauzeit in Unix-Sekunden (wie beim Export in ILIAS), die Installations-ID
ist immer `0`, die Quell-ID steht in `kurs.yml`. Nur wenn `zeitstempel:` in `kurs.yml` oder
`--zeitstempel N` gesetzt ist, wird der Zeitstempel fest übernommen (reproduzierbare Builds).

**Fertiges Beispiel zum direkten Import:** `beispiel/fertig/1792681542__0__lm_100001.zip`
(nicht umbenennen). Es wurde mit dem Stand dieses Commits gebaut, daneben liegt der Bericht
`beispiel/fertig/report.json`.

Aufrufe im Überblick:

```bash
python -m md2ilias kurs.md                         # eine Datei
python -m md2ilias mein-kurs/ -c kurs.yml -o out   # Ordner mit 01-....md, 02-....md
python -m md2ilias --init                          # kommentierte Beispiel-kurs.yml schreiben
python -m md2ilias kurs.md --zeitstempel 1767225600  # reproduzierbarer Dateiname
```

Eine `kurs.yml` neben der Eingabe wird automatisch gefunden. Der Rückgabecode ist 0 bei
Erfolg; `report.json` enthält unter `befunde` alles, was Sie prüfen sollten (fehlende
Bilder, übersprungene Quizfragen, unauflösbare Links, TeX-Reste). Ein sauberer Lauf hat
`"befund_anzahl": 0`.

Aus Python:

```python
from md2ilias import bauen, lade_kurs
ergebnis = bauen("kurs.md", "build", lade_kurs("kurs.yml"))
print(ergebnis.zip_pfad, ergebnis.report["befunde"])
```

## Eingabe

* **Eine `.md`-Datei:** `# Überschrift` beginnt ein Kapitel, `## Überschrift` eine Seite.
  Eine Datei darf mehrere Kapitel enthalten.
* **Ein Ordner:** jede `.md`-Datei ist (mindestens) ein Kapitel, `##` bleibt die Seite.
  Die Reihenfolge ergibt sich aus dem Dateinamen mit natürlicher Sortierung
  (`01-…`, `02-…`, `10-…`). Dateien, die mit `_` oder `.` beginnen, werden übergangen.
  Unterordner werden nicht durchsucht, dürfen aber Bilder enthalten.
* **Bilder** werden relativ zur jeweiligen `.md`-Datei angegeben (`bilder/foto.png`).

## Markdown-Syntaxreferenz

Es wird bewusst nur der Umfang unterstützt, den der ILIAS-Export sicher abbilden kann.
Alles Übrige erscheint als einfacher Text.

### Kapitel, Seiten, Überschriften

```markdown
# Kapitel 1: Titel des Kapitels

Text vor der ersten Seite landet auf der automatischen Seite „Überblick“.

## Erste Seite

### Zwischenüberschrift
#### Kleinere Zwischenüberschrift
```

* Führende Nummern („3.1 “) und der Vorspann „Kapitel 3 · “ werden aus Titeln entfernt,
  weil ILIAS selbst gliedert. Dekorative Emojis in Überschriften entfallen.
* `###` und `####` werden zu den ILIAS-Überschriften „Überschrift 2“ bzw. „3“.
* Ein YAML-Kopf (`---` … `---`) am Dateianfang wird ignoriert.
* Die linke Navigation in ILIAS zeigt Kapitel und alle Seiten.

### Text, Listen, Zitate

* Absätze werden durch Leerzeilen getrennt; Zeilenumbrüche im Absatz werden zu Leerzeichen.
* **Fett, kursiv und Inline-Code werden als reiner Text übernommen** (die Auszeichnung entfällt).
  Wichtiges heben Sie über Hinweiskästen (siehe unten) hervor.
* Aufzählungen (`- `, `* `, `+ `) und nummerierte Listen (`1. `, `1) `) werden zu ILIAS-Listen.
  Verschachtelte Listen werden **eingeebnet** (Unterpunkte erscheinen auf Hauptebene).
* Zitate: Das Zeichen `>` wird entfernt, der Text bleibt normaler Absatz. Für ein echtes
  Zitat-Element verwenden Sie den Kasten `!!! quote` (siehe unten).
* HTML-Tags werden entfernt, ihr Text bleibt stehen. Horizontale Linien (`---`) entfallen.
* Das Zeichen `&` (etwa in `cmd1 && cmd2`) ist erlaubt; md2ilias schützt es für den
  Importer von ILIAS 9.20.

### Tabellen

```markdown
| Eigenschaft | DACS | Fuchs |
|---|---|---|
| Grabtiefe in m | 4 | 1,5 |
```

Die erste Zeile wird zur Kopfzeile einer nativen ILIAS-Tabelle. Zellen enthalten nur Text.
`\|` und Pipes in Inline-Code oder Formeln trennen keine Zellen. Spaltenausrichtung wird nicht
ausgewertet; leere Spalten werden entfernt.

### Bilder und Abbildungen

```markdown
![Alternativtext, zugleich Bildunterschrift](bilder/dacs-kopf.png)

<figure markdown>
![Alternativtext](bilder/dacsbau-querschnitt.svg)
<figcaption>Eigene Bildunterschrift</figcaption>
</figure>
```

* Ohne `<figcaption>` dient der Alternativtext als Bildunterschrift.
* Bilder werden zentriert und auf höchstens 1000 Pixel Breite begrenzt.
* Nicht gefundene Bilder erscheinen als Hinweis im Text und als Befund im Bericht.
* Zusätzliche Suchordner für Bilder lassen sich in `kurs.yml` (`bildordner`) angeben.
* Ein angehängtes `{ width="50%" }` (MkDocs-Schreibweise) wird ignoriert.

### Formeln

```markdown
Inline: $a = 0{,}9$ m oder \(\Delta T\)

Abgesetzt:

$$V = \frac{4}{3} \pi \, a \, b \, c$$
```

`$…$`, `\(…\)`, `$$…$$` und `\[…\]` werden zu ILIAS-Formeln (`[tex]…[/tex]`). Mehrzeilige
TeX-Umgebungen (`aligned`, `cases`, …) werden vereinfacht, damit der Import gelingt. Dollarzeichen in
Codeblöcken sind keine Formeln. Ob die Formel in ILIAS gesetzt dargestellt wird, hängt von der
Formeldarstellung (LaTeX/MathJax) der Installation ab.

### Code

````markdown
```bash
ls bau/ && echo "Alles ordentlich"
```
````

Codeblöcke werden zu ILIAS-Codeabsätzen. Eine Sprachangabe wird nicht ausgewertet. Auch in
Listeneinträgen (`1. ```text`) werden Zäune erkannt.

### Links

```markdown
[Wikipedia: Wald](https://de.wikipedia.org/wiki/Wald)  -> Text (https://de.wikipedia.org/wiki/Wald)
[Querschnitt des Baus](#querschnitt-des-baus)          -> interner ILIAS-Seitenlink
[Wer kann was?](02-nachbarn.md#wer-kann-was)           -> interner ILIAS-Seitenlink
```

* **Externe Links** erscheinen als „Text (Adresse)“ (kein anklickbarer Link).
* **Interne Links** auf eine Seite des Kurses (`#anker` oder `datei.md#anker`; ohne Anker die
  erste Seite der Datei) werden zu echten ILIAS-Seitenlinks. Der Anker ist der Seitentitel in
  Kleinbuchstaben mit Bindestrichen; Umlaute dürfen als `ae/oe/ue/ss` geschrieben werden.
  Nicht auflösbare Links werden gemeldet.
* Links auf `.md`-Dateien, die nicht zum Kurs gehören, behalten nur den Linktext.

### Hinweiskästen (Admonitions)

```markdown
!!! warning "Nicht nachmachen"
    Der Inhalt ist um vier Leerzeichen eingerückt und darf Listen,
    Tabellen, Code und weitere Kästen enthalten.

??? success "Lösung: Wer schläft am ruhigsten?"
    Aufklappbare Kästen (`???`) erscheinen als statische Kästen; ihr Titel erhält
    den Zusatz „Lösung: “, falls er nicht schon „Lösung“ enthält.
```

| Art (`!!! art`) | ILIAS-Kasten |
|---|---|
| `info`, `mission`, `abstract`, `summary`, `definition`, `tool` | Information |
| `warning`, `danger`, `security` | Achtung |
| `example`, `idea`, `counterexample`, `adler` | Beispiel |
| `note` | Bemerkung |
| `success` | Bestätigung |
| `tip` | Merkhilfe |
| `question`, `practical` | Interaktion |
| `quote`, `cite` | Zitat |
| `literature` | Literatur |
| `teaching` | Hintergrund |
| `deep-dive`, `deepdive`, `deep` | Vertiefung |
| `expert`, `special` | Besonderes |
| jede andere Art | allgemeiner Block |

Zusätzlich werden die Abschnitte unter den Überschriften **Lernziele**, **Zusammenfassung** und
**Executive Summary** (Ebene `##` oder `###`) als Informationskasten dargestellt. Die Liste ist in
`kurs.yml` über `kasten_ueberschriften` änderbar.

### Dozentenblöcke

```markdown
::: {.lecture}
Nur für die Lehrperson, nicht im Lernmodul.
:::
```

Solche Blöcke (Pandoc-Div mit Klasse `lecture`) werden entfernt.

### Single-Choice-Fragen

Fragen werden als **native ILIAS-Fragen** (QTI) in die Seite eingebettet, mit Auswertung und
Rückmeldung. Zwei gleichwertige Schreibweisen:

**Schreibweise A – mit Auswahlkästchen (empfohlen):**

```markdown
<div class="quiz" data-question-type="single-choice" markdown>
**Wer gräbt den tiefsten Bau?**

- [ ] der Hase
- [x] der DACS
- [ ] der Fuchs

??? success "Feedback"
    Der DACS gräbt mit etwa vier Metern am tiefsten.
</div>
```

**Schreibweise B – mit Schaltflächen:**

```markdown
<div class="li-quiz" data-explanation="Erklärung, die nach der Antwort erscheint." markdown>
**Welche Kammer liegt im Zentrum des Baus?**

<button data-answer="wrong">Die Vorratskammer.</button>
<button data-answer="correct">Die Wohnkammer.</button>
<button data-answer="wrong">Der Lüftungsschacht.</button>
<div class="li-quiz-feedback"></div>
</div>
```

Regeln:

* Mindestens zwei Antworten und **genau eine richtige** – das ist der geprüfte Fall.
  Enthält eine Frage mehrere richtige Antworten, wird sie als Mehrfachauswahl-Frage
  mit „alles oder nichts“ ausgegeben (im Lehrbuch nur in Einzelfällen erprobt; vor dem
  produktiven Einsatz in ILIAS ausprobieren). Ohne richtige Antwort wird die Frage
  übersprungen und gemeldet.
* Die Erklärung erscheint als Rückmeldung zu jeder Antwort.
* Fragetext und Antworten sind reiner Text; Formeln wie `\varepsilon` werden in Unicode umgesetzt.
* Eine Zeile `**Quiz 3**` am Anfang wird entfernt.
* Die Fragen erhalten die IDs `il_0_qst_<fragen_startnummer>`, `…+1`, …

### Übungen mit Lösungsseite

```markdown
<div class="li-mini-task" markdown>
**Aufgabe 1**

Nennen Sie zwei Kammern eines Dacsbaus.
</div>

??? success "Lösung"
    Zum Beispiel Wohnkammer und Vorratskammer.
```

* Die fett gesetzte Zeile ist der Titel der Aufgabe (fehlt sie: „Mini-Übung N“).
* Die Aufgabe erscheint als Kasten „Interaktion“ mit Link „Lösung auf separater Seite öffnen“.
* Die Lösung steht auf einer **eigenen Seite** „Lösung zu <Titel>“ mit Link „Zurück zur Aufgabe“.
* Die Seite mit der Aufgabe heißt „<Seitentitel> · <Aufgabentitel>“.
* Der Lösungsblock muss unmittelbar auf `</div>` folgen und vier Leerzeichen eingerückt sein.
* Der Audit-Bericht (`audit/exercise-classification.md`) schätzt für jede Aufgabe, ob sie sich
  als Auswahlfrage eignen würde (Hinweis zum Umschreiben in Schreibweise A oder B).

## kurs.yml

`python -m md2ilias --init` schreibt eine kommentierte Vorlage. Alle Schlüssel sind optional.

| Schlüssel | Bedeutung | Standard |
|---|---|---|
| `titel` | Titel in ILIAS | Name von Datei bzw. Ordner |
| `beschreibung` | Kurzbeschreibung | leer |
| `sprache` | Sprachcode der Texte/Metadaten | `de` |
| `autor` | Autor, eingetragen in den Fragen-Metadaten | leer |
| `schlagwoerter` | Schlagwörter des Lernmoduls | leer |
| `quell_id` | Teil des Dateinamens `<Zeitstempel>__0__lm_<Quell-ID>` | `100001` |
| `startnummer` | erste freie Kapitel-/Seiten-ID | `910100` |
| `fragen_startnummer` | erste Fragen-ID | `930000` |
| `zeitstempel` | Zeitstempel im Dateinamen (Unix-Sekunden); fester Wert nur für reproduzierbare Builds | Bauzeit |
| `installation_url` | ILIAS-Installation | `https://lernplattform.bund.de` |
| `ilias_version` | Version in den Fragen-Metadaten | `9.20.0` |
| `bildordner` | zusätzliche Bild-Suchordner | leer |
| `kasten_ueberschriften` | Überschriften, die als Kasten erscheinen | Lernziele, Zusammenfassung, Executive Summary |
| `seiten_auslassen` | Seitentitel, die nicht exportiert werden | leer |
| `strikt` | Verhalten wie der Lehrbuch-Export (siehe unten) | `false` |

Unbekannte Schlüssel werden mit einer Fehlermeldung abgewiesen. Die Schlagwörter sind in den
verfügbaren Referenzexporten nicht belegt (dort ist das Feld leer); wer exakt das Format der
Referenz behalten will, lässt sie leer. Der Autor wird nur in die Fragen-Metadaten übernommen.

## Import in ILIAS

1. Im Magazin den Zielordner öffnen.
2. *Hinzufügen* → *Lernmodul ILIAS* → *Importieren*.
3. Die erzeugte ZIP-Datei auswählen und hochladen. **Die Datei nicht umbenennen:** ILIAS
   verlangt, dass der Dateiname dem einzigen Hauptordner im ZIP plus `.zip` entspricht
   (`<Zeitstempel>__<Installations-ID>__lm_<Quell-ID>`, Installations-ID `0`). md2ilias prüft das beim Bauen.
4. Nach dem Import das Lernmodul öffnen, Navigation, Bilder, Formeln und Fragen kurz prüfen.

Wird ein Kurs mehrfach gebaut, unterscheidet der Zeitstempel die Dateien; die Quell-ID darf
gleich bleiben.

## Grenzen

* Getestet ist das Format für **ILIAS 9.20 auf lernplattform.bund.de**. Andere Versionen und
  Installationen sind nicht geprüft. Ein erfolgreicher Build ersetzt den Probeimport nicht.
  Probeimport des Beispiels auf lernplattform.bund.de (ILIAS 9.20) am 22.10.2026 erfolgreich.
* **Nur statische Inhalte:** JavaScript, Akkordeons, Registerkarten und andere interaktive
  Webelemente werden nicht übernommen. Aufklappbare Kästen erscheinen als normale Kästen.
* Fett/kursiv/Inline-Code, verschachtelte Listen und klickbare externe Links gibt der Export
  nicht aus (siehe oben).
* Fragen: Single Choice ist geprüft; Mehrfachauswahl ist schwächer erprobt. Andere Fragetypen
  (Zuordnung, Reihenfolge, Lückentext) gibt es nicht; der Audit-Bericht nennt Kandidaten.
* Das erzeugte XML folgt bewusst dem Referenzformat; md2ilias erfindet keine neuen Strukturen.
* Bilder: SVG wird gerastert; sehr große Bilder erhöhen die Paketgröße entsprechend.

## Verbesserungen gegenüber dem Original (`strikt`)

md2ilias stammt aus dem Export eines Lehrbuch-Projekts. Mit `strikt: true` (oder `--strikt`)
wird exakt dessen Verhalten reproduziert, auch bei den folgenden bekannten Macken, die im
Normalbetrieb behoben sind. Am erzeugten XML-Format ändert sich dadurch nichts.

| Verhalten im strikten Modus | Normalbetrieb |
|---|---|
| `![..](..){ width="50%" }` lässt `{ width="50%" }` im Text stehen und verfehlt die Bildunterschrift | Attributliste wird entfernt, `<figcaption>` wird Bildunterschrift (bereinigt) |
| `##` und `#` innerhalb von Codeblöcken (auch in Listeneinträgen) teilen Seiten | Code wird erkannt und geschützt |
| `---` und `>` am Zeilenanfang werden auch in Codeblöcken entfernt | Code bleibt unverändert |
| Verschachtelte Kästen (`!!!` in `!!!`) bleiben Rohtext | werden umgewandelt |
| Links auf andere Seiten erscheinen als „Text (datei.md#anker)“ | echte ILIAS-Seitenlinks |
| Seitentitel mit Aufgabe: „Titel · Mini-Übung <Aufgabentitel>“ | „Titel · <Aufgabentitel>“ (bei Titeln „Mini-Übung …“ unverändert) |
| Fragetexte enthalten Markdown-Zeichen (`**…**`, Backticks) | Zeichen werden entfernt |
| mehrere richtige Antworten: Frage wird übersprungen | Mehrfachauswahl-Frage |
| `{.lecture}` ohne weitere Klassen wird nicht erkannt | wird erkannt |
| TeX-Reste im Bericht zählen auch gewollte `[tex]`-Formeln | nur Reste außerhalb von `[tex]` |

## Technische Struktur

```text
md2ilias/
├── cli.py               Kommandozeile
├── config.py            kurs.yml
├── eingabe.py           Datei/Ordner einsammeln, Kapitel erkennen
├── markdown_quellen.py  Vorverarbeitung, Quizblöcke, Kapitel/Seiten
├── uebungen.py          Aufgaben mit Lösungsseite, Link-Auflösung, Qualitätsprüfung
├── copage.py            Markdown -> ILIAS-COPage-XML (Text, Tabellen, Kästen, Formeln)
├── medien.py            Bilder, SVG-Rasterung, MediaObject-XML
├── fragen.py            QTI-Fragen und Einbettung
├── engine.py            klont Kapitel-/Seitenblöcke der Vorlage
├── skelett.py           leere Lernmodul-Vorlage (ILIAS-9.20-Struktur)
├── audit.py             Audit-Bericht
└── paket.py             Ablauf, Ampersand-Schutz, Validierung, report.json
```

Die Vorlage (`skelett.py`) beschreibt ein leeres Lernmodul mit einem Kapitel und einer Seite; die
Engine klont deren XML-Blöcke für alle weiteren Kapitel und Seiten. Es liegen keine
Referenzexporte im Repository.

## Tests

```bash
pip install -e ".[test]"
python -m pytest
```

* `tests/test_beispiel.py` baut `beispiel/kurs.md` (alle Elemente) und prüft XML,
  Manifest, Dateinamensregel und einen Bericht ohne Befunde.
* `tests/test_eingabe.py` prüft Ordner-/Dateieingabe, `kurs.yml` und CLI.
* `tests/test_bausteine.py` prüft Einzelheiten.
* `tests/test_paritaet.py` vergleicht gegen den Lehrbuch-Export. Er läuft nur, wenn
  `LEHRBUCH_DIR` auf einen Checkout des Lehrbuch-Projekts zeigt (optional
  `LEHRBUCH_ILIAS_ZIP` für ein fertiges Referenz-ZIP) und wird sonst übersprungen.
  Ergebnis beim Erstlauf: im strikten Modus sind alle 109 Paketteile (alle XML-Dateien samt
  `qti.xml` byte-identisch; 32 Kapitel, 432 Seiten, 88 Medienobjekte, 167 Tabellen, 43 Fragen, 1 Übung).

## Herkunft

md2ilias wurde aus dem ILIAS-Export eines privaten Lehrbuch-Projekts herausgelöst. Die
Struktur des Exports wurde aus Exporten von ILIAS 9.20 rekonstruiert. Die Builder-Kette des
Projekts wurde zu den oben genannten Modulen zusammengeführt; fachspezifische
Sonderlogik (festverdrahtete Übungen eines Moduls) wurde nicht übernommen.

## Lizenz

Lizenziert unter der **EUPL-1.2** (siehe [LICENSE](LICENSE) und [NOTICE](NOTICE)).
Copyright (c) 2026 Klaus Möllenhoff.
Entstanden mit Unterstützung von KI-Werkzeugen (Claude, ChatGPT Codex).

Bereitgestellt wie besehen, ohne Gewähr und ohne Support.
