# SPDX-License-Identifier: EUPL-1.2
"""Native Single-Choice-Fragen: QTI-Export und Einbettung in die Seiten."""
from __future__ import annotations

import hashlib
import re
from xml.etree import ElementTree as ET

from .kontext import Z
from .markdown_quellen import Question

MATH_REPLACEMENTS = {
    r"\varepsilon": "ε",
    r"\epsilon": "ε",
    r"\emptyset": "∅",
    r"\Sigma": "Σ",
    r"\Gamma": "Γ",
    r"\Delta": "Δ",
    r"\lambda": "λ",
    r"\subseteq": "⊆",
    r"\subset": "⊂",
    r"\in": "∈",
    r"\notin": "∉",
    r"\cup": "∪",
    r"\cap": "∩",
    r"\rightarrow": "→",
    r"\to": "→",
}
QUIZ_LABEL_RE = re.compile(r"^\s*\*\*\s*Quiz\s*\d+\s*\*\*\s*", re.IGNORECASE)
QUESTION_TOKEN_RE = re.compile(r"ILIASQUESTION\d{4}TOKEN")


def qti_text(value: str) -> str:
    """Kurze TeX-Fragmente als Unicode (der Fragenrenderer kennt kein MathJax)."""
    text = value
    for source, target in MATH_REPLACEMENTS.items():
        text = text.replace(source, target)
    text = re.sub(r"\\mathcal\{P\}", "℘", text)
    text = re.sub(r"\\text\{([^{}]*)\}", r"\1", text)
    text = text.replace(r"\{", "{").replace(r"\}", "}")
    text = text.replace("$", "")
    if not Z.strikt:
        # QTI-Text ist reiner Text: Markdown-Auszeichnung nicht anzeigen.
        text = re.sub(r"\*\*|__|`", "", text)
        text = re.sub(r"(?<!\w)\*(\S(?:.*?\S)?)\*(?!\w)", r"\1", text)
    return text.strip() if not Z.strikt else text


def clean_question(question: Question) -> Question:
    """Entfernt Markdown-Labels wie ``**Quiz 2**`` aus der sichtbaren Frage."""
    prompt = QUIZ_LABEL_RE.sub("", question.prompt).strip()
    title = QUIZ_LABEL_RE.sub("", question.title).strip()
    question.prompt = prompt
    question.title = title or prompt
    return question


def _text(parent: ET.Element, name: str, value: object) -> ET.Element:
    element = ET.SubElement(parent, name)
    element.text = "" if value is None else str(value)
    return element


