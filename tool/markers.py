"""`@REQ_REF` markers in source and tests.

    @REQ_REF(TSSR_FWN_023) no code above the abstraction may name a vendor register

One ID per marker, then a few words on what that requirement asks for.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .config import Config

REQ_REF = re.compile(r"@REQ_REF\(\s*([^)]*?)\s*\)[ \t]*(.*)")
SPLIT = re.compile(r"[\s,;]+")
#: What an ID looks like: a prefix, a separator, a number. Anything else in the
#: parentheses, such as `@REQ_REF(<ID>)` in a comment explaining markers, is
#: not a marker.
LOOKS_LIKE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_]*[_-]\d+")


@dataclass
class Ref:
    id: str
    file: str
    line: int
    is_test: bool
    note: str = ""
    #: Only ever populated by a malformed marker naming several IDs.
    extra_ids: tuple[str, ...] = ()


def scan(cfg: Config) -> list[Ref]:
    mk = cfg.markers
    skip = set(mk.skip)
    exts = set(mk.extensions)
    req_dir = cfg.requirements.resolve()
    found: list[Ref] = []
    for dirpath, dirnames, filenames in os.walk(cfg.root):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames
                             if d not in skip and not d.startswith(".")
                             and (here / d).resolve() != req_dir)
        for name in sorted(filenames):
            if Path(name).suffix not in exts:
                continue
            p = here / name
            rel = str(p.relative_to(cfg.root))
            low = rel.lower()
            is_test = any(t.lower() in low for t in mk.test_paths)
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            for m in REQ_REF.finditer(text):
                ids = [t for t in SPLIT.split(m.group(1)) if t]
                if not ids or not LOOKS_LIKE_ID.fullmatch(ids[0]):
                    continue
                line = text[: m.start()].count("\n") + 1
                note = m.group(2).strip().rstrip("*/").strip()
                found.append(Ref(ids[0], rel, line, is_test, note, tuple(ids[1:])))
    return found
