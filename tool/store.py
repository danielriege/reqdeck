"""The files requirements live in.

One *unit* per prefix, as three files side by side in the requirements folder:

    firmware-node.csv          the requirements, one row each, ordered by ID
    firmware-node.toml         the unit: level, prefix, title, sections
    firmware-node.details.md   optional multi-line detail, one `## <ID>` each

Rows are only ever appended, so a row's line number is as permanent as its ID.
Where a requirement is *shown* is its `section`, a stable key declared in the
`.toml`; section numbers are derived from declaration order when rendering, so
inserting a section renumbers the document without touching a single row.
"""

from __future__ import annotations

import csv
import io
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

#: Columns reqkit understands, in the order a new file gets them. Any other
#: column is kept, shown, and otherwise left alone.
STANDARD = ["id", "section", "title", "statement", "rationale", "satisfies", "topic",
            "source", "verification", "status", "security"]
STORY_COLUMNS = ["id", "section", "statement"]

DETAIL_HEADING = re.compile(r"^## (\S+)[ \t]*$", re.M)


@dataclass
class Section:
    key: str
    title: str
    description: str = ""

    @property
    def parent(self) -> str:
        return self.key.rpartition(".")[0]


@dataclass
class Unit:
    stem: str
    level: str
    prefixes: list[str]
    title: str
    description: str
    code: bool
    sections: list[Section]
    csv_path: Path
    toml_path: Path
    details_path: Path
    header: list[str] = field(default_factory=list)

    def section(self, key: str) -> Section | None:
        return next((s for s in self.sections if s.key == key), None)

    def numbering(self) -> dict[str, str]:
        """Section key to its displayed number, from declaration order."""
        out: dict[str, str] = {}
        counters: dict[str, int] = {}
        for s in self.sections:
            counters[s.parent] = counters.get(s.parent, 0) + 1
            base = out.get(s.parent, "")
            out[s.key] = f"{base}.{counters[s.parent]}" if base else str(counters[s.parent])
        return out


@dataclass
class Row:
    values: dict[str, str]
    line: int


class StoreError(Exception):
    pass


def units(req_dir: Path) -> list[Unit]:
    out = []
    for toml_path in sorted(req_dir.glob("*.toml")):
        stem = toml_path.stem
        try:
            meta = tomllib.loads(toml_path.read_text())
        except tomllib.TOMLDecodeError as e:
            raise StoreError(f"{toml_path}: {e}") from e
        prefixes = meta.get("prefixes") or ([meta["prefix"]] if "prefix" in meta else [])
        sections = [Section(s.get("key", ""), s.get("title", ""), s.get("description", "").strip())
                    for s in meta.get("sections", [])]
        out.append(Unit(
            stem=stem, level=meta.get("level", ""), prefixes=list(prefixes),
            title=meta.get("title", stem), description=meta.get("description", "").strip(),
            code=bool(meta.get("code", False)), sections=sections,
            csv_path=req_dir / f"{stem}.csv", toml_path=toml_path,
            details_path=req_dir / f"{stem}.details.md",
        ))
    return out


def read_rows(unit: Unit) -> list[Row]:
    if not unit.csv_path.exists():
        raise StoreError(f"{unit.toml_path.name} has no {unit.csv_path.name} beside it")
    with unit.csv_path.open(newline="") as f:
        reader = csv.reader(f)
        try:
            unit.header = next(reader)
        except StopIteration:
            raise StoreError(f"{unit.csv_path.name} is empty — it needs at least a header row")
        rows = []
        for raw in reader:
            if not any(c.strip() for c in raw):
                continue
            if len(raw) != len(unit.header):
                raise StoreError(f"{unit.csv_path.name}:{reader.line_num}: {len(raw)} fields, "
                                 f"header has {len(unit.header)}")
            rows.append(Row(dict(zip(unit.header, raw)), reader.line_num))
    return rows


def read_details(unit: Unit) -> list[tuple[str, str, int]]:
    """(id, markdown, line) for every `## <ID>` block in the details file."""
    if not unit.details_path.exists():
        return []
    text = unit.details_path.read_text()
    heads = list(DETAIL_HEADING.finditer(text))
    out = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        out.append((h.group(1), text[h.end():end].strip("\n"), text[:h.start()].count("\n") + 1))
    return out


def render_csv(header: list[str], rows: list[dict[str, str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow([r.get(c, "") for c in header])
    return buf.getvalue()


def write_rows(unit: Unit, rows: list[dict[str, str]]) -> None:
    unit.csv_path.write_text(render_csv(unit.header, rows))


def append_row(unit: Unit, row: dict[str, str]) -> int:
    """Append one row and return its line number."""
    text = unit.csv_path.read_text()
    if text and not text.endswith("\n"):
        text += "\n"
    line = render_csv(unit.header, [row]).split("\n", 1)[1]
    unit.csv_path.write_text(text + line)
    return text.count("\n") + 1


def is_canonical(unit: Unit, rows: list[Row]) -> bool:
    """Whether the file is byte-for-byte what reqkit itself would write."""
    return unit.csv_path.read_text() == render_csv(unit.header, [r.values for r in rows])


def toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def create_unit(req_dir: Path, stem: str, level: str, prefixes: list[str], title: str,
                code: bool, columns: list[str]) -> Unit:
    csv_path, toml_path = req_dir / f"{stem}.csv", req_dir / f"{stem}.toml"
    for p in (csv_path, toml_path):
        if p.exists():
            raise StoreError(f"{p} already exists")
    req_dir.mkdir(parents=True, exist_ok=True)
    prefix_line = (f"prefix = {toml_str(prefixes[0])}" if len(prefixes) == 1
                   else f"prefixes = [{', '.join(toml_str(p) for p in prefixes)}]")
    lines = [f"level = {toml_str(level)}", prefix_line, f"title = {toml_str(title)}"]
    if code:
        lines.append("code = true")
    lines += ['description = """', '"""', "",
              "# Sections, in the order they are shown. A key with a dot nests under",
              "# the key before it: `power.bus` is a subsection of `power`.",
              "#", "# [[sections]]", '# key = "power"', '# title = "Power"', ""]
    toml_path.write_text("\n".join(lines))
    csv_path.write_text(render_csv(columns, []))
    return next(u for u in units(req_dir) if u.stem == stem)
