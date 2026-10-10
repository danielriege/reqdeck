"""Project configuration: `.reqdeck.toml` in the root of the project using reqdeck.

Everything project-specific lives here — where the files are, which levels of
requirement exist, which verification methods, and how `@REQ_REF` markers are
found. The rest of the tool reads only this object.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = ".reqdeck.toml"

#: Review status. Fixed rather than configurable: it is the one signal that a
#: human has read a requirement, and only the user ever sets Accepted.
STATUS = {
    "Proposed": "written, not yet reviewed",
    "Accepted": "reviewed and agreed by the user",
    "Reopened": "was accepted, then changed; needs review again",
}

DEFAULT_VERIFICATION = {
    "A": ("Analysis", "Calculation, modelling or simulation shows the requirement is met.", False),
    "I": ("Inspection", "Examination of the design, drawings or source, without operating it.", False),
    "D": ("Demonstration", "Operate the system and observe the expected behaviour.", False),
    "T": ("Test", "An automated test shows the requirement is met.", True),
}

DEFAULT_EXTENSIONS = [".c", ".h", ".cpp", ".hpp", ".cc", ".py", ".swift", ".rs", ".go",
                      ".js", ".ts", ".kt", ".java", ".m", ".mm", ".s", ".S"]
DEFAULT_SKIP = ["docs", "node_modules", ".build", "build", "dist", "__pycache__",
                ".venv", "venv", "DerivedData", "Pods"]


class ConfigError(Exception):
    pass


@dataclass
class Level:
    kind: str
    title: str = ""
    #: Kinds this level may name in `satisfies`. Empty means a top level.
    satisfies: list[str] = field(default_factory=list)
    #: Every requirement of this level names the OPEN-QUESTIONS topic behind it.
    topic: bool = False
    #: Carries source, verification and status. False for user stories.
    reviewed: bool = True
    #: Code and tests may reference it directly. False for a level that is only
    #: ever traced through what satisfies it.
    traced: bool = True
    separator: str = "_"
    digits: int = 3


@dataclass
class Verification:
    code: str
    name: str
    definition: str
    #: Discharged by an automated test, so untraced until a test names it.
    automated: bool


@dataclass
class Markers:
    extensions: list[str] = field(default_factory=lambda: list(DEFAULT_EXTENSIONS))
    skip: list[str] = field(default_factory=lambda: list(DEFAULT_SKIP))
    #: A path containing any of these, case-insensitively, is a test.
    test_paths: list[str] = field(default_factory=lambda: ["test", "spec"])
    #: Outside tests, markers may only sit in files with these extensions.
    #: Empty allows any source file.
    declaration_extensions: list[str] = field(default_factory=list)
    #: A file whose stem ends in one of these declares an interface, which
    #: never carries a marker.
    interface_suffixes: list[str] = field(default_factory=list)


@dataclass
class Editor:
    #: Command opening a file at a line, `{file}` and `{line}` substituted:
    #: "nvim +{line} {file}", "code --goto {file}:{line}". Empty means the
    #: user's $VISUAL or $EDITOR, through a preset for the common ones.
    command: str = ""
    #: The TUI hands the terminal over until the editor exits. Unset means
    #: yes for a terminal editor and no for a windowed one.
    suspend: bool | None = None


@dataclass
class Config:
    root: Path
    requirements: Path
    questions: Path | None
    levels: list[Level]
    verification: dict[str, Verification]
    markers: Markers
    editor: Editor = field(default_factory=Editor)

    def level(self, kind: str) -> Level | None:
        return next((lv for lv in self.levels if lv.kind == kind), None)

    def rel(self, p: Path) -> str:
        return str(p.relative_to(self.root))

    @property
    def parent_kinds(self) -> set[str]:
        """Kinds something else exists to satisfy — so expected to be satisfied."""
        return {k for lv in self.levels for k in lv.satisfies}


def find_root(start: Path | None = None) -> Path | None:
    """The nearest directory holding `.reqdeck.toml`: `REQDECK_ROOT` if set,
    otherwise searched upward from the current directory."""
    env = os.environ.get("REQDECK_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    base = (start or Path.cwd()).resolve()
    for d in (base, *base.parents):
        if (d / CONFIG_NAME).is_file():
            return d
    return None


def load(root: Path) -> Config:
    path = root / CONFIG_NAME
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from e

    if "requirements" not in data:
        raise ConfigError(f"{path}: `requirements` (the folder holding the CSV files) is required")

    levels = []
    for raw in data.get("levels", []):
        if "kind" not in raw:
            raise ConfigError(f"{path}: every [[levels]] entry needs a kind")
        unknown = set(raw) - set(Level.__dataclass_fields__)
        if unknown:
            raise ConfigError(f"{path}: level {raw['kind']}: unknown key(s) {', '.join(sorted(unknown))}")
        levels.append(Level(**raw))
    if not levels:
        raise ConfigError(f"{path}: at least one [[levels]] entry is required")
    kinds = {lv.kind for lv in levels}
    for lv in levels:
        for k in lv.satisfies:
            if k not in kinds:
                raise ConfigError(f"{path}: level {lv.kind} satisfies unknown level {k}")

    verification = {}
    for code, (name, definition, automated) in DEFAULT_VERIFICATION.items():
        verification[code] = Verification(code, name, definition, automated)
    if "verification" in data:
        verification = {
            code: Verification(code, v.get("name", code), v.get("definition", ""),
                               bool(v.get("automated", False)))
            for code, v in data["verification"].items()
        }

    m = data.get("markers", {})
    unknown = set(m) - set(Markers.__dataclass_fields__)
    if unknown:
        raise ConfigError(f"{path}: [markers]: unknown key(s) {', '.join(sorted(unknown))}")
    markers = Markers(**m)

    e = data.get("editor", {})
    unknown = set(e) - set(Editor.__dataclass_fields__)
    if unknown:
        raise ConfigError(f"{path}: [editor]: unknown key(s) {', '.join(sorted(unknown))}")
    editor = Editor(**e)

    q = data.get("questions")
    return Config(
        root=root,
        requirements=root / data["requirements"],
        questions=root / q if q else None,
        levels=levels,
        verification=verification,
        markers=markers,
        editor=editor,
    )
