"""`reqdeck init`: set a project up, asking as it goes.

Asks everything first, checks that none of the files it would create exist,
shows a summary, and writes only once that is confirmed. A failure while
writing removes what this run created, so a project is either set up or
untouched. An existing OPEN-QUESTIONS.md and existing skill folders are kept.
"""

from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from . import store
from .config import CONFIG_NAME

PACKAGE = Path(__file__).resolve().parent
PREFIX_RE = re.compile(r"[A-Z][A-Z0-9]*")
PREFIX_HINT = "capitals and digits, starting with a letter"
PATH_RE = re.compile(r"[^/\s][^\s]*")
STEM_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
SKILL_DIRS = (".claude/skills", ".agents/skills")

SHAPES = """\
Requirements form levels, each satisfying the one above it, rooted in user
stories. Pick the shape that fits — it can be edited in .reqdeck.toml later.

  1) Stories → System → Sub-system + Interface
     A product of several parts that talk to each other: firmware, hardware,
     an app. Interface requirements describe behaviour at a boundary.
  2) Stories → System → Sub-system
     Several parts, no boundary worth specifying on its own.
  3) Stories → Requirements
     One app or one component.
"""


class Abort(Exception):
    """Stop before anything is written."""


def skills_source() -> Path:
    """The skills shipped with reqdeck: inside the package when installed, at
    the repository root in a checkout."""
    for p in (PACKAGE / "skills", PACKAGE.parent / "skills"):
        if p.is_dir():
            return p
    raise FileNotFoundError("reqdeck's skills are missing from this installation")


def _ask(prompt: str, default: str = "", pattern: re.Pattern | None = None, hint: str = "") -> str:
    while True:
        try:
            answer = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
        except EOFError:
            raise Abort("input ended before setup was complete — nothing written") from None
        answer = answer or default
        if pattern is None or pattern.fullmatch(answer):
            return answer
        print(f"  {hint or 'not a valid answer'}", file=sys.stderr)


def _yes(prompt: str, default: bool) -> bool:
    try:
        answer = input(f"{prompt} [{'Y/n' if default else 'y/N'}]: ").strip()
    except EOFError:
        raise Abort("input ended before setup was complete — nothing written") from None
    return answer.lower().startswith("y") if answer else default


@dataclass
class UnitPlan:
    stem: str
    level: str
    prefixes: list[str]
    title: str
    code: bool


def _ask_prefix(prompt: str, default: str, taken: list[str], what: str) -> str:
    while True:
        p = _ask(prompt, default, PREFIX_RE, PREFIX_HINT)
        if p not in taken:
            return p
        print(f"  must differ from {what}", file=sys.stderr)


def _ask_units(level: str, what: str, units: list[UnitPlan]) -> None:
    print(f"\n{what} units — one per part. Blank code to finish.")
    while True:
        code = _ask("  Unit code (e.g. FW, APP, BUS)", "", re.compile(r"([A-Za-z][A-Za-z0-9]*)?"),
                    "letters and digits, starting with a letter").upper()
        if not code:
            return
        prefix = f"{level}_{code}"
        if any(prefix in u.prefixes for u in units):
            print(f"  {prefix} is already a unit", file=sys.stderr)
            continue
        while True:
            stem = _ask("  File name", code.lower(), STEM_RE, "lower case letters, digits and hyphens")
            if all(stem != u.stem for u in units):
                break
            print(f"  {stem} is already taken", file=sys.stderr)
        title = _ask("  Title", code)
        units.append(UnitPlan(stem, level, [prefix], title, _yes("  Implemented in code?", True)))