def build_qti(questions: list[Question]) -> bytes:
    """Schreibt die qti.xml (Single Choice; Mehrfachauswahl bei mehreren richtigen)."""
    qrefs = [q.qref for q in questions]
    doppelte = sorted({r for r in qrefs if qrefs.count(r) > 1})
    if doppelte:
        raise RuntimeError("Native ILIAS-Fragen besitzen doppelte QRefs: " + ", ".join(doppelte))

    root = ET.Element("questestinterop")
    for question in questions:
        multiple = sum(a.correct for a in question.answers) > 1
        prompt = qti_text(question.prompt)
        title = qti_text(question.title)
        explanation = qti_text(question.explanation)
        item = ET.SubElement(root, "item", {
            "ident": question.qref,
            "title": title,
            # ILIAS: 0 = unbegrenzte Versuche (formative Übung im Lernmodul).
            "maxattempts": "0",
        })
        ET.SubElement(item, "qticomment")
        qtimetadata = ET.SubElement(ET.SubElement(item, "itemmetadata"), "qtimetadata")
        metadata_fields = {
            "ILIAS_VERSION": Z.ilias_version,
            "QUESTIONTYPE": "MULTIPLE CHOICE QUESTION" if multiple else "SINGLE CHOICE QUESTION",
            "AUTHOR": Z.autor,
            "additional_cont_edit_mode": "default",
            "externalId": hashlib.sha1(f"{question.id}:{prompt}".encode()).hexdigest()[:24],
            "ilias_lifecycle": "draft",
            "lifecycle": "draft",
            "thumb_size": "150",
            "feedback_setting": "2",
            "singleline": "1",
        }
        for label, entry in metadata_fields.items():
            feld = ET.SubElement(qtimetadata, "qtimetadatafield")
            _text(feld, "fieldlabel", label)
            _text(feld, "fieldentry", entry)

        presentation = ET.SubElement(item, "presentation", {"label": title})
        flow = ET.SubElement(presentation, "flow")
        material = ET.SubElement(flow, "material")
        _text(material, "mattext", prompt).set("texttype", "text/plain")
        response = ET.SubElement(flow, "response_lid", {
            "ident": "MCSR",
            "rcardinality": "Multiple" if multiple else "Single",
        })
        render_choice = ET.SubElement(response, "render_choice", {"shuffle": "Yes"})
        for index, answer in enumerate(question.answers):
            label = ET.SubElement(render_choice, "response_label", {"ident": str(index)})
            answer_material = ET.SubElement(label, "material")
            _text(answer_material, "mattext", qti_text(answer.text)).set("texttype", "text/plain")

        resprocessing = ET.SubElement(item, "resprocessing")
        outcomes = ET.SubElement(resprocessing, "outcomes")
        ET.SubElement(outcomes, "decvar", {"maxvalue": "1", "minvalue": "0", "vartype": "Decimal"})

        if multiple:
            condition = ET.SubElement(resprocessing, "respcondition", {"continue": "No"})
            and_node = ET.SubElement(ET.SubElement(condition, "conditionvar"), "and")
            for index, answer in enumerate(question.answers):
                if answer.correct:
                    _text(and_node, "varequal", index).set("respident", "MCSR")
                else:
                    not_node = ET.SubElement(and_node, "not")
                    _text(not_node, "varequal", index).set("respident", "MCSR")
            _text(condition, "setvar", 1).set("action", "Set")
            ET.SubElement(condition, "displayfeedback", {
                "feedbacktype": "Response", "linkrefid": "response_correct"})
            otherwise = ET.SubElement(resprocessing, "respcondition", {"continue": "No"})
            ET.SubElement(ET.SubElement(otherwise, "conditionvar"), "other")
            _text(otherwise, "setvar", 0).set("action", "Set")
            ET.SubElement(otherwise, "displayfeedback", {
                "feedbacktype": "Response", "linkrefid": "response_wrong"})
            feedback_ids = ["response_correct", "response_wrong"]
        else:
            for index, answer in enumerate(question.answers):
                condition = ET.SubElement(resprocessing, "respcondition", {"continue": "Yes"})
                conditionvar = ET.SubElement(condition, "conditionvar")
                _text(conditionvar, "varequal", index).set("respident", "MCSR")
                _text(condition, "setvar", 1 if answer.correct else 0).set("action", "Add")
                ET.SubElement(condition, "displayfeedback", {
                    "feedbacktype": "Response", "linkrefid": f"response_{index}"})
            feedback_ids = [f"response_{i}" for i, _ in enumerate(question.answers)]

        for feedback_id in feedback_ids:
            feedback = ET.SubElement(item, "itemfeedback", {"ident": feedback_id, "view": "All"})
            feedback_material = ET.SubElement(ET.SubElement(feedback, "flow_mat"), "material")
            _text(feedback_material, "mattext", explanation).set("texttype", "text/plain")

    ET.indent(root, space="  ")
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    deklaration, rest = payload.split(b"\n", 1)
    doctype = b'<!DOCTYPE questestinterop SYSTEM "ims_qtiasiv1p2p1.dtd">'
    return deklaration + b"\n" + doctype + b"\n" + rest


def embed_questions(members: dict[str, bytes], questions: list[Question]) -> list[dict]:
    """Ersetzt Platzhalterabsätze durch ``<Question>``-Elemente und legt die qti.xml an."""
    if not questions:
        return []
    by_token = {q.source_key: q for q in questions}
    replaced: set[str] = set()
    pattern = re.compile(
        r'<PageContent\b[^>]*>\s*<Paragraph\b[^>]*>\s*'
        r'(?P<token>ILIASQUESTION\d{4}TOKEN)\s*'
        r'</Paragraph>\s*</PageContent>',
        re.DOTALL,
    )
    for name, payload in list(members.items()):
        if "/Services/COPage/" not in name or not name.endswith(".xml"):
            continue

        def replace(match: re.Match[str]) -> str:
            token = match.group("token")
            question = by_token.get(token)
            if question is None:
                return match.group(0)
            replaced.add(token)
            pcid_match = re.search(r'PCID="([^"]+)"', match.group(0))
            pcid = pcid_match.group(1) if pcid_match else "1"
            return f'<PageContent PCID="{pcid}"><Question QRef="{question.qref}"/></PageContent>'

        members[name] = pattern.sub(replace, payload.decode("utf-8")).encode("utf-8")

    missing = sorted(set(by_token) - replaced)
    if missing:
        raise RuntimeError(
            "Quiz-Platzhalter konnten nicht in native Fragen umgewandelt werden: " + ", ".join(missing)
        )
    members[f"{Z.wurzel}/qti.xml"] = build_qti(questions)
    return [
        {
            "title": q.title,
            "type": "multiple_choice" if sum(a.correct for a in q.answers) > 1 else "single_choice",
            "answers": len(q.answers),
            "correct_answers": sum(a.correct for a in q.answers),
            "qref": q.qref,
        }
        for q in questions
    ]
