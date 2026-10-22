# SPDX-License-Identifier: EUPL-1.2
"""Markdown-Vorverarbeitung: Quizblöcke, Kapitel- und Seitenzerlegung.

Aus dem ILIAS-Export des Lehrbuch-Projekts übernommen (Stufe "legacy"),
soweit die Builder-Kette sie tatsächlich benutzt.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

from .kontext import Z

FRONT_MATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^\s*(?:(?:\d+[.)]|[-*+])\s+)?(```|~~~)")
ADMONITION_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<marker>!!!|\?\?\?)\s+"
    r"(?P<kind>[A-Za-z0-9_-]+)(?:\s+\"(?P<title>[^\"]*)\")?\s*$"
)
QUIZ_RE = re.compile(
    r'<div\s+class="li-quiz"\s+data-explanation="(?P<explanation>.*?)"\s+markdown>\s*'
    r"(?P<body>.*?)"
    r'<div\s+class="li-quiz-feedback"></div>\s*</div>',
    re.IGNORECASE | re.DOTALL,
)
CHECKBOX_QUIZ_RE = re.compile(
    r'<div\s+class="quiz"\s+data-question-type="single-choice"\s+markdown>\s*'
    r"(?P<body>.*?)"
    r'\?\?\?\s+success\s+"Feedback"\s*\n(?P<explanation>(?:[ \t]+.*(?:\n|$))+)'
    r"\s*</div>",
    re.IGNORECASE | re.DOTALL,
)
LEGACY_CHECKBOX_QUIZ_RE = re.compile(
    r'<div\s+class="li-quiz"\s+data-correct="[^"]+"\s+markdown>\s*'
    r"(?P<body>.*?)"
    r'<div\s+class="li-feedback li-feedback-correct"\s+markdown>\s*'
    r"(?P<explanation>.*?)</div>\s*"
    r'<div\s+class="li-feedback li-feedback-wrong"\s+markdown>.*?</div>\s*</div>',
    re.IGNORECASE | re.DOTALL,
)
CHECKBOX_ANSWER_RE = re.compile(
    r"^\s*-\s*\[(?P<mark>[ xX])\]\s*(?P<text>.+?)\s*$",
    re.MULTILINE,
)
BUTTON_RE = re.compile(
    r'<button\s+data-answer="(?P<answer>correct|wrong)">(?P<text>.*?)</button>',
    re.IGNORECASE | re.DOTALL,
)
DECORATIVE_SYMBOLS = re.compile(
    "[📚🎯💡⚠✅❌🧠🔍🧩🚀🛡🧪📝📌🔧🧭📖🏁✨👉👈🔐🔒🔓🧱🧮🗂🗃🧰✗✓🎓👨🏫🔬🏛🌐]"
)
LECTURE_START_STRIKT = re.compile(r"^(?P<f>:{3,})\s+\{[^}]*\.lecture(?:\s|\})[^}]*\}\s*$")
LECTURE_START = re.compile(r"^(?P<f>:{3,})\s+\{[^}]*\.lecture(?:\s[^}]*)?\}\s*$")


class BuildError(RuntimeError):
    """Benutzerbezogener Fehler beim Export."""


@dataclass
class Answer:
    text: str
    correct: bool


@dataclass
class Question:
    source_key: str
    title: str
    prompt: str
    explanation: str
    answers: list[Answer]
    id: int = 0
    installation_id: int = 0

    @property
    def qref(self) -> str:
        return f"il_{self.installation_id}_qst_{self.id}"


@dataclass
class Page:
    id: int
    title: str
    markdown: str
    questions: list[Question] = field(default_factory=list)
    source_dir: Path | None = None
    source_key: str = ""
    original_title: str = ""


@dataclass
class Chapter:
    id: int
    title: str
    pages: list[Page]


@dataclass
class Quelle:
    """Ein Kapitel-Rohtext samt Herkunft (für Bildpfade und Meldungen)."""
    text: str
    schluessel: str
    verzeichnis: Path
    standardtitel: str = "Kapitel"


class IdAllocator:
    def __init__(self, chapter_start: int, page_start: int, question_start: int):
        self.chapter = chapter_start
        self.page = page_start
        self.question = question_start

    def next_chapter(self) -> int:
        value = self.chapter
        self.chapter += 1
        return value

    def next_page(self) -> int:
        value = self.page
        self.page += 1
        return value

    def next_question(self) -> int:
        value = self.question
        self.question += 1
        return value


def plain_text(fragment: str) -> str:
    fragment = html.unescape(fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    fragment = re.sub(r"\s+", " ", fragment)
    return fragment.strip()


def strip_front_matter(text: str) -> str:
    return FRONT_MATTER_RE.sub("", text, count=1)


def clean_heading(title: str) -> str:
    title = plain_text(DECORATIVE_SYMBOLS.sub("", title)).strip()
    title = re.sub(
        r"^(?:Vertiefung\s*[·:–-]\s*)?Kapitel\s+\d+\s*[·:–-]\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"^\d+(?:\.\d+)*\s+", "", title)
    return title.strip() or "Ohne Titel"


def strip_lecture_blocks(text: str) -> str:
    """Entfernt Pandoc-Divs mit Klasse ``lecture`` (Dozentenhinweise)."""
    result: list[str] = []
    closing_length: int | None = None
    for line in text.splitlines():
        if closing_length is None:
            match = (LECTURE_START_STRIKT if Z.strikt else LECTURE_START).match(line)
            if match:
                closing_length = len(match.group("f"))
                result.append("")
            else:
                result.append(line)
        else:
            if re.fullmatch(rf":{{{closing_length},}}\s*", line):
                closing_length = None
            result.append("")
    if closing_length is not None:
        raise BuildError("Nicht geschlossener .lecture-Block")
    return "\n".join(result)


def extract_quizzes(text: str, source_key: str, warnungen: list[str],
                    installation_id: int) -> tuple[str, list[Question]]:
    questions: list[Question] = []

    def baue(match: re.Match[str], antworten: list[Answer], prompt: str,
             explanation: str, art: str) -> str:
        correct_count = sum(a.correct for a in antworten)
        if len(antworten) < 2 or correct_count < 1 or (Z.strikt and correct_count != 1):
            warnungen.append(
                f"{art} in {source_key} übersprungen: unterstützt werden "
                "mindestens zwei Antworten und mindestens eine richtige Antwort."
            )
            return f"\n**Nicht exportiertes Quiz:** {prompt}\n"
        token = f"ILIASQUESTION{len(questions) + 1:04d}TOKEN"
        questions.append(
            Question(
                source_key=token,
                title=prompt[:180],
                prompt=prompt,
                explanation=explanation,
                answers=antworten,
                installation_id=installation_id,
            )
        )
        return f"\n\n{token}\n\n"

    def replacement(match: re.Match[str]) -> str:
        body = match.group("body")
        answers = [
            Answer(plain_text(b.group("text")), b.group("answer").lower() == "correct")
            for b in BUTTON_RE.finditer(body)
        ]
        prompt = plain_text(BUTTON_RE.sub("", body)) or "Frage"
        return baue(match, answers, prompt, plain_text(match.group("explanation")), "Quiz")

    def checkbox_replacement(match: re.Match[str]) -> str:
        body = match.group("body")
        answers = [
            Answer(plain_text(a.group("text")), a.group("mark").lower() == "x")
            for a in CHECKBOX_ANSWER_RE.finditer(body)
        ]
        prompt = plain_text(CHECKBOX_ANSWER_RE.sub("", body)) or "Frage"
        return baue(match, answers, prompt, plain_text(match.group("explanation")), "Checkbox-Quiz")

    previous = None
    while previous != text:
        previous = text
        text = QUIZ_RE.sub(replacement, text)
        text = CHECKBOX_QUIZ_RE.sub(checkbox_replacement, text)
        text = LEGACY_CHECKBOX_QUIZ_RE.sub(checkbox_replacement, text)
    return text, questions


def codezeilen(zeilen: list[str]) -> set[int]:
    """Indizes aller Zeilen, die zu einem Code-Zaun gehören (inkl. Zäune)."""
    drin: set[int] = set()
    im_code, zaun = False, ""
    for i, zeile in enumerate(zeilen):
        m = FENCE_RE.match(zeile)
        if not im_code and m:
            im_code, zaun = True, m.group(1)
            drin.add(i)
        elif im_code:
            drin.add(i)
            if zeile.strip().startswith(zaun):
                im_code = False
    return drin


def _ohne_codebloecke(text: str, funktion) -> str:
    """Wendet ``funktion`` nur auf Text außerhalb von Code-Zäunen an."""
    zeilen = text.split("\n")
    drin = codezeilen(zeilen)
    ergebnis: list[str] = []
    puffer: list[str] = []
    for i, zeile in enumerate(zeilen):
        if i in drin:
            if puffer:
                ergebnis.append(funktion("\n".join(puffer)))
                puffer = []
            ergebnis.append(zeile)
        else:
            puffer.append(zeile)
    if puffer:
        ergebnis.append(funktion("\n".join(puffer)))
    return "\n".join(ergebnis)


def _html_und_striche(text: str) -> str:
    text = re.sub(r'<div\s+class="li-meta"[^>]*>.*?</div>', "", text, flags=re.I | re.S)
    text = re.sub(
        r"<summary>(.*?)</summary>",
        lambda m: f"\n### {plain_text(m.group(1))}\n",
        text, flags=re.I | re.S,
    )
    text = re.sub(r"</?details\b[^>]*>", "", text, flags=re.I)
    # Horizontale Linien dürfen nicht als '--'/'---' im Export erscheinen.
    text = re.sub(r"(?m)^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", "", text)
    # Zitatzeichen werden entfernt (Zitate erscheinen als normaler Absatz).
    return re.sub(r"(?m)^\s*>\s?", "", text)


def preprocess_markdown(text: str, source_key: str, warnungen: list[str],
                        installation_id: int) -> tuple[str, list[Question]]:
    text = strip_lecture_blocks(text)
    text = strip_front_matter(text)
    text, questions = extract_quizzes(text, source_key, warnungen, installation_id)
    if Z.strikt:
        text = _html_und_striche(text)
    else:
        text = _ohne_codebloecke(text, _html_und_striche)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip() + "\n", questions


def split_h1(text: str) -> list[str]:
    """Teilt einen Text an Überschriften der Ebene 1 (außerhalb von Code)."""
    zeilen = text.splitlines()
    drin = codezeilen(zeilen)
    teile: list[list[str]] = [[]]
    for i, zeile in enumerate(zeilen):
        if (i not in drin and re.match(r"^#\s+\S", zeile)
                and any(t.strip() for t in teile[-1])):
            teile.append([])
        teile[-1].append(zeile)
    return ["\n".join(t) for t in teile if any(x.strip() for x in t)] or [text]


def split_source(quelle: Quelle, allocator: IdAllocator, warnungen: list[str],
                 installation_id: int) -> Chapter:
    text, questions = preprocess_markdown(
        quelle.text, quelle.schluessel, warnungen, installation_id
    )
    lines = text.splitlines()

    drin = set() if Z.strikt else codezeilen(lines)
    chapter_title = quelle.standardtitel
    h1_index = None
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line) if index not in drin else None
        if match and len(match.group(1)) == 1:
            chapter_title = clean_heading(match.group(2))
            h1_index = index
            break
    if h1_index is not None:
        lines.pop(h1_index)
        drin = {i - 1 if i > h1_index else i for i in drin}

    sections: list[tuple[str, list[str]]] = []
    current_title = "Überblick"
    current_lines: list[str] = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line) if index not in drin else None
        if match and len(match.group(1)) == 2:
            if any(item.strip() for item in current_lines):
                sections.append((current_title, current_lines))
            current_title = clean_heading(match.group(2))
            current_lines = []
        else:
            current_lines.append(line)
    if any(item.strip() for item in current_lines) or not sections:
        sections.append((current_title, current_lines))

    question_by_token = {q.source_key: q for q in questions}
    pages: list[Page] = []
    for title, section_lines in sections:
        markdown = "\n".join(section_lines).strip()
        page_questions: list[Question] = []
        for token, question in question_by_token.items():
            if token in markdown:
                question.id = allocator.next_question()
                page_questions.append(question)
        pages.append(
            Page(
                id=allocator.next_page(),
                title=title or "Inhalt",
                markdown=markdown,
                questions=page_questions,
                source_dir=quelle.verzeichnis,
                source_key=quelle.schluessel,
                original_title=title or "Inhalt",
            )
        )
    return Chapter(id=allocator.next_chapter(), title=chapter_title, pages=pages)
