"""Writing requirements. Shared by the CLI and the TUI, so both obey the same rules.

The status rule is enforced here rather than trusted to the caller: `add`
writes Proposed and nothing else, `edit` turns an Accepted requirement into
Reopened when it changes, and only `accept` — reached from the TUI, by a
person — ever writes Accepted.
"""

from __future__ import annotations

from . import store
from .model import Model, split

#: Fields `edit` may change. Status is not among them.
EDITABLE = ("title", "statement", "rationale", "satisfies", "topic", "source",
            "verification", "security", "section")


class OpError(Exception):
    pass


def _normalise(m: Model, rid: str, kind: str, unit, fields: dict[str, str]) -> None:
    lv = m.cfg.level(kind)
    if fields.get("verification"):
        fields["verification"] = fields["verification"].upper()
        if fields["verification"] not in m.cfg.verification:
            raise OpError(f"Bad verification {fields['verification']!r} — one of "
                          f"{', '.join(m.cfg.verification)}")
    if "topic" in fields:
        topics = [t.zfill(2) for t in split(fields["topic"])]
        for t in topics:
            if t not in m.topics:
                raise OpError(f"{rid}: topic {t} is not a topic in OPEN-QUESTIONS")
        fields["topic"] = " ".join(topics)
    if "satisfies" in fields:
        sat = split(fields["satisfies"])
        for t in sat:
            tr = m.reqs.get(t)
            if tr is None:
                raise OpError(f"{rid}: satisfies undefined {t}")
            if lv and tr.kind not in lv.satisfies:
                raise OpError(f"{rid}: a {kind} cannot satisfy {t}, a {tr.kind}")
        fields["satisfies"] = " ".join(sat)
    if fields.get("section") and not unit.section(fields["section"]):
        keys = ", ".join(s.key for s in unit.sections) or "none declared"
        raise OpError(f"{rid}: section {fields['section']!r} is not in {unit.toml_path.name} ({keys})")
    if "security" in fields:
        fields["security"] = "Yes" if fields["security"].strip().lower() in ("yes", "y", "true", "1") else ""
    missing = [c for c, v in fields.items() if v and c not in unit.header]
    if missing:
        raise OpError(f"{unit.csv_path.name} has no column for {', '.join(missing)}")


def add(m: Model, prefix: str, fields: dict[str, str]) -> tuple[str, str, int]:
    """Allocate the next ID under `prefix` and append it. Returns (id, file, line)."""
    unit = m.unit(prefix)
    if unit is None:
        raise OpError(f"No unit holds {prefix}. A new prefix is a new unit of the design — "
                      f"create it deliberately with `reqdeck unit`, then add to it.")
    want = prefix.upper().rstrip("_-")
    exact = next((p for p in unit.prefixes if p.upper() == want), unit.prefixes[0])
    lv = m.cfg.level(unit.level)
    rid = m.next_id(exact)
    store.read_rows(unit)

    fields = {k: (v or "").strip() for k, v in fields.items() if k != "status"}
    _normalise(m, rid, unit.level, unit, fields)
    if not fields.get("statement"):
        raise OpError(f"{rid}: a statement is required")
    if lv and lv.topic and not fields.get("topic"):
        raise OpError(f"{rid}: a topic is required on {lv.kind}")
    if not lv or lv.reviewed:
        if not fields.get("source"):
            raise OpError(f"{rid}: a source is required — what decided it")
        if not fields.get("verification"):
            raise OpError(f"{rid}: a verification method is required")
        fields["status"] = "Proposed"
    line = store.append_row(unit, {"id": rid, **fields})
    return rid, m.cfg.rel(unit.csv_path), line


def edit(m: Model, rid: str, changes: dict[str, str]) -> tuple[list[str], bool]:
    """Change fields of an existing requirement. Returns (changed, reopened).

    A change to an Accepted requirement makes it Reopened, since what the user
    agreed to is no longer what is written."""
    r = m.reqs.get(rid)
    if r is None:
        raise OpError(f"No such requirement: {rid}")
    if "status" in changes or "id" in changes:
        raise OpError("id and status are not editable")
    unit = m.unit(r.unit)
    rows = store.read_rows(unit)
    changes = {k: v.strip() for k, v in changes.items()}
    if not changes:
        raise OpError("Nothing to change.")
    _normalise(m, rid, r.kind, unit, changes)
    row = next(x for x in rows if x.values["id"].strip() == rid)
    before = dict(row.values)
    row.values.update(changes)
    if row.values == before:
        raise OpError(f"{rid}: already says that.")
    reopened = before.get("status") == "Accepted"
    if reopened:
        row.values["status"] = "Reopened"
    store.write_rows(unit, [x.values for x in rows])
    return sorted(k for k in changes if before.get(k, "") != row.values[k]), reopened


def accept(m: Model, rid: str) -> None:
    """Mark a requirement Accepted.

    Only ever called on a person's explicit action in the TUI. No CLI command
    reaches it: an agent that accepts its own work erases the one record of
    what a human has reviewed."""
    r = m.reqs.get(rid)
    if r is None or not m.reviewed(r):
        raise OpError(f"{rid} carries no review status")
    unit = m.unit(r.unit)
    rows = store.read_rows(unit)
    row = next(x for x in rows if x.values["id"].strip() == rid)
    row.values["status"] = "Accepted"
    store.write_rows(unit, [x.values for x in rows])
