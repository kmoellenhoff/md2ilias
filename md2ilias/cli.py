# SPDX-License-Identifier: EUPL-1.2
"""Kommandozeile: python -m md2ilias EINGABE [-c kurs.yml] [-o AUSGABEORDNER]."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import BEISPIEL_KURS_YML, KonfigurationsFehler, lade_kurs
from .eingabe import sammle_quellen
from .markdown_quellen import BuildError
from .paket import baue


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="md2ilias",
        description="Wandelt Markdown in ein importfertiges ILIAS-Lernmodul-ZIP um "
                    "(ILIAS 9.20, lernplattform.bund.de).",
    )
    p.add_argument("eingabe", nargs="*", type=Path,
                   help="eine .md-Datei oder ein Ordner mit nummerierten .md-Dateien")
    p.add_argument("-c", "--config", type=Path, metavar="KURS.YML",
                   help="Einstellungen (Standard: kurs.yml neben der Eingabe, falls vorhanden)")
    p.add_argument("-o", "--output", type=Path, default=Path("build"), metavar="ORDNER",
                   help="Ausgabeordner (Standard: build)")
    p.add_argument("--init", nargs="?", const=Path("kurs.yml"), type=Path, metavar="DATEI",
                   help="schreibt eine kommentierte Beispiel-kurs.yml (Standard: ./kurs.yml) und beendet sich")
    p.add_argument("--force", action="store_true", help="--init darf eine vorhandene Datei überschreiben")
    p.add_argument("--zeitstempel", type=int, metavar="UNIX",
                   help="fester Unix-Zeitstempel für den Dateinamen (reproduzierbar)")
    p.add_argument("--strikt", action="store_true",
                   help="exakt das Verhalten des Lehrbuch-Exports (ohne Verbesserungen)")
    p.add_argument("--version", action="version", version=f"md2ilias {__version__}")
    return p


def _kurs_pfad(args: argparse.Namespace) -> Path | None:
    if args.config:
        return args.config
    for eingabe in args.eingabe:
        ordner = eingabe if eingabe.is_dir() else eingabe.parent
        kandidat = ordner / "kurs.yml"
        if kandidat.is_file():
            return kandidat
    return None


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.init is not None:
        if args.init.exists() and not args.force:
            print(f"FEHLER: {args.init} existiert bereits (mit --force überschreiben).", file=sys.stderr)
            return 1
        args.init.write_text(BEISPIEL_KURS_YML, encoding="utf-8")
        print(f"Beispiel-Konfiguration geschrieben: {args.init}")
        return 0
    if not args.eingabe:
        _parser().print_usage(sys.stderr)
        print("FEHLER: Bitte eine .md-Datei oder einen Ordner angeben.", file=sys.stderr)
        return 2
    try:
        kurs = lade_kurs(_kurs_pfad(args))
        if args.zeitstempel is not None:
            kurs.zeitstempel = args.zeitstempel
        if args.strikt:
            kurs.strikt = True
        quellen, wurzeln, titel = sammle_quellen(args.eingabe)
        ergebnis = baue(quellen, kurs, args.output, bild_wurzeln=wurzeln, standardtitel=titel)
    except (BuildError, KonfigurationsFehler, RuntimeError, OSError) as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 1

    r = ergebnis.report
    print(f"ILIAS-ZIP:  {ergebnis.zip_pfad}")
    print(f"Bericht:    {ergebnis.report_pfad}")
    print(f"Kapitel {r['chapters']}, Seiten {r['pages']}, Bilder {r['media_objects']}, "
          f"Tabellen {r['table_count']}, Fragen {r['quiz_count']}, Übungen {r['exercise_count']}")
    if r["befund_anzahl"]:
        print(f"Befunde ({r['befund_anzahl']}):")
        for befund in r["befunde"][:20]:
            print(f"  - {befund}")
        if r["befund_anzahl"] > 20:
            print("  ... weitere siehe report.json")
    print("WICHTIG: ZIP-Datei vor dem Import nicht umbenennen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
