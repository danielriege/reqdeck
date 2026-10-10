"""Themes for the TUI beyond Textual's own (dracula, nord, gruvbox, monokai,
tokyo-night, catppuccin, solarized, rose-pine, atom-one, flexoki …)."""

from textual.theme import Theme

THEMES = [
    Theme(name="github-dark", dark=True,
          background="#0d1117", surface="#161b22", panel="#21262d", foreground="#e6edf3",
          primary="#2f81f7", secondary="#a371f7", accent="#ffa657",
          success="#3fb950", warning="#d29922", error="#f85149"),
    Theme(name="github-light", dark=False,
          background="#ffffff", surface="#f6f8fa", panel="#eaeef2", foreground="#1f2328",
          primary="#0969da", secondary="#8250df", accent="#bc4c00",
          success="#1a7f37", warning="#9a6700", error="#cf222e"),
    Theme(name="xcode-light", dark=False,
          background="#ffffff", surface="#f5f5f7", panel="#e8e8ed", foreground="#1d1d1f",
          primary="#007aff", secondary="#9b44c8", accent="#c45500",
          success="#248a3d", warning="#b25000", error="#d70015"),
    Theme(name="xcode-dark", dark=True,
          background="#1f1f24", surface="#292a30", panel="#2f3037", foreground="#dfdfe0",
          primary="#0a84ff", secondary="#bf5af2", accent="#ff9f0a",
          success="#30d158", warning="#ffd60a", error="#ff453a"),
    Theme(name="vscode-dark", dark=True,
          background="#1e1e1e", surface="#252526", panel="#2d2d30", foreground="#d4d4d4",
          primary="#3794ff", secondary="#c586c0", accent="#ce9178",
          success="#89d185", warning="#cca700", error="#f14c4c"),
    Theme(name="vscode-light", dark=False,
          background="#ffffff", surface="#f3f3f3", panel="#e5e5e5", foreground="#1f1f1f",
          primary="#005fb8", secondary="#af00db", accent="#a31515",
          success="#388a34", warning="#bf8803", error="#e51400"),
    Theme(name="darcula", dark=True,
          background="#2b2b2b", surface="#313335", panel="#3c3f41", foreground="#a9b7c6",
          primary="#6897bb", secondary="#9876aa", accent="#cc7832",
          success="#6a8759", warning="#bbb529", error="#ff6b68"),
]

DEFAULT = "github-dark"
