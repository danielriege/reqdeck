"""Markdown views of the model, shared by `reqdeck doc --markdown` and the TUI."""

from __future__ import annotations

import functools
from pathlib import Path

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


def excerpt(root: Path, file: str, line: int, before: int = 3, after: int = 8) -> list[tuple[int, str]]:
    """Numbered source lines around `line` of `file`, which is relative to `root`."""
    try:
        lines = (root / file).read_text(errors="replace").splitlines()
    except OSError:
        return []
    start = max(1, line - before)
    return [(n, lines[n - 1]) for n in range(start, min(len(lines), line + after) + 1)]


COMMENT = ("//", "/*", "*", "#", '"""', "'''", "--", "///")


def origin(root: Path, file: str, line: int) -> str:
    """What the marker at `line` is attached to: the first line of code after its
    comment, or "file header" when the comment is the file's own @file block."""
    try:
        mtime = (root / file).stat().st_mtime_ns
    except OSError:
        return ""
    _seen.add((root, file, line, mtime))
    return _origin(root, file, line, mtime)


def origin_cached(root: Path, file: str, line: int) -> bool:
    """Whether `origin` would answer without reading the file."""
    try:
        mtime = (root / file).stat().st_mtime_ns
    except OSError:
        return True
    key = (root, file, line, mtime)
    return key in _seen


_seen: set = set()


@functools.lru_cache(maxsize=4096)
def _origin(root: Path, file: str, line: int, mtime: int) -> str:
    """`origin`, cached until the file changes."""
    try:
        lines = (root / file).read_text(errors="replace").splitlines()
    except OSError:
        return ""
    # The comment block the marker sits in, upwards then downwards.
    start = line - 1
    while start > 0 and lines[start - 1].strip().startswith(COMMENT):
        start -= 1
    block = lines[start:line]
    end = line
    while end < len(lines) and (not lines[end].strip() or lines[end].strip().startswith(COMMENT)):
        block.append(lines[end])
        end += 1
    if any("@file" in b for b in block):
        return "file header"
    code = lines[end].strip() if end < len(lines) else ""
    code = code.rstrip("{").rstrip()
    return code if len(code) <= 72 else code[:71] + "…"
