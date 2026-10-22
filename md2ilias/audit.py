# SPDX-License-Identifier: EUPL-1.2
"""Audit-Bericht: Klassifikation aller Übungen und Quizfragen.

Der Bericht ist beratend (verändert keinen Inhalt). Er zeigt, welche Aufgaben
als native ILIAS-Frage und welche als Textübung mit Lösungsseite erscheinen.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .markdown_quellen import Chapter
from .uebungen import MINI_TASK_RE, dedent_solution, exercise_title

INTERACTIVE_TYPES = {
    "single_choice", "multiple_choice", "true_false", "true_false_series",
    "matching", "ordering",
}


def plain(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[`*_#]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def classify_task(title: str, body: str, solution: str) -> tuple[str, str, float]:
    text = plain(f"{title} {body} {solution}").lower()
    numbered_items = len(re.findall(r"(?m)^\s*\d+[.)]\s+", body))
    bullet_items = len(re.findall(r"(?m)^\s*[-*+]\s+", body))

    if re.search(r"\b(wahr|falsch|richtig|unrichtig)\b", text):
        return "true_false_series", "Mehrere Aussagen werden jeweils einzeln als Richtig/Falsch geprüft.", 0.95
    if re.search(r"\b(zuordnen|zuordnung|ordnen sie .* zu)\b", text):
        return "matching", "Die Aufgabe verlangt eine Zuordnung.", 0.95
    if re.search(r"\b(sortieren|reihenfolge|bringen sie .* reihenfolge|anordnen)\b", text):
        return "ordering", "Die Aufgabe verlangt eine Reihenfolge.", 0.95
    if re.search(r"\b(mehrere|alle zutreffenden|welche .* gelten|kreuzen sie .* an)\b", text):
        return "multiple_choice", "Mehrere Antworten können gleichzeitig zutreffen.", 0.88
    if numbered_items >= 3 or bullet_items >= 4:
        if re.search(r"\b(entscheiden|bewerten|klassifizieren|gültig|ungültig|gehört|gehören)\b", text):
            return "true_false_series", "Mehrere einzelne Beispiele sollten unabhängig bewertet werden.", 0.82
    if re.search(r"\b(welche|welcher|welches|genau eine|eine richtige)\b", text) and numbered_items <= 1:
        return "single_choice", "Eine klar abgegrenzte Auswahlfrage mit voraussichtlich genau einer richtigen Antwort.", 0.72
    if re.search(r"\b(nennen|begründen|erklären|beschreiben|konstruieren|entwerfen|formulieren|beweisen|leiten sie ab|zeichnen|bestimmen|simulieren|verfolgen|ändern)\b", text):
        return "open", "Die Aufgabe verlangt eine eigenständige Begründung, Konstruktion, Berechnung oder Darstellung.", 0.92
    return "open", "Keine verlässliche automatische Abbildung auf einen geschlossenen Fragetyp erkannt.", 0.60


def delivery_for(kind: str, classification: str) -> dict[str, object]:
    interactive = kind == "chapter_quiz" or classification in INTERACTIVE_TYPES
    return {
        "ilias": "native_question" if interactive else "text_exercise_with_solution",
        "machine_assessable": interactive,
    }


def build_audit(chapters: list[Chapter]) -> dict[str, object]:
    """Klassifiziert Aufgaben (vor der Zerlegung in Aufgaben-/Lösungsseiten)."""
    records: list[dict[str, object]] = []
    exercise_index = 0
    for chapter in chapters:
        for page in chapter.pages:
            for match in MINI_TASK_RE.finditer(page.markdown):
                exercise_index += 1
                title, body = exercise_title(match.group("body"), exercise_index)
                solution = dedent_solution(match.group("solution"))
                kind, reason, confidence = classify_task(title, body, solution)
                records.append({
                    "kind": "exercise",
                    "chapter": chapter.title,
                    "page": page.title,
                    "title": title,
                    "classification": kind,
                    "confidence": confidence,
                    "reason": reason,
                    "delivery": delivery_for("exercise", kind),
                    "task_excerpt": plain(body)[:280],
                    "solution_excerpt": plain(solution)[:220],
                    "review_required": confidence < 0.80,
                })
            for question in page.questions:
                correct = sum(answer.correct for answer in question.answers)
                qtype = "single_choice" if correct == 1 else "multiple_choice"
                records.append({
                    "kind": "chapter_quiz",
                    "chapter": chapter.title,
                    "page": page.title,
                    "title": plain(question.title),
                    "classification": qtype,
                    "confidence": 1.0,
                    "reason": f"Strukturierter Quizblock mit {correct} richtiger/richtigen Antwort(en).",
                    "delivery": delivery_for("chapter_quiz", qtype),
                    "answers": len(question.answers),
                    "correct_answers": correct,
                    "review_required": False,
                })
    counts = Counter(str(r["classification"]) for r in records)
    delivery_counts = Counter(str(r["delivery"]["ilias"]) for r in records)
    return {
        "total": len(records),
        "counts": dict(sorted(counts.items())),
        "delivery_counts": dict(sorted(delivery_counts.items())),
        "review_required": sum(bool(r["review_required"]) for r in records),
        "records": records,
    }


def markdown_report(report: dict[str, object]) -> str:
    lines = [
        "# Audit der Übungen und Quizfragen",
        "",
        "Der Bericht ist beratend. Quizfragen werden als native ILIAS-Fragen "
        "eingebettet; Aufgaben mit Lösung (`li-mini-task`) erscheinen als Textübung "
        "mit separater Lösungsseite. Die Klassifikation der Aufgaben zeigt, welche "
        "sich für eine native Frage eignen würden.",
        "",
        f"Gesamtzahl: **{report['total']}**",
        f"Manuell zu prüfen: **{report['review_required']}**",
        "",
        "## Verteilung nach Fragetyp",
        "",
    ]
    for kind, count in report["counts"].items():
        lines.append(f"- `{kind}`: {count}")
    lines.extend(["", "## Ausgabe in ILIAS", ""])
    for kind, count in report["delivery_counts"].items():
        lines.append(f"- `{kind}`: {count}")
    lines.extend(["", "## Einzelprüfung", ""])
    for record in report["records"]:
        marker = "PRÜFEN" if record["review_required"] else "OK"
        lines.extend([
            f"### [{marker}] {record['chapter']} · {record['page']}",
            "",
            f"**Element:** {record['title']}",
            "",
            f"**Vorschlag:** `{record['classification']}`  ",
            f"**ILIAS-Ausgabe:** `{record['delivery']['ilias']}`  ",
            f"**Sicherheit:** {float(record['confidence']):.0%}  ",
            f"**Begründung:** {record['reason']}",
            "",
        ])
        if record.get("task_excerpt"):
            lines.extend([f"> {record['task_excerpt']}", ""])
    return "\n".join(lines).rstrip() + "\n"


def schreibe_audit(report: dict[str, object], ordner: Path) -> Path:
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "exercise-classification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ziel = ordner / "exercise-classification.md"
    ziel.write_text(markdown_report(report), encoding="utf-8")
    return ziel
