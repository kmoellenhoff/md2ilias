# SPDX-License-Identifier: EUPL-1.2
"""Übungen: Aufgaben mit getrennter Lösungsseite, interne Links, Qualitätsprüfung."""
from __future__ import annotations

import html
import io
import re
import zipfile

from .copage import xml_text
from .kontext import Z
from .markdown_quellen import Chapter, Page

# Trennzeichen "|" (Übungslinks) oder "¦" (Seitenlinks; "|" würde in Tabellenzellen trennen)
LINK_TOKEN_RE = re.compile(r"@@ILIASINTLINK[|¦]([A-Za-z0-9_-]+)[|¦]([^@]+)@@")
MINI_TASK_RE = re.compile(
    r'<div\s+class="li-mini-task"\s+markdown>\s*'
    r'(?P<body>.*?)\s*</div>\s*'
    r'\?\?\?\s+success\s+"(?P<solution_title>[^"]*)"\s*\n'
    r'(?P<solution>(?:(?:[ \t]{4}|\t).*?(?:\n|$))+)',
    re.IGNORECASE | re.DOTALL,
)


def dedent_solution(value: str) -> str:
    lines: list[str] = []
    for line in value.splitlines():
        if line.startswith("\t"):
            lines.append(line[1:])
        elif line.startswith("    "):
            lines.append(line[4:])
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def exercise_title(body: str, fallback: int) -> tuple[str, str]:
    match = re.search(r"^\s*\*\*(.+?)\*\*\s*(?:  )?\s*$", body, re.MULTILINE)
    if not match:
        return f"Mini-Übung {fallback}", body.strip()
    title = match.group(1).strip()
    cleaned = (body[:match.start()] + body[match.end():]).strip()
    return title, cleaned


def combined_title(original_title: str, titles: list[str]) -> str:
    """Seitentitel einer Seite mit Aufgaben: ``Original · Aufgabe(n)``."""
    if not titles:
        return original_title
    if Z.strikt or all(t.startswith("Mini-Übung") for t in titles):
        suffixes = [re.sub(r"^Mini-Übung\s*", "", t).strip() for t in titles]
        if len(suffixes) == 1:
            suffix = f"Mini-Übung {suffixes[0]}"
        else:
            suffix = "Mini-Übungen " + ", ".join(suffixes[:-1]) + " und " + suffixes[-1]
    elif len(titles) == 1:
        suffix = titles[0]
    else:
        suffix = ", ".join(titles[:-1]) + " und " + titles[-1]
    return f"{original_title} · {suffix}"


def split_exercises(chapters: list[Chapter]) -> None:
    """Trennt Aufgaben und Lösungen: Lösung auf eigener Seite, gegenseitig verlinkt."""
    exercise_number = 0
    for chapter in chapters:
        expanded: list[Page] = []
        for page in chapter.pages:
            original_title = page.title
            source = page.markdown
            generated: list[Page] = []
            cursor = 0
            rewritten: list[str] = []
            titles: list[str] = []
            source_keys: list[str] = []

            for match in MINI_TASK_RE.finditer(source):
                exercise_number += 1
                rewritten.append(source[cursor:match.start()])
                title, task_body = exercise_title(match.group("body"), exercise_number)
                solution = dedent_solution(match.group("solution"))
                solution_page_title = f"Lösung zu {title}"
                solution_key = f"exercise-{exercise_number}-solution"
                source_key = f"exercise-{exercise_number}-source"
                Z.link_ziele[solution_key] = ("titel", solution_page_title)
                source_keys.append(source_key)
                titles.append(title)

                rewritten.append(
                    f'\n\n!!! question "{title}"\n'
                    + "\n".join(f"    {line}" if line else "" for line in task_body.splitlines())
                    + "\n\n"
                    + f"    @@ILIASINTLINK|{solution_key}|Lösung auf separater Seite öffnen@@\n\n"
                )
                solution_markdown = (
                    f"## {solution_page_title}\n\n"
                    '!!! success "Lösung"\n'
                    + "\n".join(f"    {line}" if line else "" for line in solution.splitlines())
                    + f"\n\n@@ILIASINTLINK|{source_key}|Zurück zur Aufgabe@@\n"
                )
                generated.append(Page(id=0, title=solution_page_title,
                                      markdown=solution_markdown, questions=[],
                                      source_dir=page.source_dir,
                                      source_key=page.source_key,
                                      original_title=solution_page_title))
                Z.uebungen.append({
                    "exercise": title,
                    "source_page_original": original_title,
                    "solution_page": solution_page_title,
                    "link_key_solution": solution_key,
                    "link_key_source": source_key,
                })
                cursor = match.end()

            if rewritten:
                rewritten.append(source[cursor:])
                page.markdown = "".join(rewritten)
                page.title = combined_title(original_title, titles)
                for key in source_keys:
                    Z.link_ziele[key] = ("titel", page.title)

            expanded.append(page)
            expanded.extend(generated)
        chapter.pages = expanded


