"""OPEN-QUESTIONS: the topics and the questions inside them.

Markdown rather than CSV, because a question is a discussion and its answer is
prose. The shape is fixed, since the method depends on it:

    ## Topic 03 — LED interface

    ### OQ-0301 — Which LEDs must work
    **Question:** ...
    **Answer:** <blank until decided>
    **Blocks:** ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

TOPIC = re.compile(r"^## Topic (\d{2}) — (.+?)\s*$", re.M)
QUESTION = re.compile(r"^### (OQ-(\d{2})\d{2}) — (.+?)\s*$", re.M)
FIELD = re.compile(r"^\*\*([\w ]+?):\*\* ?(.*)$", re.M)


@dataclass
class Question:
    id: str
    topic: str
    title: str
    question: str
    answer: str
    blocks: str
    line: int

    @property
    def open(self) -> bool:
        return not self.answer.strip()


def load(path: Path | None) -> tuple[dict[str, str], list[Question]]:
    if path is None or not path.exists():
        return {}, []
    text = path.read_text()
    topics = {m.group(1): m.group(2) for m in TOPIC.finditer(text)}
    heads = list(QUESTION.finditer(text))
    questions = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        nxt = TOPIC.search(text, h.end(), end)
        body = text[h.end(): nxt.start() if nxt else end]
        # A field runs until the next field, so a multi-paragraph answer is kept whole.
        fields: dict[str, str] = {}
        marks = list(FIELD.finditer(body))
        for j, f in enumerate(marks):
            stop = marks[j + 1].start() if j + 1 < len(marks) else len(body)
            fields[f.group(1)] = (f.group(2) + body[f.end():stop]).strip()
        questions.append(Question(
            id=h.group(1), topic=h.group(2), title=h.group(3),
            question=fields.get("Question", ""), answer=fields.get("Answer", ""),
            blocks=fields.get("Blocks", ""), line=text[:h.start()].count("\n") + 1,
        ))
    return topics, questions
