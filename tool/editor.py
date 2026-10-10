"""Opening a file at a line in the user's editor, as lazygit does."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from .config import Editor

#: Editor executable to (command template, runs in the terminal).
PRESETS = {
    "nvim": ("nvim +{line} {file}", True),
    "vim": ("vim +{line} {file}", True),
    "vi": ("vi +{line} {file}", True),
    "nano": ("nano +{line} {file}", True),
    "micro": ("micro {file}:{line}", True),
    "hx": ("hx {file}:{line}", True),
    "helix": ("helix {file}:{line}", True),
    "kak": ("kak +{line} {file}", True),
    "emacs": ("emacs -nw +{line} {file}", True),
    "code": ("code --goto {file}:{line}", False),
    "cursor": ("cursor --goto {file}:{line}", False),
    "codium": ("codium --goto {file}:{line}", False),
    "zed": ("zed {file}:{line}", False),
    "subl": ("subl {file}:{line}", False),
}


def resolve(editor: Editor) -> tuple[str, bool]:
    """The command template and whether it runs in the terminal."""
    template = editor.command.strip()
    if not template:
        env = (os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi").strip()
        exe = Path(shlex.split(env)[0]).name
        template, terminal = PRESETS.get(exe, (f"{env} {{file}}", True))
        if exe in PRESETS and env != exe:
            # Keep the user's own path or flags, with the preset's arguments.
            template = env + template[len(exe):]
    else:
        exe = Path(shlex.split(template)[0]).name
        terminal = PRESETS.get(exe, ("", True))[1]
    if editor.suspend is not None:
        terminal = editor.suspend
    return template, terminal


def command(editor: Editor, file: str, line: int) -> tuple[list[str], bool]:
    """argv opening `file` at `line`, and whether the terminal must be handed over."""
    template, terminal = resolve(editor)
    return [part.format(file=file, line=line) for part in shlex.split(template)], terminal