def _config(shape: str, req_dir: str, questions: str, sys_: str, sub: str, icd: str,
            split_tests: bool, headers: bool) -> str:
    out = ["# reqdeck configuration — https://github.com/danielriege/reqdeck", "",
           f'requirements = "{req_dir}"', f'questions = "{questions}"', "",
           "# Most abstract first. `satisfies` names the levels a requirement may point at.",
           "# `satisfied`, `code` and `test` (true or false) set what a level needs before it is",
           "# done; unset, they follow from `satisfies`, the unit's `code` and the verification.",
           "# `code` and `test` are met by a marker on the requirement itself, or, with `satisfied`,",
           "# by markers on every requirement beneath it; with `code`, its own marker also counts",
           "# for `satisfied`. See the README.", "",
           '[[levels]]\nkind = "STORY"\ntitle = "User story"\nreviewed = false\ntraced = false\n'
           'separator = "-"\ndigits = 2\n']
    if shape == "3":
        out.append(f'[[levels]]\nkind = "{sys_}"\ntitle = "Requirement"\nsatisfies = ["STORY"]\ntopic = true\n')
    else:
        out.append(f'[[levels]]\nkind = "{sys_}"\ntitle = "System requirement"\nsatisfies = ["STORY"]\n'
                   f'topic = true\ntraced = false\n')
        if shape == "1":
            out.append(f'[[levels]]\nkind = "{icd}"\ntitle = "Interface requirement"\nsatisfies = ["{sys_}"]\n')
            out.append(f'[[levels]]\nkind = "{sub}"\ntitle = "Sub-system requirement"\n'
                       f'satisfies = ["{sys_}", "{icd}"]\ntopic = true\n')
        else:
            out.append(f'[[levels]]\nkind = "{sub}"\ntitle = "Sub-system requirement"\n'
                       f'satisfies = ["{sys_}"]\ntopic = true\n')
    methods = [("A", "Analysis", "Calculation, modelling or simulation shows the requirement is met.", False),
               ("I", "Inspection", "Examination of the design, drawings or source, without operating it.", False),
               ("D", "Demonstration", "Operate the system and observe the expected behaviour.", False)]
    if split_tests:
        methods += [("U", "Unit test", "Automated, on a development machine, with the hardware mocked.", True),
                    ("S", "Integration test", "Automated, on the real target.", True),
                    ("M", "Manual test", "Measured or run by a person, with instruments where needed.", False)]
    else:
        methods += [("T", "Test", "An automated test shows the requirement is met.", True)]
    for code, name, definition, automated in methods:
        out.append(f'[verification.{code}]\nname = "{name}"\ndefinition = "{definition}"'
                   + ("\nautomated = true" if automated else "") + "\n")
    out.append("[markers]")
    if headers:
        out += ['declaration_extensions = [".h", ".hpp", ".swift", ".py"]', 'interface_suffixes = ["_interface"]']
    else:
        out += ["# declaration_extensions = []   # restrict non-test markers to these file types",
                "# interface_suffixes = []       # file stems that declare an interface, never marked"]
    out += ["", "# Where the TUI opens a code or test reference. Unset: $VISUAL or $EDITOR.",
            "# [editor]", '# command = "nvim +{line} {file}"     # or "code --goto {file}:{line}"', ""]
    return "\n".join(out)


def copy_skills(root: Path, dirs: list[str], created: list[Path] | None = None,
                update: bool = False) -> tuple[list[str], list[str]]:
    """Copy reqdeck's skills into `dirs` of the project. Returns (written, kept).

    A folder that exists is kept unless `update` and it is reqdeck's own — its
    SKILL.md names the same skill — so a folder of the user's is never replaced."""
    written, kept = [], []
    for d in dirs:
        for skill in sorted(p for p in skills_source().iterdir() if p.is_dir()):
            target = root / d / skill.name
            rel = f"{d}/{skill.name}"
            if target.exists() or target.is_symlink():
                ours = (target / "SKILL.md").is_file() and \
                    f"name: {skill.name}" in (target / "SKILL.md").read_text()
                if not (update and ours and not target.is_symlink()):
                    kept.append(rel)
                    continue
                shutil.rmtree(target)
            else:
                _mkdirs(target.parent, created)
                if created is not None:
                    created.append(target)
            shutil.copytree(skill, target)
            written.append(rel)
    return written, kept


def _mkdirs(d: Path, created: list[Path] | None) -> None:
    missing = []
    while not d.exists():
        missing.append(d)
        d = d.parent
    for m in reversed(missing):
        m.mkdir()
        if created is not None:
            created.append(m)


def _rollback(created: list[Path]) -> None:
    print("init: setup failed — removing what this run created", file=sys.stderr)
    for p in reversed(created):
        if p.is_symlink() or p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p, ignore_errors=True)


def run(root: Path) -> int:
    root = root.resolve()
    if (root / CONFIG_NAME).exists():
        print(f"init: {CONFIG_NAME} already exists — this project is set up. Add a unit with\n"
              f"  reqdeck unit <file> --level <LEVEL> --prefix <PREFIX> --title <title>", file=sys.stderr)
        return 1
    try:
        plan = _questions(root)
    except Abort as e:
        print(f"init: {e}", file=sys.stderr)
        return 1
    created: list[Path] = []
    try:
        _write(root, plan, created)
    except BaseException:
        _rollback(created)
        raise
    return 0


