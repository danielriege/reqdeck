"""The requirement model: everything loaded, linked and queryable.

    from tool.config import find_root, load
    from tool.model import Model

    m = Model.load(load(find_root()))
    m.reqs["TSR_009"].statement
    m.up("ICD_BUS_014")         # what it satisfies, transitively
    m.down("TSR_009")           # what satisfies it, transitively
    m.covering_refs("TSR_009")  # markers on it or on anything beneath it

Only `satisfies` is ever written, pointing one level up. The reverse direction
is derived here, so the two can never disagree.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import markers, questions, store
from .config import STATUS, Config
from .markers import Ref
from .store import Unit

SPLIT = re.compile(r"[\s,;]+")
NONE = {"", "—", "-"}


def split(cell: str) -> list[str]:
    return [t for t in SPLIT.split(cell.strip()) if t and t not in NONE]


@dataclass
class Req:
    id: str
    kind: str
    unit: str
    prefix: str
    title: str = ""
    statement: str = ""
    rationale: str = ""
    satisfies: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    source: str = ""
    verification: str = ""
    status: str = ""
    #: "Yes" where the requirement carries a security property. Absent means
    #: not security relevant, so nothing is written on the majority.
    security: str = ""
    section: str = ""
    #: Columns reqkit does not interpret, kept as they are.
    extra: dict[str, str] = field(default_factory=dict)
    #: Multi-line markdown from the unit's details file.
    detail: str = ""
    file: str = ""
    line: int = 0

    @property
    def label(self) -> str:
        if self.title:
            return self.title
        s = self.statement
        return s if len(s) <= 72 else s[:71] + "…"

    def to_dict(self) -> dict:
        return asdict(self)


class Model:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.units: list[Unit] = []
        self.reqs: dict[str, Req] = {}
        self.refs: list[Ref] = []
        self.topics: dict[str, str] = {}
        self.questions: list[questions.Question] = []
        #: Problems found while loading, reported by `check`.
        self.load_problems: list[str] = []
        self.satisfied_by: dict[str, list[str]] = {}

    # ---------------------------------------------------------------- loading

    @classmethod
    def load(cls, cfg: Config, scan: bool = True) -> "Model":
        m = cls(cfg)
        m.topics, m.questions = questions.load(cfg.questions)
        try:
            m.units = store.units(cfg.requirements)
        except store.StoreError as e:
            m.load_problems.append(str(e))
        for u in m.units:
            m._load_unit(u)
        if scan:
            m.refs = markers.scan(cfg)
        m.relink()
        return m

    def _load_unit(self, u: Unit) -> None:
        try:
            rows = store.read_rows(u)
        except store.StoreError as e:
            self.load_problems.append(str(e))
            return
        rel = self.cfg.rel(u.csv_path)
        if "id" not in u.header:
            self.load_problems.append(f"{rel}: header has no `id` column")
            return
        extras = [c for c in u.header if c not in store.STANDARD]
        for row in rows:
            v = row.values
            rid = v["id"].strip()
            if rid in self.reqs:
                other = self.reqs[rid]
                self.load_problems.append(f"duplicate id {rid} ({other.file}:{other.line}, {rel}:{row.line})")
                continue
            prefix = next((p for p in u.prefixes if rid.startswith(p)), "")
            self.reqs[rid] = Req(
                id=rid, kind=u.level, unit=u.stem, prefix=prefix,
                title=v.get("title", "").strip(), statement=v.get("statement", "").strip(),
                rationale=v.get("rationale", "").strip(),
                satisfies=split(v.get("satisfies", "")), topics=split(v.get("topic", "")),
                source=v.get("source", "").strip(), verification=v.get("verification", "").strip(),
                status=v.get("status", "").strip(), security=v.get("security", "").strip(),
                section=v.get("section", "").strip(),
                extra={c: v[c] for c in extras if v.get(c, "").strip()},
                file=rel, line=row.line,
            )
        for rid, text, line in store.read_details(u):
            r = self.reqs.get(rid)
            if r is None or r.unit != u.stem:
                self.load_problems.append(
                    f"{self.cfg.rel(u.details_path)}:{line}: detail for {rid}, "
                    f"which is not a requirement in {u.csv_path.name}")
            elif r.detail:
                self.load_problems.append(f"{self.cfg.rel(u.details_path)}:{line}: second detail for {rid}")
            else:
                r.detail = text

    def relink(self) -> None:
        self.satisfied_by = {k: [] for k in self.reqs}
        for r in self.reqs.values():
            for target in r.satisfies:
                self.satisfied_by.setdefault(target, []).append(r.id)

    # ---------------------------------------------------------------- queries

    def unit(self, name: str) -> Unit | None:
        """A unit by file stem or by prefix."""
        name_u = name.upper().rstrip("_-")
        return next((u for u in self.units
                     if u.stem == name or name_u in (p.upper() for p in u.prefixes)), None)

    def level_order(self, kind: str) -> int:
        kinds = [lv.kind for lv in self.cfg.levels]
        return kinds.index(kind) if kind in kinds else len(kinds)

    def sort_key(self, r: Req):
        num = re.search(r"(\d+)$", r.id)
        return (self.level_order(r.kind), r.prefix, int(num.group(1)) if num else 0, r.id)

    def refs_for(self, rid: str) -> list[Ref]:
        return [r for r in self.refs if r.id == rid]

    def up(self, rid: str, _seen=None) -> list[str]:
        """Transitive closure of what `rid` satisfies, nearest first."""
        _seen = _seen if _seen is not None else set()
        out = []
        r = self.reqs.get(rid)
        for t in (r.satisfies if r else []):
            if t in _seen:
                continue
            _seen.add(t)
            out.append(t)
            out += self.up(t, _seen)
        return out

    def down(self, rid: str, _seen=None) -> list[str]:
        """Transitive closure of what satisfies `rid`."""
        _seen = _seen if _seen is not None else set()
        out = []
        for s in self.satisfied_by.get(rid, []):
            if s in _seen:
                continue
            _seen.add(s)
            out.append(s)
            out += self.down(s, _seen)
        return out

    def covering_refs(self, rid: str) -> list[Ref]:
        """Refs on this requirement or on anything that satisfies it.

        A test against a low-level requirement also verifies everything that
        requirement satisfies, which is the point of the chain.
        """
        ids = {rid} | set(self.down(rid))
        return [r for r in self.refs if r.id in ids]

    def code_bearing(self, rid: str) -> bool:
        r = self.reqs.get(rid)
        u = self.unit(r.unit) if r else None
        return bool(u and u.code)

    def automated(self, r: Req) -> bool:
        v = self.cfg.verification.get(r.verification)
        return bool(v and v.automated)

    def reviewed(self, r: Req) -> bool:
        lv = self.cfg.level(r.kind)
        return lv.reviewed if lv else True

    def traced(self, r: Req) -> bool:
        lv = self.cfg.level(r.kind)
        return lv.traced if lv else True

    def next_id(self, prefix: str) -> str:
        unit = self.unit(prefix)
        lv = self.cfg.level(unit.level) if unit else None
        sep, digits = (lv.separator, lv.digits) if lv else ("_", 3)
        pat = re.compile(re.escape(prefix + sep) + r"(\d+)$")
        nums = [int(mm.group(1)) for rid in self.reqs if (mm := pat.match(rid))]
        return f"{prefix}{sep}{(max(nums) if nums else 0) + 1:0{digits}d}"

    # ---------------------------------------------------------------- reports

    def gaps(self) -> dict:
        g = {"dangling": [], "orphans": [], "unsatisfied": [], "untested": [],
             "uncoded": [], "not_accepted": []}
        parents = self.cfg.parent_kinds
        for r in self.reqs.values():
            lv = self.cfg.level(r.kind)
            for t in r.satisfies:
                if t not in self.reqs:
                    g["dangling"].append({"id": r.id, "missing": t})
            if lv and lv.satisfies and not r.satisfies:
                g["orphans"].append(r.id)
            if r.kind in parents and not self.satisfied_by.get(r.id):
                g["unsatisfied"].append(r.id)
            if not self.reviewed(r):
                continue
            if self.automated(r) and not [x for x in self.covering_refs(r.id) if x.is_test]:
                g["untested"].append(r.id)
            if self.code_bearing(r.id) and not [x for x in self.refs_for(r.id) if not x.is_test]:
                g["uncoded"].append(r.id)
            if r.status != "Accepted":
                g["not_accepted"].append(r.id)
        for k in g:
            if k != "dangling":
                g[k].sort(key=lambda rid: self.sort_key(self.reqs[rid]))
        return g

    def problems(self) -> list[str]:
        """Everything `check` fails on."""
        cfg = self.cfg
        out = list(self.load_problems)
        kinds = {lv.kind for lv in cfg.levels}

        homes: dict[str, str] = {}
        for u in self.units:
            rel = cfg.rel(u.toml_path)
            if u.level not in kinds:
                out.append(f"{rel}: level {u.level!r} is not a level in {cfg.root.name}/.reqkit.toml")
            if not u.prefixes:
                out.append(f"{rel}: no prefix")
            for p in u.prefixes:
                if p in homes:
                    out.append(f"prefix {p} is declared by both {homes[p]} and {rel} — "
                               f"one prefix belongs in one unit")
                homes[p] = rel
            keys = set()
            for s in u.sections:
                if not s.key or not s.title:
                    out.append(f"{rel}: a section needs both key and title")
                if s.key in keys:
                    out.append(f"{rel}: section {s.key} declared twice")
                if s.parent and s.parent not in keys:
                    out.append(f"{rel}: section {s.key} comes before its parent {s.parent}, "
                               f"or its parent is missing")
                keys.add(s.key)
            if u.header and u.csv_path.exists():
                try:
                    rows = store.read_rows(u)
                    if not store.is_canonical(u, rows):
                        out.append(f"{cfg.rel(u.csv_path)}: not in canonical form — run `req fmt`")
                except store.StoreError:
                    pass

        for r in self.reqs.values():
            u = self.unit(r.unit)
            lv = cfg.level(r.kind)
            where = f"{r.id}"
            if u and not r.prefix:
                out.append(f"{where}: does not start with a prefix of {u.csv_path.name} "
                           f"({', '.join(u.prefixes)})")
            elif lv and u:
                if not re.fullmatch(re.escape(r.prefix + lv.separator) + r"\d{%d}" % lv.digits, r.id):
                    out.append(f"{where}: expected {r.prefix}{lv.separator} and {lv.digits} digits")
            if not r.statement:
                out.append(f"{where}: missing statement")
            if self.reviewed(r):
                for fld in ("source", "verification", "status"):
                    if not getattr(r, fld):
                        out.append(f"{where}: missing {fld}")
                if r.verification and r.verification not in cfg.verification:
                    out.append(f"{where}: bad verification {r.verification!r} — expected one of "
                               f"{', '.join(cfg.verification)}")
                if r.status and r.status not in STATUS:
                    out.append(f"{where}: bad status {r.status!r} — expected one of {', '.join(STATUS)}")
            if r.security and r.security != "Yes":
                out.append(f"{where}: security is {r.security!r} — the only value is Yes; "
                           f"leave it empty where a requirement is not security relevant")
            for t in r.satisfies:
                tr = self.reqs.get(t)
                if tr is None:
                    out.append(f"{where}: satisfies undefined {t}")
                elif lv and tr.kind not in lv.satisfies:
                    allowed = ", ".join(lv.satisfies) or "nothing — it is a top level"
                    out.append(f"{where}: satisfies {t}, a {tr.kind}; a {r.kind} satisfies {allowed}")
            if lv and lv.topic and not r.topics:
                out.append(f"{where}: missing topic")
            for t in r.topics:
                if t not in self.topics:
                    out.append(f"{where}: topic {t} is not a topic in "
                               f"{cfg.rel(cfg.questions) if cfg.questions else 'OPEN-QUESTIONS'}")
            if r.section and u and not u.section(r.section):
                out.append(f"{where}: section {r.section!r} is not declared in {u.toml_path.name}")

        mk = cfg.markers
        for ref in self.refs:
            at = f"{ref.file}:{ref.line}"
            r = self.reqs.get(ref.id)
            if r is None:
                out.append(f"{at}: @REQ_REF to undefined {ref.id}")
            elif not self.traced(r):
                below = ", ".join(self.satisfied_by.get(ref.id, [])) or "nothing yet"
                out.append(f"{at}: @REQ_REF({ref.id}) names a {r.kind}, which is traced through "
                           f"what satisfies it ({below}) — reference that instead")
            # One ID per marker.  A marker naming three requirements reads as
            # one obligation and hides that the three may have diverged.
            if ref.extra_ids:
                out.append(f"{at}: @REQ_REF names {len(ref.extra_ids) + 1} requirements "
                           f"({ref.id}, {', '.join(ref.extra_ids)}) — one per marker, one line each")
            if not ref.note:
                out.append(f"{at}: @REQ_REF({ref.id}) has no description — "
                           f"add a few words on what the requirement asks for")
            if not ref.is_test and mk.interface_suffixes and \
                    Path(ref.file).stem.endswith(tuple(mk.interface_suffixes)):
                out.append(f"{at}: @REQ_REF({ref.id}) is on an interface — "
                           f"put it on the code that implements it")
            if not ref.is_test and mk.declaration_extensions and \
                    Path(ref.file).suffix not in mk.declaration_extensions:
                out.append(f"{at}: @REQ_REF({ref.id}) is in an implementation file — "
                           f"markers belong on the declaration, or in a test")
        return out

    def status_tally(self) -> dict[str, int]:
        counts = {k: 0 for k in STATUS}
        counts["missing"] = 0
        for r in self.reqs.values():
            if not self.reviewed(r):
                continue
            counts[r.status if r.status in STATUS else "missing"] += 1
        return counts

    # ---------------------------------------------------------------- document

    def document(self, unit: Unit) -> list[dict]:
        """A unit as a document, in reading order.

        A flat list of entries, each either a section heading or a requirement,
        with its depth. Requirements with no section come first, as the body
        text before the first heading; within a section they follow ID order.
        """
        mine = sorted((r for r in self.reqs.values() if r.unit == unit.stem), key=self.sort_key)
        by_section: dict[str, list[Req]] = {}
        for r in mine:
            key = r.section if unit.section(r.section) else ""
            by_section.setdefault(key, []).append(r)
        numbers = unit.numbering()
        out: list[dict] = [{"type": "req", "depth": 0, "req": r} for r in by_section.get("", [])]
        for s in unit.sections:
            depth = s.key.count(".") + 1
            out.append({"type": "section", "depth": depth, "section": s, "number": numbers[s.key]})
            out += [{"type": "req", "depth": depth, "req": r} for r in by_section.get(s.key, [])]
        return out
