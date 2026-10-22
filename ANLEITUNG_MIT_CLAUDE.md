# Vorhandenes Material mit Claude in das md2ilias-Format bringen

Liegt Ihr Material als Word-Dokument, PDF oder in Folien vor, kann Claude daraus das
Markdown-Format für md2ilias erzeugen. Sie müssen die Syntax nicht selbst lernen: Geben Sie
Claude die Referenz aus dem [README](README.md) mit und lassen Sie das Ergebnis anschließend von
md2ilias prüfen.

## Vorgehen

1. **Material bereitstellen.** Word-Datei oder PDF an Claude anhängen (bei Folien: als PDF).
   Bilder, die im Dokument stehen, bitte als eigene Dateien (PNG, JPG oder SVG) in einen
   Ordner `bilder/` legen; Claude kann sie nur verlinken, nicht ins Markdown einbetten.
2. **Syntaxreferenz mitgeben.** Hängen Sie `README.md` und `beispiel/kurs.md` an. Das
   Beispiel zeigt jedes unterstützte Element in der richtigen Schreibweise.
3. **Auftrag stellen** (Beispiel-Prompt unten) und das Ergebnis als `.md`-Datei speichern.
4. **Bauen und Bericht lesen:** `python -m md2ilias kurs.md -o build`. Alles unter `befunde`
   in `build/report.json` ist ein Hinweis, was nachzubessern ist (fehlende Bilder, übersprungene
   Fragen, nicht auflösbare Links).
5. **Probeimport** in ILIAS und Sichtprüfung.

## Beispiel-Prompt

```text
Du bekommst anbei mein Lehrmaterial (Word/PDF) sowie die Dokumentation des Werkzeugs
md2ilias (README.md) und eine Beispieldatei (beispiel/kurs.md).

Wandle das Material in genau dieses Markdown-Format um:

- "# " beginnt ein Kapitel, "## " eine Seite des ILIAS-Lernmoduls. Eine Seite sollte
  einen in sich geschlossenen Gedanken enthalten (etwa eine Bildschirmseite).
- Gib Überschriften ohne Nummerierung an.
- Verwende nur die in der README beschriebenen Elemente: Absätze, einfache (nicht
  verschachtelte) Listen, Tabellen, Bilder als ![Beschreibung](bilder/datei.png),
  Formeln in $...$ bzw. $$...$$, Codeblöcke, Hinweiskästen (!!! info/warning/example/
  definition/tip "Titel" mit 4 Leerzeichen Einrückung).
- Verzichte auf Fettdruck zur Gliederung; nutze stattdessen Kästen oder Zwischenüberschriften.
- Verständnisfragen mit einer richtigen Antwort schreibst du als Schreibweise A (Auswahlkästchen)
  aus der README, mit kurzer Erklärung im Feedback.
- Aufgaben mit Musterlösung schreibst du als li-mini-task mit "??? success" -Lösung.
- Erfinde keine Inhalte. Fehlt eine Information oder ist etwas unklar, setze an der Stelle
  "TODO: ..." und liste alle TODOs am Ende deiner Antwort auf.
- Bilder: Nenne zu jedem Bild den Dateinamen, den ich unter bilder/ anlegen soll, und einen
  sinnvollen Alternativtext.

Liefere die Datei vollständig als einen Markdown-Block.
```

## Typische Nacharbeit

* **Bilder prüfen:** Dateinamen stimmen mit `bilder/` überein, sonst meldet der Bericht „Bild nicht gefunden“.
* **Tabellen:** Zellen sind reiner Text; verbundene Zellen und Bilder in Zellen gibt es nicht.
* **Fragen:** je Frage genau eine richtige Antwort markieren.
* **Formeln:** Claude schreibt sie meist korrekt in LaTeX; kontrollieren Sie sie nach dem Import in ILIAS.
* Bei großen Dokumenten: kapitelweise umwandeln lassen und als Ordner mit `01-….md`, `02-….md` ablegen.

## Datenschutz

Geben Sie nur Material an Claude, das Sie dafür verwenden dürfen (keine personenbezogenen
Daten, keine vertraulichen Prüfungsunterlagen).