def _questions(root: Path) -> dict:
    print(f"reqdeck setup in {root}\n\n{SHAPES}")
    shape = _ask("Shape", "1", re.compile(r"[123]"), "pick 1, 2 or 3")
    req_dir = _ask("Folder for the requirement files", "docs/requirements", PATH_RE, "a relative path without spaces")
    questions = _ask("Open questions file", "docs/OPEN-QUESTIONS.md", PATH_RE, "a relative path without spaces")
    while True:
        letters = _ask("Persona letters for user stories, space-separated (A-01, B-01, …)", "A",
                       re.compile(r"[A-Z]( [A-Z])*"), "single capital letters separated by spaces, e.g. A B C").split()
        if len(set(letters)) == len(letters):
            break
        print("  each letter once", file=sys.stderr)

    sys_, sub, icd = "TSR", "TSSR", "ICD"
    if shape == "3":
        sys_ = _ask_prefix("Requirement prefix", "REQ", letters, "the persona letters")
    else:
        sys_ = _ask_prefix("System level prefix", "TSR", letters, "the persona letters")
        sub = _ask_prefix("Sub-system level prefix", "TSSR", [sys_, *letters], f"{sys_} and the persona letters")
        if shape == "1":
            icd = _ask_prefix("Interface level prefix", "ICD", [sys_, sub, *letters],
                              f"{sys_}, {sub} and the persona letters")
    print()
    split_tests = _yes("Split testing into unit (U), integration (S) and manual (M) instead of one T?", False)
    headers = _yes("C or C++ with headers — keep markers on headers, never on .c/.cpp?", False)

    units = [UnitPlan("stories", "STORY", letters, "User stories", False)]
    if shape == "3":
        units.append(UnitPlan("requirements", sys_, [sys_], "Requirements",
                              _yes("Are the requirements implemented in code (so code must reference them)?", True)))
    else:
        units.append(UnitPlan("system", sys_, [sys_], "System requirements", False))
        _ask_units(sub, "Sub-system", units)
        if shape == "1":
            _ask_units(icd, "Interface", units)
    skill_dirs = [d for d in SKILL_DIRS if _yes(f"Copy the reqdeck skills into {d}?", True)]

    conflicts = [f"{req_dir}/{u.stem}.{ext}" for u in units for ext in ("csv", "toml", "details.md")
                 if (root / req_dir / f"{u.stem}.{ext}").exists()]
    if conflicts:
        print("\n".join(f"  {c}" for c in conflicts), file=sys.stderr)
        raise Abort("these files already exist — move them away or pick other names; nothing written")
    keep_questions = (root / questions).exists()
    if keep_questions and not re.search(r"^## Topic \d{2} — ", (root / questions).read_text(), re.M):
        print(f"warning: {questions} exists but has no\n  '## Topic NN — Title' heading, so reqdeck will "
              f"find no topics in it. It is kept as it is.", file=sys.stderr)

    print("\nAbout to create:\n  .reqdeck.toml")
    for u in units:
        print(f"  {req_dir + '/' + u.stem + '.csv':<36} {' '.join(u.prefixes):<12} {u.title}"
              f"{' (code)' if u.code else ''}")
    if not keep_questions:
        print(f"  {questions}")
    for d in skill_dirs:
        print(f"  {d}/ with the reqdeck skills")
    print()
    if not _yes("Create these?", True):
        raise Abort("nothing written")
    return dict(shape=shape, req_dir=req_dir, questions=questions, sys_=sys_, sub=sub, icd=icd,
                split_tests=split_tests, headers=headers, units=units, skill_dirs=skill_dirs,
                keep_questions=keep_questions)


def _write(root: Path, plan: dict, created: list[Path]) -> None:
    from . import config
    from .model import Model

    cfg_path = root / CONFIG_NAME
    created.append(cfg_path)
    cfg_path.write_text(_config(plan["shape"], plan["req_dir"], plan["questions"], plan["sys_"],
                                plan["sub"], plan["icd"], plan["split_tests"], plan["headers"]))
    req_dir = root / plan["req_dir"]
    _mkdirs(req_dir, created)
    for u in plan["units"]:
        created += [req_dir / f"{u.stem}.csv", req_dir / f"{u.stem}.toml"]
        level = next(lv for lv in config.load(root).levels if lv.kind == u.level)
        columns = list(store.STORY_COLUMNS) if not level.reviewed else \
            [c for c in store.STANDARD if level.topic or c != "topic"]
        store.create_unit(req_dir, u.stem, u.level, u.prefixes, u.title, u.code, columns)
    if not plan["keep_questions"]:
        q = root / plan["questions"]
        _mkdirs(q.parent, created)
        created.append(q)
        shutil.copyfile(PACKAGE / "templates" / "OPEN-QUESTIONS.md", q)
    _, kept = copy_skills(root, plan["skill_dirs"], created)

    problems = Model.load(config.load(root)).problems()
    if problems:
        raise RuntimeError("the new project does not pass check:\n" + "\n".join(problems))

    for k in kept:
        print(f"kept the existing {k} — it is not reqdeck's copy")
    print(f"""Done. Next:
  reqdeck check        validate
  reqdeck levels       the levels and units just created
  reqdeck tui          browse

Then write the product brief and start the first topics in {plan['questions']} —
the reqdeck-method skill describes how.""")
