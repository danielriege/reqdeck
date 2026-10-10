"""Themes: Textual's own, each given reqkit's full colour suite by a file in
this folder. See README.md for the roles."""

from __future__ import annotations

import dataclasses
import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from textual.theme import BUILTIN_THEMES, Theme

ROLES = ("foreground", "muted", "border", "border_active", "border_search", "selection",
         "title", "heading", "id", "link", "link_active", "code", "table_header",
         "statement_bar", "accepted", "proposed", "reopened", "security", "open",
         "answered", "keys")
HEX = re.compile(r"#[0-9a-fA-F]{6}")
DEFAULT = "dracula"


class ThemeError(Exception):
    pass


@dataclass
class Palette:
    name: str
    title: str
    extends: str
    colors: dict[str, str]

    def theme(self) -> Theme:
        """The Textual theme, with every role as a `$rk-<role>` CSS variable."""
        base = BUILTIN_THEMES[self.extends]
        variables = {**base.variables, **{f"rk-{k.replace('_', '-')}": v for k, v in self.colors.items()}}
        return dataclasses.replace(base, name=self.name, variables=variables)


def user_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "reqkit" / "themes"


def parse(path: Path) -> Palette:
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ThemeError(f"{path}: {e}") from e
    name = data.get("name", path.stem)
    extends = data.get("extends", name)
    if extends not in BUILTIN_THEMES:
        raise ThemeError(f"{path}: extends {extends!r}, which is not a Textual theme")
    colors = data.get("colors", {})
    missing = [r for r in ROLES if r not in colors]
    unknown = [r for r in colors if r not in ROLES]
    bad = [r for r, v in colors.items() if not HEX.fullmatch(str(v))]
    for what, items in (("missing", missing), ("unknown", unknown), ("not #rrggbb", bad)):
        if items:
            raise ThemeError(f"{path}: {what}: {', '.join(items)}")
    return Palette(name, data.get("title", name), extends, dict(colors))


def load_all() -> dict[str, Palette]:
    """Bundled themes, then the user's, which win on a name clash."""
    out: dict[str, Palette] = {}
    dirs = [Path(__file__).parent, user_dir()]
    for d in dirs:
        for path in sorted(d.glob("*.toml")) if d.is_dir() else []:
            p = parse(path)
            out[p.name] = p
    return out
