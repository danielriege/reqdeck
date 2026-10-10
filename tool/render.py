"""Markdown views of the model, shared by `req doc --markdown` and the TUI."""

from __future__ import annotations

from .model import Model, Req
from .questions import Question
from .store import Unit


def _meta(m: Model, r: Req) -> list[str]:
    meta = []
    if r.rationale:
        meta.append(f"*Rationale:* {r.rationale}")
    if r.satisfies:
        meta.append(f"*Satisfies:* {', '.join(r.satisfies)}")
    if r.topics:
        meta.append("*Topic:* " + ", ".join(f"{t} {m.topics.get(t, '?')}" for t in r.topics))
    if r.source:
        meta.append(f"*Source:* {r.source}")
    for k, v in r.extra.items():
        meta.append(f"*{k.capitalize()}:* {v}")
    bits = []
    if r.verification:
        v = m.cfg.verification.get(r.verification)
        bits.append(f"*Verification:* {r.verification}" + (f" — {v.name}" if v else ""))
    if r.status:
        bits.append(f"*Status:* {r.status}")
    if r.security:
        bits.append("*Security relevant*")
    if bits:
        meta.append(" · ".join(bits))
    return meta


def requirement(m: Model, r: Req, heading: str = "##", chain: bool = False) -> str:
    out = [f"{heading} {r.id}" + (f" — {r.title}" if r.title else ""), "", r.statement, ""]
    if r.detail:
        out += [r.detail, ""]
    meta = _meta(m, r)
    if meta:
        out += ["  \n".join(meta), ""]
    if chain:
        up = [f"- {t} — {m.reqs[t].label if t in m.reqs else '(undefined)'}" for t in r.satisfies]
        down = [f"- {t} — {m.reqs[t].label}" for t in m.satisfied_by.get(r.id, [])]
        out += ["**Satisfies**", ""] + (up or ["- nothing"]) + [""]
        out += ["**Satisfied by**", ""] + (down or ["- nothing yet"]) + [""]
        refs = m.refs_for(r.id)
        if refs:
            out += ["**References**", ""]
            out += [f"- `{x.file}:{x.line}` {'test' if x.is_test else 'code'} — {x.note}" for x in refs]
            out.append("")
        out.append(f"`{r.file}:{r.line}`")
    return "\n".join(out).rstrip() + "\n"


def document(m: Model, unit: Unit) -> str:
    out = [f"# {unit.title}", ""]
    if unit.description:
        out += [unit.description, ""]
    for e in m.document(unit):
        if e["type"] == "section":
            s = e["section"]
            out += [f"{'#' * min(e['depth'] + 1, 6)} {e['number']} {s.title}", ""]
            if s.description:
                out += [s.description, ""]
        else:
            out += [requirement(m, e["req"], heading="######")]
    return "\n".join(out).rstrip() + "\n"


def question(q: Question, topic_title: str) -> str:
    out = [f"## {q.id} — {q.title}", "", f"*Topic {q.topic} — {topic_title}*", "",
           "**Question**", "", q.question or "—", "",
           "**Answer**", "", q.answer or "*Open.*", ""]
    if q.blocks:
        out += ["**Blocks**", "", q.blocks, ""]
    return "\n".join(out)