def _page_title_to_ids(members: dict[str, bytes]) -> dict[str, list[str]]:
    lm_name = f"{Z.wurzel}/Modules/LearningModule/set_1/export.xml"
    text = members[lm_name].decode("utf-8")
    result: dict[str, list[str]] = {}
    for record in re.findall(r'<ds:Rec Entity="lm_tree">(.*?)</ds:Rec>', text, re.DOTALL):
        type_match = re.search(r"<Type>pg</Type>", record)
        id_match = re.search(r"<Child>(\d+)</Child>", record)
        title_match = re.search(r"<Title>(.*?)</Title>", record, re.DOTALL)
        if not (type_match and id_match and title_match):
            continue
        title = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip())
        result.setdefault(title, []).append(id_match.group(1))
    return result


def replace_link_tokens(members: dict[str, bytes], seiten_export: dict[int, str]) -> None:
    """Ersetzt Link-Platzhalter durch ``IntLink``-Elemente auf die Export-Seiten-IDs."""
    title_to_ids = _page_title_to_ids(members)
    resolved: dict[str, str] = {}
    for key, (art, ziel) in Z.link_ziele.items():
        if art == "seite":
            if ziel not in seiten_export:
                raise RuntimeError(f"Zielseite für internen Link nicht gefunden: {key}")
            resolved[key] = seiten_export[ziel]
            continue
        ids = title_to_ids.get(ziel, [])
        if not ids:
            raise RuntimeError(f"Zielseite für internen Link nicht gefunden: {ziel}")
        if len(ids) > 1:
            raise RuntimeError(
                f"Zielseite für internen Übungslink ist nicht eindeutig: {ziel} ({len(ids)} Seiten)"
            )
        resolved[key] = ids[0]

    unresolved: list[str] = []
    for name, payload in list(members.items()):
        if "/Services/COPage/" not in name or not name.endswith(".xml"):
            continue

        def replace(match: re.Match[str]) -> str:
            target_id = resolved.get(match.group(1))
            if target_id is None:
                unresolved.append(match.group(1))
                return match.group(0)
            return (
                f'<IntLink Target="il_0_pg_{target_id}" Type="PageObject">'
                f'{xml_text(match.group(2))}</IntLink>'
            )

        members[name] = LINK_TOKEN_RE.sub(replace, payload.decode("utf-8")).encode("utf-8")
    if unresolved:
        raise RuntimeError("Nicht aufgelöste interne Linkschlüssel: " + ", ".join(sorted(set(unresolved))))


def quality_audit(members: dict[str, bytes]) -> dict[str, object]:
    """Sucht sichtbare Exportartefakte (Markdown-, Formel-, Link-Reste) im XML."""
    checks = {
        "math_placeholders": re.compile(r"@@ILIASMATH"),
        "link_placeholders": re.compile(r"@@ILIASINTLINK"),
        "unresolved_internal_links": re.compile(r"could not resolve link target", re.IGNORECASE),
        "visible_varepsilon": re.compile(r"(?<!\\)varepsilon"),
        "markdown_images": re.compile(r"!\[[^\]]*\]\("),
        "markdown_table_separators": re.compile(r"\|\s*:?-{3,}"),
        "visible_horizontal_rules": re.compile(r"(?:^|>)\s*---+\s*(?:<|$)"),
    }
    findings: dict[str, list[dict[str, str]]] = {name: [] for name in checks}
    for name, payload in members.items():
        if not name.endswith(".xml"):
            continue
        text = payload.decode("utf-8", errors="replace")
        for check_name, pattern in checks.items():
            for match in pattern.finditer(text):
                start = max(0, match.start() - 60)
                end = min(len(text), match.end() + 100)
                findings[check_name].append({
                    "file": name,
                    "context": re.sub(r"\s+", " ", text[start:end]),
                })
    return {
        "quality_issue_count": sum(len(v) for v in findings.values()),
        "quality_findings": findings,
    }
